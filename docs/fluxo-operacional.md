# Fluxo operacional e tempos medidos

## Estados da rota
`planejada → em_carregamento → liberada → em_rota → finalizada` (ou `cancelada`).

## Eventos auditáveis (`route_events.event_type`)
`ARRIVED_CD, ENTERED_DOCK, LOADING_STARTED, LOADING_FINISHED, OPERATOR_RELEASED,
DEPARTED_CD, ARRIVED_STOP, DELIVERED,
FAILED_DELIVERY, RETURN_STARTED, RETURN_COMPLETED, ROUTE_CLOSED`

## Endpoints do fluxo (API)
| Ação | Endpoint | Evento |
|---|---|---|
| Chegada ao CD | `POST /routes/{id}/arrive-cd` | ARRIVED_CD |
| Entrada na doca | `POST /routes/{id}/enter-dock` | ENTERED_DOCK |
| Início carregamento | `POST /routes/{id}/loading-start` | LOADING_STARTED |
| Fim carregamento | `POST /routes/{id}/loading-finish` | LOADING_FINISHED |
| Liberação operador | `POST /routes/{id}/release` | OPERATOR_RELEASED |
| Saída do CD | `POST /routes/{id}/depart` | DEPARTED_CD |
| Check-in no cliente | `POST /routes/{id}/stops/{stop}/checkin` | ARRIVED_STOP |
| Entrega | `POST /routes/{id}/stops/{stop}/deliver` | DELIVERED / FAILED_DELIVERY |
| Fechar rota | `POST /routes/{id}/close` | ROUTE_CLOSED |

## Tempos calculados (`dock_sessions`)
- `waiting_before_dock_minutes` = chegada CD → entrada doca
- `loading_minutes` = início → fim do carregamento
- `waiting_release_minutes` = fim carregamento → liberação
- `total_cd_minutes` = chegada CD → saída do CD

## Entrada de rotas
As rotas são criadas manualmente, importadas por planilha ou sincronizadas pela
integração autorizada. Não existe processamento automático de documentos.

## Rótulos i18n sensíveis
- F.Entr → **pt-BR:** "Data limite de entrega" · **pt-PT:** "Data limite de entrada/entrega"
- caminhão (BR) / camião (PT) · CD (BR) / armazém-plataforma (PT)
