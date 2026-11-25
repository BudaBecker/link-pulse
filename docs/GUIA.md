# Guia do LinkPulse

Percurso pelo projeto inteiro para quem chega agora: como ele foi feito, como o sistema funciona, como rodar, como conferir e como ler os resultados do benchmark. Cada seção resume e aponta para o documento que tem os detalhes. Se algo aqui divergir do documento apontado, vale o documento apontado.

## Como o projeto foi feito

O LinkPulse é o projeto incremental da disciplina Bancos de Dados NoSQL, entregue em dois marcos ([DISCIPLINA](produto/DISCIPLINA.md)):

- **Marco 1, modelagem inicial.** Só documentação ([ADR-0011](decisoes/ADR-0011-marco-1-so-documentacao.md)): o problema em [VISAO](produto/VISAO.md) e [PITCH](produto/PITCH.md), a modelagem e a justificativa técnica em [ARQUITETURA](arquitetura/ARQUITETURA.md), e os fluxos em [FUNCIONALIDADES](arquitetura/FUNCIONALIDADES.md).
- **Marco 2, sistema completo.** O resultado principal é um benchmark que compara os bancos NoSQL do projeto com o PostgreSQL, sobre uma aplicação simples ([ADR-0012](decisoes/ADR-0012-marco-2-benchmark-sql-x-nosql.md)). A apresentação é em 25/11/2026.

### Do requisito ao código

Todo trabalho segue o caminho requisito, especificação, tarefa e pull request ([ADR-0001](decisoes/ADR-0001-desenvolvimento-guiado-por-especificacoes.md)):

| Peça | Onde fica | O que é |
| --- | --- | --- |
| Requisito | [REQUISITOS](requisitos/REQUISITOS.md) | O que o sistema deve fazer: funcional (`RF-xx`), não funcional (`RNF-xx`) ou regra de negócio (`RN-xx`), cada um com a origem nos documentos e um critério verificável |
| Questão | [QUESTOES](requisitos/QUESTOES.md) | Dúvida ou contradição que precisa de decisão do grupo (`Q-xx`). Uma questão aberta bloqueia o que depende dela; uma adiada, não |
| Decisão | [docs/decisoes/](decisoes/README.md) | Registro de decisão (ADR, do inglês *Architecture Decision Record*) para escolhas difíceis de desfazer. Um ADR aceito não é reescrito: se a decisão mudar, um ADR novo o substitui |
| Especificação | [docs/specs/](specs/README.md) | Uma entrega implementável (`SPEC-NNN`): comportamento, plano em passos e critérios de aceitação. Só se implementa comportamento novo com a spec `Pronta` |
| Tarefa | [ROADMAP](roadmap/ROADMAP.md) | Um passo de spec ou de documentação (`RM-NN`), com uma issue no GitHub que registra o andamento |
| Pull request | GitHub | Cita a spec e os IDs que atende e passa por revisão registrada antes do merge ([CONTRIBUTING](../CONTRIBUTING.md)) |

Os critérios de aceitação são numerados dentro de cada spec: "CA-1 da SPEC-005" é o primeiro critério da spec de testes de stress.

### As decisões do Marco 2

- **Escopo** ([ADR-0012](decisoes/ADR-0012-marco-2-benchmark-sql-x-nosql.md)): o que o benchmark mede, as cinco funções da aplicação, o MongoDB para as campanhas e o que ficou de fora.
- **Stack e ambiente** ([ADR-0013](decisoes/ADR-0013-stack-e-ambiente-do-marco-2.md)): Python com FastAPI, Docker Compose, o mesmo teto de CPU e memória nos bancos comparados e a configuração padrão de cada banco.
- **Modelo de dados e método** ([ADR-0014](decisoes/ADR-0014-modelo-de-dados-e-metodo-do-benchmark.md)): as tabelas dos dois lados, a forma de aplicar a carga, os dados carregados e as durações.

### O que já está implementado

| Entrega | Spec e tarefa | Onde está |
| --- | --- | --- |
| Ambiente local | Passo 1 da [SPEC-004](specs/SPEC-004-aplicacao.md#plano-de-implementação) (RM-24) | [infra/](../infra/README.md), [docker-compose.yml](../docker-compose.yml), [Dockerfile](../Dockerfile) |
| Base de referência do benchmark | Passo 1 da [SPEC-005](specs/SPEC-005-testes-de-stress.md#plano-de-implementação) (RM-29) | [benchmark/](../benchmark/README.md), [docker-compose.benchmark.yml](../docker-compose.benchmark.yml) |
| Aplicação | Passos 2 a 6 da SPEC-004 (RM-30) | Cadastro de cliente, campanha e criação de link (passo 2, RM-36), redirecionamento, contador e gravação assíncrona do clique (passo 3, RM-37) consultas de analytics (passo 4, RM-38), tela (passo 5, RM-39) e testes de aceitação com a réplica e o Cassandra parados (passo 6, RM-40) em [app/](../app/README.md) |
| Gerador de carga, calibração e cenários | Passos 2 a 5 da SPEC-005 (RM-31) | Gerador em laço fechado das quatro operações em [benchmark/](../benchmark/README.md#gerador-de-carga) (RM-41), [calibração](../benchmark/README.md#calibração), que escolheu 8 conexões (RM-42), [pico de tráfego](../benchmark/README.md#pico-de-tráfego) (RM-43) e [queda do Cassandra](../benchmark/README.md#queda-do-cassandra), pela aplicação, em laço aberto (RM-44) |
| Tela de testes | Passo 6 da SPEC-005 (RM-32) | Planejada |
| Execuções completas, com o resultado salvo | Passo 7 da SPEC-005 (RM-33) | Planejadas |

O andamento de cada tarefa fica na issue indicada no [ROADMAP](roadmap/ROADMAP.md).

## Como o sistema funciona

### O problema

Um clique exige dois tipos de trabalho, com necessidades diferentes ([ARQUITETURA](arquitetura/ARQUITETURA.md), Resumo e Passo 1): o redirecionamento é uma leitura simples que não pode ser lenta nem falhar, e o registro do clique é uma escrita em rajada, lida depois em consultas que varrem muitos eventos. Num único banco relacional, as agregações do painel disputariam o disco com as escritas dos cliques, e aguentar picos exigiria uma máquina cada vez maior (Passo 2). Essa afirmação nunca tinha sido medida, e é ela que o benchmark do Marco 2 põe à prova.

### Papel de cada banco

| Banco | Família | O que guarda | Por quê |
| --- | --- | --- | --- |
| Redis, um master e uma réplica | Chave-Valor | Por link, um Hash `link:{short_code}` com URL, cliente, canal e datas; o contador `contador:{short_code}`; o Set `links:cliente:{cliente_id}` com os links de cada cliente; os clientes em `cliente:{cliente_id}` | Leitura por chave, em memória, no caminho de cada clique; o `INCR` soma o contador sem perder incrementos entre acessos simultâneos ([ARQUITETURA](arquitetura/ARQUITETURA.md) Passo 4) |
| Cassandra, um nó | Wide-Column | A tabela `cliques_por_link`, com uma partição por link e as linhas em ordem do clique mais recente para o mais antigo | A consulta "cliques deste link entre duas datas" lê uma única partição ([ARQUITETURA](arquitetura/ARQUITETURA.md) Passo 5; [ADR-0014](decisoes/ADR-0014-modelo-de-dados-e-metodo-do-benchmark.md#cliques-no-mesmo-milissegundo)) |
| MongoDB | Documentos | Um documento por campanha, com descrição, tags e a lista de links | Dado semiestruturado e mutável, ao contrário do clique, que nunca muda ([ADR-0007](decisoes/README.md#registro); modelo do documento no [ADR-0014](decisoes/ADR-0014-modelo-de-dados-e-metodo-do-benchmark.md#dados-novos-da-aplicação)) |
| PostgreSQL | Relacional | As tabelas `links`, `contadores` e `cliques`, sem chave estrangeira e só com os índices das chaves primárias | Só a base de comparação do benchmark, fazendo o mesmo trabalho que o lado NoSQL ([ADR-0014](decisoes/ADR-0014-modelo-de-dados-e-metodo-do-benchmark.md#modelo-do-lado-postgresql)) |

Os serviços, as imagens, os tetos e as portas estão em [infra/README.md](../infra/README.md#serviços).

### O caminho de um clique

O desenho está em [ARQUITETURA](arquitetura/ARQUITETURA.md) Passo 3, e o comportamento da aplicação, na [SPEC-004](specs/SPEC-004-aplicacao.md#redirecionamento) e em [app/README.md](../app/README.md#o-caminho-de-um-clique). Em resumo: a aplicação lê o link na réplica do Redis (ou no master, se o link estiver ausente na réplica, a conexão com ela falhar ou a leitura der erro; a conexão com a réplica desiste em 0,25 s) e responde `302` com a URL. Só depois da resposta ela soma o contador e grava o clique no Cassandra. Se essa gravação falhar ou passar de 2 s, a aplicação desiste dela e conta uma falha, sem mudar a resposta; o total de falhas fica em `GET /metricas`. O Cassandra ainda pode concluir uma escrita depois do tempo limite, e então um clique contado como falha aparece no histórico.

### Os compromissos

- **Disponibilidade antes de consistência.** O redirecionamento continua respondendo com a réplica do Redis ou o Cassandra fora do ar (RNF-01).
- **A resposta não espera o clique.** Com o Cassandra lento ou parado, o redirecionamento continua respondendo em menos de 50 ms em 95% dos casos, medido no servidor (RNF-02).
- **O painel pode atrasar.** Um clique aparece no painel em até 60 s (RNF-03).
- **Perder um clique é tolerado; falhar um redirecionamento, não** (RN-07).
- **Replicação.** Master e réplica no Redis e, no desenho, vários nós que aceitam escrita no Cassandra (Master-Master) ([ADR-0009](decisoes/ADR-0009-replicacao-por-banco.md)). No ambiente local, o Cassandra tem um nó só e fator de replicação 1 ([ADR-0013](decisoes/ADR-0013-stack-e-ambiente-do-marco-2.md#consequências)).

## Como rodar

### Pré-requisitos

- **Docker com o Compose.** Os tetos de memória dos bancos somam 7,5 GB; o ambiente foi medido numa máquina virtual do Docker com 7,6 GiB. No Windows, a memória do Docker se ajusta em `.wslconfig` ([infra/README.md](../infra/README.md#consumo-de-memória-medido)).
- **Python 3.11 ou mais novo no computador**, para preparar a base com `benchmark/base.py` e medir as operações com `benchmark/medir.py`. Ambos usam a biblioteca padrão. As bibliotecas de acesso aos bancos rodam dentro dos contêineres, nas versões de [requirements.txt](../requirements.txt). A aplicação é a exceção: roda no computador, num ambiente virtual Python com essas bibliotecas (ver [Aplicação](#aplicação)). A queda do Cassandra também precisa desse ambiente virtual, porque o `medir.py` sobe a API com ele, e do Docker Desktop, porque o gerador alcança a API por `host.docker.internal`.
- **Disco.** A base do benchmark ocupa cerca de 2,8 GB, e a cópia guardada para restaurá-la ocupa outro tanto. Ao fazer uma cópia nova, a anterior só é apagada quando a nova fica pronta.
- **Senha do PostgreSQL**, opcional: a variável `POSTGRES_PASSWORD` (padrão `linkpulse`).

### Ambiente de desenvolvimento

`docker compose up -d --wait` sobe os bancos e espera todos ficarem saudáveis; `docker compose run --rm verificar` confere o ambiente. Os comandos para parar e apagar os dados, o tempo de subida e o consumo medido estão em [infra/README.md](../infra/README.md#como-usar).

### Aplicação

Com os bancos de desenvolvimento no ar:

1. **Criar o ambiente Python uma vez**, na raiz do repositório: `python -m venv .venv` e `.venv/Scripts/python -m pip install -r requirements-testes.txt` (no Linux e no macOS, `.venv/bin/python`).
2. **Subir a API:** `.venv/Scripts/python -m uvicorn app.main:app --port 8000`. As rotas ficam documentadas em `http://127.0.0.1:8000/docs`.

A aplicação grava nos volumes de desenvolvimento. Rotas, variáveis de ambiente e respostas de erro estão em [app/README.md](../app/README.md).

### Base de referência do benchmark

Os mesmos bancos rodam com volumes próprios do benchmark, separados dos de desenvolvimento. O roteiro de uso:

1. **Carregar uma vez:** `python benchmark/base.py carregar`. Recria os volumes do benchmark vazios, grava o histórico de 10 milhões de cliques no Cassandra e no PostgreSQL e os links e contadores correspondentes no Redis e no PostgreSQL, confere tudo e guarda uma cópia dos volumes. Leva cerca de 10 minutos ([tempos por etapa](../benchmark/README.md#carga)).
2. **Calibrar o gerador numa máquina nova:** `python benchmark/calibrar.py`. Mede tudo com 8, 32 e 64 conexões e escolhe o maior número em que o gerador fica abaixo de 70% da sua cota de CPU, em cerca de 40 minutos ([calibração](../benchmark/README.md#calibração)).
3. **Medir a sequência de testes:** `python benchmark/medir.py`, que usa 8 conexões e roda as seis etapas: as quatro operações, o pico de tráfego e a queda do Cassandra. Para medir só o pico, use `python benchmark/medir.py --operacoes pico`, e só a queda, `python benchmark/medir.py --operacoes queda`; os dois também restauram a cópia antes. Na queda, o `medir.py` sobe a API na porta 8001, para e religa o Cassandra sozinho e encerra a API no fim. Se a calibração escolheu outro número, passe-o em `--conexoes`, como em `python benchmark/medir.py --conexoes 32`. O comando restaura a cópia, mede um lado por vez e salva os resultados em `benchmark/registros/`. Para apenas repor e conferir a base, use `python benchmark/base.py restaurar`. Veja as [opções de medição](../benchmark/README.md#gerador-de-carga).
4. **Conferir a qualquer momento:** `python benchmark/base.py conferir`.
5. **Voltar ao desenvolvimento:** `docker compose up -d --wait`. Os volumes do benchmark continuam guardados. Para voltar a eles, pare os bancos com `docker compose stop` e rode `restaurar`.

Só um comando da base roda por vez. Cada `carregar`, `copiar` e `restaurar` grava os tempos e a memória medidos em `benchmark/registros/`, fora do Git. Os comandos, a trava e o que cada um faz com os volumes estão em [benchmark/README.md](../benchmark/README.md).

### Problemas comuns

| Mensagem de `benchmark/base.py` | O que fazer |
| --- | --- |
| `outro comando da base está rodando (...)` | Esperar: a mensagem diz qual comando, processo e pasta estão com a trava |
| `Esperando terminar N contêiner(es) de um comando anterior` | Nada: um comando anterior foi interrompido e o atual espera os contêineres dele terminarem |
| `Nada foi parado: os bancos no ar não usam os volumes de benchmark` | Os bancos de desenvolvimento estão no ar. Pare-os com `docker compose stop` e repita o comando |
| `bancos parados (...); a conferência não liga bancos` | Subir os bancos com `python benchmark/base.py restaurar` |
| `nenhuma cópia selada e íntegra` | Rodar `python benchmark/base.py carregar` |
| `a base de benchmark não tem manifesto válido` | Rodar `carregar`, ou `restaurar` para repor a cópia |
| `a reposição dos volumes falhou` ou `a gravação do manifesto da base falhou` | Os bancos ficam parados de propósito, para não subirem com dados pela metade. Rodar `restaurar` de novo |
| Aviso de que o espelho `base-de-referencia.json` difere do manifesto da base | O arquivo do Git não é o da base carregada; a conferência usa o da base. `restaurar` e `carregar` reescrevem o espelho |

## Como testar e conferir

- **Ambiente:** `docker compose run --rm verificar` confere o Redis (réplica ligada e gravação em disco no padrão), o keyspace e as chaves de `cliques_por_link` no Cassandra, as tabelas, os índices e a confirmação de escrita do PostgreSQL, e se o MongoDB responde. Sai com código 1 se algo falhar. A lista completa está em [infra/README.md](../infra/README.md#como-usar).
- **Base do benchmark** (CA-1 da [SPEC-005](specs/SPEC-005-testes-de-stress.md#critérios-de-aceitação)): `python benchmark/base.py conferir` consulta os próprios bancos e confere, link a link, que os dois lados têm os mesmos links e cliques, que o link popular tem 20% dos cliques e que os contadores batem com os cliques, em cerca de 45 s. Com `--completo`, lê os 10 milhões de cliques dos dois lados e confere a distribuição de dispositivos e a assinatura dos cliques, em cerca de 3 minutos. Termina com `CA-1 conferido.` ou com a lista do que falhou ([benchmark/README.md](../benchmark/README.md#conferência-ca-1)).
- **Aplicação:** `.venv/Scripts/python -m pytest app`, com os bancos de desenvolvimento no ar e o Node no `PATH` para os testes da tela, verifica os critérios CA-1 a CA-10, CA-12, CA-13 e CA-15 a CA-17 da [SPEC-004](specs/SPEC-004-aplicacao.md#critérios-de-aceitação) (cadastro de cliente, campanha, criação de link, redirecionamento, contador, gravação do clique, consultas de analytics, modelagem e painel), os pedidos rejeitados sem nada gravado, a falha de gravação no Redis e o clique descartado quando a gravação no Cassandra falha, em cerca de 30 s. Os testes usam o banco 15 do Redis, o banco `linkpulse_testes` do MongoDB e o keyspace `linkpulse_testes` do Cassandra, sem tocar nos dados da demonstração ([app/README.md](../app/README.md#como-testar)). `.venv/Scripts/python -m pytest app -m quedas` verifica o CA-11 e o CA-14 com a réplica do Redis e o Cassandra de fato parados: para cada contêiner com `docker compose stop`, confere que o redirecionamento continua respondendo `302`, com p95 abaixo de 50 ms e o contador de falhas subindo um por clique enquanto o Cassandra está parado, e religa o contêiner no fim, em 30 s a 1 min. Esses testes ficam fora de `pytest app` porque param bancos que a demonstração usa (Q-58, [app/README.md](../app/README.md#testes-com-a-réplica-e-o-cassandra-parados)).
- **Benchmark:** `python benchmark/medir.py` mede as quatro operações e o pico de tráfego nos dois lados (CA-2 da SPEC-005, [benchmark/README.md](../benchmark/README.md#gerador-de-carga)), e `python benchmark/calibrar.py` escolhe o número de conexões e confere que, com ele, o gerador fica abaixo de 70% da sua cota nessas quatro operações, parte do CA-3 ([calibração](../benchmark/README.md#calibração)). O pico de tráfego teve zero erros nas três operações do lado NoSQL (CA-5), com o CA-3 conferido nele ([pico de tráfego](../benchmark/README.md#pico-de-tráfego)). Numa execução de teste da queda do Cassandra, os redirecionamentos continuaram respondendo `302` com p95 no servidor de 1,5 ms, o contador continuou somando e a diferença entre o contador e o histórico foi igual às falhas de gravação ([queda do Cassandra](../benchmark/README.md#queda-do-cassandra)). Ainda faltam as 3 execuções da queda, a exibição das falhas na tela e a apresentação dos resultados ao vivo e gravados.

## Como a aplicação funciona

O cadastro de cliente, a campanha, a criação de link, o redirecionamento, com o contador e a gravação do clique, as consultas de analytics e o painel já estão implementados em [app/](../app/README.md). O comportamento completo e os critérios de aceitação estão na [SPEC-004](specs/SPEC-004-aplicacao.md):

- **Clientes:** `POST /clientes` cadastra um cliente pelo nome no Redis, e `GET /clientes` lista os da demonstração, sem os clientes carregados para o benchmark.
- **Campanhas:** `POST /campanhas` grava no MongoDB um documento com nome, descrição, tags e a lista de links da campanha, e `GET /campanhas` lista as campanhas de um cliente (Q-50).
- **Links:** `POST /links` gera um código de 7 caracteres, aleatório, com letras e dígitos, que nunca sobrescreve um código existente. A aplicação grava o link no Redis e só responde `201` depois que o Redis confirma a gravação; se a gravação falhar, responde `503`, sem código. Um pedido inválido é rejeitado com `422`, sem gravar nada (Q-40). `GET /links` lista os links de um cliente, com o contador de cada um (Q-54).
- **Redirecionamento:** `GET /r/{short_code}` responde `302` para a URL, `404` se o link não existe e `410` se ele expirou, como em [O caminho de um clique](#o-caminho-de-um-clique).
- **Consultas de analytics:** `GET /analytics/por-dia`, `GET /analytics/por-canal`, `GET /analytics/por-dispositivo` e `GET /analytics/total` contam os cliques de um intervalo: por dia de um link, com os dias de Brasília, por link entre os links de um cliente, por dispositivo de um link e no total de um link (Q-49). Cada consulta ao Cassandra lê a partição de um link, sem `ALLOW FILTERING` ([app/README.md](../app/README.md#as-consultas-de-analytics)).
- **Painel:** uma página HTML em `http://127.0.0.1:8000/`, servida pela própria aplicação, em que se escolhe ou cadastra um cliente, cadastra campanhas e cria links. Para o link escolhido, mostra nos últimos 7 dias (o dia do fechamento da janela e os 6 anteriores, em Brasília) o total de cliques, os cliques por dia e por dispositivo e a comparação entre os canais do cliente; mostra também o contador desde a criação e, se o link é de uma campanha, a descrição e as tags. A página refaz as consultas a cada 5 s, numa janela que fecha 5 s antes da leitura para reduzir as divergências entre as consultas, e só publica números que batem entre si; um clique novo aparece em cerca de 10 s (RNF-03). Os gráficos usam Chart.js 4.6.1, servido pela aplicação para funcionar sem internet ([ADR-0013](decisoes/ADR-0013-stack-e-ambiente-do-marco-2.md#decisão); [app/README.md](../app/README.md#a-tela)).

## Como analisar os resultados do benchmark

O gerador de carga já mede as quatro operações, o pico de tráfego (RM-43) e a queda do Cassandra (RM-44), e a calibração escolheu 8 conexões (RM-42). A tela de testes e as execuções completas ainda não foram implementadas (RM-32 e RM-33). Os números em [benchmark/README.md](../benchmark/README.md#gerador-de-carga) vêm do computador de desenvolvimento e não valem para a apresentação; a calibração precisa ser repetida na máquina da apresentação.

### O que é comparado

Quatro operações do produto, cada uma no banco NoSQL escolhido para ela e numa versão equivalente no PostgreSQL ([ADR-0012](decisoes/ADR-0012-marco-2-benchmark-sql-x-nosql.md#decisão)): redirecionamento (leitura do link), contador (incremento), registro de clique (uma inserção por clique) e histórico por período (cliques de um link nas últimas 24 horas da base, até 1.000 linhas). Além delas, dois cenários: o pico de tráfego, com as três operações do clique ao mesmo tempo no link popular, e a queda do Cassandra durante 30 s.

A sequência de seis etapas está na [SPEC-005](specs/SPEC-005-testes-de-stress.md#sequência-de-testes). A **execução ao vivo** roda uma vez em até 480 s e só ilustra. Os números que valem são os da **execução completa**: nas cinco primeiras etapas, cada lado roda por 60 s após 10 s de aquecimento. A sequência inteira é repetida três vezes. Publica-se a mediana das cinco primeiras etapas e o resultado de cada uma das três quedas do Cassandra.

### Como ler as métricas

- **Vazão:** operações concluídas com sucesso por segundo. Cada conexão espera a resposta antes de enviar o próximo pedido. Se o gerador demora para enviá-lo, o banco pode ficar à espera. Por isso, leia a vazão junto com o uso de CPU do gerador.
- **Latência p50, p95 e p99:** o tempo abaixo do qual ficam 50%, 95% e 99% das operações. O p50 é o caso típico; o p95 e o p99 mostram as pausas e filas que a mediana esconde.
- **Taxa de erro:** a fração das operações que falharam.
- **CPU do gerador:** os núcleos usados pelo próprio gerador e o percentual da sua cota. Para a comparação oficial, o percentual precisa ficar abaixo de 70% em cada etapa. A partir desse valor, o gerador pode estar limitando a carga que chega ao banco.
- **CPU do banco:** os núcleos usados pelo banco medido, na mesma janela. Um banco no teto, com o gerador abaixo de 70%, indica que o limite está no banco.
- **Na queda do Cassandra:** os cliques que falharam ao gravar e a diferença entre o contador e o histórico, isto é, os cliques que o contador somou e o histórico não tem. A taxa é fixa, de 200 por segundo, e por isso a vazão não muda. O que importa é o p95, medido no servidor, da chegada do pedido ao início da resposta. Também importa o tempo até a aplicação voltar a gravar depois do religamento.

### Antes de comparar: a medição vale?

- Os dois lados têm os mesmos dados (CA-1).
- Cada etapa roda um lado de cada vez, com o mesmo número de conexões e os mesmos tetos, e o uso de CPU do gerador fica registrado e abaixo de 70% (CA-3).
- A execução completa repete a sequência 3 vezes, restaura a cópia antes de cada repetição e antes do histórico por período, descarta o aquecimento e publica a mediana (CA-4).
- O número de conexões saiu da calibração com 8, 32 e 64 conexões, que fica registrada ([ADR-0014](decisoes/ADR-0014-modelo-de-dados-e-metodo-do-benchmark.md#como-a-carga-é-aplicada)).

### O que se espera

- **Não há vencedor previsto por operação.** Os números entram na apresentação como saírem; se o PostgreSQL vencer alguma operação, o resultado aparece com a explicação do motivo ([ADR-0012](decisoes/ADR-0012-marco-2-benchmark-sql-x-nosql.md#decisão)).
- **Pico de tráfego:** zero erros nas três operações do lado NoSQL (CA-5, RNF-04).
- **Queda do Cassandra:** em cada uma das 3 execuções, enquanto o Cassandra está parado, os redirecionamentos continuam respondendo `302` com p95 abaixo de 50 ms, o contador continua somando e os cliques que falharam aparecem na tela (CA-6; RNF-01, RNF-02, RN-07). O aviso de que o Cassandra poderia levar mais que os 30 s previstos para voltar ([ADR-0014](decisoes/ADR-0014-modelo-de-dados-e-metodo-do-benchmark.md#consequências)) foi verificado na execução de teste: ele voltou a aceitar conexões 14,5 s depois do religamento, e a aplicação voltou a gravar aos 75 s da etapa de 90 s, porque o driver espera no máximo 2 s entre as tentativas de reconexão ([medições](../benchmark/README.md#queda-do-cassandra)).
- **Tela de testes:** a execução ao vivo termina em até 480 s, e a execução completa salva abre sem internet, identificada como gravada (CA-7 e CA-8).

Os critérios completos estão na [SPEC-005](specs/SPEC-005-testes-de-stress.md#critérios-de-aceitação).

### Limites da comparação

- **Vale para este ambiente.** Os números mostram como cada operação se comportou com estes dados e estes tetos. Não provam que um banco é melhor em geral, nem dizem como o Cassandra escala em vários nós ([ADR-0012](decisoes/ADR-0012-marco-2-benchmark-sql-x-nosql.md#consequências)).
- **Cada banco confirma a escrita em um momento diferente.** No padrão, o PostgreSQL força a gravação no disco antes de confirmar; o Cassandra e o Redis gravam no disco de tempos em tempos. Por isso as duas escritas rodam uma segunda vez no PostgreSQL com essa espera desligada (`synchronous_commit=off`). Essa **curva extra** aparece à parte, identificada como fora do padrão, e separa o efeito da garantia de gravação do efeito do modelo de dados ([ADR-0014](decisoes/ADR-0014-modelo-de-dados-e-metodo-do-benchmark.md#garantia-de-gravação)).
- **O laço fechado esconde parte dos atrasos.** Quando um banco trava, o gerador também para de enviar, e o atraso que os pedidos não enviados teriam sofrido não entra na latência medida. Essa limitação entra na apresentação junto com os números ([ADR-0014](decisoes/ADR-0014-modelo-de-dados-e-metodo-do-benchmark.md#consequências)).
- **O teto de CPU pode pesar mais no Cassandra.** O script de partida do Cassandra decide quantas threads fazem a coleta de lixo da memória Java (GC) pelas CPUs que o contêiner enxerga, que são todas as da máquina, e não pelas 2 do teto. As pausas dessa coleta podem ficar mais longas só nesse lado; a questão continua aberta (Q-38 em [QUESTOES](requisitos/QUESTOES.md#abertas)).
- **Desempenho só na máquina dedicada.** As medições valem na máquina da apresentação, com os dados de referência carregados e os outros programas fechados.

## Termos

| Termo | Significado |
| --- | --- |
| Lado NoSQL | O Redis e o Cassandra, cada um nas operações para as quais foi escolhido |
| Lado PostgreSQL | O PostgreSQL fazendo as mesmas operações, sobre os mesmos dados |
| Base de referência | Os 150 clientes, 45 mil links e 10 milhões de cliques carregados nos dois lados, sempre os mesmos para a mesma semente ([benchmark/README.md](../benchmark/README.md#a-base)) |
| Link popular | O link que concentra 20% dos cliques da base, usado no pico de tráfego |
| Manifesto | O arquivo que descreve a base carregada: semente, período, link popular, janela do histórico e assinatura dos cliques. `base-de-referencia.json` é o espelho dele no Git |
| Cópia, geração e selo | A cópia dos volumes guardada para restauração. Cada cópia é uma geração, e o selo, gravado por último, marca a geração como completa |
| Trava | O contêiner de nome fixo que impede dois comandos da base de rodarem ao mesmo tempo |
| Teto | O limite de CPU e memória de cada contêiner, igual nos três bancos comparados |
| Laço fechado | Um número fixo de conexões, cada uma enviando a próxima operação só quando a anterior responde. Usado nas quatro operações e no pico |
| Laço aberto | Operações enviadas a uma taxa fixa, independente das respostas. Usado na queda do Cassandra, com 200 redirecionamentos por segundo |
| Calibração | A rodada com 8, 32 e 64 conexões que escolhe o número de conexões usado nos dois lados |
| Execução ao vivo e execução completa | A primeira ilustra durante a apresentação; a segunda produz os números publicados |
| Curva extra | As duas escritas no PostgreSQL com `synchronous_commit=off`, mostradas à parte |
| *Tombstone* | A marca que o Cassandra grava ao apagar uma linha e que deixa as leituras seguintes mais lentas; por isso a base é restaurada da cópia, e não limpa com exclusões |
