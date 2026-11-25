# Benchmark do LinkPulse

O benchmark do LinkPulse compara as mesmas operações no lado NoSQL (Redis e Cassandra) e no PostgreSQL, e a comparação só vale se os dois lados tiverem exatamente os mesmos dados. Esta pasta carrega esses dados, sempre iguais para a mesma semente, nos dois lados: clientes, links e cliques. Depois guarda uma cópia dos volumes dos bancos, para voltar a esse estado antes de cada repetição das medições. A pasta também tem o [gerador de carga](#gerador-de-carga), que mede as quatro operações sobre essa base, o cenário de [queda do Cassandra](#queda-do-cassandra), a [tela de testes](#tela-de-testes) e as [execuções completas](#execução-completa). A base é o passo 1 do plano dos testes de stress ([SPEC-005](../docs/specs/SPEC-005-testes-de-stress.md#plano-de-implementação)), na tarefa de carregar os dados de referência nos dois lados (RM-29). Os dados seguem o modelo e o método do benchmark ([ADR-0014](../docs/decisoes/ADR-0014-modelo-de-dados-e-metodo-do-benchmark.md#dados-e-durações)).

## Como usar

Os comandos rodam no próprio computador, fora dos contêineres, na raiz do repositório, com Python 3.11 ou mais novo e o Docker. O `base.py` só usa a biblioteca padrão do Python. A carga e a conferência rodam no contêiner `carga`, com as bibliotecas fixadas em [requirements.txt](../requirements.txt).

"CA-1" é o primeiro critério de aceitação da SPEC-005: depois da carga e de cada restauração, os dois lados têm os mesmos links e cliques, e o link popular tem 20% dos cliques nos dois.

| Ação | Comando |
| --- | --- |
| Carregar a base do zero, conferir e guardar a cópia | `python benchmark/base.py carregar` |
| Restaurar a cópia e conferir os links, os cliques e os contadores | `python benchmark/base.py restaurar` (`--sem-conferir` pula a conferência) |
| Conferir os dados dos dois lados | `python benchmark/base.py conferir` |
| Conferir também dispositivos e assinatura, lendo todos os cliques | `python benchmark/base.py conferir --completo` |
| Guardar de novo a cópia do estado atual | `python benchmark/base.py copiar` |
| Só reescrever o espelho do manifesto, sem mudar a base carregada | `python benchmark/base.py manifesto` |
| Voltar aos volumes de desenvolvimento | `docker compose up -d --wait` |

`carregar` e `manifesto` aceitam `--semente`, `--fim` (instante final, em ISO 8601 com fuso, como `2026-11-01T00:00:00Z`, entre 2000 e 2100) e `--processos` (padrão 4). Um `--fim` fora dessa regra é recusado antes de qualquer coisa ser gerada, gravada ou apagada. O manifesto gerado também passa pela validação antes de ir para o espelho e, na carga, antes de os volumes serem apagados. Cada `carregar`, `copiar` e `restaurar` grava os tempos e a memória medidos em `benchmark/registros/`, fora do Git.

**Um comando por vez.** `copiar` e `restaurar` deixam os bancos parados enquanto trocam os volumes, e outro comando no meio poderia religá-los. Por isso os comandos `carregar`, `copiar`, `restaurar`, `conferir` e o script de medição usam a mesma trava: um contêiner com nome fixo, `linkpulse-benchmark-trava`, que o Docker não deixa existir duas vezes. Os volumes e o projeto Compose também têm nome fixo, então a trava vale para qualquer cópia do repositório que use o mesmo Docker. Enquanto um comando roda, os outros saem com erro e dizem qual comando, processo e pasta estão com a trava. O contêiner da trava lê a entrada padrão do comando: quando o comando termina ou morre, essa entrada se fecha, o contêiner sai e o Docker o apaga (`--rm`). O script de reserva da queda do Cassandra não usa a trava, porque roda durante a medição (ver [Queda do Cassandra](#queda-do-cassandra)).

Os contêineres que os comandos criam para mexer na base (cópia de volumes, leitura e gravação do manifesto, `carga`) levam o rótulo `linkpulse.benchmark.auxiliar` e podem continuar no Docker depois que o comando morre. Por isso, logo depois de pegar a trava, o comando espera terminar qualquer auxiliar de um comando anterior e avisa quais está esperando. Um auxiliar criado e ainda não iniciado (estado `created`) é removido, sem forçar: se ele começar a rodar no meio da remoção, o Docker recusa e ele passa a ser esperado. Ele é removido porque nenhum comando vivo vai iniciá-lo e o cliente do Docker do comando morto ainda poderia fazer isso no meio da operação. A conferência roda o contêiner `carga` com `--no-deps`, que não sobe os bancos de que ele depende, e recusa bancos parados: ela nunca liga um banco.

## A base

| Item | Valor |
| --- | --- |
| Semente | 2026 |
| Período dos cliques | de 03/08/2026 00:00 UTC a 01/11/2026 00:00 UTC (90 dias) |
| Janela do histórico por período | as últimas 24 horas da base: de 31/10/2026 00:00 UTC a 01/11/2026 00:00 UTC |
| Clientes | 150, de `bench-001` a `bench-150`, com 300 links cada |
| Links | 45.000, com `short_code` de 7 caracteres em Base62 (dígitos e letras maiúsculas e minúsculas), sem `expira_em` |
| Cliques | 10.000.000 |
| Link popular | `uGDsIV1`, com 2.000.000 de cliques (20%) |
| Demais links | 177 ou 178 cliques cada |
| Dispositivo | exatamente 6.000.000 `mobile`, 3.000.000 `desktop`, 500.000 `tablet` e 500.000 `outro` |

O manifesto é o arquivo JSON que descreve a base: guarda esses valores e a assinatura dos cliques. O [gerador de carga](#gerador-de-carga) lê dele o link popular e a janela do histórico. O instante final é um parâmetro fixo e não depende do relógio: carregar em outro dia produz a mesma base.

O manifesto que vale é o da base carregada, no volume `linkpulse-benchmark-manifesto`. Só `carregar` e `restaurar` o gravam, e a carga e a conferência o leem dali. O arquivo [base-de-referencia.json](base-de-referencia.json) é uma cópia dele, o espelho, para leitura e para o Git. `carregar` e `restaurar` atualizam o espelho, e `manifesto` reescreve só o espelho. Se o espelho divergir da base, `conferir` avisa e usa o manifesto da base. Um manifesto só é aceito, no volume e no selo da cópia (ver [Volumes e cópia](#volumes-e-cópia)), se for idêntico ao que a semente e o instante final geram, com uma assinatura de 16 dígitos hexadecimais. Campo faltando, campo a mais ou valor alterado o invalidam, assim como um `fim` que não seja texto com fuso entre 2000 e 2100. A validação nunca lança erro: um manifesto que não passa só é recusado. A carga grava no volume o texto que ela mesma gerou, e não o espelho, que outro comando pode ter reescrito no meio.

**Determinismo.** A geração está em [referencia.py](referencia.py). Os cliques saem em blocos de até 10.000, cada um com o próprio gerador de números aleatórios, iniciado a partir da semente, do link e do número do bloco. Assim, cada processo gera os seus blocos sem depender da ordem, e os 10 milhões de cliques nunca ficam todos em memória. O `clique_id` é um `timeuuid`, o identificador do Cassandra que carrega o instante em que foi criado (um UUID versão 1). Ele é montado com o mesmo milissegundo de `clicado_em`, e o restante dos bits sai do gerador do bloco. Para o dispositivo, uma fórmula fixa dá a cada clique uma posição diferente entre 0 e 10 milhões: os primeiros 60% das posições são `mobile`, os 30% seguintes `desktop` e as duas faixas de 5% `tablet` e `outro`, o que dá a proporção exata no total. O `pais` fica vazio, como na aplicação ([SPEC-004](../docs/specs/SPEC-004-aplicacao.md#redirecionamento)).

**Assinatura.** A assinatura confere que os dois bancos têm exatamente os mesmos cliques sem comparar linha a linha. Cada clique vira um número de 64 bits, um resumo (*hash*) das suas colunas (`short_code`, `clicado_em` em ms, `clique_id`, `dispositivo`, `referrer`, `pais`). A assinatura é a soma desses números, descartando o que passar de 64 bits, e por isso não depende da ordem de leitura. O manifesto guarda a assinatura dos cliques gerados, e a conferência completa calcula a de cada banco a partir das linhas lidas.

## Como os dados ficam em cada banco

| Banco | Dados |
| --- | --- |
| Redis master | Hash `cliente:{id}` com `nome`; Hash `link:{short_code}` com `url`, `cliente_id`, `canal` e `criado_em`; Set `links:cliente:{id}`; `contador:{short_code}` com o total de cliques do link. Os clientes do benchmark ficam fora do Set `clientes` ([ADR-0014](../docs/decisoes/ADR-0014-modelo-de-dados-e-metodo-do-benchmark.md#dados-novos-da-aplicação)) |
| Cassandra | `cliques_por_link`, gravada em lotes de 30 linhas do mesmo link, isto é, da mesma partição (o grupo de linhas que o Cassandra guarda junto, um por `short_code`); cada processo mantém até 16 lotes em andamento. Os lotes são `UNLOGGED`: sem o registro prévio que o Cassandra faz para lotes que atravessam partições, desnecessário aqui |
| PostgreSQL | `links`, `contadores` e `cliques` por `COPY`, o comando de carga em massa do PostgreSQL, no modelo do ADR-0014, sem mudar o esquema. Depois, `VACUUM (ANALYZE)`, que faz a manutenção das tabelas e atualiza as estatísticas do planejador de consultas, e `CHECKPOINT`, que grava no disco tudo o que estava pendente. Assim, a manutenção automática (autovacuum) não roda no meio das medições |

O Redis recebe as gravações em pipelines (vários comandos enviados de uma vez, sem esperar cada resposta) de 500 links, com 4 conexões. A carga recusa bancos que já tenham dados; `carregar` recria os volumes de benchmark vazios antes de começar.

O Cassandra continua trabalhando depois de receber as linhas: ele junta, em segundo plano, os arquivos gravados no disco (compactação). Para isso não acontecer no meio das medições, a carga só termina o lado NoSQL depois de as compactações ficarem paradas por 30 s. Ela consulta as tabelas de sistema `system_views.thread_pools` e `system_views.sstable_tasks` pela linguagem de consulta do Cassandra (CQL). A ferramenta de linha de comando do Cassandra (`nodetool`) ficou de fora porque abriria outro processo Java (uma JVM) dentro do teto de memória do contêiner, e esse processo herdaria o heap de 1 GB (`MAX_HEAP_SIZE=1G`).

## Volumes e cópia

O [docker-compose.benchmark.yml](../docker-compose.benchmark.yml) entra junto com o [docker-compose.yml](../docker-compose.yml) e troca os volumes do Redis master, da réplica, do Cassandra e do PostgreSQL por volumes próprios do benchmark:

| Banco | Volume de benchmark | Cópia, por geração |
| --- | --- | --- |
| Redis master | `linkpulse-benchmark-redis-master` | `linkpulse-benchmark-copia-{geração}-redis-master` |
| Redis réplica | `linkpulse-benchmark-redis-replica` | `linkpulse-benchmark-copia-{geração}-redis-replica` |
| Cassandra | `linkpulse-benchmark-cassandra` | `linkpulse-benchmark-copia-{geração}-cassandra` |
| PostgreSQL | `linkpulse-benchmark-postgres` | `linkpulse-benchmark-copia-{geração}-postgres` |
| Manifesto da base | `linkpulse-benchmark-manifesto` | `linkpulse-benchmark-copia-{geração}-selo` |

A geração é o instante da cópia (`AAAAmmdd-HHMMSS`). Os comandos só apagam ou sobrescrevem os volumes de benchmark e as cópias. As cópias são escolhidas pelos rótulos `linkpulse.benchmark.geracao` e `linkpulse.benchmark.papel`. Os volumes de desenvolvimento (`linkpulse_*-dados`), o do MongoDB e os de outros projetos ficam intactos. As cópias são volumes do Docker e, por isso, ficam fora do Git. Volume para volume, a cópia roda dentro da máquina virtual do Docker, sem passar pelo disco do Windows. Durante a cópia, a geração anterior continua guardada, então é preciso espaço em disco para duas (cerca de 2,8 GB cada).

**Só com os volumes de benchmark.** O `docker-compose.yml` e o `docker-compose.benchmark.yml` usam o mesmo projeto e os mesmos serviços. Por isso, antes de parar qualquer banco, `copiar`, `restaurar` e `conferir` conferem os volumes montados pelos contêineres no ar, além de pegarem a trava. Se algum banco estiver com outro volume, por exemplo os de desenvolvimento depois de um `docker compose up -d --wait`, o comando para sem tocar em nada e pede a parada normal (`docker compose stop`). Já `carregar` troca de modo de propósito: ele remove os contêineres com parada normal, e os volumes de desenvolvimento continuam guardados.

**Copiar** (`copiar`, também no fim de `carregar`):

1. Grava no disco a fotografia da memória do Redis (o arquivo RDB), com `SAVE`, no master e na réplica.
2. Para os bancos com prazo de 300 s e confere no log do Cassandra que ele foi drenado: na parada normal, ele grava no disco os dados que ainda estavam só na memória (as memtables).
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

O ambiente está pronto para uso quando o `--wait` retorna, com as verificações de saúde (healthchecks) dos contêineres passando. Em seguida, a conferência do CA-1 roda nos próprios bancos. A restauração segue a [SPEC-005](../docs/specs/SPEC-005-testes-de-stress.md#carga-de-dados): os volumes voltam inteiros, sem apagar linhas. No Cassandra, apagar linhas deixa marcas de exclusão (*tombstones*) que deixariam as leituras seguintes mais lentas só nesse lado.

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

Medido em 23/11/2026, no computador de desenvolvimento em uso médio (máquina virtual do Docker com 7,6 GiB e 24 CPUs), com os tetos do [ADR-0013](../docs/decisoes/ADR-0013-stack-e-ambiente-do-marco-2.md) e `--processos 4`. São tempos de carga e de restauração. As medições de desempenho do benchmark valem na máquina dedicada da apresentação.

### Carga

| Etapa | Tempo |
| --- | --- |
| Manifesto e assinatura dos 10 milhões de cliques gerados, no computador, fora dos contêineres | 17 s |
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

Pico observado pelo `docker stats` durante a carga completa, com uma amostra a cada 3 s, mais ou menos (98 amostras). O intervalo pedido é de 1 s, mas cada chamada ao `docker stats` leva cerca de 2 s.

| Banco | Pico | Teto | % do teto | Encerrado por falta de memória |
| --- | --- | --- | --- | --- |
| `cassandra` | 1.800 MiB | 2.048 MiB | 88% | não |
| `postgres` | 571 MiB | 2.048 MiB | 28% | não |
| `redis-master` | 19 MiB | 2.048 MiB | 1% | não |

O Cassandra coube no teto de 2 GB, então a regra do ADR-0013 (subir o teto dos três bancos juntos) não foi aplicada. O teto de cada contêiner é aplicado pelo Linux por meio de um cgroup, o grupo de controle de recursos, que também registra o uso. Depois das conferências, a memória do próprio processo (`anon` no cgroup) estava em 1.735 MiB. O cache de arquivos ocupa o resto até o teto, e por isso o pico registrado pelo cgroup (`memory.peak`) chega a 2.048 MiB no Cassandra e no PostgreSQL. Esse cache é liberado pelo sistema quando precisa, e o cgroup registrou zero encerramentos por falta de memória (`oom_kill 0`). A folga do processo Java do Cassandra é de cerca de 300 MiB. As pausas da coleta de lixo do Java (GC) sob carga continuam em aberto, na questão sobre como aplicar o teto de CPU sem penalizar um dos bancos (Q-38 em [QUESTOES](../docs/requisitos/QUESTOES.md#abertas)).

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
| 15, com duas gerações mais novas, de `fim` nulo e de `fim` no ano 1 | 1 s | 25 s | 30 s | 58 s | ok |
| 16, depois dos testes de auxiliares em `created` | 1 s | 27 s | 29 s | 58 s | ok |

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
- na falha simulada da restauração 13, os bancos ficaram parados com a mensagem; na 14, os bancos subiram com o aviso;
- com o processo que segurava a trava encerrado à força enquanto um auxiliar `copiar-volumes` ainda rodava, a trava foi solta, mas o comando seguinte avisou e esperou: pelos eventos do Docker, o auxiliar terminou às 18:42:06 e o `conferir` só começou às 18:42:09;
- na restauração 15, as duas gerações com `fim` inválido foram ignoradas com aviso, e a geração íntegra foi restaurada;
- `carregar --fim 1999-11-01T00:00:00Z`, `carregar --fim 2026-11-01T00:00:00` (sem fuso) e `manifesto --fim 1999-11-01T00:00:00Z` saíram com erro na leitura dos argumentos: os bancos não reiniciaram e os volumes e o espelho ficaram iguais;
- um auxiliar rotulado criado com `docker create` e não iniciado foi removido pelo comando seguinte: pelos eventos do Docker, ele só teve `create` e `destroy`. Com um auxiliar rodando e outro em `created` ao mesmo tempo, o comando removeu o segundo, esperou o primeiro e só então começou.

A subida é quase toda a partida do Cassandra. Ela não precisa reaplicar o registro de escritas recentes (o commit log), porque a cópia foi feita com o Cassandra drenado.

### CA-1 conferido

Conferido depois da carga e depois de cada restauração, consultando os bancos:

| Lado | Links | Cliques | Link popular `uGDsIV1` | Percentual |
| --- | --- | --- | --- | --- |
| NoSQL (Redis + Cassandra) | 45.000 | 10.000.000 | 2.000.000 | 20,0000% |
| PostgreSQL | 45.000 | 10.000.000 | 2.000.000 | 20,0000% |

Dispositivos, nos dois lados e lidos linha a linha: 6.000.000 `mobile` (60%), 3.000.000 `desktop` (30%), 500.000 `tablet` (5%) e 500.000 `outro` (5%). Os cliques de cada link batem entre os dois lados e com a semente, e os contadores batem com os cliques.

## Gerador de carga

O gerador mede as quatro operações do produto nos dois lados, em laço fechado: um número fixo de conexões, e cada uma só envia a próxima operação quando a anterior responde ([ADR-0014](../docs/decisoes/ADR-0014-modelo-de-dados-e-metodo-do-benchmark.md#como-a-carga-é-aplicada)). O gerador mede a leitura do link, o incremento do contador, a gravação de clique, a consulta ao histórico e o [pico de tráfego](#pico-de-tráfego), as etapas 1 a 5 da sequência de testes. A [calibração](#calibração) escolheu o número de conexões. A [queda do Cassandra](#queda-do-cassandra), a etapa 6, passa pela aplicação, em laço aberto. A [tela de testes](#tela-de-testes) roda a sequência ao vivo e abre as [execuções completas](#execução-completa) gravadas.

| Ação | Comando |
| --- | --- |
| Restaurar a base e medir a sequência de testes: as quatro operações e o pico nos dois lados, e a queda do Cassandra | `python benchmark/medir.py` |
| Restaurar a base e medir só o pico de tráfego | `python benchmark/medir.py --operacoes pico` |
| Restaurar a base e medir só a queda do Cassandra | `python benchmark/medir.py --operacoes queda` |
| Medir só algumas operações ou um lado, com outras durações | `python benchmark/medir.py --operacoes contador registro --lados postgres --duracao 20 --aquecimento 5` |
| Medir sobre o estado atual, sem restaurar em momento nenhum, nem antes do histórico | `python benchmark/medir.py --sem-restaurar` |
| Rodar também a curva extra do PostgreSQL, com `synchronous_commit=off`, no contador e no registro de clique | `python benchmark/medir.py --curva-extra contador registro` |
| Rodar a sequência ao vivo da tela de testes, pelo terminal | `python benchmark/medir.py --ao-vivo` |
| Rodar a execução completa e gravá-la em `benchmark/gravacoes/` | `python benchmark/medir.py --completa` |
| Abrir a tela de testes | `python benchmark/tela.py` e `http://127.0.0.1:8002` |
| Calibrar: medir as quatro operações com 8, 32 e 64 conexões e escolher o número | `python benchmark/calibrar.py` |

`--conexoes` vale 8 por padrão, o número escolhido pela calibração. Se uma nova calibração escolher outro número, passe-o em toda medição, como em `python benchmark/medir.py --conexoes 32`. `--duracao` (60 s) e `--aquecimento` (10 s) seguem a execução completa. `--processos` muda o número de processos do gerador, que por padrão é um por conexão.

O [medir.py](medir.py) roda no computador, como o `base.py`, e pega a mesma trava: nenhum comando da base roda no meio de uma medição. Por padrão, ele restaura a base antes de começar e de novo antes do histórico por período e antes do pico, se uma escrita rodou desde a última restauração ([SPEC-005](../docs/specs/SPEC-005-testes-de-stress.md#sequência-de-testes)). As etapas seguem a ordem da sequência de testes, um lado de cada vez. Cada execução é um contêiner `gerador` (8 CPUs, 3 GB), que roda o [gerador.py](gerador.py). Na janela medida, o `medir.py` lê também a CPU de cada banco que a etapa exercita, com os bancos lidos em paralelo. O resultado vai para `benchmark/registros/`, fora do Git, e o resumo sai em tabela no fim. O [calibrar.py](calibrar.py) repete as quatro operações isoladas, com as mesmas restaurações, para cada número de conexões; o pico não entra na calibração.

### O que cada operação executa

| Operação | NoSQL | PostgreSQL |
| --- | --- | --- |
| Redirecionamento | `HGETALL link:{short_code}` no Redis master | `SELECT` das colunas de `links` pela chave |
| Contador | `INCR contador:{short_code}` no Redis master | `UPDATE contadores SET total = total + 1` pela chave |
| Registro de clique | `INSERT` em `cliques_por_link` no Cassandra | `INSERT` em `cliques` |
| Histórico por período | `SELECT` em `cliques_por_link` na janela do manifesto, `LIMIT 1000` | o mesmo em `cliques`, `ORDER BY clicado_em DESC, clique_id DESC LIMIT 1000` |
| Pico de tráfego | redirecionamento, contador e registro em sequência, no link popular | os mesmos três comandos, na mesma ordem, no link popular |

- **Link de cada chamada:** 20% caem no link popular do manifesto, e o resto se divide por igual entre os outros 44.999 links, com um sorteio de semente fixa por conexão.
- **Clique gravado:** instante atual, `clique_id` `timeuuid` do mesmo instante, `pais` vazio, dispositivo e referrer na mesma proporção da base. Os instantes ficam depois da janela do histórico.
- **Redis no master,** o banco que tem o mesmo teto dos outros dois.
- **Comandos preparados:** `prepare` no Cassandra e `prepare=True` no PostgreSQL. O Redis não tem comando preparado.
- **Curva extra:** com `--curva-extra`, o contador e o registro de clique rodam uma segunda vez no PostgreSQL, com `SET synchronous_commit = off` em cada conexão do gerador, só na sessão. A configuração do servidor continua a padrão, e o gerador confere com `SHOW synchronous_commit` que a sessão aceitou o valor. O resultado fica com `curva_extra: true` e aparece como "PostgreSQL, synchronous_commit=off (fora do padrão)" (ADR-0014, Q-73).
- **Conexões:** um processo por conexão, com uma thread cada, para as conexões não disputarem o interpretador do Python (ver [Calibração](#calibração)). Cada thread tem a sua conexão e uma operação pendente nela. No Cassandra, cada conexão é um `Cluster` próprio do driver, com uma conexão de dados com o nó e outra de controle, quase parada. Durante um histórico com 8 conexões, `system_views.clients` mostrou 8 conexões de dados, com cerca de 3.000 pedidos cada, e 8 de controle, com 5.

### Métricas

| Métrica | Como é calculada |
| --- | --- |
| Vazão | operações concluídas sem erro nos segundos medidos, divididas pela duração |
| p50, p95 e p99 | percentis por posição (nearest-rank) das latências sem erro, em ms |
| Sucessos e erros | operações medidas que terminaram sem erro e com erro. No pico, contados por operação |
| Taxa de erro | erros divididos pelo total de operações medidas. Exceção do driver, link sem dados no redirecionamento e contador ausente contam como erro. Sem nenhuma tentativa na janela, a taxa é indefinida (`null`, mostrada como `—`) |
| CPU do gerador | `usage_usec` do cgroup do contêiner, de `cpu.stat`, na janela medida, dividido pelo tempo: dá os núcleos usados. Dividido também pelas CPUs do limite (`cpu.max`), dá o percentual da cota, registrado arredondado em `cpu_gerador_pct` e sem arredondamento em `cpu_gerador_pct_exato` |
| CPU do banco | o mesmo cálculo em cada contêiner de banco exercitado (Redis master, Cassandra ou PostgreSQL; no pico do lado NoSQL, o Redis master e o Cassandra), lido pelo `medir.py` com `docker exec` no início e no fim da janela, que o gerador marca na saída. Fica em `cpu_bancos`, por banco |
| Memória do gerador | pico do cgroup do contêiner (`memory.peak`), da partida ao fim da execução |
| Série por segundo | em `serie`, uma linha por segundo desde a partida, aquecimento incluído: por operação, as operações concluídas naquele segundo, os erros e o p95. Conta pela hora de conclusão, e por isso só ilustra: o placar usa as métricas acima |
| CPU e memória dos bancos por segundo | em `serie_recursos`, lidas pelo `medir.py` com `docker exec` a cada segundo desde a partida: CPU em % do teto (`cpu.stat` e `cpu.max`) e memória em uso do contêiner (`memory.current`, que inclui o cache de arquivos) |

As operações que começam no aquecimento são descartadas, e só entram as que começam dentro da janela medida.

**Custo da `serie_recursos`.** A leitura por segundo roda dentro da janela medida e entra nos números. Cada `docker exec` gasta de 14 a 19 ms de CPU no cgroup do banco, cerca de 1,5 a 2% de um núcleo. Em 25/11/2026, com 8 conexões, 5 s de aquecimento e 30 s medidos, em 3 pares alternados com e sem a série, a maior diferença na mediana foi de −2,2% na vazão do redirecionamento no PostgreSQL, com o banco no teto de CPU. No redirecionamento no Redis e no histórico nos dois lados, a diferença ficou entre −1,1% e +1,5%, dentro da variação entre execuções. O custo vale para os dois lados, e a série fica nas execuções oficiais porque as curvas das gravações dependem dela (Q-71, Q-74).

### Execução de desenvolvimento

Medido em 24/11/2026, antes da calibração, no computador de desenvolvimento (o mesmo das [medições da base](#resultados-medidos)), com o gerador em 4 CPUs e 1 GB, em 4 processos de 2 threads, com 8 conexões, 10 s de aquecimento e 60 s medidos por lado. A base foi restaurada antes do redirecionamento e antes do histórico, com o CA-1 conferido nas duas vezes. As duas linhas do Cassandra são de uma segunda execução, com uma conexão de dados por conexão pedida, também com a base restaurada antes de cada operação. Essas medições de desenvolvimento confirmam que o gerador produz as métricas das quatro operações nos dois lados. A comparação para a apresentação depende da calibração e das repetições na máquina dedicada.

| Operação | Lado | Operações | Vazão (ops/s) | p50 (ms) | p95 (ms) | p99 (ms) | Taxa de erro | CPU do gerador |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Redirecionamento | NoSQL | 2.255.384 | 37.590 | 0,176 | 0,347 | 0,508 | 0% | 99,7% |
| Redirecionamento | PostgreSQL | 1.822.851 | 30.381 | 0,189 | 0,326 | 0,461 | 0% | 91,7% |
| Contador | NoSQL | 2.504.306 | 41.738 | 0,166 | 0,307 | 0,468 | 0% | 99,1% |
| Contador | PostgreSQL | 70.282 | 1.171 | 4,243 | 20,373 | 35,861 | 0% | 3,4% |
| Registro de clique | NoSQL | 464.235 | 7.737 | 0,817 | 1,406 | 3,228 | 0% | 81,6% |
| Registro de clique | PostgreSQL | 220.950 | 3.682 | 1,209 | 4,433 | 5,549 | 0% | 11,8% |
| Histórico por período | NoSQL | 126.708 | 2.112 | 1,467 | 12,129 | 31,203 | 0% | 68,8% |
| Histórico por período | PostgreSQL | 528.065 | 8.801 | 0,244 | 2,136 | 4,748 | 0% | 71,6% |

**CPU do gerador acima de 70% com 8 conexões.** Nos dois lados do redirecionamento, no contador do Redis, no registro no Cassandra e no histórico no PostgreSQL, o gerador passou de 70% do seu limite já com 8 conexões. Nessas cinco medições, o gerador pode ter limitado a carga enviada aos bancos. A [calibração](#calibração) mudou a configuração do gerador e ficou abaixo de 70% com 8 conexões.

### Calibração

Passo 3 do [plano de testes](../docs/specs/SPEC-005-testes-de-stress.md#plano-de-implementação) (RM-42). O gerador mede as quatro operações nos dois lados com 8, 32 e 64 conexões, e vale o maior número em que ele fica abaixo de 70% da sua cota de CPU em todas as combinações ([ADR-0014](../docs/decisoes/ADR-0014-modelo-de-dados-e-metodo-do-benchmark.md#como-a-carga-é-aplicada)). Se alguma combinação chegasse a 70% já com 8 conexões, o `calibrar.py` pararia ali, e a regra do [ADR-0013](../docs/decisoes/ADR-0013-stack-e-ambiente-do-marco-2.md#decisão) indicaria reescrever o laço de disparo em Rust.

**Regra de decisão.** A comparação com os 70% usa o percentual sem arredondamento (`cpu_gerador_pct_exato`); o arredondado serve só para exibição. Uma execução sem nenhuma operação concluída ou com algum erro é inválida, porque a CPU do gerador nela não mede a carga. Um nível com execução inválida não é aprovado nem reprovado por CPU: a calibração para nele, lista as combinações inválidas e não indica a reescrita. O registro guarda o `motivo` de cada nível: `aprovado`, `cpu_acima_do_teto`, `medicao_invalida` ou `interrompido`, quando um comando falhou no meio do nível. A `escolha` só é gravada quando a calibração termina sem falha de comando e sem medição inválida; nos outros casos fica `null`, e as medições já feitas continuam no registro. O `calibrar.py` sai com 0 quando grava a escolha, 1 quando um comando falha, 2 quando o nível de 8 conexões chega a 70% e 3 quando há medição inválida.

**Resultado: 8 conexões, com o gerador em Python.** Com 8 conexões, o maior uso foi 50,3% da cota (4,02 núcleos), no registro de clique no Cassandra. Com 32, o registro de clique no Cassandra chegou a 80,6%. Com 64, o redirecionamento no Redis chegou a 75,3% e o registro de clique no Cassandra, a 91,7%. Como nenhuma combinação passou de 70% com 8 conexões, a reescrita em Rust não foi necessária. O mesmo número vale para os dois lados e para as quatro operações.

**Alcance do CA-3.** Com 8 conexões, as quatro operações isoladas rodaram um lado de cada vez, com os mesmos tetos, e o uso de CPU do gerador ficou registrado e abaixo de 70% da cota em todas: o CA-3 da [SPEC-005](../docs/specs/SPEC-005-testes-de-stress.md#critérios-de-aceitação) foi conferido nelas. No pico de tráfego (etapa 5), ele foi conferido na [execução do pico](#pico-de-tráfego).

**Configuração adotada.** O gerador tem 8 CPUs e 3 GB, com um processo por conexão. Os bancos comparados continuam com 2 CPUs e 2 GB cada. Com 4 CPUs e 4 processos de 2 threads, a primeira versão chegou a 99,8% da cota no redirecionamento no Redis. Com 8 processos de 1 thread, a vazão subiu 32%, porque as threads do mesmo processo disputavam o interpretador do Python ([análise na issue #47](https://github.com/BudaBecker/link-pulse/issues/47)).

**Memória.** Cada processo carrega os drivers dos três bancos, cerca de 52 MB antes de abrir a conexão. Com 64 conexões, o pico do gerador ficou entre 2.438 e 3.056 MiB, acima do 1 GB anterior. As alternativas eram distribuir as conexões em menos processos, com threads, ou dar mais memória ao gerador. A memória subiu para 3 GB. Com threads, as conexões voltariam a disputar o interpretador, e isso aumentaria a CPU do gerador nos níveis de 32 e 64, justamente os testados. A máquina virtual do Docker tem 7,6 GiB. Numa sondagem com 64 conexões, o `docker stats` mostrou os bancos com cerca de 2,2 GiB: o Cassandra com 1,87 GiB, o MongoDB com 0,23 GiB e cada um dos outros com menos de 0,1 GiB. O gerador cabe no que sobra. No histórico por período no Cassandra com 64 conexões, o pico de 3.056 MiB encostou no teto de 3.072 MiB, sem encerramento por falta de memória. Com as 8 conexões escolhidas, o pico ficou entre 352 e 448 MiB.

**Máquina.** As cotas somam 15 CPUs: 8 do gerador, 2 de cada banco comparado e 1 da réplica. A calibração mediu um banco por vez: no computador de desenvolvimento, de 24 CPUs, o gerador e o banco medido usaram no máximo 9,2 núcleos ao mesmo tempo. O número de núcleos da máquina da apresentação ainda precisa ser conferido.

#### Medições

Medido em 24/11/2026, das 11h03 às 11h43 (horário de Brasília), no computador de desenvolvimento, com 10 s de aquecimento e 60 s medidos por lado. A base foi restaurada antes de cada número de conexões e antes de cada histórico por período, seis vezes ao todo, com o CA-1 conferido em todas. Nenhuma das 24 execuções teve erro. A CPU do banco aparece em núcleos e, entre parênteses, em percentual do teto de 2 CPUs. Valores em negrito estão em 70% da cota ou acima.

| Conexões | Operação | Banco | Vazão (ops/s) | p95 (ms) | Erros | CPU do gerador (núcleos) | CPU do gerador (% da cota de 8) | CPU do banco (núcleos) | Pico de memória do gerador (MiB) |
| ---: | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 8 | Redirecionamento | Redis | 49.133 | 0,251 | 0% | 4,00 | 50,0% | 1,00 (50%) | 448 |
| 8 | Redirecionamento | PostgreSQL | 27.179 | 0,274 | 0% | 2,82 | 35,3% | 2,00 (100%) | 393 |
| 8 | Contador | Redis | 43.332 | 0,267 | 0% | 2,95 | 36,9% | 1,00 (50%) | 422 |
| 8 | Contador | PostgreSQL | 2.497 | 9,971 | 0% | 0,26 | 3,3% | 0,43 (22%) | 352 |
| 8 | Registro de clique | Cassandra | 7.764 | 1,120 | 0% | 4,02 | 50,3% | 2,00 (100%) | 367 |
| 8 | Registro de clique | PostgreSQL | 3.363 | 4,470 | 0% | 0,43 | 5,4% | 0,53 (27%) | 354 |
| 8 | Histórico por período | Cassandra | 1.992 | 12,392 | 0% | 3,05 | 38,1% | 2,00 (100%) | 445 |
| 8 | Histórico por período | PostgreSQL | 7.129 | 2,148 | 0% | 2,73 | 34,1% | 2,00 (100%) | 362 |
| 32 | Redirecionamento | Redis | 53.636 | 0,770 | 0% | 4,80 | 60,0% | 1,00 (50%) | 1.326 |
| 32 | Redirecionamento | PostgreSQL | 47.218 | 0,345 | 0% | 2,91 | 36,4% | 2,00 (100%) | 1.288 |
| 32 | Contador | Redis | 51.624 | 0,786 | 0% | 4,02 | 50,3% | 1,00 (50%) | 1.309 |
| 32 | Contador | PostgreSQL | 1.223 | 164,067 | 0% | 0,13 | 1,7% | 0,42 (21%) | 1.245 |
| 32 | Registro de clique | Cassandra | 9.734 | 3,786 | 0% | 6,44 | **80,6%** | 1,99 (100%) | 1.284 |
| 32 | Registro de clique | PostgreSQL | 10.296 | 5,124 | 0% | 1,99 | 24,8% | 1,58 (79%) | 1.264 |
| 32 | Histórico por período | Cassandra | 2.004 | 78,757 | 0% | 4,26 | 53,2% | 1,99 (100%) | 1.570 |
| 32 | Histórico por período | PostgreSQL | 6.712 | 12,496 | 0% | 2,67 | 33,4% | 2,00 (100%) | 1.278 |
| 64 | Redirecionamento | Redis | 49.296 | 1,638 | 0% | 6,02 | **75,3%** | 1,00 (50%) | 2.502 |
| 64 | Redirecionamento | PostgreSQL | 40.413 | 1,091 | 0% | 3,22 | 40,2% | 2,00 (100%) | 2.483 |
| 64 | Contador | Redis | 48.808 | 1,667 | 0% | 5,16 | 64,5% | 1,00 (50%) | 2.491 |
| 64 | Contador | PostgreSQL | 1.681 | 217,227 | 0% | 0,21 | 2,6% | 0,98 (49%) | 2.438 |
| 64 | Registro de clique | Cassandra | 8.734 | 59,759 | 0% | 7,34 | **91,7%** | 1,86 (93%) | 2.496 |
| 64 | Registro de clique | PostgreSQL | 11.232 | 8,580 | 0% | 2,90 | 36,2% | 1,97 (99%) | 2.458 |
| 64 | Histórico por período | Cassandra | 2.008 | 92,914 | 0% | 4,44 | 55,6% | 2,00 (100%) | 3.056 |
| 64 | Histórico por período | PostgreSQL | 6.043 | 87,011 | 0% | 2,58 | 32,3% | 2,00 (100%) | 2.501 |

#### Leitura

- **Com 8 conexões, o gerador ficou abaixo do limite da regra.** Ele usou no máximo 4,02 dos seus 8 núcleos (50,3%). O Cassandra e o PostgreSQL ficaram em 2,00 núcleos, o teto, nas leituras, e o Cassandra também no registro de clique. O Redis executa os comandos em uma thread só e ficou em 1,00 núcleo, metade do seu teto de 2 CPUs. Nas duas escritas do PostgreSQL, o banco e o gerador usaram pouca CPU (o banco, até 0,53 núcleo): as conexões passaram a maior parte do tempo esperando, e a CPU não mostra o quê. Uma hipótese, não medida, é a gravação em disco que o PostgreSQL faz antes de cada confirmação (`fsync`, ver [Garantia de gravação](../docs/decisoes/ADR-0014-modelo-de-dados-e-metodo-do-benchmark.md#garantia-de-gravação)).
- **Com mais conexões, a vazão parou de crescer em parte dos casos.** O redirecionamento no Redis subiu 9% de 8 para 32 conexões e voltou a 49 mil ops/s com 64, e o histórico no Cassandra ficou em 2 mil ops/s nos três níveis; nesses dois casos, as conexões a mais aumentaram sobretudo o p95. Já o redirecionamento no PostgreSQL subiu de 27.179 para 47.218 ops/s (+74%) de 8 para 32 conexões, com o banco a 100% da cota nos dois níveis, e caiu para 40.413 com 64. A CPU do banco no teto, sozinha, não indica que a vazão parou de crescer.
- **O registro de clique no Cassandra é o que mais pesa no gerador.** Com 8 conexões, o driver do Cassandra gastou cerca de 0,5 ms de CPU do gerador por gravação, contra 0,08 ms por leitura no Redis. Com 32 conexões, o gerador usou 6,44 núcleos para 9,7 mil ops/s, e o Cassandra continuou em 2 núcleos.
- **As escritas do PostgreSQL mudam com mais conexões.** O registro de clique foi de 3,4 mil para 10,3 mil ops/s com 32 conexões, e o contador caiu de 2,5 mil para 1,2 mil ops/s, com p95 de 164 ms. Nos dois casos o banco ficou abaixo do teto de CPU (79% e 21%), e os dados de CPU não identificam a espera. As hipóteses, não medidas, são um mesmo `fsync` gravar as confirmações de várias transações no registro e as conexões esperarem pelo bloqueio da linha do link popular, que recebe 20% das chamadas, no contador. Nenhum dos dois efeitos entra na comparação, que usa 8 conexões.
- **Medição de desenvolvimento.** Estes números são do computador de desenvolvimento, com outros programas abertos. A calibração precisa ser repetida na máquina da apresentação, com `python benchmark/calibrar.py`, antes das execuções completas.

### Pico de tráfego

Passo 4 do [plano de testes](../docs/specs/SPEC-005-testes-de-stress.md#plano-de-implementação) (RM-43). Leitura do link, incremento do contador e registro de clique rodam ao mesmo tempo, todos no link popular, um lado de cada vez. Cada conexão repete as três operações em sequência, na ordem de um clique no produto, e a latência é medida por operação (Q-39 em [QUESTOES](../docs/requisitos/QUESTOES.md#respondidas)). A mistura fica em 1:1:1 nos dois lados, e cada conexão tem no máximo uma operação pendente. No lado NoSQL, cada conexão abre uma conexão com o Redis master e outra com o Cassandra; no PostgreSQL, uma só. Como as três operações de uma conexão se alternam, a vazão é praticamente a mesma nas três: ela mede quantos cliques completos por segundo o lado aguenta. A latência de cada operação mostra onde está a demora.

**Estado dos dados.** Na sequência de testes, o pico roda depois do histórico por período, que só lê, e por isso parte do estado restaurado antes do histórico. Nesse caso, o `medir.py` não restaura de novo antes do pico. Numa seleção sem o histórico, como `--operacoes registro pico`, ele restaura antes do pico, porque o registro acrescentou cliques em cada lado na vazão do próprio lado. Medido sozinho, com `python benchmark/medir.py --operacoes pico`, o pico restaura a cópia antes de começar e parte do mesmo estado. Cada lado escreve só nos próprios bancos, então a ordem dos lados não muda o estado que o outro encontra.

**Comando reproduzível.** `python benchmark/medir.py` mede as etapas 1 a 5 nos dois lados, com 8 conexões, 10 s de aquecimento e 60 s medidos por lado, restaurando a base antes do redirecionamento e antes do histórico, e depois a [queda do Cassandra](#queda-do-cassandra). Em outra máquina, passe o número da calibração dela, como em `python benchmark/medir.py --conexoes 32`. O registro fica em `benchmark/registros/`, e o pico aparece com `operacao: "pico"` e as métricas de cada operação em `por_operacao`.

#### Medições

Medido em 24/11/2026, das 14h44 às 14h58 (horário de Brasília), no computador de desenvolvimento, com `python benchmark/medir.py`: as etapas 1 a 5, com 8 conexões em 8 processos, 10 s de aquecimento e 60 s medidos por lado. A base foi restaurada antes do redirecionamento e antes do histórico, com o CA-1 conferido nas duas vezes. O pico rodou depois do histórico, sem nova restauração. Os tetos conferidos com `docker inspect` foram 2 CPUs e 2 GiB no Redis master, no Cassandra e no PostgreSQL, e o gerador ficou com 8 CPUs.

| Lado | Operação | Vazão (ops/s) | p50 (ms) | p95 (ms) | p99 (ms) | Sucessos | Erros | Taxa de erro |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| NoSQL | Redirecionamento (Redis) | 6.216 | 0,209 | 0,382 | 0,534 | 372.929 | 0 | 0% |
| NoSQL | Contador (Redis) | 6.215 | 0,191 | 0,338 | 0,454 | 372.927 | 0 | 0% |
| NoSQL | Registro de clique (Cassandra) | 6.216 | 0,742 | 1,017 | 1,311 | 372.929 | 0 | 0% |
| PostgreSQL | Redirecionamento | 322 | 0,198 | 0,293 | 0,416 | 19.331 | 0 | 0% |
| PostgreSQL | Contador | 322 | 15,291 | 52,634 | 81,938 | 19.331 | 0 | 0% |
| PostgreSQL | Registro de clique | 322 | 3,958 | 4,563 | 6,207 | 19.331 | 0 | 0% |

CPU na mesma janela de 60 s, em núcleos e em percentual da cota de cada contêiner:

| Lado | Início (UTC) | Gerador (cota de 8) | Redis master (teto de 2) | Cassandra (teto de 2) | PostgreSQL (teto de 2) | Pico de memória do gerador (MiB) |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| NoSQL | 17:56:26 | 5,00 (62,5%) | 0,58 (29,1%) | 1,92 (96,1%) | — | 389 |
| PostgreSQL | 17:57:41 | 0,13 (1,7%) | — | — | 0,20 (9,9%) | 352 |

A comparação com os 70% usa o percentual sem arredondamento: 62,497% no lado NoSQL e 1,679% no PostgreSQL. Na mesma execução, as quatro operações isoladas também ficaram abaixo de 70%, com o máximo de 52,2% no redirecionamento no Redis, e nenhuma das dez execuções teve erro.

#### Critérios conferidos

- **CA-5:** no lado NoSQL, as três operações executaram e nenhuma teve erro: 372.929 leituras, 372.927 incrementos e 372.929 registros, com 0 erros em cada uma.
- **CA-3 no pico:** os lados rodaram um depois do outro, cada um no seu contêiner `gerador` (o NoSQL a partir das 17:56:26 e o PostgreSQL a partir das 17:57:41, em UTC), com as mesmas 8 conexões e os mesmos tetos de 2 CPUs e 2 GiB nos bancos. A CPU do gerador ficou registrada e abaixo de 70% da cota nos dois lados: 62,5% e 1,7%.

#### Leitura

- **O lado NoSQL completou 19 vezes mais cliques por segundo** que o PostgreSQL: 6.216 contra 322. No PostgreSQL, o contador tem p50 de 15 ms e p99 de 82 ms. As 8 conexões atualizam a mesma linha de `contadores`, e cada `UPDATE` espera o bloqueio da linha, que só é solto quando a transação anterior confirma. Com o banco a 9,9% do teto de CPU, as conexões passam quase todo o tempo esperando. O bloqueio é a explicação provável, ainda não medida; a gravação em disco a cada confirmação (`fsync`) pode somar.
- **No lado NoSQL, o Cassandra limita o ciclo.** Ele ficou a 96% do teto, e o registro de clique responde em 0,74 ms, contra cerca de 0,2 ms em cada operação do Redis. O Redis ficou a 29% do teto.
- **O gerador ficou mais perto do teto no pico** do que nas operações isoladas: 62,5% da cota, por causa do driver do Cassandra, que é o que mais pesa no gerador (ver [Calibração](#calibração)). Na máquina da apresentação, confira essa margem depois de calibrar.
- **O redirecionamento continua rápido nos dois lados.** No PostgreSQL, a leitura do link não espera o bloqueio do contador: o p95 ficou em 0,29 ms.
- **Medição de desenvolvimento.** Os números são de uma execução no computador de desenvolvimento, com outros programas abertos. A comparação para a apresentação depende das 3 repetições na máquina dedicada (CA-4).

### Queda do Cassandra

Passo 5 do [plano de testes](../docs/specs/SPEC-005-testes-de-stress.md#plano-de-implementação) (RM-44), a etapa 6 da sequência de testes. É a única etapa que passa pela aplicação: 200 redirecionamentos por segundo, em laço aberto, durante 90 s. O Cassandra para aos 30 s e volta aos 60 s, de forma automática ([ADR-0014](../docs/decisoes/ADR-0014-modelo-de-dados-e-metodo-do-benchmark.md#como-a-carga-é-aplicada)). O cenário mede se o redirecionamento continua respondendo `302` rápido com o Cassandra fora (RNF-01, RNF-02), se o contador continua somando e quantos cliques se perdem (RN-07). As decisões de método são as questões Q-62 a Q-68 em [QUESTOES](../docs/requisitos/QUESTOES.md#respondidas).

| Ação | Comando |
| --- | --- |
| Restaurar a base e medir a queda | `python benchmark/medir.py --operacoes queda` |
| Medir a queda sobre o estado atual da base | `python benchmark/medir.py --operacoes queda --sem-restaurar` |
| Medir parando e religando o Cassandra à mão, com o script de reserva | `python benchmark/medir.py --operacoes queda --queda-manual` e, num segundo terminal, `python benchmark/queda_manual.py parar` e depois `religar`, quando o `medir.py` avisar |

A API roda com as bibliotecas do ambiente virtual da aplicação, em `.venv` ([app/README.md](../app/README.md#como-rodar)). Não é preciso subir nenhuma API antes: o `medir.py` sobe a dele, e recusa começar se a porta 8001 já estiver em uso. O cenário precisa do Docker Desktop, o ambiente da apresentação: a API escuta só em `127.0.0.1`, e é o `host.docker.internal` do Docker Desktop que leva o contêiner até ela. A queda também recusa uma base cujos cliques vão além do momento atual, carregada com `--fim` no futuro, porque a conferência contaria cliques da base como cliques da etapa. Com `--lados postgres` e só a queda, o `medir.py` sai com erro antes de restaurar, porque a queda só tem o lado NoSQL.

**Como funciona:**

- **API.** Depois de restaurar a base, o `medir.py` sobe a API no computador, como na demonstração, com o Python do `.venv` e `uvicorn` na porta 8001, para não disputar a 8000 com a API da demonstração. Ela roda num processo só (`--workers 1`), mesmo com `WEB_CONCURRENCY` no terminal, porque cada processo guarda as próprias falhas de gravação, e `GET /metricas` mostraria só as de um. A API conecta aos bancos no ar, que são os do benchmark, já conferidos pelo `medir.py`. O endereço dos bancos e o keyspace `linkpulse` são fixados ao subir a API, e as variáveis de conexão do terminal não valem para ela. Ela sobe pelo [api_cronometrada.py](api_cronometrada.py), um envoltório que não muda a aplicação. Ele devolve, no cabeçalho `Server-Timing`, o tempo de cada redirecionamento da chegada do pedido ao início da resposta, a mesma medida do teste da aplicação (Q-59). O log da API vai para `benchmark/registros/queda-api-*.log`, e a API é encerrada ao fim da etapa.
- **Gerador.** O [queda.py](queda.py) roda no contêiner `gerador-queda` (2 CPUs, 1 GB) e alcança a API por `host.docker.internal`. Todos os envios vão ao link popular. A agenda é fixa: o envio *i* sai em `i / 200` s e vai para o primeiro de 32 workers livre, cada um com uma conexão HTTP persistente. Um envio atrasado sai assim que houver worker livre e nunca é descartado. A latência do gerador conta do instante agendado, então o atraso aparece no resultado em vez de sumir, como acontece no laço fechado (omissão coordenada, nas [consequências do ADR-0014](../docs/decisoes/ADR-0014-modelo-de-dados-e-metodo-do-benchmark.md#consequências)).
- **Parada e religamento.** O `gerador-queda` é o único serviço com o socket do Docker montado (`/var/run/docker.sock`, aceito pelo Docker Desktop no Windows) e fala com a API do Docker pela biblioteca padrão do Python. Aos 30 s, ele para o contêiner do Cassandra, com o prazo de 10 s do `docker compose stop`. Aos 60 s, dispara o religamento sem esperar o healthcheck: a carga segue a agenda, e outra thread registra quando o Docker marca o Cassandra como saudável. Se um comando do Docker falhar, a carga segue até o fim, o erro vai para `erros_no_controle`, o `ca6` sai falso e o resumo marca a rodada como inválida, para ser repetida. Assim, um comando que falhou não se confunde com um Cassandra que demorou a voltar.
- **Leituras.** A cada 0,25 s, o gerador lê o contador do link no Redis master e, logo depois, `falhas_gravacao_clique` em `GET /metricas`. O instante de cada leitura das falhas é o fim da consulta a `/metricas`, porque um aumento das falhas visto nela pode ter acontecido até ali. O contador guarda o intervalo da própria consulta ao Redis, do início ao fim do `GET`. Ele é lido antes das falhas para que, numa janela que termina no fim de uma leitura das falhas, a leitura do contador feita junto com ela caiba na janela. Em outra thread, sonda a porta CQL do Cassandra (9042). A sondagem fica separada porque, com o contêiner parado, resolver o nome `cassandra` leva alguns segundos e atrasaria as leituras. A leitura final só acontece depois de as duas threads pararem, para não dividir com elas a conexão com a API.
- **Volta da gravação.** O driver espera no máximo 2 s entre as tentativas de reconexão ([SPEC-004](../docs/specs/SPEC-004-aplicacao.md#redirecionamento), Q-66). Por isso, depois de o Cassandra abrir a porta CQL, a tentativa seguinte sai em até 2 s. A conexão ainda precisa ser concluída, e só então a primeira escrita chega: a porta aberta, a conexão do driver e a primeira escrita são marcos distintos. A volta da gravação é o primeiro clique gravado depois da parada, lido no próprio Cassandra na conferência, se ele foi gravado durante a carga. A janela do CA-6 vai dos 30 s até a volta ou até a última leitura em que as falhas aumentaram, o que vier depois (Q-68). Com uma leitura a cada 0,25 s, a leitura que detecta o último aumento pode vir depois do primeiro clique gravado, mesmo que a falha tenha acontecido antes dele. Estender a janela até essa leitura deixa dentro dela qualquer falha que ainda possa pertencer à queda. Sem clique gravado durante a carga, a janela vai até os 90 s. A última leitura com falha nova nunca prova a volta sozinha, porque uma leitura de `/metricas` sem resposta ou redirecionamentos que deixam de responder `302` também fariam as falhas pararem de subir sem o Cassandra ter voltado. O instante do clique vem do relógio do computador, onde a API roda, e o da etapa, do contêiner; o Docker Desktop mantém os dois sincronizados. Depois da carga, o gerador espera o Cassandra por até 60 s, sem carga, só para a conferência. Se ele não voltar nesse prazo, ou se a consulta da conferência falhar, o resultado sai mesmo assim, com o histórico marcado como indisponível (`null`) e, no segundo caso, o erro da consulta em `conferencia.erro`. Sem a consulta, também não há o primeiro clique gravado: a volta da gravação fica indeterminada (`gravacao_voltou_na_etapa` nulo), e a janela do CA-6 vai até os 90 s.
- **Conferência.** 10 s depois do fim da carga, cinco vezes o tempo limite da gravação (Q-41), o gerador lê de novo as falhas e o contador e conta os cliques do link no Cassandra desde o início da etapa. A diferença entre o contador e o histórico são os cliques que o contador somou e o histórico não tem. Ela deve ser igual às falhas, e o resultado mostra quanto se afasta delas, por uma escrita que falhou na aplicação mas foi concluída no Cassandra ou por um incremento perdido no Redis.

**Estado dos dados.** Na sequência de testes, a queda roda depois do pico, sem restaurar: as métricas são aumentos durante a etapa, e o estado inicial não muda o resultado. Medida sozinha, com `--operacoes queda`, a etapa parte da base restaurada, como as outras. A queda só roda quando `--lados` inclui `nosql`.

**Resultado.** Fica em `benchmark/registros/`, com `operacao: "queda"`:

| Campo | Conteúdo |
| --- | --- |
| `marcos` | Instantes em segundos desde o início da etapa: parada pedida e concluída, porta CQL fechada e aberta, religamento pedido, Cassandra saudável pelo healthcheck (só na parada automática), última leitura em que as falhas aumentaram e volta da gravação, o primeiro clique gravado depois da parada, lido no próprio Cassandra |
| `queda` | A janela do CA-6, dos 30 s até a volta da gravação ou a última falha, o que vier depois (Q-68): envios, respostas `302`, p50, p95 e p99 no servidor e no gerador, envios atrasados, se a gravação voltou na etapa, quanto o contador e as falhas somaram, os intervalos das duas consultas ao Redis usadas no aumento do contador (`contador_lido_s`), e `ca6`, verdadeiro quando todos os envios receberam `302`, o p95 no servidor ficou abaixo de 50 ms, o contador somou pelo menos os envios da janela menos 100 (Q-69), os envios de uma leitura em cada borda, as falhas aumentaram e a rodada é válida |
| `rodada_invalida` | Os motivos que invalidam a rodada: um comando do Docker que falhou ou o contador da janela indeterminado. Com algum motivo, a rodada não vale para o CA-6 e precisa ser repetida; vazio numa rodada válida |
| `erros_no_controle` | Os erros dos comandos do Docker para parar e religar o Cassandra; vazio numa rodada válida |
| `fases` e `total` | As mesmas métricas antes da parada (0 a 30 s), com o Cassandra parado (30 a 60 s), na volta (60 a 90 s) e nos 90 s |
| `conferencia` | Aumentos do contador, do histórico e das falhas, a diferença entre o contador e o histórico, essa diferença menos as falhas e, em `erro`, o erro da consulta ao Cassandra, se ela falhou |
| `serie` | Por segundo: envios, `302`, p95 no servidor e no gerador, falhas e contador lidos, e quanto as falhas e o contador aumentaram desde a leitura de antes da carga (`falhas_na_etapa` e `contador_na_etapa`). Durante a carga, cada segundo sai também numa linha `PARCIAL`, para a [tela de testes](#tela-de-testes) |

O registro traz também a CPU e a memória do gerador, como nas outras etapas. A CPU dos bancos não é lida, porque o Cassandra para no meio da janela.

**Script de reserva.** O [queda_manual.py](queda_manual.py) para (`docker compose stop`) e religa (`docker compose start --wait`) o Cassandra do benchmark e mostra quanto cada passo levou. Ele recusa bancos no ar com os volumes de desenvolvimento, como os comandos da base, mas não pega a trava, porque roda durante a medição, que já está com ela. Com `--queda-manual`, o gerador roda no serviço `gerador`, que não monta o socket do Docker, e avisa, aos 30 s e aos 60 s, a hora de rodar cada comando. Nesse modo, ficam de fora os marcos de parada concluída e de Cassandra saudável, e a porta CQL fechada marca a parada.

#### Medições

Medido em 25/11/2026, no computador de desenvolvimento (o mesmo das [medições da base](#resultados-medidos)), com a API no Windows e os tetos do [ADR-0013](../docs/decisoes/ADR-0013-stack-e-ambiente-do-marco-2.md#decisão), 2 CPUs e 2 GiB no Cassandra, conferidos com `docker inspect`. A execução de teste começou às 03h33 (horário de Brasília), com `python benchmark/medir.py --operacoes queda`, depois de a base ser restaurada e o CA-1 conferido. Uma segunda execução, às 04h10, usou a parada manual com o script de reserva, também com a base restaurada antes. As duas rodaram no código final do cenário, e as duas rodadas saíram válidas (`rodada_invalida` vazio).

| Fase | Envios | `302` | p50 no servidor (ms) | p95 no servidor (ms) | p99 no servidor (ms) | p95 no gerador (ms) | Envios atrasados mais de 5 ms |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Antes (0 a 30 s) | 6.000 | 6.000 | 1,026 | 1,350 | 1,788 | 2,798 | 1 |
| Parado (30 a 60 s) | 6.000 | 6.000 | 0,964 | 1,459 | 1,861 | 2,988 | 0 |
| Volta (60 a 90 s) | 6.000 | 6.000 | 1,023 | 1,396 | 1,989 | 2,871 | 0 |
| **Queda vista pela aplicação (30 a 74,0 s)** | **8.801** | **8.801** | 0,976 | **1,450** | 1,880 | 2,973 | 0 |

Nenhum envio ficou sem resposta, e o maior atraso de envio foi de 7,9 ms, antes da parada. O gerador usou 0,08 núcleo (4,0% da cota de 2), com pico de 89 MiB.

| Marco, em segundos desde o início da etapa | Execução de teste | Parada manual |
| --- | ---: | ---: |
| Parada pedida | 30,0 | 30,0 (aviso) |
| Porta CQL fechada | 30,1 | 32,1 |
| Parada concluída (o Docker devolve o `stop`) | 36,0 | — |
| Religamento pedido | 60,0 | 60,0 (aviso) |
| Porta CQL aberta | 73,5 | 78,5 |
| Volta da gravação: primeiro clique gravado depois da parada | 73,9 | 80,1 |
| Leitura que detectou o último aumento das falhas, fim da janela do CA-6 | 74,0 | 80,3 |
| Cassandra saudável pelo healthcheck | 75,9 | — |

| Conferência, 10 s depois da carga | Execução de teste | Parada manual |
| --- | ---: | ---: |
| Contador | +18.000 | +18.000 |
| Histórico | +9.220 | +8.378 |
| Falhas | +8.780 | +9.622 |
| Diferença entre o contador e o histórico | 8.780 | 9.622 |
| Diferença menos as falhas | 0 | 0 |

Na parada manual, os 10.051 envios da queda vista pela aplicação, dos 30 s aos 80,3 s, receberam `302`, com p95 no servidor de 1,546 ms, e o contador somou 10.050 na janela. O gerador rodou no serviço `gerador`, sem o socket do Docker. O script de reserva levou 3,8 s para parar o Cassandra e 20,9 s para religá-lo até o healthcheck.

Os aumentos do contador e das falhas na janela vêm das leituras a cada 0,25 s e, por isso, podem diferir dos envios da janela em até cerca de 50 cliques em cada borda, os envios de 0,25 s. Por isso o `ca6` aceita um contador até 100 abaixo dos envios: uma perda maior não vem das leituras (Q-69). O aumento do contador vai da primeira à última leitura válida dentro da janela, para não contar incrementos de fora dela. Uma leitura só fica dentro da janela se a consulta ao Redis inteira, do início ao fim, cabe nela. Se os envios entre as bordas e essas consultas passam de 100, porque leituras falharam ou atrasaram perto de uma borda, o aumento fica indeterminado (`null`), e a rodada fica inválida, para ser repetida: o resultado não prova perda de incrementos, só que as leituras não bastaram para medir. A conferência final não tem essa imprecisão, porque lê os valores depois de a carga terminar.

#### Critérios conferidos

- **CA-6, na execução de teste:** enquanto o Cassandra esteve fora para a aplicação, dos 30 s aos 74,0 s, os 8.801 redirecionamentos responderam `302`, com p95 no servidor de 1,450 ms, abaixo dos 50 ms. Na mesma janela, o contador somou 8.800 entre as consultas ao Redis dos 30,0 s e dos 74,0 s, dentro da margem das leituras, e as falhas, 8.780. A rodada foi válida: nenhum comando do Docker falhou, e o contador da janela foi determinado. Os cliques que falharam aparecem na [tela de testes](#tela-de-testes) (RM-32); as 3 execuções ficam para a execução completa oficial (RM-33). Por isso o CA-6 continua desmarcado na [SPEC-005](../docs/specs/SPEC-005-testes-de-stress.md#critérios-de-aceitação).
- **Tempo real de volta:** o Cassandra voltou a aceitar conexões 13,5 s depois do religamento, e a aplicação gravou o primeiro clique 0,4 s depois disso, aos 73,9 s, antes do fim da etapa. A janela de 30 s e a etapa de 90 s continuam valendo, e o aviso do ADR-0014 de que a volta poderia passar dos 30 s previstos foi verificado sem exigir decisão nova.

#### Leitura

- **A queda não mudou o redirecionamento.** O p95 no servidor ficou entre 1,3 e 1,7 ms nas três fases, nas duas execuções. O redirecionamento só lê o Redis, e a gravação do clique roda depois da resposta. Com o Cassandra fora, o driver falha cada gravação na hora (`NoHostAvailable`), sem esperar os 2 s do tempo limite.
- **O Cassandra deixa de aceitar escritas assim que recebe o sinal de parada.** As falhas começaram aos 30,1 s, quase 6 s antes de o contêiner terminar de parar. Ele fecha a porta CQL na hora, o driver marca o nó como fora do ar, e as gravações seguintes falham sem chegar ao Cassandra. Nos logs da API, quase todas as falhas são `NoHostAvailable` sem nó tentado. Em algumas execuções, de uma a três das primeiras trouxeram `Server is shutting down` ou a conexão fechada pelo Cassandra.
- **A aplicação ficou cerca de 44 s sem gravar:** 30 s com o Cassandra parado e quase 14 s com ele subindo. O primeiro clique foi gravado 0,4 s depois da porta aberta, dentro dos 2 s de espera máxima entre as tentativas do driver, mais o tempo de concluir a conexão. A leitura que detectou o último aumento das falhas terminou 91 ms depois do primeiro clique. Como as leituras são a cada 0,25 s, a falha pode ter acontecido antes do clique ou logo depois, e esses dois marcos não dizem qual; a janela do CA-6 vai até essa leitura para incluir as duas possibilidades. Com as esperas padrão do driver, que dobram a cada tentativa, a conta, não medida, punha a volta por volta dos 100 s, depois do fim da etapa.
- **A diferença entre o contador e o histórico foi exatamente o número de falhas** nas duas execuções: nenhuma escrita falhou na aplicação e foi concluída no Cassandra, e nenhum incremento se perdeu.
- **Execuções anteriores.** Das 01h22 às 03h11, outras catorze execuções, automáticas e manuais, com versões anteriores do cenário, tiveram a mesma forma: todos os envios com `302`, p95 no servidor entre 1,465 e 6,974 ms na queda, volta entre 75 e 83 s e diferença igual às falhas. Nas automáticas, a porta CQL abriu de 13,8 a 16,0 s depois do religamento. Na primeira, às 01h22, as leituras das falhas e do contador travaram por 3 a 4 s com o Cassandra parado, porque a sondagem da porta ainda ficava na mesma thread. A latência dela já era maior antes da parada (p95 de 5,9 ms de 0 a 30 s), e por isso não veio da queda. O mesmo vale para a manual das 03h09, com p95 de 6,8 ms já de 0 a 30 s.
- **Medição de desenvolvimento.** Os números são do computador de desenvolvimento, com outros programas abertos. As 3 execuções que valem para o CA-6 rodam na máquina da apresentação, na execução completa (CA-4).

## Tela de testes

Passo 6 do [plano de testes](../docs/specs/SPEC-005-testes-de-stress.md#plano-de-implementação) (RM-32). A tela controla o benchmark inteiro pelo navegador: prepara os bancos, restaura a base, inicia a sequência ao vivo e a execução completa, mostra a etapa atual, as curvas dos dois lados sobrepostas e o placar de cada etapa, abre as [execuções completas](#execução-completa) gravadas e devolve o ambiente de desenvolvimento. As decisões estão nas questões Q-70 a Q-76 em [QUESTOES](../docs/requisitos/QUESTOES.md#respondidas).

Abra com `python benchmark/tela.py` e, no navegador, `http://127.0.0.1:8002` (`--porta` troca a porta). Os botões rodam os mesmos comandos do terminal, que continuam valendo:

| Botão | Comando |
| --- | --- |
| 1. Parar os bancos de desenvolvimento | `docker compose stop` |
| 2. Restaurar a base | `python benchmark/base.py restaurar` |
| 3. Iniciar sequência ao vivo | `python benchmark/medir.py --ao-vivo --eventos` |
| Conferir a base | `python benchmark/base.py conferir` |
| Execução completa, de teste | `python benchmark/medir.py --completa --duracao 5 --aquecimento 2 --eventos` |
| Execução completa, oficial | `python benchmark/medir.py --completa --eventos` |
| Carregar a base do zero | `python benchmark/base.py carregar` |
| Voltar ao desenvolvimento | `docker compose stop` e `docker compose up -d --wait` |

**Como funciona:**

- **Servidor.** O [tela.py](tela.py) usa só a biblioteca padrão do Python, como o `base.py`, e escuta em `127.0.0.1:8002`, fora da 8000 da demonstração e da 8001 da queda. Ele serve a página de [tela/](tela/) e, sem cópia, o `painel.css` e o Chart.js 4.6.1 da tela da aplicação, em `app/static/`. Nenhum arquivo da tela aponta para a internet. A página abre com os bancos parados, e as gravações abrem sem Docker (Q-70). Uma segunda tela na mesma porta sai com erro.
- **Tarefas** (Q-76). Cada botão roda o seu comando como processo filho, um por vez: com uma tarefa rodando, os botões ficam desabilitados, e um pedido direto recebe `409`. O servidor só aceita pedidos `POST` vindos da própria tela (`Host` e `Origin` em `127.0.0.1` ou `localhost` na porta dela); os outros recebem `403`. A saída de cada comando, e cada linha `EVENTO {json}` do `medir.py`, chegam à tela por *Server-Sent Events*. Uma aba que abre ou recarrega no meio recebe a última medição desde o início e as tarefas seguintes. As proteções continuam nos comandos: a trava da base, a recusa a mexer nos volumes de desenvolvimento e a conferência depois de restaurar. Quando um comando recusa, a tela mostra a mensagem dele e abre a saída completa.
- **Bancos.** A cada 5 s, a tela lê no Docker com que volumes cada banco está no ar (desenvolvimento, benchmark, em parte ou parados) e só habilita os botões que cabem: restaurar com os bancos de desenvolvimento parados, iniciar a sequência ao vivo com os quatro bancos do benchmark no ar. Mostra também a hora da última restauração ou carga registrada em `benchmark/registros/` e quantas medições foram registradas depois dela; os passos 1 e 2 aparecem marcados quando estão feitos.
- **Interromper.** Com uma tarefa rodando, o botão "Interromper" encerra o comando e os processos filhos dele (no Windows, com `taskkill /T`), como a API da queda. A trava se solta sozinha, e o próximo comando espera os contêineres auxiliares que ainda estiverem rodando. Depois de interromper, restaure a base antes de medir de novo.
- **Sequência ao vivo** (Q-72). Parte da base como está, sem restaurar: a restauração é o passo 2, fora dos 480 s. Nas etapas 1 a 4, cada execução tem 3 s de aquecimento descartados e 18 s medidos; no pico, 3 s e 45 s; a queda mantém os 90 s. A curva extra roda só no registro de clique. O relógio e a barra de progresso contam do clique no botão ao fim da medição, e o limite é de 480 s (CA-7).
- **Execução completa pela tela.** A tela mostra a repetição em andamento, com as restaurações entre elas, e, quando a gravação termina, abre-a com a mediana.
- **Curvas** (Q-71). Cada etapa tem um gráfico, com o eixo em segundos desde a partida de cada lado, e por isso os dois lados aparecem sobrepostos, e o aquecimento sombreado como descartado. Botões trocam a métrica: vazão e p95 por segundo, da `serie` do gerador, e CPU (% do teto) e memória de cada banco exercitado, da `serie_recursos`. No pico, a vazão conta cliques completos, os registros concluídos, e o p95 tem uma linha por operação. A curva extra aparece tracejada, com o rótulo "PostgreSQL, synchronous_commit=off (fora do padrão)".
- **Placar.** Vazão, p50, p95, p99 e erros, com a taxa de erro, de cada lado, por etapa, com os números do resultado de cada execução, calculados como na [tabela de métricas](#métricas). No pico, uma linha por operação.
- **Queda** (Q-75). O gráfico mostra os redirecionamentos com `302` e os cliques que falharam ao gravar, por segundo, com linhas na parada (30 s), no religamento (60 s) e na volta da gravação, e a janela do CA-6 sombreada quando o resultado chega. Enquanto a etapa roda, uma linha mostra quantos `302`, quantos cliques que falharam e quanto o contador somou até ali. O placar mostra a janela do CA-6, os `302`, o p95 no servidor, os cliques que falharam na janela e na conferência, quanto o contador somou, a diferença entre o contador e o histórico, essa diferença menos as falhas e se o CA-6 foi cumprido, não foi ou se a rodada é inválida.
- **Execução gravada** (Q-74). A lista "Execuções", na barra lateral, traz a última medição pedida pela tela e as gravações de `benchmark/gravacoes/`, da mais nova para a mais antiga. A gravação abre inteira, sem animação, com a faixa "Execução gravada em …, não é ao vivo" e, nas de teste, "gravação de teste, com durações curtas". O placar das etapas 1 a 5 mostra a mediana das repetições; o da queda, uma linha por repetição. As curvas mostram uma repetição por vez, escolhida no seletor. Abrir uma gravação não interrompe a medição em andamento, que volta à tela pelo primeiro item da lista.

**Bancos da aplicação.** A sequência ao vivo usa os mesmos contêineres de banco que a aplicação da demonstração, com os volumes do benchmark, e a queda para o Cassandra. Durante a sequência, a demonstração da aplicação não deve ser usada; depois, o ambiente de desenvolvimento volta pelo botão "Voltar ao desenvolvimento".

#### Medições

Medido em 25/11/2026, às 05h47 (horário de Brasília), no computador de desenvolvimento (o mesmo das [medições da base](#resultados-medidos)), com o botão da tela. A base foi restaurada antes, com `python benchmark/base.py restaurar`, e o CA-1 foi conferido. A sequência levou 457,5 s do clique ao fim da medição, dentro dos 480 s, e nenhuma execução teve erro. Cada execução das etapas 1 a 4 levou cerca de 26,5 s, 21 s de carga e o resto para subir o contêiner e abrir as conexões; o pico, 53 s por lado; a queda, 107 s, com a subida da API e a conferência.

| Etapa | Lado | Início, desde o clique (s) | Vazão (ops/s) | p50 (ms) | p95 (ms) | p99 (ms) |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| Redirecionamento | NoSQL | 3,2 | 42.718 | 0,162 | 0,320 | 0,534 |
| Redirecionamento | PostgreSQL | 30,4 | 24.934 | 0,172 | 0,308 | 0,484 |
| Contador | NoSQL | 56,6 | 40.295 | 0,180 | 0,313 | 0,455 |
| Contador | PostgreSQL | 83,2 | 1.209 | 4,217 | 19,582 | 33,849 |
| Registro de clique | NoSQL | 109,7 | 6.468 | 0,757 | 1,168 | 19,179 |
| Registro de clique | PostgreSQL | 136,0 | 4.873 | 1,272 | 4,357 | 4,902 |
| Registro de clique | PostgreSQL, `synchronous_commit=off` (fora do padrão) | 162,7 | 17.375 | 0,240 | 0,421 | 0,686 |
| Histórico por período | NoSQL | 189,5 | 1.518 | 1,642 | 35,397 | 58,923 |
| Histórico por período | PostgreSQL | 216,2 | 6.262 | 0,271 | 2,436 | 48,643 |
| Pico (cliques completos) | NoSQL | 243,3 | 5.331 | 0,864 no registro | 1,330 no registro | 2,082 no registro |
| Pico (cliques completos) | PostgreSQL | 297,1 | 305 | 16,785 no contador | 52,903 no contador | 79,043 no contador |

Na queda, que começou aos 350,3 s, a janela do CA-6 foi dos 30 s aos 77,0 s. Os 9.401 redirecionamentos dela responderam `302`, com p95 de 1,56 ms no servidor. O contador somou 9.400 na janela, e 9.383 cliques falharam ao gravar. Na conferência, a diferença entre o contador e o histórico foi de 9.383, igual às falhas. O Cassandra abriu a porta aos 75,6 s, e o primeiro clique foi gravado aos 77,0 s.

#### Critérios conferidos

- **CA-7:** o botão iniciou a sequência, e um segundo clique durante ela recebeu `409`. Capturas da página pelo Edge headless, aos 145 s e aos 396 s, mostraram a etapa atual, as curvas dos dois lados sobrepostas crescendo, o placar das etapas concluídas e o relógio. A sequência terminou em 457,5 s, dentro dos 480 s.
- **Cliques que falharam (parte do CA-6):** aos 40 s da queda, a página mostrava 8.000 redirecionamentos com `302`, 1.941 cliques que falharam ao gravar e o contador com +7.950; no fim, o gráfico por segundo e o placar com as 9.383 falhas, na janela e na conferência. O CA-6 continua desmarcado na [SPEC-005](../docs/specs/SPEC-005-testes-de-stress.md#critérios-de-aceitação): faltam as 3 execuções oficiais (RM-33).
- **Sem internet:** o Edge rodou com um proxy inexistente para tudo fora de `127.0.0.1`. A página carregou com os gráficos, e todos os pedidos foram ao `127.0.0.1:8002`: a página, o CSS, o script, o Chart.js e as rotas `/api/`.

#### Leitura

- **A curva extra mostra o peso da gravação em disco no PostgreSQL.** Com `synchronous_commit=off`, o registro de clique foi de 4.873 para 17.375 ops/s, e o p95 caiu de 4,357 para 0,421 ms, mais rápido que o Cassandra nesta execução. A hipótese da [calibração](#leitura), de que as escritas do PostgreSQL esperavam o `fsync` de cada confirmação, fica medida no registro; o contador com a curva extra roda só na execução completa.
- **No pico, o PostgreSQL ficou limitado pelo contador.** Com as 8 conexões no link popular, o `UPDATE` da mesma linha fez o contador esperar (p95 de 52,9 ms), e o lado completou 305 cliques por segundo, contra 5.331 no lado NoSQL.
- **Medição de desenvolvimento e curta.** A sequência ao vivo só ilustra: 18 s medidos por lado, sem repetição e com outros programas abertos. Os números para a apresentação são os da execução completa.

## Execução completa

Passo 7 do [plano de testes](../docs/specs/SPEC-005-testes-de-stress.md#plano-de-implementação). `python benchmark/medir.py --completa` repete a sequência inteira, queda incluída, 3 vezes (Q-36). Restaura a base antes de cada repetição e antes do histórico por período, roda a curva extra no contador e no registro de clique e grava o resultado em `benchmark/gravacoes/`, no Git, ao contrário de `benchmark/registros/` (Q-74). As durações seguem `--duracao` e `--aquecimento`: com 60 s e 10 s, todas as etapas e os dois lados, a gravação é `completa`; com qualquer outra combinação, ou com `--queda-manual`, é `teste`. As execuções oficiais rodam na máquina da apresentação (RM-33). Se um comando falhar no meio, nada é gravado em `gravacoes/`, e o que já foi medido vai para `registros/`.

| Campo da gravação | Conteúdo |
| --- | --- |
| `formato` | Versão do formato, hoje `1` |
| `tipo` | `completa` ou `teste` |
| `inicio` e `gravada_em` | Início da medição e hora da gravação, com o fuso do computador |
| `maquina` | Sistema operacional e número de CPUs do computador |
| `parametros` | Os argumentos do `medir.py` |
| `mediana` | Uma linha por etapa de 1 a 5, lado e curva extra, com a mediana de cada métrica entre as repetições: operações, erros, vazão, p50, p95, p99 e taxa de erro; no pico, por operação. Cada métrica tem a sua mediana, que pode vir de repetições diferentes |
| `repeticoes` | As 3 repetições, cada uma com `restauracoes` e `execucoes` no formato do registro do `medir.py`, com a `serie` e a `serie_recursos` de cada execução e o resultado completo de cada queda |

### Gravação de teste

Gravada em 25/11/2026, das 05h56 às 06h16 (horário de Brasília), no computador de desenvolvimento, com `python benchmark/medir.py --completa --duracao 5 --aquecimento 2`: [gravacoes/20261125-061623-teste.json](gravacoes/20261125-061623-teste.json). As durações curtas servem só para conferir o formato e a tela; os números não valem para a apresentação. A execução levou 20 min 25 s, com 6 restaurações, duas por repetição, todas com o CA-1 conferido. Cada repetição tem 13 execuções: as 11 da sequência e a curva extra no contador e no registro de clique. A mediana tem 12 linhas, uma por etapa de 1 a 5, lado e curva extra, e confere com o cálculo refeito a partir das repetições. Nas 3 quedas, todos os redirecionamentos da janela do CA-6 responderam `302`, com p95 no servidor entre 1,371 e 1,540 ms; a diferença entre o contador e o histórico foi igual às falhas, e o CA-6 saiu cumprido nas três.

#### Critérios conferidos

- **CA-8, com a gravação de teste:** com o Edge sob um proxy inexistente para tudo fora de `127.0.0.1` e com todos os contêineres parados, a tela carregou os gráficos, listou a gravação e a abriu com a faixa "Execução gravada em 25/11/2026, 06:16 · gravação de teste, com durações curtas · não é ao vivo". O placar mostrou a mediana de 3 repetições, a curva extra apareceu tracejada no contador e no registro, o seletor trocou as curvas para a repetição 2, e a queda mostrou uma linha por repetição. Todos os pedidos foram ao `127.0.0.1:8002`. A conferência com a execução completa oficial fica na RM-33, e por isso o CA-8 continua desmarcado na [SPEC-005](../docs/specs/SPEC-005-testes-de-stress.md#critérios-de-aceitação).
- **Botão com os bancos parados:** o `medir.py` saiu com código 1, e a tela mostrou o código e, na saída da medição, a mensagem dos bancos parados com o comando de restauração.
