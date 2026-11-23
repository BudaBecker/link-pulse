# Ambiente local do Marco 2

Docker Compose com os bancos do Marco 2, nos tetos e na configuração do [ADR-0013](../docs/decisoes/ADR-0013-stack-e-ambiente-do-marco-2.md) e com os esquemas do [ADR-0014](../docs/decisoes/ADR-0014-modelo-de-dados-e-metodo-do-benchmark.md). É o passo 1 do plano da [SPEC-004](../docs/specs/SPEC-004-aplicacao.md#plano-de-implementação) (RM-24).

## Como usar

| Ação | Comando |
| --- | --- |
| Subir tudo e esperar ficar saudável | `docker compose up -d --wait` |
| Conferir o ambiente | `docker compose run --rm verificar` |
| Parar, mantendo os dados | `docker compose down` |
| Parar e apagar os dados | `docker compose down -v` |
| Carregar ou restaurar a base de referência do benchmark | ver [benchmark/](../benchmark/README.md) |

Com os volumes vazios, a subida leva de 65 a 75 s, quase todos esperando o Cassandra; com os volumes já criados, cerca de 20 s. O esquema do PostgreSQL é criado só quando o volume está vazio. O do Cassandra é aplicado a cada subida, com `IF NOT EXISTS`, pelo `cassandra-esquema`, que depois fica em espera para o `--wait` não tratar a saída dele como falha. A senha do PostgreSQL vem de `POSTGRES_PASSWORD` (padrão `linkpulse`). As portas ficam só em `127.0.0.1`.

Os healthchecks são leves para não gastar a cota de CPU dos bancos durante o benchmark. O do Cassandra só abre uma conexão na porta 9042, que abre ao fim da partida; a conferência por CQL é feita uma vez, pelo `cassandra-esquema`. O do PostgreSQL usa `pg_isready` por TCP, como a aplicação: na primeira subida, o servidor temporário que cria o esquema já responde pelo socket local, mas ainda não por TCP.

O `verificar` confere, com as bibliotecas fixadas: Redis master com réplica ligada, AOF desligado e RDB ligado; keyspace com fator de replicação 1 e `cliques_por_link` com a chave e a ordem do ADR-0014; tabelas do PostgreSQL sem chave estrangeira, só com os índices das chaves primárias e com `synchronous_commit` no padrão; MongoDB respondendo.

## Serviços

| Serviço | Imagem | Porta | CPUs | Memória | Observação |
| --- | --- | --- | --- | --- | --- |
| `redis-master` | `redis:8.2.11-bookworm` | 6379 | 2 | 2 GB | Configuração padrão: sem AOF, RDB periódico |
| `redis-replica` | `redis:8.2.11-bookworm` | 6380 | 1 | 512 MB | `--replicaof redis-master 6379` |
| `cassandra` | `cassandra:5.0.9` | 9042 | 2 | 2 GB | Heap de 1 GB (`MAX_HEAP_SIZE`); commit log periódico de 10 s |
| `cassandra-esquema` | `cassandra:5.0.9` | — | 1 | 256 MB | Aplica [esquema.cql](cassandra/esquema.cql) e fica em espera |
| `postgres` | `postgres:18.7-bookworm` | 5432 | 2 | 2 GB | Parâmetros padrão; aplica [esquema.sql](postgres/esquema.sql) |
| `mongo` | `mongo:8.0.38-noble` | 27017 | 1 | 1 GB | Campanhas; fora do benchmark |
| `verificar` | [Dockerfile](../Dockerfile) | — | 1 | 256 MB | Perfil `verificacao`; só sobe com `run` |

Os três bancos comparados (Redis master, Cassandra e PostgreSQL) usam o mesmo bloco de teto no [docker-compose.yml](../docker-compose.yml). O `memswap_limit` igual ao `mem_limit` impede que um contêiner passe do teto usando swap. A aplicação e o gerador de carga entram com os seus tetos nas tarefas que os implementam (RM-30 e RM-31).

## Versões fixadas

- Imagens: as tags da tabela acima, com a versão completa.
- Python 3.13.18 (`python:3.13.18-slim-bookworm`).
- Bibliotecas em [requirements.txt](../requirements.txt): FastAPI 0.165.0, uvicorn 0.54.0, redis-py 8.2.0, cassandra-driver 3.30.1, psycopg 3.3.9, pymongo 4.20.1.

## Consumo de memória medido

Medido em 23/11/2026 com `docker stats`, com os bancos sem dados e outras aplicações abertas no computador (editor, navegador, vídeo). A VM do Docker tinha 7,6 GiB e 24 CPUs. Os valores se repetiram em duas subidas, uma com os volumes vazios e outra com os volumes já criados. São uma referência de desenvolvimento: a medição de desempenho vale na máquina dedicada da apresentação, com os dados de referência carregados.

| Serviço | Uso | Teto | % do teto |
| --- | --- | --- | --- |
| `cassandra` | 1,70 GiB | 2 GiB | 85% |
| `mongo` | 104 MiB | 1 GiB | 10% |
| `postgres` | 41 MiB | 2 GiB | 2% |
| `redis-master` | 5 MiB | 2 GiB | 0,3% |
| `redis-replica` | 5 MiB | 512 MiB | 1% |
| `cassandra-esquema` | 1 MiB | 256 MiB | 0,4% |
| **Total** | **1,86 GiB** | | |

Com tudo no ar, a VM ficou com 4,5 GiB disponíveis nessa execução; o valor muda com o que mais estiver aberto no computador.

- **Cassandra perto do teto já sem dados.** Os 1,70 GiB são quase todos memória do processo Java: o heap de 1 GB é reservado inteiro na partida, e o resto é memória da JVM fora do heap. Com os 10 milhões de cliques carregados, o contêiner coube no teto de 2 GB, sem encerramento por falta de memória, e o teto dos três bancos continua o mesmo ([medição da carga](../benchmark/README.md#memória-durante-a-carga)).
- **Folga da máquina.** Os tetos somados dos bancos chegam a 7,5 GB, quase toda a VM. Os bancos usam bem menos que o teto, mas subir o teto dos três para 3 GB passaria da memória da VM; nesse caso é preciso dar mais memória ao Docker (no Windows, `memory` em `.wslconfig`).
- **Threads de GC do Cassandra.** O script de partida do Cassandra calcula as threads de GC pelas CPUs que enxerga (24), não pelo teto de 2 CPUs. A questão continua aberta, como Q-38 em [QUESTOES](../docs/requisitos/QUESTOES.md#abertas), até a medição do Cassandra sob carga na máquina dedicada.
