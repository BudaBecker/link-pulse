# ADR-0001 — Adotar desenvolvimento guiado por especificações leve

- **Status:** Aceita
- **Data:** 2026-09-25
- **Decidido por:** Gabriel Becker
- **Relacionados:** Q-01, Q-07

## Contexto

A documentação do Marco 1 descreve o produto e a modelagem de dados, mas não diz como transformar esse conteúdo em trabalho implementável e rastreável. O time tem quatro integrantes e usa agentes de código. Sem um caminho único, requisitos se perdem entre documentos, decisões ficam implícitas e mudanças chegam sem critério de aceite.

## Decisão

Todo trabalho de implementação segue o caminho **requisito → especificação → tarefas → PR**:

1. requisitos catalogados em [`docs/requisitos/`](../requisitos/README.md), com ID, origem e critério verificável;
2. decisões arquiteturais e de produto registradas aqui, em `docs/decisoes/`;
3. uma especificação curta por entrega em [`docs/specs/`](../specs/README.md), com plano e critérios de aceitação;
4. as tarefas derivadas da spec ficam no [roadmap](../roadmap/README.md), cada uma com sua issue no GitHub;
5. cada PR cita a spec e os IDs de requisito que atende.

Nenhuma stack de implementação é escolhida por este ADR. A escolha exige um ADR próprio.

## Alternativas consideradas

- **Só issues no GitHub** — perde a visão consolidada dos requisitos e a origem de cada um na documentação.
- **Processo formal (SRS completo, matriz de rastreabilidade separada)** — custo alto para um time de quatro pessoas em projeto de disciplina.

## Consequências

- Requisitos e specs precisam ser atualizados no mesmo PR que muda o comportamento.
- A rastreabilidade fica nos próprios arquivos (colunas "Spec" e "Requisitos"), sem ferramenta extra.
- Mudanças só de documentação ou processo não precisam de spec.
