# ADR-0011 — Marco 1 entrega só a documentação exigida; o sistema completo fica para o Marco 2

- **Status:** Aceita
- **Data:** 2026-09-25
- **Decidido por:** Gabriel Becker
- **Relacionados:** Q-23, ADR-0008 (substituída), ADR-0010, EN-01 a EN-13

## Contexto

O [ADR-0008](ADR-0008-aplicacao-no-marco-1.md) previa uma aplicação funcional já no Marco 1. Revendo o prazo (vencimento no AVA em 29/09/2026 às 00:00) e o que a disciplina avalia ([DISCIPLINA](../produto/DISCIPLINA.md)), o grupo reduziu o escopo.

## Decisão

O Marco 1 entrega exatamente o que a disciplina pede:

1. descrição do problema — contexto, requisitos principais e estimativa de volume;
2. modelagem inicial dos dados — diagramas ou exemplos concretos;
3. justificativa tecnológica — conforme o checklist das Unidades 1 a 3.

A aplicação **não** é entregável do Marco 1 e não precisa estar completa nele. O sistema funcional é entregue no Marco 2. A stack definida no [ADR-0010](ADR-0010-stack-da-aplicacao.md) continua valendo para quando o desenvolvimento começar.

## Alternativas consideradas

- **Manter a aplicação no Marco 1 (ADR-0008)** — disputa tempo com a documentação, que é o que a nota do Marco 1 avalia.

## Consequências

- O roadmap do Marco 1 se concentra no checklist da disciplina, no PDF e na apresentação. Specs e implementação passam para o Marco 2.
- Os requisitos em [REQUISITOS.md](../requisitos/REQUISITOS.md) descrevem o sistema modelado no Marco 1 e implementado até o Marco 2.
- Metas medidas só em operação (disponibilidade mensal) continuam fora do escopo de verificação dos marcos.
