# SPEC-005 — Testes de stress: benchmark SQL x NoSQL

- **Status:** Pronta
- **Requisitos:** RF-10, RF-11, RNF-01, RNF-02, RNF-04, RNF-08, RN-07
- **Decisões:** ADR-0012, ADR-0013, ADR-0014
- **Bloqueios:** nenhum

## Objetivo

Um gerador de carga e uma tela de testes que medem as quatro operações do produto nos bancos NoSQL e no PostgreSQL, mostram o pico de tráfego e a queda do Cassandra, e guardam uma execução completa para a apresentação ([ADR-0012](../decisoes/ADR-0012-marco-2-benchmark-sql-x-nosql.md)).

## Fora de escopo

- Benchmark do MongoDB.
- Cassandra com mais de um nó.
- Ajuste de parâmetros dos bancos, além da curva extra do PostgreSQL.
- Comportamento da aplicação ([SPEC-004](SPEC-004-aplicacao.md)); aqui ela só é exercitada no cenário de queda.

## Comportamento

O método, o modelo do lado PostgreSQL e os dados carregados estão no [ADR-0014](../decisoes/ADR-0014-modelo-de-dados-e-metodo-do-benchmark.md); os tetos e a configuração dos bancos, no [ADR-0013](../decisoes/ADR-0013-stack-e-ambiente-do-marco-2.md).

### Carga de dados

Antes dos testes, um comando carrega os mesmos clientes, links e cliques no lado NoSQL (Redis e Cassandra) e no PostgreSQL. A geração é determinística: a mesma semente produz os mesmos dados. O `dispositivo` dos cliques carregados segue uma distribuição fixa: 60% `mobile`, 30% `desktop`, 5% `tablet` e 5% `outro`.

Depois da carga, uma cópia dos volumes de dados do Redis, do Cassandra e do PostgreSQL fica guardada (Q-35). Restaurar a cópia significa parar os contêineres desses bancos, trocar os volumes pela cópia e religá-los. Apagar as linhas acrescentadas não serve: no Cassandra, a exclusão deixa marcas (*tombstones*) que deixariam as leituras seguintes mais lentas só nesse lado.

### Sequência de testes

| # | Etapa | O que roda | Ao vivo |
| --- | --- | --- | --- |
| 1 | Redirecionamento | leitura do link, um lado de cada vez | 60 s |
| 2 | Contador | incremento, um lado de cada vez | 60 s |
| 3 | Registro de clique | `INSERT` individual, um lado de cada vez, mais a curva extra | 90 s |
| 4 | Histórico por período | leitura de 24 horas com limite de 1.000 linhas, um lado de cada vez | 60 s |
| 5 | Pico de tráfego | leitura, contador e registro ao mesmo tempo, todos no link popular, um lado de cada vez | 120 s |
| 6 | Queda do Cassandra | 200 redirecionamentos por segundo pela aplicação; o Cassandra para aos 30 s e volta aos 60 s | 90 s |

- **Ao vivo:** a sequência roda uma vez, em até 480 s, contados do clique no botão ao resultado da queda, com a subida de cada execução. Cada etapa divide o seu tempo por igual entre as execuções que contém. Nas etapas 1 a 4, cada execução tem 3 s de aquecimento descartados e 18 s medidos; no pico, 3 s e 45 s; a queda mantém 90 s e usa a folga das outras etapas para subir a API e conferir (Q-72).
- **Execução completa:** nas etapas 1 a 5, cada lado roda 60 s depois de 10 s de aquecimento descartados; a curva extra entra nas etapas 2 e 3. A sequência inteira, incluindo a queda do Cassandra, repete 3 vezes (Q-36). Nas etapas 1 a 5, o resultado é a mediana; na queda, as 3 execuções são publicadas e todas precisam cumprir o CA-6. O resultado é gravado em `benchmark/gravacoes/`, no Git (Q-74).
- **Curva extra:** cada conexão do gerador aplica `synchronous_commit=off` só na sua sessão; a configuração do servidor continua a padrão (Q-73).
- **Estado dos dados:** a cópia é restaurada antes de cada repetição e antes do histórico por período, a única leitura afetada pelas linhas que o registro de clique acrescenta. A execução ao vivo parte da cópia restaurada e não restaura no meio, porque só ilustra. A restauração dela roda antes do botão, pelo terminal, fora dos 480 s (Q-72).
- **Pico de tráfego:** cada conexão repete as três operações em sequência no link popular, leitura, contador e registro, como um clique no produto; a mistura fica em 1:1:1 nos dois lados, e a latência é medida por operação (Q-39). Na sequência, o pico parte do estado restaurado antes do histórico por período, que não escreve.
- **Calibração:** antes da primeira execução completa, o gerador testa 8, 32 e 64 conexões e registra o número escolhido e o seu uso de CPU.

### Métricas

Para cada execução: vazão (operações por segundo), latência p50, p95 e p99, taxa de erro e uso de CPU do gerador. No cenário de queda, também o número de cliques que falharam ao gravar e a diferença entre o contador e o histórico.

### Tela de testes

- Um botão inicia a sequência; a tela mostra a etapa atual.
- As curvas dos dois lados aparecem sobrepostas por tempo decorrido e crescem durante a execução.
- Um placar mostra vazão, p50, p95, p99 e erros de cada lado, por etapa.
- A curva extra aparece identificada como fora do padrão.
- Outro botão abre a execução completa salva, identificada como gravada.
- A tela funciona sem internet.
- **Servidor:** a tela tem servidor próprio no benchmark, separado da aplicação, que roda a medição a pedido do botão e repassa os eventos dela à tela; a tela abre com os bancos parados (Q-70).
- **Curvas:** uma amostra por segundo de vazão e p95, do gerador, e de CPU e memória dos bancos exercitados, com o aquecimento sombreado; no pico, a vazão conta cliques completos (Q-71).
- **Gravação:** o placar mostra a mediana das repetições, e as curvas, uma repetição por vez (Q-74).
- **Queda:** a tela mostra os `302` e os cliques que falharam por segundo, com a parada, o religamento e a volta da gravação marcados, e um placar da janela do CA-6 e da conferência (Q-75).

## Plano de implementação

1. Esquema do PostgreSQL, carga de dados nos dois lados e cópia dos volumes para restauração.
2. Gerador de carga em laço fechado para as quatro operações, com a coleta de métricas.
3. Calibração e registro do resultado; troca da linguagem do laço de disparo, se a regra do [ADR-0013](../decisoes/ADR-0013-stack-e-ambiente-do-marco-2.md) indicar.
4. Cenário de pico.
5. Cenário de queda do Cassandra, em laço aberto pela aplicação, com parada e religamento automáticos.
6. Tela de testes.
7. Execuções completas e gravação do resultado.

## Critérios de aceitação

- [x] **CA-1** (RNF-08) — Depois da carga e depois de cada restauração da cópia, a contagem de links e de cliques é igual no lado NoSQL e no PostgreSQL, e o link popular tem 20% dos cliques nos dois.
- [x] **CA-2** (RF-10) — Para cada uma das quatro operações, a execução produz vazão, p50, p95, p99 e taxa de erro dos dois lados.
- [x] **CA-3** (RNF-08) — Em cada etapa, os dois lados rodam um de cada vez, com o mesmo número de conexões e os mesmos tetos de CPU e memória; o uso de CPU do gerador fica registrado e abaixo de 70% do seu limite.
- [ ] **CA-4** (RF-10, RNF-08) — A execução completa repete a sequência inteira 3 vezes, restaura a cópia antes de cada repetição e antes do histórico por período, descarta os 10 s de aquecimento e publica a mediana das etapas 1 a 5; a curva extra aparece nas duas escritas, separada da execução padrão.
- [x] **CA-5** (RNF-04) — No cenário de pico, a taxa de erro das três operações no lado NoSQL é zero.
- [ ] **CA-6** (RNF-01, RNF-02, RN-07) — No cenário de queda, em cada uma das 3 execuções da execução completa e enquanto o Cassandra está parado, os redirecionamentos continuam respondendo `302` com p95 abaixo de 50 ms; o contador continua somando, e os cliques que falharam aparecem na tela.
- [x] **CA-7** (RF-11) — A tela inicia a sequência com um botão, mostra a etapa atual, as curvas sobrepostas e o placar, e conclui a execução ao vivo em até 480 s.
- [ ] **CA-8** (RF-11) — Com a rede desligada, a tela carrega com os gráficos e abre a execução salva, identificada como gravada.
