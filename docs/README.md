# Documentação do LinkPulse

Índice da documentação. Cada pasta tem um `README.md` que explica o seu conteúdo.

Para um percurso pelo projeto inteiro (processo, arquitetura, como rodar, como conferir e como analisar o benchmark), comece pelo [GUIA](GUIA.md).

| Pasta | Para quê | Comece por |
| --- | --- | --- |
| [produto/](produto/README.md) | Problema, público, pitch e regras da disciplina | [VISAO.md](produto/VISAO.md) |
| [arquitetura/](arquitetura/README.md) | Modelagem de dados, justificativa técnica e fluxos | [ARQUITETURA.md](arquitetura/ARQUITETURA.md) |
| [requisitos/](requisitos/README.md) | Funcionalidades, metas de qualidade, regras de negócio e questões abertas | [REQUISITOS.md](requisitos/REQUISITOS.md) |
| [decisoes/](decisoes/README.md) | Registro de decisões (ADR) | [README](decisoes/README.md) |
| [specs/](specs/README.md) | Especificações de entrega: plano e critérios de aceitação | [Aplicação](specs/SPEC-004-aplicacao.md) e [benchmark](specs/SPEC-005-testes-de-stress.md) |
| [roadmap/](roadmap/README.md) | Marcos e tarefas, com uma issue no GitHub para cada tarefa | [ROADMAP.md](roadmap/ROADMAP.md) |

## Como as peças se ligam

```
produto/ + arquitetura/  ──origem──▶  requisitos/  ──cobertos por──▶  specs/  ──quebradas em──▶  roadmap/  ──▶  PR
                                          ▲                              ▲
                                  questões respondidas            decisões (ADR)
```

O grupo registrou [como passa dos requisitos à implementação](decisoes/ADR-0001-desenvolvimento-guiado-por-especificacoes.md). Regras de contribuição em [CONTRIBUTING](../CONTRIBUTING.md); instruções para agentes em [AGENTS](../AGENTS.md).
