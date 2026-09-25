# ADR-0008 — Entregar uma aplicação funcional já no Marco 1

- **Status:** Substituída por [ADR-0011](ADR-0011-marco-1-so-documentacao.md)
- **Data:** 2026-09-25
- **Decidido por:** Gabriel Becker
- **Relacionados:** Q-01, EN-15, RM-16

## Contexto

As regras da disciplina ([DISCIPLINA](../produto/DISCIPLINA.md)) pedem só modelagem e justificativa no Marco 1 e deixam o sistema funcional para o Marco 2. A questão Q-01 perguntava se o LinkPulse teria implementação e quando.

## Decisão

O grupo entrega uma aplicação funcional já no Marco 1, implementando os requisitos do Marco 1 em [REQUISITOS.md](../requisitos/REQUISITOS.md). O Marco 2 evolui essa aplicação.

A stack (linguagem, framework, infraestrutura) **não** é definida por este ADR. Ela exige um ADR próprio (RM-16), que precisa estar `Aceita` antes do primeiro código.

## Alternativas consideradas

- **Só modelagem no Marco 1** (mínimo exigido pela disciplina) — adia o risco técnico para o Marco 2, que já concentra a integração de novas famílias NoSQL.

## Consequências

- O prazo do Marco 1 passa a incluir implementação: o roadmap prioriza o ADR de stack e as specs do caminho crítico (redirecionamento e criação de link).
- Metas de RNF que só podem ser medidas em operação real (disponibilidade mensal) ficam verificadas por projeto e por teste de falha no Marco 1, não por medição.
- O PDF do Marco 1 continua sendo a entrega avaliada; a aplicação é complemento para a apresentação.
