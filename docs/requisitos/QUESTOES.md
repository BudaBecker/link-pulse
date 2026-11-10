# Questões

Dúvidas, lacunas e contradições encontradas na documentação. Uma questão aberta bloqueia os requisitos e specs que a citam. Uma questão adiada não bloqueia: o requisito segue com o comportamento mais simples já documentado, e a questão volta a ser discutida depois do Marco 2.

Quando uma questão for respondida:

1. se a decisão atravessa vários requisitos (tecnologia, modelo, escopo), registre um ADR em [`../decisoes/`](../decisoes/README.md);
2. atualize os requisitos afetados em [REQUISITOS.md](REQUISITOS.md) (descrição, critério, origem `Q-xx`, pendências);
3. mova a linha para **Respondidas**, com a resposta e o link de onde ela foi registrada.

A coluna "Proposta" é só uma sugestão para acelerar a decisão; ela não vale como requisito.

## Abertas

Nenhuma.

## Adiadas (pós-Marco 2)

O projeto é da disciplina e mostra o básico de cada família NoSQL. Estas questões refinam a modelagem além do que o Marco 1 e o Marco 2 exigem; ficam registradas para depois do Marco 2.

| ID | Tipo | Questão | Origem | Afeta | Proposta (não aprovada) |
| --- | --- | --- | --- | --- | --- |
| Q-09 | Contradição | O contador Redis é "recalculável a partir do histórico", mas a perda pontual de cliques no Cassandra é aceita — os dois podem divergir. Qual é a fonte da verdade da contagem? | [ARQUITETURA](../arquitetura/ARQUITETURA.md) Passo 4 × §Trade-offs | RF-04, RN-05, RN-07 | Cassandra é a fonte da verdade do histórico; o contador é aproximação e pode ser maior |
| Q-10 | Lacuna | O exemplo do CAP cita "URL editada", mas não há funcionalidade de edição de link. Links são editáveis? | [ARQUITETURA](../arquitetura/ARQUITETURA.md) Passo 6 §CAP | — | Fora do Marco 1; `url` imutável após a criação |
| Q-12 | Lacuna | A partição `short_code` cresce sem limite (500 cliques/min em pico). Adotar *bucket* por período na partition key? | [ARQUITETURA](../arquitetura/ARQUITETURA.md) Passo 5 × §Estimativa | RNF-04, RNF-05 | Manter `short_code` no Marco 1 e registrar `(short_code, dia)` como evolução |
| Q-13 | Lacuna | Autenticação e isolamento por cliente (agências): exigidos no Marco 1? `cliente_id` não está no Cassandra. | [VISAO](../produto/VISAO.md) §Para quem é; [FUNCIONALIDADES](../arquitetura/FUNCIONALIDADES.md) `POST /links` | RN-02 | Fora do Marco 1; `cliente_id` informado na criação, sem autenticação |
| Q-14 | Lacuna | Como obter país/região (GeoIP?) e quais dados pessoais são guardados (IP, user-agent)? Retenção e LGPD? | [FUNCIONALIDADES](../arquitetura/FUNCIONALIDADES.md) §Registro de cliques | RF-03 | Não armazenar IP; país por cabeçalho ou base GeoIP local; dispositivo derivado do user-agent; retenção a definir |
| Q-15 | Inconsistência | Afirmações sobre concorrentes divergem: VISAO diz que expiração é "raramente suportada"; PITCH diz "recurso pago/limitado" no Bit.ly. Não há fonte citada. | [VISAO](../produto/VISAO.md) §Diferenciais × [PITCH](../produto/PITCH.md) §Diferencial | Nenhum requisito | Tratar como posicionamento; citar fonte ou suavizar o texto |
| Q-16 | Lacuna | Cliques de bots/crawlers (pré-visualização de links em redes sociais) entram nas métricas? | Não documentado | RF-03, RF-05 | Fora do Marco 1; registrar como está |
| Q-17 | Lacuna | O mapeamento `link:{short_code}` só existe no Redis (em memória). Se ele for perdido, os links deixam de redirecionar — o oposto do compromisso central. Qual a durabilidade exigida? | [ARQUITETURA](../arquitetura/ARQUITETURA.md) Passo 4 (só o contador é declarado *soft state*) | RNF-01, RN-08 | Persistência AOF ligada no Redis + réplica (ADR-0009) |
## Respondidas

| ID | Questão | Resposta | Registrada em |
| --- | --- | --- | --- |
| Q-01 | Haverá aplicação executável, e quando? | Sim. Primeiro previsto para o Marco 1, depois revisto: o sistema é entregue no Marco 2 | [ADR-0008](../decisoes/ADR-0008-aplicacao-no-marco-1.md), substituída por [ADR-0011](../decisoes/ADR-0011-marco-1-so-documentacao.md) |
| Q-02 | Os documentos atuais podem ser movidos ou alterados? | Sim, para a melhor organização | [docs/README.md](../README.md) (nova estrutura) |
| Q-03 | Metas de disponibilidade, latência e defasagem | Disponibilidade mensal ≥ 99,9%; p95 do redirecionamento < 50 ms; defasagem do painel ≤ 60 s | RNF-01, RNF-02, RNF-03 em [REQUISITOS.md](REQUISITOS.md) |
| Q-04 | Como o canal de um clique é determinado? | Um link curto por canal | RF-05 em [REQUISITOS.md](REQUISITOS.md) (detalhe em Q-18) |
| Q-05 | "Master-Slave" para o sistema todo, com Cassandra *masterless* | Seguir o checklist da disciplina: Redis Master-Slave, Cassandra Master-Master | [ADR-0009](../decisoes/ADR-0009-replicacao-por-banco.md) |
| Q-06 | Resposta para link inexistente e expirado | `404` para inexistente, `410` para expirado | RN-03 em [REQUISITOS.md](REQUISITOS.md) (registro do clique em Q-22) |
| Q-07 | Fluxo Git | PR obrigatório com revisão obrigatória (autor, colega ou agente), squash merge, branch apagada após o merge | [CONTRIBUTING](../../CONTRIBUTING.md) |
| Q-08 | Onde organizar as tarefas e o andamento? | Todo no GitHub: uma issue por tarefa do roadmap, milestone por marco, sub-issue para tarefa complementar; andamento pelo estado da issue e do PR | [roadmap](../roadmap/README.md) |
| Q-19 | Prazo do Marco 1 | Vencimento no AVA: 29/09/2026 às 00:00 — enviar até a noite de 28/09 | [DISCIPLINA](../produto/DISCIPLINA.md) |
| Q-20 | Stack da aplicação | Python + FastAPI, `redis-py`, `cassandra-driver`, Docker Compose com Redis (master + réplica) e Cassandra | [ADR-0010](../decisoes/ADR-0010-stack-da-aplicacao.md), substituída por [ADR-0013](../decisoes/ADR-0013-stack-e-ambiente-do-marco-2.md) (ver Q-25) |
| Q-21 | Forma do painel de analytics | Página HTML servida pela própria aplicação. A biblioteca de gráficos, antes carregada por CDN, passou a ser servida pela aplicação | RF-06 em [REQUISITOS.md](REQUISITOS.md); [ADR-0010](../decisoes/ADR-0010-stack-da-aplicacao.md), substituída por [ADR-0013](../decisoes/ADR-0013-stack-e-ambiente-do-marco-2.md) |
| Q-18 | Com "canal = link", como o painel sabe o nome do canal e quais links são de um cliente? | Campo opcional `canal` no Hash `link:{short_code}` e Set `links:cliente:{cliente_id}` no Redis | RF-01, RF-05 em [REQUISITOS.md](REQUISITOS.md); [ARQUITETURA](../arquitetura/ARQUITETURA.md) Passo 4 |
| Q-23 | O que a aplicação precisa cumprir no Marco 1? | Nada: o Marco 1 entrega só descrição do problema, modelagem e justificativa; o sistema fica para o Marco 2 | [ADR-0011](../decisoes/ADR-0011-marco-1-so-documentacao.md) |
| Q-11 | Qual alfabeto, tamanho e tratamento de colisão do `short_code`? | Base62 com 7 caracteres; a gravação só acontece se a chave ainda não existir, com nova tentativa em colisão | RF-01 e RN-01 em [REQUISITOS.md](REQUISITOS.md) |
| Q-22 | Clique em link expirado (`410`) é registrado como evento ou conta no contador? | Não registra nem conta | RN-03 em [REQUISITOS.md](REQUISITOS.md) |
| Q-24 | Qual é o resultado principal do Marco 2? | A comparação medida entre os bancos NoSQL do projeto e o PostgreSQL; a aplicação fica com o necessário para a demonstração | [ADR-0012](../decisoes/ADR-0012-marco-2-benchmark-sql-x-nosql.md) |
| Q-25 | O que muda na stack e no ambiente com o benchmark? | Entram PostgreSQL, MongoDB, `psycopg`, `pymongo` e Chart.js servido pela aplicação; os três bancos comparados rodam com a configuração padrão e o mesmo teto de 2 CPUs e 2 GB | [ADR-0013](../decisoes/ADR-0013-stack-e-ambiente-do-marco-2.md) |
| Q-26 | Dois cliques do mesmo link no mesmo milissegundo têm a mesma chave em `cliques_por_link` e viram uma linha só. Como evitar? | `clique_id timeuuid` como segunda clustering column; `uuid` no PostgreSQL | [ADR-0014](../decisoes/ADR-0014-modelo-de-dados-e-metodo-do-benchmark.md); [ARQUITETURA](../arquitetura/ARQUITETURA.md) Passo 5; RF-03 |
| Q-27 | Qual modelo o PostgreSQL usa para a comparação ser justa? | Tabelas `links`, `contadores` e `cliques`; chave primária composta em `cliques`, sem índice extra e sem chave estrangeira | [ADR-0014](../decisoes/ADR-0014-modelo-de-dados-e-metodo-do-benchmark.md) |
| Q-28 | Os bancos confirmam a escrita com garantias diferentes. Como tratar isso na comparação? | Todos no padrão, com a garantia de cada um mostrada ao lado dos números; uma curva extra do PostgreSQL com `synchronous_commit=off` nas duas escritas | [ADR-0014](../decisoes/ADR-0014-modelo-de-dados-e-metodo-do-benchmark.md) |
| Q-29 | Como a carga é aplicada, e em que nível? | Laço fechado nas quatro operações e no pico; laço aberto com 200 redirecionamentos por segundo na queda do Cassandra; número de conexões escolhido por calibração (8, 32 e 64), com o gerador abaixo de 70% do seu limite de CPU | [ADR-0014](../decisoes/ADR-0014-modelo-de-dados-e-metodo-do-benchmark.md); RNF-04 |
| Q-30 | Quais as durações, as repetições e a distribuição dos dados do benchmark? | 60 s por lado depois de 10 s de aquecimento, 3 repetições e mediana; 20% dos cliques no link popular, ao longo de 90 dias; histórico lê 24 horas com limite de 1.000 linhas | [ADR-0014](../decisoes/ADR-0014-modelo-de-dados-e-metodo-do-benchmark.md); [SPEC-005](../specs/SPEC-005-testes-de-stress.md) |
| Q-31 | A réplica do Redis pode ainda não ter um link recém-criado. De onde o redirecionamento lê? | Da réplica; se o link não estiver lá ou a réplica não responder, do master, antes de responder `404` | RF-02 em [REQUISITOS.md](REQUISITOS.md) |
| Q-32 | O que a aplicação faz com um clique que falhou ao gravar no Cassandra? | Descarta e soma em um contador de falhas, sem fila nem nova tentativa | RN-07 em [REQUISITOS.md](REQUISITOS.md) |
| Q-33 | O documento do MongoDB representa um link ou uma campanha? | Uma campanha, com os links embutidos; a campanha é opcional na criação do link | [ADR-0014](../decisoes/ADR-0014-modelo-de-dados-e-metodo-do-benchmark.md); RF-09 |
| Q-34 | Onde ficam os clientes cadastrados? | No Redis: nome em `cliente:{cliente_id}` e Set `clientes` só com os clientes da demonstração | [ADR-0014](../decisoes/ADR-0014-modelo-de-dados-e-metodo-do-benchmark.md); RF-08 |
