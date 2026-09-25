# Pitch — LinkPulse

## Em uma frase

**LinkPulse é o encurtador de links feito para quem vive de campanha:** cada clique é um dado, e nenhum redirecionamento pode falhar.

## O problema

Times de marketing rodam a mesma campanha em cinco canais diferentes e, no fim do dia, não sabem qual canal realmente converteu. Encurtadores genéricos entregam um número — "1.240 cliques" — quando a pergunta real é "quantos vieram do Instagram Stories vs. do e-mail, e em que horário?".

## A solução

Um encurtador de URLs desenhado, desde a modelagem de dados, para dois compromissos que um encurtador genérico não assume:

1. O link **nunca falha** — mesmo se um post viralizar e gerar centenas de cliques por minuto.
2. Cada clique **vira dado analisável** — dispositivo, região, canal, horário — disponível em um painel que o time consulta todos os dias, não só no fim da campanha.

## Por que agora / por que assim

O padrão de tráfego de uma campanha de marketing é o pior caso possível para um banco relacional único: escrita em rajada, imprevisível, competindo por I/O com as mesmas agregações que o time quer ver em tempo real. O LinkPulse resolve isso separando responsabilidades desde o dia 1:

- **Redis (Chave-Valor)** para o caminho crítico de latência — resolver `short_code → URL`.
- **Cassandra (Wide-Column)** para o histórico de cliques, modelado *query-first* em torno da pergunta que o negócio mais faz: "como este link performou em um período?".

Essa escolha é o que permite ao produto prometer disponibilidade mesmo sob pico — a prioridade é nunca perder um clique de redirecionamento, mesmo que o dashboard leve alguns segundos para refletir o número mais recente.

## Diferencial competitivo

| | Bit.ly / TinyURL | LinkPulse |
| --- | --- | --- |
| Granularidade do analytics | Totais agregados | Por canal, dispositivo, região e período |
| Resiliência a picos | Não é o foco declarado | Desenhado para picos de campanha desde a modelagem |
| Expiração de campanha | Recurso pago/limitado | Nativo |
| Público-alvo | Uso geral | Marketing digital e agências |

## Tração esperada (cenário do projeto)

~150 clientes, 300 links ativos por cliente, picos de até 500 cliques/minuto por link em lançamentos — volume suficiente para justificar uma arquitetura distribuída desde o início, não como otimização futura.

## Próximo passo

Marco 2: enriquecer o modelo com metadados de campanha (banco de Documentos), mantendo o mesmo compromisso de baixa latência no redirecionamento.
