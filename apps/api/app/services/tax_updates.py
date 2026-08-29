"""Pesquisa tributária via Groq; resultados entram inativos para revisão humana."""
import json
import re
from datetime import date, datetime, timezone
from decimal import Decimal, InvalidOperation
from urllib.parse import urlparse

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.models import TaxRule
from app.services.audit import log

GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"

# Escopo fechado para reduzir tokens e impedir pesquisas tributárias genéricas.
# Alíquotas dependentes de regime/UF/município continuam como propostas, nunca
# como verdade universal ou aplicação automática.
TRANSPORT_TAX_TARGETS = {
    "ICMS": "transporte intermunicipal/interestadual, UF de início, CT-e, crédito, substituição e redespacho",
    "ISS": "transporte estritamente intramunicipal e serviços acessórios sujeitos ao município",
    "PIS": "PIS/Pasep sobre receita, regime cumulativo/não cumulativo e transição para CBS",
    "COFINS": "Cofins sobre receita, regime cumulativo/não cumulativo e transição para CBS",
    "IRPJ": "IRPJ de transportadora, lucro real/presumido e percentuais de presunção",
    "CSLL": "CSLL de transportadora, lucro real/presumido e percentuais de presunção",
    "CPP_INSS": "contribuição previdenciária patronal, folha e eventual CPRB aplicável ao setor",
    "IPVA": "IPVA da frota por UF, calendário, alíquota e benefícios para veículos de carga",
    "CBS": "CBS e cronograma da reforma tributária aplicável ao transporte",
    "IBS": "IBS e cronograma da reforma tributária aplicável ao transporte",
    "IS": "Imposto Seletivo somente quando houver impacto verificável em combustível ou frota",
    "SIMPLES_NACIONAL": "Anexos, faixas e transição CBS/IBS para transportadoras optantes",
}


def _json_payload(content: str) -> dict:
    match = re.search(r"\{.*\}", content, re.DOTALL)
    if not match:
        raise ValueError("A Groq não retornou JSON válido.")
    return json.loads(match.group(0))


def _official_source(value: str) -> bool:
    host = (urlparse(value).hostname or "").lower()
    return host == "gov.br" or host.endswith(".gov.br")


def research_tax_updates() -> list[dict]:
    if not settings.groq_api_key:
        raise RuntimeError("GROQ_API_KEY não configurada.")
    targets = "\n".join(f"- {code}: {scope}" for code, scope in TRANSPORT_TAX_TARGETS.items())
    prompt = f"""Hoje é {date.today().isoformat()}. Faça UMA pesquisa objetiva, somente em fontes oficiais
*.gov.br, e verifique alterações publicadas desde a última atualização ou vigentes nestes tributos de transportadoras:
{targets}
Não pesquise assuntos fora desta lista. Não invente alíquotas. Não trate regra estadual, municipal, benefício,
faixa ou regime tributário como universal; registre essas limitações na base legal. Retorne apenas regra com
alíquota e início de vigência expressamente confirmados pela fonte oficial. Não repita regra sem mudança.
Retorne SOMENTE JSON no formato {{"rules":[{{"name":"...","tax_code":"...","applies_to":"revenue|expense",
"rate_percent":0.0,"effective_from":"AAAA-MM-DD","effective_to":null,"legal_basis":"ato e contexto, incluindo
limitações de regime/UF/município","source_url":"https://...gov.br/..."}}]}}.
Se não houver dado verificável, retorne {{"rules":[]}}."""
    response = httpx.post(
        GROQ_URL,
        headers={"Authorization": f"Bearer {settings.groq_api_key}", "Content-Type": "application/json"},
        json={"model": settings.groq_model, "messages": [{"role": "user", "content": prompt}], "temperature": 0},
        timeout=120,
    )
    response.raise_for_status()
    content = response.json()["choices"][0]["message"]["content"]
    rows = _json_payload(content).get("rules", [])
    valid: list[dict] = []
    for item in rows:
        try:
            source = str(item["source_url"])
            applies = str(item["applies_to"])
            rate = Decimal(str(item["rate_percent"]))
            start = date.fromisoformat(str(item["effective_from"]))
            end = date.fromisoformat(str(item["effective_to"])) if item.get("effective_to") else None
            code = str(item["tax_code"]).upper()
            if (not _official_source(source) or code not in TRANSPORT_TAX_TARGETS
                    or applies not in {"revenue", "expense"} or rate < 0 or rate > 100 or (end and end < start)):
                continue
            valid.append({
                "name": str(item["name"])[:120], "tax_code": code,
                "applies_to": applies, "rate_percent": rate, "effective_from": start, "effective_to": end,
                "legal_basis": str(item.get("legal_basis") or "")[:2000], "source_url": source[:500],
            })
        except (KeyError, TypeError, ValueError, InvalidOperation):
            continue
    return valid


def stage_tax_updates(db: Session, tenant_id: int | None, actor_id: int | None = None,
                      candidates: list[dict] | None = None) -> dict:
    candidates = research_tax_updates() if candidates is None else candidates
    created = 0
    for item in candidates:
        duplicate = db.scalar(select(TaxRule.id).where(
            TaxRule.tenant_id == tenant_id, TaxRule.tax_code == item["tax_code"],
            TaxRule.applies_to == item["applies_to"], TaxRule.effective_from == item["effective_from"],
            TaxRule.rate_percent == item["rate_percent"],
        ))
        if duplicate:
            continue
        row = TaxRule(tenant_id=tenant_id, **item, debit_account_code="6.1.01",
                      credit_account_code="2.2.01", active=False)
        db.add(row); db.flush(); created += 1
        log(db, user_id=actor_id, action="research", entity="tax_rule", entity_id=row.id,
            detail=f"Proposta Groq; {row.tax_code}; {row.rate_percent}%; fonte={row.source_url}")
    db.commit()
    return {"status": "success", "researched_at": datetime.now(timezone.utc).isoformat(),
            "candidates": len(candidates), "created": created, "model": settings.groq_model}
