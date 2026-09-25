# Requisitos do sistema

Catálogo de requisitos funcionais (RF), não funcionais (RNF) e regras de negócio (RN) do LinkPulse.

**Regra deste arquivo:** só entra aqui o que está escrito na documentação do projeto ou foi decidido pelo grupo em uma questão respondida (`Q-xx`). Cada item aponta para a sua origem. Propostas ainda não decididas ficam em [QUESTOES.md](QUESTOES.md).

## Como ler

| Campo | Significado |
| --- | --- |
| **ID** | Identificador estável. Nunca é reaproveitado; item removido fica com status `Descartado`. |
| **Origem** | Documento e seção de onde o requisito foi extraído, ou a questão que o decidiu. |
| **Critério verificável** | Condição objetiva de aceite. Valores ainda indefinidos aparecem como `[meta: Q-xx]`. |
| **Pendências** | Questões de [QUESTOES.md](QUESTOES.md) que precisam ser respondidas antes da implementação. |
| **Spec** | Especificação em [`../specs/`](../specs/README.md) que implementa o item (`—` se nenhuma). |
| **Status** | `Documentado` (ainda não coberto por spec pronta) · `Especificado` (spec `Pronta`) · `Implementado` · `Descartado`. |

Escopo: os itens abaixo descrevem o sistema **modelado no Marco 1** e implementado até o **Marco 2** ([ADR-0011](../decisoes/ADR-0011-marco-1-so-documentacao.md)). A direção de novas funcionalidades do Marco 2 está no fim do documento e não é requisito aprovado.

## Requisitos funcionais (RF)

| ID | Descrição | Origem | Critério verificável | Pendências | Spec | Status |
| --- | --- | --- | --- | --- | --- | --- |
| RF-01 | Criar link curto a partir de uma URL longa, com `cliente_id`, `canal` opcional (nome do canal de divulgação) e `expira_em` opcional, gerando um `short_code` não sequencial. | [FUNCIONALIDADES](../arquitetura/FUNCIONALIDADES.md) §Lista e §Fluxo: criação de link; Q-18 | `POST /links {url, cliente_id}` com URL válida retorna `201` com `short_code`; a chave `link:{short_code}` passa a conter `url`, `cliente_id`, `criado_em` e, se informados, `canal` e `expira_em`; o `short_code` passa a fazer parte do Set `links:cliente:{cliente_id}`. | Q-11 | — | Documentado |
| RF-02 | Redirecionar um `short_code` válido para a URL original. | [FUNCIONALIDADES](../arquitetura/FUNCIONALIDADES.md) §Fluxo: redirecionamento | `GET /r/{short_code}` de um link existente e não expirado retorna `302` com `Location` igual à `url` gravada. | — | [SPEC-001](../specs/SPEC-001-redirecionamento.md) | Documentado |
| RF-03 | Registrar cada clique como evento com timestamp, dispositivo, país/região e referrer. | [FUNCIONALIDADES](../arquitetura/FUNCIONALIDADES.md) §Lista; [ARQUITETURA](../arquitetura/ARQUITETURA.md) Passo 5 | Após um redirecionamento válido, existe uma linha em `cliques_por_link` com `short_code`, `clicado_em`, `pais`, `dispositivo` e `referrer` preenchidos (ou vazios, quando o dado não vier na requisição). | Q-14, Q-16 | [SPEC-001](../specs/SPEC-001-redirecionamento.md) | Documentado |
| RF-04 | Manter um contador de cliques por link consultável sem varrer o histórico. | [FUNCIONALIDADES](../arquitetura/FUNCIONALIDADES.md) §Lista; [ARQUITETURA](../arquitetura/ARQUITETURA.md) Passo 4 | Cada redirecionamento válido executa `INCR contador:{short_code}`; a leitura do total é uma única operação no Redis. | Q-09 | [SPEC-001](../specs/SPEC-001-redirecionamento.md) | Documentado |
| RF-05 | Oferecer consultas de analytics pré-definidas: cliques por link/dia, cliques por canal e total de cliques em uma janela de tempo. **Canal = link:** cada canal de divulgação usa o seu próprio link curto, e "cliques por canal" compara os links de um mesmo cliente (lidos do Set `links:cliente:{cliente_id}`), identificados pelo campo `canal`. | [FUNCIONALIDADES](../arquitetura/FUNCIONALIDADES.md) §Lista; Q-04 (opção b); Q-18 | Para um conjunto de eventos conhecido, cada consulta retorna exatamente as contagens esperadas: por dia de um link, por link entre os links de um cliente, e no intervalo `[início, fim]`. | — | — | Documentado |
| RF-06 | Painel de analytics que mostra os cliques de um link em um período, agregados por dia, canal e dispositivo. | [FUNCIONALIDADES](../arquitetura/FUNCIONALIDADES.md) §Fluxo: consulta de analytics; Q-21 | Uma página HTML servida pela aplicação, ao pedir "cliques do link X nos últimos 7 dias", exibe os agregados por dia e dispositivo, e a comparação entre canais do mesmo cliente, coerentes com RF-05. | — | — | Documentado |
| RF-07 | Permitir expiração opcional de links. | [FUNCIONALIDADES](../arquitetura/FUNCIONALIDADES.md) §Lista; [VISAO](../produto/VISAO.md) §Diferenciais | Um link criado com `expira_em` deixa de redirecionar após essa data (ver RN-03); um link criado sem `expira_em` continua redirecionando (ver RN-04). | — | [SPEC-001](../specs/SPEC-001-redirecionamento.md) | Documentado |

## Requisitos não funcionais (RNF)

| ID | Descrição | Origem | Critério verificável | Pendências | Spec | Status |
| --- | --- | --- | --- | --- | --- | --- |
| RNF-01 | O redirecionamento prioriza disponibilidade sobre consistência (AP no teorema CAP): prefere servir um dado momentaneamente desatualizado a falhar. Meta operacional: disponibilidade mensal ≥ 99,9%. | [ARQUITETURA](../arquitetura/ARQUITETURA.md) Passo 6 §CAP; [VISAO](../produto/VISAO.md) §Compromissos; Q-03 | No ambiente de teste, com uma réplica do Redis ou o Cassandra derrubados, o redirecionamento continua respondendo `302`. A meta mensal só é medida em operação real ([ADR-0011](../decisoes/ADR-0011-marco-1-so-documentacao.md)). | Q-17 | — | Documentado |
| RNF-02 | A resposta do redirecionamento não espera a gravação do evento de clique (escrita assíncrona). | [FUNCIONALIDADES](../arquitetura/FUNCIONALIDADES.md) §Fluxo: redirecionamento; [ARQUITETURA](../arquitetura/ARQUITETURA.md) Passo 3; Q-03 | Com o Cassandra lento ou indisponível, o redirecionamento continua respondendo `302` com latência p95 < 50 ms, medida no servidor. | — | [SPEC-001](../specs/SPEC-001-redirecionamento.md) | Documentado |
| RNF-03 | O analytics é eventualmente consistente: o painel pode mostrar números com defasagem. | [ARQUITETURA](../arquitetura/ARQUITETURA.md) Passo 6 §BASE e §Trade-offs; Q-03 | Um clique registrado aparece no painel em até 60 s. | — | — | Documentado |
| RNF-04 | Suportar picos de campanha concentrados em um único link. Volume de referência (cenário assumido, não medido): ~150 clientes, ~45.000 links ativos, até ~500 cliques/min em um link. | [ARQUITETURA](../arquitetura/ARQUITETURA.md) §Estimativa de volume; [PITCH](../produto/PITCH.md) §Tração | Teste de carga com 500 cliques/min em um único `short_code` por 10 min sem erro de redirecionamento e sem perda de eventos acima do tolerado por RN-07. | Q-12 | — | Documentado |
| RNF-05 | Escalar horizontalmente, com particionamento hash por `short_code`, replicação Master-Slave no Redis e Master-Master no Cassandra. | [ARQUITETURA](../arquitetura/ARQUITETURA.md) Passo 2 §Problema 2 e Passo 6 §Sharding/§Replicação; [ADR-0009](../decisoes/ADR-0009-replicacao-por-banco.md) | A partition key de `cliques_por_link` é `short_code`; o ambiente declara um master e ao menos uma réplica no Redis e um fator de replicação no keyspace do Cassandra. | Q-12 | — | Documentado |
| RNF-06 | Modelagem *query-first*: cada consulta do painel é atendida lendo uma única partição, em ordem de `clicado_em DESC`. | [ARQUITETURA](../arquitetura/ARQUITETURA.md) Passos 1 e 5 | Nenhuma consulta CQL do produto usa `ALLOW FILTERING` nem omite a partition key; a tabela declara `CLUSTERING ORDER BY (clicado_em DESC)`. | — | — | Documentado |
| RNF-07 | O contador não perde incrementos por condição de corrida. | [ARQUITETURA](../arquitetura/ARQUITETURA.md) Passo 4 §Contador | Com N redirecionamentos concorrentes em um mesmo link e o Redis disponível, o contador aumenta exatamente N. | — | [SPEC-001](../specs/SPEC-001-redirecionamento.md) | Documentado |
