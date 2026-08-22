# Regras de extração do manifesto (Salvesen → JM Rotas)

Estas regras valem tanto para o extrator por **regras** quanto para o **prompt da IA**.

## 0. Filtro de páginas (OBRIGATÓRIO)
- Considerar **apenas** as páginas cujo cabeçalho contém a palavra **`MANIFIESTO`**.
- Toda página sem `MANIFIESTO` (capas, normas, anexos, etc.) é **descartada**.
- Se um PDF tem várias páginas MANIFIESTO com o **mesmo Código UT**, junte as paradas de todas numa só rota.
- Páginas MANIFIESTO com **Código UT diferente** = rotas diferentes (gere um manifesto/rota por código).

## 1. Cabeçalho → ROTA
| Campo | Origem no documento | Observação |
|---|---|---|
| `codigo_ut` | "Código UT" | **É o código da rota.** Só dígitos (6–9). |
| `data_carga` | "Fecha y Hora de Carga" | normalizar p/ `YYYY-MM-DD` (ex.: "11 jun. 2026" → 2026-06-11). |
| `hora_carga` | "Fecha y Hora de Carga" | `HH:MM` (ex.: "5:00" → 05:00). |
| `origem` | "Origen" | nome (ex.: SALVESEN LOGISTICA PORTUGAL). |
| `origem_morada` | "Dirección" | morada + código postal. |
| `transportadora` | "Transportista" | remover o prefixo "PTGxxx - ". |
| `matricula` | "Matrícula" | ex.: 24-XC-34. |
| `natureza` | "Naturaleza de la Mercancía" | ex.: PRODUTO A TEMPERATURA CONTROLADA. |

## 2. Tabela → PARADAS (uma por DESTINO)
Colunas: `ORIGEN | DESTINO | F.ENTR | HORA | TEMP.°C | PESO | PALÉS | PEDIDO`.

**Cada parada ocupa 2 linhas no papel** e deve ser **agrupada** numa só:
1. **Linha principal:** ORIGEM (Salvesen…) + DESTINO (cliente) + morada + código postal/cidade. Coluna PEDIDO mostra "N Pedidos".
2. **Linha de detalhe (logo abaixo):** começa com o **fornecedor** (ex.: `Alpro Portugal (311)`, `Danone Portugal (011)`, `Lactacores (405)`) e repete o nome do cliente; a coluna **PEDIDO traz os números reais** (ex.: `5023052772 / 415197196`).

→ Regra de agrupamento: a linha que começa com um **fornecedor entre parênteses com código** `(\d{3})` é a **continuação** da parada imediatamente acima (mesmo cliente). Use-a só para preencher `fornecedor` e `pedido`.

### Mapeamento por coluna
| Coluna | Campo | Normalização |
|---|---|---|
| ORIGEN | `origem` | texto |
| DESTINO (1ª linha) | `nome` | cliente |
| DESTINO (linhas seguintes) | `morada`, `codigo_postal`, `cidade` | código postal `\d{4}-\d{3}`; cidade = localidade após o CP |
| F.ENTR | `data_limite` | `DD/MM/AAAA` → `YYYY-MM-DD` |
| HORA | `hora_limite` | `HH:MM` (00:00 é válido) |
| TEMP.°C | `temperatura` | `Amb.`/`Ambiente` → "Ambiente"; número → "4" |
| PESO | `peso_kg` | `2.314,22 Kg` → `2314.22` (ponto=milhar, vírgula=decimal) |
| PALÉS | `pales` | `2,85 Pal` → `2.85` |
| PEDIDO (linha detalhe) | `pedido` | junte múltiplos por ` / `; aceita `REF-F ...` |
| fornecedor (linha detalhe) | `fornecedor` | ex.: `Alpro Portugal (311)` |

## 3. Normalização numérica (PT/ES)
- Milhar = `.` e decimal = `,`. Sempre: remova `.`, troque `,` por `.`, `float()`.
- Remova sufixos: `Kg`, `Pal`, `Pedidos`, `€`.

## 4. Confiança e revisão
- `destino.confianca` ≈ confiança média do OCR daquela parada.
- `necessita_revisao = true` se `confianca_ocr < OCR_MIN_CONFIDENCE` **ou** se faltar `nome`, `data_limite`, `peso_kg` ou `pedido` em alguma parada.
- **A IA nunca cria a rota direto:** gera a pré-rota; um operador confere (tela lado-a-lado) e só então `generate-route`.

## 5. Casos especiais observados
- Prefixos numéricos no cliente (`2. FRUSTOCK...`) fazem parte do nome — manter.
- `LIDL E CIA LOURES` e `LIDL LOURES` são destinos distintos — não unificar.
- Pedido pode ser alfanumérico (`415147499REP08051548`, `REF-F.659719REP06091111`).
- Cidade nem sempre tem código postal (ex.: "1000 Lisboa") — preencher só o que houver.
