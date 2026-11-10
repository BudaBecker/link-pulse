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

Antes dos testes, um comando carrega os mesmos clientes, links e cliques no lado NoSQL (Redis e Cassandra) e no PostgreSQL. A geração é determinística: a mesma semente produz os mesmos dados.

### Sequência de testes

| # | Etapa | O que roda | Ao vivo |
| --- | --- | --- | --- |
| 1 | Redirecionamento | leitura do link, um lado de cada vez | 60 s |
| 2 | Contador | incremento, um lado de cada vez | 60 s |
| 3 | Registro de clique | `INSERT` individual, um lado de cada vez, mais a curva extra | 90 s |
| 4 | Histórico por período | leitura de 24 horas com limite de 1.000 linhas, um lado de cada vez | 60 s |
| 5 | Pico de tráfego | leitura, contador e registro ao mesmo tempo, todos no link popular, um lado de cada vez | 120 s |
| 6 | Queda do Cassandra | 200 redirecionamentos por segundo pela aplicação; o Cassandra para aos 30 s e volta aos 60 s | 90 s |

- **Ao vivo:** a sequência roda uma vez, em até 480 s. Cada etapa divide o seu tempo por igual entre as execuções que contém.
- **Execução completa:** nas etapas 1 a 5, cada lado roda 60 s depois de 10 s de aquecimento descartados; a curva extra entra nas etapas 2 e 3. A sequência repete 3 vezes e o resultado é a mediana.
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

## Plano de implementação

1. Esquema do PostgreSQL e carga de dados nos dois lados.
2. Gerador de carga em laço fechado para as quatro operações, com a coleta de métricas.
3. Calibração e registro do resultado; troca da linguagem do laço de disparo, se a regra do [ADR-0013](../decisoes/ADR-0013-stack-e-ambiente-do-marco-2.md) indicar.
4. Cenário de pico.
5. Cenário de queda do Cassandra, em laço aberto pela aplicação, com parada e religamento automáticos.
6. Tela de testes.
7. Execuções completas e gravação do resultado.

## Critérios de aceitação

- [ ] **CA-1** (RNF-08) — Depois da carga, a contagem de links e de cliques é igual no lado NoSQL e no PostgreSQL, e o link popular tem 20% dos cliques nos dois.
- [ ] **CA-2** (RF-10) — Para cada uma das quatro operações, a execução produz vazão, p50, p95, p99 e taxa de erro dos dois lados.
- [ ] **CA-3** (RNF-08) — Em cada etapa, os dois lados rodam um de cada vez, com o mesmo número de conexões e os mesmos tetos de CPU e memória; o uso de CPU do gerador fica registrado e abaixo de 70% do seu limite.
- [ ] **CA-4** (RF-10) — A execução completa repete a sequência 3 vezes, descarta os 10 s de aquecimento e publica a mediana; a curva extra aparece nas duas escritas, separada da execução padrão.
- [ ] **CA-5** (RNF-04) — No cenário de pico, a taxa de erro das três operações no lado NoSQL é zero.
- [ ] **CA-6** (RNF-01, RNF-02, RN-07) — No cenário de queda, enquanto o Cassandra está parado, os redirecionamentos continuam respondendo `302` com p95 abaixo de 50 ms; o contador continua somando, e os cliques que falharam aparecem na tela.
- [ ] **CA-7** (RF-11) — A tela inicia a sequência com um botão, mostra a etapa atual, as curvas sobrepostas e o placar, e conclui a execução ao vivo em até 480 s.
- [ ] **CA-8** (RF-11) — Com a rede desligada, a tela carrega com os gráficos e abre a execução salva, identificada como gravada.
