# Ambiente local do Marco 2

Um Docker Compose sobe, no próprio computador, todos os bancos do LinkPulse: Redis (master e réplica) para links e contadores, Cassandra para o histórico de cliques, MongoDB para as campanhas e PostgreSQL como base de comparação do benchmark. Os limites de CPU e memória (tetos) e a configuração seguem a decisão de stack e ambiente do Marco 2 ([ADR-0013](../docs/decisoes/ADR-0013-stack-e-ambiente-do-marco-2.md)), e os esquemas, o modelo de dados do benchmark ([ADR-0014](../docs/decisoes/ADR-0014-modelo-de-dados-e-metodo-do-benchmark.md)). É o passo 1 do plano da aplicação ([SPEC-004](../docs/specs/SPEC-004-aplicacao.md#plano-de-implementação)), na tarefa de montar o ambiente local (RM-24). Esta pasta guarda os esquemas e o script de conferência; os serviços estão no [docker-compose.yml](../docker-compose.yml), na raiz.

## Como usar

| Ação | Comando |
| --- | --- |
| Subir tudo e esperar ficar saudável | `docker compose up -d --wait` |
| Conferir o ambiente | `docker compose run --rm verificar` |
| Parar, mantendo os dados | `docker compose down` |
| Parar e apagar os dados | `docker compose down -v` |
| Carregar ou restaurar a base de referência do benchmark | ver [benchmark/](../benchmark/README.md) |

Com os volumes vazios, a subida leva de 65 a 75 s, quase todos esperando o Cassandra; com os volumes já criados, cerca de 20 s. O esquema do PostgreSQL é criado só quando o volume está vazio. O do Cassandra é aplicado a cada subida, com `IF NOT EXISTS`, pelo serviço `cassandra-esquema`. Depois de aplicar, esse serviço fica em espera, porque o `--wait` trataria a saída do contêiner como falha. A senha do PostgreSQL vem de `POSTGRES_PASSWORD` (padrão `linkpulse`). As portas ficam só em `127.0.0.1`.

As verificações de saúde (healthchecks), que o Docker repete para saber se cada contêiner está pronto, são leves para não gastar a cota de CPU dos bancos durante o benchmark. A do Cassandra só abre uma conexão na porta 9042, que o Cassandra abre ao fim da partida; a consulta de verdade, pela linguagem do Cassandra (CQL), é feita uma vez, pelo `cassandra-esquema`. A do PostgreSQL usa `pg_isready` pela rede, como a aplicação vai se conectar. Na primeira subida, o servidor temporário que cria o esquema já responde pela conexão local do contêiner, mas ainda não pela rede, e o banco só conta como pronto quando o servidor definitivo sobe.

O `verificar` confere, com as bibliotecas fixadas:

- Redis: master com réplica ligada, e a gravação em disco no padrão da imagem: sem o registro de cada escrita (AOF) e com as fotografias periódicas da memória (RDB);
- Cassandra: o keyspace (o equivalente a um banco de dados) com fator de replicação 1, isto é, cada dado em um só nó, e `cliques_por_link` com a chave e a ordem do ADR-0014;
- PostgreSQL: tabelas sem chave estrangeira, só com os índices das chaves primárias, e com `synchronous_commit` no padrão, que só confirma a escrita depois de gravá-la no disco;
- MongoDB: respondendo.

## Serviços

| Serviço | Imagem | Porta | CPUs | Memória | Observação |
| --- | --- | --- | --- | --- | --- |
| `redis-master` | `redis:8.2.11-bookworm` | 6379 | 2 | 2 GB | Configuração padrão: sem AOF, RDB periódico |
| `redis-replica` | `redis:8.2.11-bookworm` | 6380 | 1 | 512 MB | `--replicaof redis-master 6379` |
| `cassandra` | `cassandra:5.0.9` | 9042 | 2 | 2 GB | Heap de 1 GB, a memória do Java para os dados (`MAX_HEAP_SIZE`); registro de escritas (commit log) gravado no disco a cada 10 s, o padrão |
| `cassandra-esquema` | `cassandra:5.0.9` | — | 1 | 256 MB | Aplica [esquema.cql](cassandra/esquema.cql) e fica em espera |
| `postgres` | `postgres:18.7-bookworm` | 5432 | 2 | 2 GB | Parâmetros padrão; aplica [esquema.sql](postgres/esquema.sql) |
| `mongo` | `mongo:8.0.38-noble` | 27017 | 1 | 1 GB | Campanhas; fora do benchmark |
| `verificar` | [Dockerfile](../Dockerfile) | — | 1 | 256 MB | Perfil `verificacao`: fica fora do `up` e só roda com `docker compose run` |

Os três bancos comparados (Redis master, Cassandra e PostgreSQL) usam o mesmo bloco de teto no [docker-compose.yml](../docker-compose.yml). O `memswap_limit` igual ao `mem_limit` impede que um contêiner passe do teto usando o disco como memória extra (swap). A aplicação e o gerador de carga ainda não existem; entram com os seus tetos nas tarefas que os implementam (RM-30 e RM-31).

## Versões fixadas

- Imagens: as tags da tabela acima, com a versão completa.
- Python 3.13.18 (`python:3.13.18-slim-bookworm`).
- Bibliotecas em [requirements.txt](../requirements.txt): FastAPI 0.165.0, uvicorn 0.54.0, redis-py 8.2.0, cassandra-driver 3.30.1, psycopg 3.3.9, pymongo 4.20.1.

Os serviços `verificar` e `carga` usam a mesma imagem Python. O script de verificação é copiado para a imagem durante o build. O serviço `carga` lê os scripts da pasta `benchmark/` montada em modo de leitura.

## Consumo de memória medido

Medido em 23/11/2026 com `docker stats`, com os bancos sem dados e outras aplicações abertas no computador (editor, navegador, vídeo). A máquina virtual (VM) do Docker tinha 7,6 GiB e 24 CPUs. Os valores se repetiram em duas subidas, uma com os volumes vazios e outra com os volumes já criados. São uma referência de desenvolvimento: a medição de desempenho vale na máquina dedicada da apresentação, com os dados de referência carregados.

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

- **Cassandra perto do teto já sem dados.** Os 1,70 GiB são quase todos memória do processo Java: o heap de 1 GB é reservado inteiro na partida, e o resto é memória que a máquina virtual Java (JVM) usa fora do heap. Com os 10 milhões de cliques carregados, o contêiner coube no teto de 2 GB, sem encerramento por falta de memória, e o teto dos três bancos continua o mesmo ([medição da carga](../benchmark/README.md#memória-durante-a-carga)).
- **Folga da máquina.** Os tetos somados dos bancos chegam a 7,5 GB, quase toda a VM. Os bancos usam bem menos que o teto, mas subir o teto dos três para 3 GB passaria da memória da VM; nesse caso é preciso dar mais memória ao Docker (no Windows, `memory` em `.wslconfig`).
- **Coleta de lixo do Cassandra.** O script de partida do Cassandra decide quantas threads fazem a coleta de lixo da memória Java (GC) pelas CPUs que enxerga (24), não pelo teto de 2 CPUs. A questão de como aplicar o teto de CPU sem penalizar um dos bancos continua aberta (Q-38 em [QUESTOES](../docs/requisitos/QUESTOES.md#abertas)), até a medição do Cassandra sob carga na máquina dedicada.
