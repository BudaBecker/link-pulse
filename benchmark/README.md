# Base de referência do benchmark

Carga determinística dos mesmos clientes, links e cliques no lado NoSQL (Redis e Cassandra) e no PostgreSQL, com uma cópia dos volumes para restaurar antes de cada repetição. É o passo 1 do plano da [SPEC-005](../docs/specs/SPEC-005-testes-de-stress.md#plano-de-implementação) (RM-29), com os dados descritos no [ADR-0014](../docs/decisoes/ADR-0014-modelo-de-dados-e-metodo-do-benchmark.md#dados-e-durações).

## Como usar

Os comandos rodam no computador do host, na raiz do repositório, com Python 3.11 ou mais novo e o Docker. O script do host só usa a biblioteca padrão; a carga e a conferência rodam no contêiner `carga`, com as bibliotecas fixadas em [requirements.txt](../requirements.txt).

| Ação | Comando |
| --- | --- |
| Carregar a base do zero, conferir e guardar a cópia | `python benchmark/base.py carregar` |
| Voltar os bancos à cópia e conferir o CA-1 | `python benchmark/base.py restaurar` |
| Conferir o CA-1 | `python benchmark/base.py conferir` |
| Conferir também dispositivos e assinatura, lendo todos os cliques | `python benchmark/base.py conferir --completo` |
| Guardar de novo a cópia do estado atual | `python benchmark/base.py copiar` |
| Só reescrever o espelho do manifesto, sem mudar a base carregada | `python benchmark/base.py manifesto` |
| Voltar aos volumes de desenvolvimento | `docker compose up -d --wait` |

`carregar` aceita `--semente`, `--fim` (instante final, ISO 8601 com fuso) e `--processos` (padrão 4). Cada `carregar`, `copiar` e `restaurar` grava os tempos e a memória medidos em `benchmark/registros/`, fora do Git.

**Um comando por vez.** `carregar`, `copiar`, `restaurar` e `conferir` pegam a trava, que é um contêiner com nome fixo, `linkpulse-benchmark-trava`. O Docker não aceita dois contêineres com o mesmo nome. Os volumes e o projeto Compose também têm nome fixo, então a trava vale para qualquer cópia do repositório que use o mesmo Docker. Enquanto um comando roda, os outros saem com erro e dizem qual comando, processo e pasta estão com a trava. O contêiner fica preso à entrada padrão do comando: quando o comando termina ou morre, ele sai e é apagado (`--rm`). Isso importa porque `copiar` e `restaurar` deixam os bancos parados enquanto trocam os volumes. A conferência roda o contêiner `carga` com `--no-deps` e recusa bancos parados: ela nunca liga um banco.

## A base

| Item | Valor |
| --- | --- |
| Semente | 2026 |
| Período dos cliques | de 03/08/2026 00:00 UTC a 01/11/2026 00:00 UTC (90 dias) |
| Janela do histórico por período | as últimas 24 horas da base: de 31/10/2026 00:00 UTC a 01/11/2026 00:00 UTC |
| Clientes | 150, de `bench-001` a `bench-150`, com 300 links cada |
| Links | 45.000, com `short_code` de 7 caracteres em Base62, sem `expira_em` |
| Cliques | 10.000.000 |
| Link popular | `uGDsIV1`, com 2.000.000 de cliques (20%) |
| Demais links | 177 ou 178 cliques cada |
| Dispositivo | exatamente 6.000.000 `mobile`, 3.000.000 `desktop`, 500.000 `tablet` e 500.000 `outro` |

O manifesto guarda esses valores e a assinatura dos cliques. O gerador de carga (RM-31) lê dele o link popular e a janela do histórico. O instante final é um parâmetro fixo e não depende do relógio: carregar em outro dia produz a mesma base.

O manifesto que vale é o da base carregada, no volume `linkpulse-benchmark-manifesto`. Só `carregar` e `restaurar` o gravam, e a carga e a conferência o leem dali. O arquivo [base-de-referencia.json](base-de-referencia.json) é um espelho para leitura e para o Git. `carregar` e `restaurar` o atualizam, e `manifesto` reescreve só o espelho. Se o espelho divergir da base, `conferir` avisa e usa o manifesto da base. Um manifesto só é aceito, no volume e no selo, se for idêntico ao que a semente e o instante final geram, com uma assinatura de 16 dígitos hexadecimais. Campo faltando, campo a mais ou valor alterado o invalidam. A carga grava no volume o texto que ela mesma gerou, e não o espelho, que outro comando pode ter reescrito no meio.

**Determinismo.** A geração está em [referencia.py](referencia.py). Os cliques saem em blocos de até 10.000, cada um com o próprio gerador aleatório, semeado pela semente, pelo link e pelo número do bloco. Assim, cada processo gera os seus blocos sem depender da ordem, e os 10 milhões de eventos nunca ficam em memória. O `clique_id` é um `timeuuid` (UUID versão 1) montado a partir do mesmo milissegundo de `clicado_em`, com o restante dos bits tirado do gerador do bloco. O dispositivo de cada clique vem de uma permutação dos índices, cortada nos limites 60/30/5/5, o que dá a proporção exata no total. O `pais` fica vazio, como na aplicação ([SPEC-004](../docs/specs/SPEC-004-aplicacao.md#redirecionamento)).

**Assinatura.** A assinatura é a soma, módulo 2^64, de um hash de 8 bytes de cada clique (`short_code`, `clicado_em` em ms, `clique_id`, `dispositivo`, `referrer`, `pais`). Ela não depende da ordem de leitura. O manifesto guarda a assinatura dos cliques gerados, e a conferência completa calcula a de cada banco a partir das linhas lidas.

## Como os dados ficam em cada banco

| Banco | Dados |
| --- | --- |
| Redis master | Hash `cliente:{id}` com `nome`; Hash `link:{short_code}` com `url`, `cliente_id`, `canal` e `criado_em`; Set `links:cliente:{id}`; `contador:{short_code}` com o total de cliques do link. Os clientes do benchmark ficam fora do Set `clientes` ([ADR-0014](../docs/decisoes/ADR-0014-modelo-de-dados-e-metodo-do-benchmark.md#dados-novos-da-aplicação)) |
| Cassandra | `cliques_por_link`, gravada em lotes `UNLOGGED` de 30 linhas da mesma partição; cada processo mantém até 16 lotes em andamento |
| PostgreSQL | `links`, `contadores` e `cliques` por `COPY`, no modelo do ADR-0014, sem mudar o esquema. Depois, `VACUUM (ANALYZE)` e `CHECKPOINT`, para o autovacuum não rodar no meio das medições |

O Redis recebe as gravações em pipelines de 500 links, com 4 conexões. A carga recusa bancos que já tenham dados; `carregar` recria os volumes de benchmark vazios antes de começar. Antes de terminar o lado NoSQL, a carga espera as compactações do Cassandra ficarem paradas por 30 s, consultando `system_views.thread_pools` e `system_views.sstable_tasks` por CQL. O `nodetool` ficou de fora porque abriria outra JVM dentro do teto de memória do contêiner do Cassandra, e essa JVM herda `MAX_HEAP_SIZE=1G`.

## Volumes e cópia

O [docker-compose.benchmark.yml](../docker-compose.benchmark.yml) entra junto com o [docker-compose.yml](../docker-compose.yml) e troca os volumes do Redis master, da réplica, do Cassandra e do PostgreSQL por volumes próprios do benchmark:

| Banco | Volume de benchmark | Cópia, por geração |
| --- | --- | --- |
| Redis master | `linkpulse-benchmark-redis-master` | `linkpulse-benchmark-copia-{geração}-redis-master` |
| Redis réplica | `linkpulse-benchmark-redis-replica` | `linkpulse-benchmark-copia-{geração}-redis-replica` |
| Cassandra | `linkpulse-benchmark-cassandra` | `linkpulse-benchmark-copia-{geração}-cassandra` |
| PostgreSQL | `linkpulse-benchmark-postgres` | `linkpulse-benchmark-copia-{geração}-postgres` |
| Manifesto da base | `linkpulse-benchmark-manifesto` | `linkpulse-benchmark-copia-{geração}-selo` |

A geração é o instante da cópia (`AAAAmmdd-HHMMSS`). Os comandos só apagam ou sobrescrevem os volumes de benchmark e as cópias. As cópias são escolhidas pelos rótulos `linkpulse.benchmark.geracao` e `linkpulse.benchmark.papel`. Os volumes de desenvolvimento (`linkpulse_*-dados`), o do MongoDB e os de outros projetos ficam intactos. As cópias são volumes do Docker e, por isso, ficam fora do Git. Volume para volume, a cópia roda dentro da VM do Docker, sem passar pelo disco do Windows. Durante a cópia, a geração anterior continua guardada, então é preciso espaço em disco para duas (cerca de 2,8 GB cada).

**Só com os volumes de benchmark.** O `docker-compose.yml` e o `docker-compose.benchmark.yml` usam o mesmo projeto e os mesmos serviços. Por isso, antes de parar qualquer banco, `copiar`, `restaurar` e `conferir` conferem os volumes montados pelos contêineres no ar, além de pegarem a trava. Se algum banco estiver com outro volume, por exemplo os de desenvolvimento depois de um `docker compose up -d --wait`, o comando para sem tocar em nada e pede a parada normal (`docker compose stop`). Já `carregar` troca de modo de propósito: ele remove os contêineres com parada normal, e os volumes de desenvolvimento continuam guardados.

**Copiar** (`copiar`, também no fim de `carregar`):

1. Grava o RDB do Redis com `SAVE`.
2. Para os bancos com prazo de 300 s e confere no log do Cassandra que ele foi drenado: a parada normal grava as memtables em disco.
3. Copia os quatro volumes, em paralelo e com `cp -a`, para uma geração nova, num contêiner da imagem do Redis já usada pelo ambiente.
4. Grava o selo só depois que as quatro cópias terminam bem. O selo leva o manifesto da base (`linkpulse-benchmark-manifesto`), e não o espelho local, e é gravado num arquivo temporário renomeado no fim: ou aparece inteiro, ou não aparece. Se algo falhar antes, a geração incompleta é apagada e a anterior continua valendo.
5. Religa os bancos e apaga as gerações anteriores.

**Restaurar** (`restaurar`):

1. Escolhe a geração mais recente com os quatro volumes e um selo íntegro. Um selo ausente, vazio ou com um manifesto que não passa na validação faz a escolha passar para a geração anterior.
2. Encerra os quatro bancos com `docker compose kill`, porque o estado atual vai ser descartado.
3. Apaga o conteúdo dos volumes de benchmark e copia a geração por cima. Se essa cópia falhar, os bancos ficam parados, para não subirem com dados pela metade, e o comando pede para restaurar de novo.
4. Grava o manifesto do selo em `linkpulse-benchmark-manifesto`. Assim, a janela do histórico e o link popular voltam junto com os dados. Se essa gravação falhar, os bancos ficam parados, para não voltarem com dados e manifesto divergentes, e o comando pede para restaurar de novo.
5. Atualiza o espelho. O espelho não é interpretado, só comparado e sobrescrito: um espelho corrompido ou que não pode ser gravado gera um aviso, mas não impede a subida.
6. Religa tudo com `docker compose up -d --wait`.

O ambiente está pronto para uso quando o `--wait` retorna, com os healthchecks passando. Em seguida, a conferência do CA-1 roda nos próprios bancos. A restauração segue a [SPEC-005](../docs/specs/SPEC-005-testes-de-stress.md#carga-de-dados): os volumes voltam inteiros, sem apagar linhas, para não deixar *tombstones* no Cassandra.

## Conferência (CA-1)

O [conferir.py](conferir.py) consulta os próprios bancos e sai com erro se algo não bater:

- links: chaves `link:*` no Redis e linhas de `links` no PostgreSQL;
- cliques: `COUNT(*)` de cada partição de `cliques_por_link` e `count(*)` por `short_code` em `cliques`, comparados link a link e com o que a semente gera. A lista de partições vem do próprio Cassandra (`SELECT DISTINCT short_code`), e não das chaves do Redis, para um clique fora dos links também entrar no total;
- nenhum clique de link inexistente: partições sem `link:*` no Redis e linhas de `cliques` sem linha em `links`;
- link popular: total e percentual nos dois lados;
- contadores: todos os `contador:*` e todas as linhas de `contadores`, iguais aos cliques de cada link;
- clientes do benchmark no Redis e fora do Set `clientes`;
- com `--completo`: a distribuição de dispositivos e a assinatura dos cliques, lendo todas as linhas dos dois lados.

A partição do link popular, com 2 milhões de linhas, e qualquer partição cujo `COUNT(*)` estoure o tempo são contadas em fatias de um dia, mais uma fatia aberta antes do início e outra depois do fim. Um `COUNT(*)` da partição inteira passa do tempo limite de leitura do servidor (5 s no padrão), e mudar esse limite tiraria o Cassandra da configuração padrão ([ADR-0013](../docs/decisoes/ADR-0013-stack-e-ambiente-do-marco-2.md#decisão)).

## Resultados medidos

Medido em 23/11/2026, no computador de desenvolvimento em uso médio (VM do Docker com 7,6 GiB e 24 CPUs), com os tetos do [ADR-0013](../docs/decisoes/ADR-0013-stack-e-ambiente-do-marco-2.md) e `--processos 4`. São tempos de carga e de restauração. As medições de desempenho do benchmark valem na máquina dedicada da apresentação.

### Carga

| Etapa | Tempo |
| --- | --- |
| Manifesto e assinatura dos 10 milhões de cliques gerados, no host | 17 s |
| Subida dos bancos com os volumes vazios | 75 s |
| Redis: 150 clientes e 45.000 links | 1 s |
| Cassandra: 10 milhões de cliques | 231 s (cerca de 43 mil por segundo, com o Cassandra no teto de 2 CPUs) |
| Cassandra: espera pelas compactações | 30 s (as compactações terminaram durante a inserção) |
| PostgreSQL: 10 milhões de cliques por `COPY` | 30 s |
| PostgreSQL: `VACUUM (ANALYZE)` e `CHECKPOINT` | 5 s |
| Conferência completa (CA-1, dispositivos e assinatura) | 165 s |
| Cópia dos volumes (parada, cópia e subida) | 6 s + 11 s + 22 s |

Três cargas completas, em horários diferentes, deram a mesma assinatura dos cliques (`684a579112df8aa2`) nos dois bancos e no manifesto. Na terceira, já com o manifesto vinculado aos volumes, o Cassandra levou 262 s e teve pico de 1.815 MiB, também sem encerramento por falta de memória. A primeira carga também chegou ao fim; a falha estava na conferência, que tentou contar a partição do link popular de uma vez só (ver [Conferência](#conferência-ca-1)).

Na base carregada, o Cassandra ocupa 300 MB em disco, o PostgreSQL 2,5 GB e cada Redis 7,4 MB.

### Memória durante a carga

Pico observado pelo `docker stats`, amostrado a cada 3 s durante a carga completa (98 amostras):

| Banco | Pico | Teto | % do teto | Encerrado por falta de memória |
| --- | --- | --- | --- | --- |
| `cassandra` | 1.800 MiB | 2.048 MiB | 88% | não |
| `postgres` | 571 MiB | 2.048 MiB | 28% | não |
| `redis-master` | 19 MiB | 2.048 MiB | 1% | não |

O Cassandra coube no teto de 2 GB, então a regra do ADR-0013 (subir o teto dos três bancos juntos) não foi aplicada. Depois das conferências, a memória do processo (`anon` no cgroup) estava em 1.735 MiB. O cache de arquivos ocupa o resto até o teto, e por isso o `memory.peak` do cgroup chega a 2.048 MiB no Cassandra e no PostgreSQL. Esse cache é liberado pelo kernel quando precisa, e o cgroup registrou zero encerramentos por falta de memória (`oom_kill 0`). A folga do processo Java do Cassandra é de cerca de 300 MiB. As pausas de GC sob carga continuam em aberto em Q-38 ([QUESTOES](../docs/requisitos/QUESTOES.md#abertas)).

### Restauração

| Execução | Parada | Cópia | Subida até o `--wait` | Pronto para uso | Conferência do CA-1 |
| --- | --- | --- | --- | --- | --- |
| 1 | 1 s | 7 s | 17 s | 25 s | 43 s, ok |
| 2 | 1 s | 6 s | 17 s | 23 s | 45 s, ok |
| 3, depois de gravar um clique a mais nos dois lados | 1 s | 8 s | 17 s | 26 s | 41 s, ok |
| 4, com cópia por geração, depois de um clique de link inexistente no Cassandra e do manifesto reescrito com outro `--fim` | 1 s | 15 s | 22 s | 38 s | 41 s, ok |
| 5, partindo dos bancos de desenvolvimento parados | 0 s | 10 s | 25 s | 35 s | 41 s, ok |
| 6, com o manifesto vinculado, criando `linkpulse-benchmark-manifesto` a partir do selo | 1 s | 26 s | 29 s | 57 s | ok |
| 7, com `conferir`, `copiar` e `restaurar` disparados durante ela | 1 s | 7 s | 17 s | 26 s | — |
| 8, com uma geração mais nova de selo vazio e o espelho do manifesto cortado no meio | 1 s | 8 s | 22 s | 31 s | ok |
| 9, depois de uma reposição de volumes com falha simulada | 0 s | 10 s | 17 s | 27 s | ok |
| 10, da cópia feita por uma nova carga completa com o manifesto vinculado | 1 s | 13 s | 17 s | 32 s | ok |
| 11, com a trava no Docker, e comandos disparados de outra cópia do repositório durante ela | 1 s | 23 s | 29 s | 54 s | ok |
| 12, com uma geração mais nova cujo selo não tem o campo `clientes` | 1 s | 24 s | 23 s | 50 s | ok |
| 13, depois de uma falha simulada na gravação do manifesto oficial | 0 s | 11 s | 22 s | 34 s | ok |
| 14, com falha simulada só na gravação do espelho | 1 s | 11 s | 22 s | 35 s | ok |

Na terceira, antes de restaurar, a conferência acusou o clique a mais (10.000.001 cliques nos dois lados). Depois da restauração, voltou aos 10.000.000. Na quarta, a conferência acusou o clique de link inexistente, e `conferir` avisou que o manifesto divergia da cópia. A restauração repôs o manifesto e voltou aos 10.000.000. Na quinta, a subida inclui recriar os contêineres com os volumes de benchmark. Na sétima, os três comandos saíram com erro, indicando a restauração que estava com a trava, e nenhum contêiner `carga` foi criado. Na oitava, a geração de selo vazio foi ignorada, e o espelho voltou a ser idêntico ao do Git. A cópia variou de 5 a 26 s com o uso do computador.

Também conferido com o Docker:

- com os bancos de desenvolvimento no ar, `restaurar`, `copiar` e `conferir` saíram com erro, e nenhum banco foi reiniciado;
- uma falha simulada no fim da cópia apagou a geração incompleta e manteve a anterior selada;
- uma geração mais nova sem selo foi ignorada pela restauração;
- com o PostgreSQL parado, `conferir` saiu com erro e não o religou;
- com o espelho reescrito com outro `--fim`, `copiar` selou o manifesto da base (fim em 01/11/2026), e não o do espelho;
- uma reposição de volumes com falha simulada deixou os bancos parados, com a mensagem, e a restauração seguinte recuperou a base;
- durante a restauração 11, `conferir`, `copiar` e `restaurar` de uma segunda cópia do repositório e `conferir` desta foram recusados, indicando o comando, o processo e a pasta com a trava;
- com o processo que segurava a trava encerrado à força (`taskkill /F`), o contêiner da trava sumiu em 1 s, e o comando seguinte pegou a trava;
- com o espelho reescrito com a semente 999 no meio de `carregar --semente 2026`, o volume oficial recebeu a semente 2026 (teste sem tocar nos volumes);
- na restauração 12, a geração com o selo sem `clientes` foi ignorada, e a anterior foi restaurada;
- na falha simulada da restauração 13, os bancos ficaram parados com a mensagem; na 14, os bancos subiram com o aviso.

A subida é quase toda a partida do Cassandra, sem repetição do commit log, porque a cópia foi feita com ele drenado.

### CA-1 conferido

Conferido depois da carga e depois de cada restauração, consultando os bancos:

| Lado | Links | Cliques | Link popular `uGDsIV1` | Percentual |
| --- | --- | --- | --- | --- |
| NoSQL (Redis + Cassandra) | 45.000 | 10.000.000 | 2.000.000 | 20,0000% |
| PostgreSQL | 45.000 | 10.000.000 | 2.000.000 | 20,0000% |

Dispositivos, nos dois lados e lidos linha a linha: 6.000.000 `mobile` (60%), 3.000.000 `desktop` (30%), 500.000 `tablet` (5%) e 500.000 `outro` (5%). Os cliques de cada link batem entre os dois lados e com a semente, e os contadores batem com os cliques.
