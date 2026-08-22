# Dicionário de campos e sinônimos (ES/PT do manifesto)

O manifesto Salvesen mistura espanhol e português. Mapeie os rótulos:

| Rótulo no papel | Idioma | Campo canônico |
|---|---|---|
| Código UT / Nº da Volta | ES/PT | `codigo_ut` (CÓDIGO DA ROTA) |
| Fecha y Hora de Carga | ES | `data_carga` + `hora_carga` |
| Origen / Origem | ES/PT | `origem` |
| Dirección / Morada | ES/PT | `origem_morada` |
| Transportista | ES | `transportadora` |
| Matrícula | ES/PT | `matricula` |
| Naturaleza de la Mercancía | ES | `natureza` |
| DESTINO | PT | `destinos[].nome` + `morada` |
| F.ENTR / F.Entr | PT | `destinos[].data_limite` (data limite de entrega) |
| HORA | PT | `destinos[].hora_limite` |
| TEMP.°C | PT | `destinos[].temperatura` |
| PESO | PT | `destinos[].peso_kg` |
| PALÉS / PALES / Pal | PT | `destinos[].pales` |
| PEDIDO / Pedidos | PT | `destinos[].pedido` |

## Fornecedores conhecidos (linha de detalhe)
Servem para identificar a 2ª linha da parada e preencher `fornecedor`:
- `Alpro Portugal (311)`
- `Danone Portugal (011)`
- `Danone Portugal Capilar (013)`
- `Tropicana España Base (015)`
- `Lactacores (405)`
> Padrão geral: `Nome do fornecedor (NNN)` com código de 3 dígitos.

## Temperatura
- `Amb.`, `Ambiente`, `AMB` → **"Ambiente"**
- `4`, `4°`, `4 ºC` → **"4"**

## Rótulos i18n no painel (não no JSON)
- F.ENTR → **pt-BR:** "Data limite de entrega" · **pt-PT:** "Data limite de entrada/entrega".
