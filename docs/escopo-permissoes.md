# Escopo de permissões operacionais

## Modelo da operação

- JM é a única empresa operacional e prestadora (`tenant`).
- Adimax é cliente/contratante da JM e não representa um ambiente de acesso.
- Piedade, Barueri e demais unidades são filiais operacionais da JM.
- A identidade visual Adimax pode ser aplicada ao portal sem conceder ou limitar acesso.

Módulo e escopo são decisões independentes:

- `module.*` define quais telas e funções o perfil pode usar.
- o escopo define quais registros essas funções podem consultar ou alterar.

| Perfil efetivo | Escopo padrão | Regra |
|---|---|---|
| Administrador global | Global | Pode cruzar empresas. |
| Admin Site / Gerente / Gestor Brasil | Empresa | Todas as filiais da própria empresa. |
| Monitoramento / Torre de Controle | Empresa | Todas as filiais da própria empresa. |
| Gestor financeiro / Auditoria / Diretoria | Empresa | Todos os registros permitidos da própria empresa. |
| Líder / Planejamento / Operador logístico | Filial | Somente a filial principal do usuário. |
| Motorista | Atribuição | Somente rotas ligadas ao `Driver.user_id` autenticado. |
| Cliente | Cliente na empresa | Somente paradas do cliente identificado no login. |

## Capacidades explícitas

- `scope.tenant`: amplia um perfil de filial para todas as filiais da própria empresa.
- `scope.global`: capacidade reservada para integrações administrativas; não é oferecida na tela de perfis.

Nenhum nome ou slug de empresa concede acesso global implicitamente. A empresa do
usuário é derivada da filial selecionada. Para motoristas, empresa e filial são
validadas contra o cadastro operacional vinculado por ID.

## Operações sensíveis

- O motorista pode registrar chegada, etapas de doca e "Liberado do CD" apenas na rota atribuída a ele.
- Gestão e monitoramento podem acompanhar rotas e ocorrências de todas as filiais da empresa.
- Uma consulta ou alteração por ID repete a validação de escopo; esconder itens na interface não é considerado autorização.
- A travessia entre empresas permanece exclusiva do administrador global.
