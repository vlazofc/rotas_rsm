# Proposta comercial, precificação e contrato SaaS — Rotas Brasil RSM

**Versão:** 1.0
**Data-base da pesquisa:** 29 de agosto de 2026
**Status:** minuta comercial e jurídica para preenchimento e revisão profissional antes da assinatura

> Este documento não substitui revisão por advogado e contador, especialmente quanto a enquadramento tributário, limitação de responsabilidade, foro, propriedade intelectual preexistente e tratamento de dados pessoais.

---

# PARTE I — ANÁLISE DO PRODUTO E PRECIFICAÇÃO

## 1. Resumo executivo

O Rotas Brasil RSM não deve ser precificado como um rastreador isolado nem como um cadastro simples de frota. O produto reúne, em uma única plataforma web multiempresa:

- operação de rotas e entregas de ponta a ponta;
- torre de controle, status, eventos, tempos de doca e ocorrências;
- check-in, entrega, insucesso, devolução e comprovantes;
- gestão de motoristas, veículos, proprietários e documentos;
- manutenção preventiva/corretiva, pneus, inspeções e ordens de serviço;
- estoque, peças, compras e aprovações;
- despesas, receitas, contas a pagar/receber, DRE, balancete e razão;
- extratos, ajustes e aceite/contestação por motorista;
- workflows, perfis, permissões, notificações e auditoria;
- dashboards, relatórios, exportações e memória de cálculo;
- rastreamento consentido e localização de prestadores próximos;
- agente executivo de IA limitado aos dados autorizados da empresa;
- personalização de marca, múltiplas empresas/filiais e idiomas;
- infraestrutura Docker, PostgreSQL/PostGIS, Redis, armazenamento S3 compatível, proxy e controles de segurança.

O posicionamento recomendado é **SaaS B2B vertical de gestão logística integrada**, com implantação assistida e suporte continuado.

## 2. Inventário funcional considerado no preço

### 2.1 Operação logística

- criação manual e importação de rotas por planilha;
- sequenciamento e otimização de paradas;
- chegada ao CD, entrada em doca, início/fim de carregamento, liberação e saída;
- check-in por parada, entrega, falha, devolução e retorno ao armazém;
- anexação de comprovantes e registro auditável de eventos;
- controle de quilometragem, pedágios, peso, paletes e tempos operacionais;
- reabertura e correção administrativa com controle de permissão;
- mapa, acompanhamento de posições e indicadores de desempenho.

### 2.2 Frota e manutenção

- veículos, proprietários, tipos, motoristas, documentos e vencimentos;
- solicitações e aprovação de alterações cadastrais;
- checklist configurável de veículos;
- pneus, movimentações, profundidade de sulco e inspeções;
- planos de manutenção, ordens de serviço, orçamento e aprovação;
- fornecedores e prestadores de serviço por proximidade;
- peças, estoque mínimo e movimentações.

### 2.3 Financeiro, compras e contabilidade gerencial

- despesas, receitas, categorias e aprovação financeira;
- contas a pagar e receber, baixa, cancelamento e anexos;
- compras com revisão, aprovação, aquisição e recebimento;
- dashboard financeiro, DRE e extrato;
- plano de contas, regras tributárias, balancete e razão;
- memória de cálculo e exportação XLSX;
- lançamentos, ajustes, extratos e aceite/contestação de motoristas.

### 2.4 Governança e gestão

- multiempresa e filial;
- usuários, papéis, permissões e perfis customizáveis;
- trilha de auditoria;
- notificações persistentes e alertas operacionais;
- branding e configuração por cliente;
- dashboards, relatórios operacionais e financeiros;
- agente executivo com IA e histórico de conversas;
- API autenticada e arquitetura preparada para integrações.

### 2.5 Segurança e operação técnica

- autenticação com access/refresh token e revogação de sessões;
- segregação por empresa, filial, papel e permissão;
- rate limit, CORS restritivo e validação de segredos em produção;
- serviços internos sem exposição pública direta;
- Cloudflare Tunnel, Caddy, Nginx e cabeçalhos de segurança;
- health/readiness checks, worker, scheduler, cache e filas;
- backup/restore e armazenamento segregado de anexos;
- frontend com carregamento sob demanda e preparação para aproximadamente 500 acessos concorrentes, sujeito ao dimensionamento da infraestrutura e teste de carga do ambiente contratado.

## 3. Pesquisa comparativa de mercado

Preços públicos consultados na data-base; impostos, câmbio, hardware, implantação e módulos adicionais podem alterar a comparação.

| Solução | Escopo comparável | Preço público observado | Leitura para a proposta |
|---|---|---:|---|
| Bsoft TMS | TMS brasileiro, documentos, frota e operação | R$ 289 a R$ 1.749/mês conforme plano/volume | Boa referência nacional, mas os planos públicos limitam veículos, usuários ou emissões. |
| FrotaGS | Frota, manutenção, relatórios e API em plano superior | R$ 49,90 a R$ 546,90/mês | Produto de prateleira com escopo e limites menores. |
| BusFrota | Frota, documentos, checklist, manutenção e IA | R$ 299 a R$ 999/mês | Referência de gestão de frota sem o conjunto completo de TMS + financeiro + workflows. |
| Vivo Frota Inteligente | Rastreamento e telemetria | R$ 59,99 a R$ 99,99 por veículo/mês | Normalmente envolve serviço/hardware de rastreamento; não substitui ERP/TMS integrado. |
| Fleetio | Gestão internacional de frota, manutenção, pneus, estoque e API | US$ 4, US$ 7 ou US$ 10 por veículo/mês, com condições e faixas | Demonstra precificação por ativo; módulos operacionais/financeiros de entrega continuam separados. |
| Onfleet | Última milha, otimização, POD, API, tracking e torre | US$ 619/mês (2.500 tarefas), US$ 1.349/mês (5.000) e US$ 3.099/mês (enterprise) | Comparável à camada operacional de entregas, sem representar sozinho todo o ERP/frota do Rotas. |
| TOTVS TMS | TMS enterprise, plano de distribuição, financeiro logístico, ocorrências e integrações | preço sob consulta | Confirma o posicionamento enterprise e modular do escopo integrado. |

### Fontes da pesquisa

- Bsoft TMS: https://bsoft.com.br/lp/bsoft-tms
- Bsoft Frota: https://lp.bsoft.com.br/frota
- FrotaGS: https://www.frotags.com/
- BusFrota: https://busfrota.com.br/
- Vivo Frota Inteligente: https://vivo.com.br/para-empresas/produtos-e-servicos/digitais/iot/frota-inteligente
- Fleetio: https://www.fleetio.com/pricing
- Onfleet: https://onfleet.com/pricing
- TOTVS TMS SaaS: https://produtos.totvs.com/ficha-tecnica/tudo-sobre-o-totvs-tms-saas/

## 4. Conclusão de valor

Somar soluções separadas de TMS/última milha, gestão de frota, manutenção, workflow, financeiro, armazenamento e BI tende a custar mais e aumenta integração, retrabalho e risco operacional. Ao mesmo tempo, o Rotas Brasil RSM ainda não deve cobrar o mesmo preço de uma suíte enterprise global madura com suporte 24x7, certificações independentes e alta disponibilidade multirregional.

Por isso, a faixa justa atual é:

- **licença e serviço gerenciado:** R$ 7.900 a R$ 9.900 por mês;
- **implantação:** de R$ 0 a R$ 18.000, conforme prazo contratado;
- **desenvolvimento fora do escopo:** R$ 190 por hora, mediante orçamento e aprovação;
- **consumo extraordinário de IA, mapas, mensagens ou terceiros:** repasse pelo custo, sem margem, ou pacote previamente aprovado.

Essa faixa pressupõe atendimento B2B assistido, evolução corretiva, infraestrutura, backup, segurança e suporte — não cessão do código-fonte.

## 5. Proposta comercial recomendada

### 5.1 Franquia incluída

- 1 grupo econômico/tenant;
- até 5 filiais;
- até 500 usuários nomeados e 500 sessões concorrentes, desde que a infraestrutura dimensionada em homologação confirme a carga;
- até 150 veículos ativos;
- até 10.000 entregas/paradas concluídas por mês;
- até 150 GB de anexos;
- ambientes de produção e homologação;
- infraestrutura em nuvem/VPS, monitoramento, backup e atualizações;
- suporte em horário comercial e SLA descrito no contrato;
- todos os módulos existentes descritos no Anexo I;
- até 8 horas mensais não cumulativas para apoio funcional, parametrização e treinamento remoto;
- franquia mensal de R$ 500 para o provedor de IA do Agente Executivo.

### 5.2 Opções de prazo

| Opção | Vigência mínima | Implantação | Mensalidade | Valor nominal do prazo | Economia nominal contra 12 meses renovados |
|---|---:|---:|---:|---:|---:|
| Flex | 12 meses | R$ 18.000 | R$ 9.900 | R$ 136.800 | referência |
| Crescimento | 24 meses | R$ 9.000 | R$ 8.900 | R$ 222.600 | R$ 33.600 |
| Parceria | 36 meses | isenta | R$ 7.900 | R$ 284.400 | R$ 72.000 |

Valores em reais, sem retenções eventualmente aplicáveis, com tributos próprios da CONTRATADA já considerados. O desconto de prazo é condicionado ao cumprimento da permanência mínima.

### 5.3 Excedentes sugeridos

| Métrica | Valor adicional |
|---|---:|
| Filial acima da franquia | R$ 350/mês por filial |
| Veículo ativo acima de 150 | R$ 18/mês por veículo |
| Bloco adicional de 5.000 entregas/mês | R$ 750/mês |
| Armazenamento acima de 150 GB | R$ 2,50/GB/mês |
| Hora de consultoria/desenvolvimento aprovada | R$ 190/hora |
| Suporte 24x7 ou SLA 99,9% | orçamento específico |
| Integração, hardware, telefonia, WhatsApp/SMS, pedágio/mapa ou IA excedente | custo de terceiro aprovado + eventual implantação orçada |

### 5.4 Premissas que exigem confirmação antes da assinatura

1. número real de filiais, veículos, usuários e entregas mensais;
2. ambiente em nuvem escolhido e exigência de residência de dados;
3. necessidade de suporte fora do horário comercial;
4. integrações obrigatórias com ERP, rastreador, SharePoint, bancos, WhatsApp ou sistemas fiscais;
5. política de retenção de comprovantes e anexos;
6. necessidade de CT-e, MDF-e, NF-e, CIOT, vale-pedágio ou averbação — **não incluídos no escopo atual**;
7. nível de disponibilidade e continuidade exigido pelo negócio;
8. titularidade do código preexistente e identificação formal das partes.

---

# PARTE II — MINUTA DE CONTRATO DE LICENÇA SaaS E PRESTAÇÃO DE SERVIÇOS

## QUADRO-RESUMO

**CONTRATADA:** [RAZÃO SOCIAL], CNPJ nº [●], com sede em [●], neste ato representada por [●], e-mail contratual [●].
**CONTRATANTE:** [RAZÃO SOCIAL], CNPJ nº [●], com sede em [●], neste ato representada por [●], e-mail contratual [●].

**Plataforma:** Rotas Brasil RSM.
**Data de início:** [●].
**Prazo selecionado:** [ ] 12 meses — [ ] 24 meses — [ ] 36 meses.
**Implantação:** R$ [●].
**Mensalidade:** R$ [●].
**Vencimento:** dia [●] de cada mês.
**Franquia contratada:** [confirmar ou substituir item 5.1 da proposta].
**Responsáveis operacionais:** CONTRATADA [●]; CONTRATANTE [●].
**Canal de suporte:** [e-mail/portal/telefone].
**Foro:** comarca de [●], Estado de [●].

As Partes celebram o presente Contrato de Licença de Uso de Software como Serviço e Prestação de Serviços (“Contrato”), regido pelo quadro-resumo, pelas cláusulas seguintes e pelos anexos.

## CLÁUSULA 1 — OBJETO

1.1. A CONTRATADA concede à CONTRATANTE licença temporária, onerosa, limitada, não exclusiva, intransferível e revogável de acesso à Plataforma durante a vigência, e prestará os serviços de implantação, hospedagem, manutenção, backup e suporte definidos neste Contrato.

1.2. A licença constitui direito de uso remoto do serviço SaaS e não implica venda, cessão, transferência ou entrega do código-fonte, banco estrutural, ferramentas internas, bibliotecas, métodos, know-how ou infraestrutura da CONTRATADA.

1.3. O escopo funcional contratado consta do Anexo I. Qualquer funcionalidade, integração, relatório, migração ou customização não descrita será tratada como serviço adicional mediante especificação, prazo e preço aprovados por escrito.

1.4. O sistema apoia decisões operacionais e gerenciais, mas não substitui controles legais, fiscais, contábeis, trabalhistas, de segurança viária ou decisões profissionais obrigatórias da CONTRATANTE.

## CLÁUSULA 2 — IMPLANTAÇÃO E ACEITE

2.1. A implantação compreende reunião inicial, configuração básica, criação do tenant e filiais, identidade visual, parametrização inicial, importação dos modelos de dados expressamente previstos e treinamento remoto de usuários-chave.

2.2. A CONTRATANTE fornecerá dados consistentes, acessos, responsáveis e validações nos prazos acordados. Atrasos atribuíveis à CONTRATANTE prorrogam o cronograma sem caracterizar inadimplemento da CONTRATADA.

2.3. A entrega será submetida a até 10 dias úteis de validação. A CONTRATANTE indicará defeitos objetivos e reproduzíveis relacionados ao escopo. Ausência de manifestação, uso produtivo ou aprovação escrita caracterizará aceite.

2.4. Defeito é divergência reproduzível do comportamento documentado. Preferência estética, nova regra de negócio, mudança legal, integração nova ou ampliação de escopo não constitui defeito.

## CLÁUSULA 3 — ACESSO E USO ACEITÁVEL

3.1. A CONTRATANTE administrará seus usuários, papéis e permissões e responderá pela legitimidade dos acessos concedidos e pelas operações realizadas com suas credenciais.

3.2. É vedado: compartilhar credenciais; tentar contornar limites ou segurança; realizar engenharia reversa fora das hipóteses legais; introduzir código malicioso; usar a Plataforma para finalidade ilícita; testar vulnerabilidades sem autorização; ou disponibilizar o serviço a terceiros não autorizados.

3.3. A CONTRATANTE comunicará imediatamente suspeita de comprometimento de conta e manterá dados de contato atualizados.

3.4. A CONTRATADA poderá bloquear preventivamente acesso que gere risco concreto à segurança, integridade, terceiros ou continuidade do serviço, devendo comunicar a medida e restabelecer o acesso assim que sanado o risco.

## CLÁUSULA 4 — PREÇO, FATURAMENTO E REAJUSTE

4.1. A CONTRATANTE pagará os valores do quadro-resumo e os excedentes efetivamente utilizados conforme Anexo II.

4.2. A implantação será faturada [na assinatura / 50% na assinatura e 50% no aceite]. A mensalidade será faturada antecipadamente, com vencimento no dia definido no quadro-resumo.

4.3. O atraso sujeita a CONTRATANTE a multa de 2%, juros de 1% ao mês pro rata die e correção monetária, sem prejuízo de cobrança comprovada.

4.4. Após 15 dias corridos de atraso e notificação, a CONTRATADA poderá suspender novos acessos, preservando os dados. Após 45 dias, poderá rescindir o Contrato, observada a disponibilização dos dados condicionada ao pagamento dos valores vencidos, ressalvados direitos legalmente indisponíveis.

4.5. Os valores serão reajustados a cada 12 meses pela variação acumulada positiva do IPCA/IBGE. Se o índice for extinto ou juridicamente inaplicável, será usado o índice oficial que melhor reflita a inflação do período. Variação negativa não reduzirá o valor nominal, salvo negociação expressa.

4.6. Mudanças tributárias, regulatórias ou de fornecedores essenciais que elevem comprovadamente o custo em mais de 10% poderão motivar revisão extraordinária negociada. Sem acordo em 30 dias, qualquer Parte poderá resilir sem multa, mantendo pagamentos vencidos e aviso prévio de 60 dias.

## CLÁUSULA 5 — PRAZO, RENOVAÇÃO E RESCISÃO

5.1. O Contrato vigorará pelo prazo selecionado no quadro-resumo, contado da data de início.

5.2. Ao término, será renovado por períodos de 12 meses, pela mensalidade vigente da opção Flex, reajustada, salvo manifestação contrária com antecedência mínima de 60 dias.

5.3. A rescisão imotivada antecipada pela CONTRATANTE exige aviso prévio de 30 dias e pagamento compensatório equivalente ao menor valor entre: (a) 30% das mensalidades vincendas do prazo mínimo; ou (b) 3 mensalidades vigentes. Valores de implantação concedidos como desconto serão recompostos proporcionalmente ao período não cumprido.

5.4. Não haverá multa quando a rescisão decorrer de descumprimento material não sanado pela outra Parte em até 15 dias úteis após notificação detalhada; para falha crítica de segurança ou violação dolosa de confidencialidade, a rescisão poderá ser imediata.

5.5. A CONTRATADA poderá descontinuar o produto mediante aviso de 180 dias, devolvendo proporcionalmente valores pagos antecipadamente relativos ao período não prestado e auxiliando a exportação prevista neste Contrato.

5.6. A rescisão não prejudica obrigações vencidas, confidencialidade, propriedade intelectual, proteção de dados, responsabilidade e solução de controvérsias.

## CLÁUSULA 6 — NÍVEIS DE SERVIÇO E SUPORTE

6.1. A meta de disponibilidade mensal é 99,5%, medida no ponto de entrada da Plataforma sob controle da CONTRATADA.

6.2. Não entram no cálculo: manutenção programada comunicada com 48 horas de antecedência, limitada a 4 horas/mês e preferencialmente fora do horário comercial; caso fortuito/força maior; internet ou equipamento da CONTRATANTE; indisponibilidade de terceiros fora do controle razoável; ataque externo inevitável apesar das medidas adequadas; uso indevido; ou suspensão contratual.

6.3. Suporte padrão: dias úteis, das 8h às 18h, horário de Brasília, pelos canais do quadro-resumo.

| Prioridade | Definição | Primeira resposta | Atualização/objetivo |
|---|---|---:|---|
| P1 Crítica | serviço indisponível para todos ou perda ativa de dados | 1 hora útil | atualizações a cada 2 horas úteis; contorno em até 8 horas úteis |
| P2 Alta | função essencial indisponível sem alternativa razoável | 4 horas úteis | contorno em até 2 dias úteis |
| P3 Média | falha parcial com alternativa disponível | 1 dia útil | correção planejada em até 10 dias úteis ou próximo ciclo |
| P4 Baixa | dúvida, melhoria ou ajuste não bloqueante | 2 dias úteis | avaliação e priorização de produto |

6.4. Os prazos são objetivos de atendimento e dependem de reprodução, informações e acesso fornecidos pela CONTRATANTE. Nova funcionalidade não se submete a prazo de incidente.

6.5. Se a disponibilidade mensal, por responsabilidade exclusiva da CONTRATADA, ficar: (a) abaixo de 99,5% e igual/acima de 99,0%, crédito de 5%; (b) abaixo de 99,0% e igual/acima de 98,0%, 10%; (c) abaixo de 98,0%, 20% da mensalidade. O crédito é solicitado em 15 dias, aplicado na fatura seguinte e constitui compensação de SLA, sem afastar direitos em caso de dolo ou culpa grave.

## CLÁUSULA 7 — MANUTENÇÃO, EVOLUÇÃO E MUDANÇAS

7.1. Estão incluídas correções, atualizações de segurança, compatibilidade razoável com navegadores suportados e melhorias gerais incorporadas ao produto padrão.

7.2. A CONTRATADA poderá alterar interface e tecnologia desde que preserve substancialmente as funções contratadas. Remoção material de função exige aviso e alternativa razoável.

7.3. Desenvolvimento exclusivo seguirá ordem de serviço com escopo, aceite, horas, preço, prazo e titularidade. Sem disposição diferente, componentes genéricos e reutilizáveis permanecem da CONTRATADA; dados e materiais específicos da CONTRATANTE permanecem da CONTRATANTE.

7.4. Mudanças legais e fiscais não previstas serão avaliadas e poderão exigir orçamento. A Plataforma não inclui emissão fiscal eletrônica salvo aditivo expresso.

## CLÁUSULA 8 — DADOS, BACKUP E PORTABILIDADE

8.1. Os dados inseridos pela CONTRATANTE ou gerados diretamente por sua operação são de sua titularidade. A CONTRATADA poderá tratá-los apenas para executar o Contrato, proteger o serviço, cumprir lei e gerar estatísticas efetivamente anonimizadas.

8.2. A rotina padrão compreende backup diário, retenção de 30 dias, objetivo de ponto de recuperação (RPO) de até 24 horas e objetivo de recuperação (RTO) de até 8 horas úteis para falha coberta, salvo plano superior.

8.3. Backup não substitui obrigação da CONTRATANTE de validar operações críticas, manter documentos cuja guarda legal lhe incumba e exportar informações essenciais conforme sua política interna.

8.4. Durante a vigência, a CONTRATANTE poderá usar exportações disponíveis. Após término regular, a CONTRATADA disponibilizará, mediante solicitação em até 30 dias, uma exportação padrão em CSV/XLSX/JSON e arquivos originais, quando tecnicamente aplicável.

8.5. Passados 60 dias do término, os dados poderão ser eliminados de produção e backups conforme ciclo técnico, salvo obrigação legal, ordem de autoridade ou contratação de retenção adicional.

## CLÁUSULA 9 — PROTEÇÃO DE DADOS PESSOAIS

9.1. Para dados pessoais tratados por conta da operação da CONTRATANTE, esta será a **Controladora** e a CONTRATADA será a **Operadora**, nos termos da Lei nº 13.709/2018 (LGPD), sem prejuízo de tratamentos em que cada Parte seja controladora independente, como faturamento, contatos contratuais e cumprimento de obrigação legal.

9.2. A CONTRATADA tratará dados conforme instruções documentadas e lícitas, finalidade contratual, necessidade e Anexo III; manterá registro apropriado, confidencialidade e medidas técnicas e administrativas adequadas.

9.3. A CONTRATANTE garante base legal, transparência, qualidade e legitimidade da coleta, inclusive para geolocalização de trabalhadores, e atenderá solicitações de titulares. A CONTRATADA prestará assistência tecnicamente razoável.

9.4. Suboperadores de nuvem, e-mail, armazenamento, mapas, IA e monitoramento poderão ser utilizados, sob obrigações compatíveis. A lista será fornecida mediante solicitação e mudanças materiais serão comunicadas.

9.5. A CONTRATADA notificará a CONTRATANTE sem demora injustificada e, sempre que possível, em até 24 horas da confirmação de incidente com dados sob sua operação, fornecendo informações disponíveis para avaliação e comunicação. A decisão e comunicação à ANPD/titulares cabem à Controladora, observada a regulamentação vigente.

9.6. Transferência internacional, se existente, observará mecanismo legal aplicável. Credenciais e segredos não serão usados para treinamento público de modelos de IA.

9.7. Encerrado o tratamento, os dados serão devolvidos ou eliminados segundo a Cláusula 8, ressalvadas retenções legais e backups em ciclo protegido.

## CLÁUSULA 10 — SEGURANÇA DA INFORMAÇÃO

10.1. A CONTRATADA manterá controles compatíveis com risco e porte: segregação lógica, autenticação, autorização por perfil, registros de auditoria, atualização de componentes, proteção de segredos, backup, monitoramento de disponibilidade e comunicação segura.

10.2. A CONTRATANTE é responsável por endpoints, rede, navegador, usuários, configuração de perfis, revogação tempestiva de acessos e proibição de compartilhamento de senha.

10.3. Nenhuma Parte garante segurança absoluta. Cada Parte cooperará na contenção, investigação, preservação de evidências e mitigação de incidente.

10.4. Teste de invasão, auditoria intrusiva ou varredura dependerá de autorização prévia, escopo, janela e regras que evitem impacto em outros clientes.

## CLÁUSULA 11 — INTELIGÊNCIA ARTIFICIAL E SERVIÇOS DE TERCEIROS

11.1. O Agente Executivo usa modelo de terceiro e dados agregados/autorizados para auxiliar análises. Respostas podem conter imprecisões e devem ser verificadas antes de decisão financeira, fiscal, trabalhista, logística ou jurídica.

11.2. A CONTRATANTE não inserirá no prompt dados sensíveis ou segredos desnecessários. A CONTRATADA aplicará minimização e restrição de contexto tecnicamente disponíveis.

11.3. Custos acima da franquia e mudanças de preço, disponibilidade ou política do provedor poderão levar à limitação temporária, troca de modelo ou repasse previamente comunicado.

11.4. Mapas, nuvem, armazenamento, mensageria, rastreadores e integrações externas estão sujeitos às condições e disponibilidade dos respectivos fornecedores.

## CLÁUSULA 12 — PROPRIEDADE INTELECTUAL

12.1. Pertencem à CONTRATADA ou licenciantes: Plataforma, código, arquitetura, interface genérica, documentação técnica, modelos, marcas, melhorias, correções e componentes preexistentes.

12.2. Pertencem à CONTRATANTE: seus dados, documentos, marcas e materiais fornecidos, cuja licença limitada é concedida à CONTRATADA apenas para executar o Contrato.

12.3. Sugestões poderão ser incorporadas ao produto sem remuneração, desde que não revelem informação confidencial nem reproduzam material exclusivo da CONTRATANTE.

12.4. É vedado usar marca da outra Parte em publicidade sem consentimento escrito, exceto identificação operacional estritamente necessária.

## CLÁUSULA 13 — CONFIDENCIALIDADE

13.1. Informação confidencial inclui dados técnicos, comerciais, financeiros, pessoais, credenciais, código, arquitetura, preços negociados e estratégias reveladas em razão do Contrato.

13.2. A Parte receptora limitará acesso a quem necessite conhecê-la, aplicará proteção não inferior à usada em suas próprias informações relevantes e não a divulgará sem autorização.

13.3. Não são confidenciais informações comprovadamente públicas sem violação, já conhecidas legitimamente, recebidas de terceiro autorizado ou desenvolvidas de forma independente.

13.4. Divulgação exigida por lei será limitada ao necessário e, quando permitido, previamente comunicada.

13.5. A obrigação vigorará durante o Contrato e por 5 anos após seu término; para segredo industrial, credenciais e dados pessoais, enquanto mantiverem essa natureza.

## CLÁUSULA 14 — GARANTIAS E RESPONSABILIDADES

14.1. Cada Parte declara ter poderes para contratar e cumprir a legislação aplicável às suas atividades.

14.2. A CONTRATADA garante prestação diligente e correção, sem custo, de defeitos reproduzíveis do escopo. Não garante operação ininterrupta, resultado econômico específico nem adequação a finalidade não informada.

14.3. Cada Parte responde por danos diretos comprovados causados por seu descumprimento. Salvo dolo, fraude, culpa grave, violação de propriedade intelectual, confidencialidade, obrigações de pagamento ou hipóteses legalmente não limitáveis, a responsabilidade agregada de cada Parte fica limitada ao total pago ou devido nos 12 meses anteriores ao evento.

14.4. Na máxima extensão legal, nenhuma Parte responderá por lucro cessante, perda de chance, dano indireto, punitivo ou consequencial, salvo quando decorrer de dolo, culpa grave ou quando a lei impedir a exclusão.

14.5. A limitação não afasta dever de mitigar danos nem responsabilidade atribuída pela LGPD na medida da participação e das obrigações de cada agente.

## CLÁUSULA 15 — INDENIZAÇÃO DE TERCEIROS

15.1. A CONTRATADA defenderá a CONTRATANTE contra alegação de que a Plataforma, usada conforme o Contrato, viola propriedade intelectual de terceiro, podendo obter licença, substituir/modificar o componente ou encerrar a função afetada com restituição proporcional.

15.2. A CONTRATANTE defenderá a CONTRATADA contra alegações decorrentes de dados, materiais, instruções ilícitas, ausência de base legal, uso indevido ou violação das obrigações de seus usuários.

15.3. A Parte indenizada notificará prontamente, permitirá controle razoável da defesa e cooperará. Acordo que imponha admissão ou obrigação não monetária dependerá de consentimento.

## CLÁUSULA 16 — COMPLIANCE

16.1. As Partes observarão legislação anticorrupção, concorrencial, trabalhista, tributária e de proteção de dados aplicável e não oferecerão vantagem indevida relacionada ao Contrato.

16.2. Não há vínculo trabalhista, sociedade, representação, exclusividade ou solidariedade entre as Partes ou seus profissionais.

## CLÁUSULA 17 — COMUNICAÇÕES

17.1. Notificações contratuais serão válidas nos e-mails do quadro-resumo, com confirmação eletrônica de envio, sem prejuízo de plataforma de assinatura ou correspondência.

17.2. Mudança de contato deverá ser informada; enquanto isso, comunicações ao endereço anterior serão consideradas válidas.

## CLÁUSULA 18 — DISPOSIÇÕES GERAIS

18.1. O Contrato e anexos constituem o acordo integral. Em conflito, prevalecem: quadro-resumo, aditivos, Contrato, Anexo de Tratamento de Dados, SLA e proposta.

18.2. Alterações exigem documento escrito ou assinatura eletrônica aceita pelas Partes. Tolerância não implica renúncia ou novação.

18.3. Nenhuma Parte cederá o Contrato sem consentimento, exceto para empresa do mesmo grupo ou sucessora em reorganização/aquisição que assuma as obrigações e não seja concorrente direto da outra Parte.

18.4. Invalidade de uma disposição não afeta as demais; as Partes a substituirão por disposição válida de efeito econômico semelhante.

18.5. Caso fortuito ou força maior suspende obrigações afetadas enquanto durar, com dever de comunicação e mitigação. Se durar mais de 60 dias, qualquer Parte poderá encerrar sem multa quanto ao período futuro.

18.6. O Contrato poderá ser assinado eletronicamente em vias digitais, reconhecendo as Partes sua autoria, integridade e validade, inclusive por plataforma aceita por ambas.

## CLÁUSULA 19 — LEI E FORO

19.1. Aplica-se a legislação brasileira.

19.2. Antes de ação judicial, representantes executivos tentarão solução de boa-fé por 15 dias úteis, sem impedir medida urgente.

19.3. Fica eleito o foro indicado no quadro-resumo, com renúncia a outro, salvo competência legal inderrogável.

E, por estarem de acordo, as Partes assinam eletronicamente este instrumento com duas testemunhas.

**[Cidade], [data].**

| CONTRATADA | CONTRATANTE |
|---|---|
| Nome: [●] | Nome: [●] |
| Cargo: [●] | Cargo: [●] |
| CPF: [●] | CPF: [●] |
| Assinatura: | Assinatura: |

| TESTEMUNHA 1 | TESTEMUNHA 2 |
|---|---|
| Nome: [●] | Nome: [●] |
| CPF: [●] | CPF: [●] |
| Assinatura: | Assinatura: |

---

# ANEXO I — ESCOPO FUNCIONAL

Integram a licença os módulos existentes descritos nos itens 2.1 a 2.5 da proposta, na versão disponível na data de início, respeitados papéis, permissões, limites e dependências técnicas.

Não estão incluídos, salvo aditivo:

- hardware GPS, chip, instalação ou telemetria veicular nativa;
- emissão/consulta fiscal de CT-e, MDF-e, NF-e, CIOT, RNTRC, averbação ou vale-pedágio;
- aplicativo móvel nativo publicado em lojas;
- integração não documentada com ERP, banco, seguradora, rastreador ou governo;
- central 24x7, operação logística humana ou digitação de dados;
- saneamento massivo, certificação contábil/fiscal ou migração além do modelo acordado;
- garantia de precisão de geocodificação, mapas ou respostas de IA de terceiros.

# ANEXO II — PLANO COMERCIAL SELECIONADO

Marcar uma única opção:

- [ ] **12 meses:** implantação R$ 18.000; mensalidade R$ 9.900.
- [ ] **24 meses:** implantação R$ 9.000; mensalidade R$ 8.900.
- [ ] **36 meses:** implantação isenta; mensalidade R$ 7.900.

Franquias e excedentes: conforme itens 5.1 e 5.3 da proposta, com as seguintes alterações negociadas: [●].

# ANEXO III — TRATAMENTO DE DADOS

| Item | Descrição inicial |
|---|---|
| Titulares | usuários, empregados, motoristas, prestadores, clientes, destinatários e contatos comerciais |
| Dados | identificação, contato, vínculo profissional, documentos, credenciais protegidas, eventos operacionais, localização quando habilitada, registros financeiros e anexos enviados |
| Finalidades | autenticação, gestão logística/frota/financeira, comprovação, segurança, suporte, auditoria e cumprimento do Contrato |
| Operações | coleta, recepção, organização, consulta, armazenamento, processamento, exportação, backup e eliminação |
| Duração | vigência e períodos de retenção da Cláusula 8 ou obrigação legal |
| Controladora | CONTRATANTE, quanto aos dados de sua operação |
| Operadora | CONTRATADA, segundo instruções da CONTRATANTE |
| Suboperadores | nuvem/VPS, storage, e-mail, mapas, monitoramento, backup e IA, conforme aplicável |
| Dados sensíveis | não previstos como finalidade principal; anexos podem contê-los e devem ser minimizados pela CONTRATANTE |
| Transferência internacional | possível para provedores contratados, mediante mecanismo legal aplicável |

# ANEXO IV — BASE LEGAL E REFERÊNCIAS DA MINUTA

- LGPD, especialmente papéis de controlador/operador, instruções, segurança e incidentes: https://www.planalto.gov.br/ccivil_03/_ato2015-2018/2018/lei/l13709.htm
- Regulamento da ANPD sobre comunicação de incidente; prazo regulatório atual de 3 dias úteis para o controlador nos casos aplicáveis: https://www.gov.br/anpd/pt-br/canais_atendimento/agente-de-tratamento/comunicado-de-incidente-de-seguranca-cis
- Lei nº 14.063/2020, classificações de assinatura eletrônica: https://www.planalto.gov.br/ccivil_03/_ato2019-2022/2020/lei/l14063.htm
- IPCA/IBGE: https://www.ibge.gov.br/indicadores-economicos/ipca.html
