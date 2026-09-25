# Visão do Produto — LinkPulse

## O problema

Equipes de marketing digital divulgam o mesmo conteúdo em múltiplos canais — redes sociais, e-mail, anúncios pagos, parcerias com influenciadores — mas raramente conseguem responder, em tempo real, uma pergunta simples: **qual canal está trazendo resultado agora?**

Encurtadores de URL genéricos resolvem apenas o redirecionamento. Eles não foram pensados para o padrão de uso de uma campanha de marketing: um único link pode receber centenas de cliques por minuto durante um pico de viralização, e cada um desses cliques precisa virar um dado analisável — não apenas um número que sobe.

## Para quem é

- **Times de marketing digital** que gerenciam várias campanhas e canais simultaneamente e precisam decidir, no meio de uma campanha, onde investir mais.
- **Agências** que respondem a múltiplos clientes e precisam isolar o desempenho de cada um sem duplicar infraestrutura.
- **Times internos** que usam links de campanha como métrica de engajamento (ex.: newsletters, lançamentos de produto).

## Os dois compromissos centrais

1. **O redirecionamento nunca falha.** Um link de campanha é a própria promessa feita a quem clicou — se ele falhar, o orçamento gasto para gerar aquele clique foi desperdiçado.
2. **Todo clique é um dado, não apenas um número.** Timestamp, dispositivo, localização aproximada e canal de origem são registrados por clique, alimentando um painel de analytics que o time consulta diariamente para decidir onde reforçar investimento.

## Por que isso é difícil de fazer bem

O padrão de escrita de um encurtador de campanha é **imprevisível e explosivo**: a maior parte do tempo o tráfego é baixo, mas um post que viraliza pode gerar centenas de cliques por minuto em um único link, concentrados de forma que nenhum sistema administrativo tradicional precisa suportar. Ao mesmo tempo, o painel de analytics faz agregações constantes (cliques por dia, por canal, por período) sobre um volume de eventos que só cresce.

Essa combinação — leitura de latência mínima para o redirecionamento, escrita em rajada para os eventos de clique, e agregações contínuas para analytics — é o que orienta todas as decisões de modelagem de dados do projeto (ver [Arquitetura](../arquitetura/ARQUITETURA.md)).

## Diferenciais em relação a um encurtador genérico

| | Encurtador genérico | LinkPulse |
| --- | --- | --- |
| Foco | Redirecionamento | Redirecionamento + analytics por canal |
| Métrica exposta | Contagem total de cliques | Cliques por canal, dispositivo, região e período |
| Expiração de link | Raramente suportada | Suportada nativamente (campanhas sazonais) |
| Escala esperada | Tráfego relativamente estável | Picos de campanha, imprevisíveis e concentrados |
| Público | Uso geral | Times de marketing e agências |

## Próximos passos da visão

A visão de longo prazo inclui metadados de campanha mais ricos (tags, UTM, descrição) — um dado semiestruturado e mutável, diferente do evento de clique imutável. Essa evolução está descrita no [roadmap](../../README.md#roadmap) do projeto.
