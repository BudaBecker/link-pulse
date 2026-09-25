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
