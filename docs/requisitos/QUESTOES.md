# Questões

Dúvidas, lacunas e contradições encontradas na documentação. Uma questão aberta bloqueia os requisitos e specs que a citam.

Quando uma questão for respondida:

1. se a decisão atravessa vários requisitos (tecnologia, modelo, escopo), registre um ADR em [`../decisoes/`](../decisoes/README.md);
2. atualize os requisitos afetados em [REQUISITOS.md](REQUISITOS.md) (descrição, critério, origem `Q-xx`, pendências);
3. mova a linha para **Respondidas**, com a resposta e o link de onde ela foi registrada.

A coluna "Proposta" é só uma sugestão para acelerar a decisão; ela não vale como requisito.

## Abertas

| ID | Tipo | Questão | Origem | Afeta | Proposta (não aprovada) |
| --- | --- | --- | --- | --- | --- |
| Q-09 | Contradição | O contador Redis é "recalculável a partir do histórico", mas a perda pontual de cliques no Cassandra é aceita — os dois podem divergir. Qual é a fonte da verdade da contagem? | [ARQUITETURA](../arquitetura/ARQUITETURA.md) Passo 4 × §Trade-offs | RF-04, RN-05, RN-07 | Cassandra é a fonte da verdade do histórico; o contador é aproximação e pode ser maior |
| Q-10 | Lacuna | O exemplo do CAP cita "URL editada", mas não há funcionalidade de edição de link. Links são editáveis? | [ARQUITETURA](../arquitetura/ARQUITETURA.md) Passo 6 §CAP | — | Fora do Marco 1; `url` imutável após a criação |
| Q-11 | Lacuna | Código aleatório não "evita colisões" por si só. Qual alfabeto, tamanho e tratamento de colisão? | [FUNCIONALIDADES](../arquitetura/FUNCIONALIDADES.md) §Criação | RF-01, RN-01 | Base62, 7 caracteres, gravação condicional (`HSETNX`/verificação de existência) e nova tentativa em colisão |
| Q-12 | Lacuna | A partição `short_code` cresce sem limite (500 cliques/min em pico). Adotar *bucket* por período na partition key? | [ARQUITETURA](../arquitetura/ARQUITETURA.md) Passo 5 × §Estimativa | RNF-04, RNF-05 | Manter `short_code` no Marco 1 e registrar `(short_code, dia)` como evolução |
| Q-13 | Lacuna | Autenticação e isolamento por cliente (agências): exigidos no Marco 1? `cliente_id` não está no Cassandra. | [VISAO](../produto/VISAO.md) §Para quem é; [FUNCIONALIDADES](../arquitetura/FUNCIONALIDADES.md) `POST /links` | RN-02 | Fora do Marco 1; `cliente_id` informado na criação, sem autenticação |
| Q-14 | Lacuna | Como obter país/região (GeoIP?) e quais dados pessoais são guardados (IP, user-agent)? Retenção e LGPD? | [FUNCIONALIDADES](../arquitetura/FUNCIONALIDADES.md) §Registro de cliques | RF-03 | Não armazenar IP; país por cabeçalho ou base GeoIP local; dispositivo derivado do user-agent; retenção a definir |
| Q-15 | Inconsistência | Afirmações sobre concorrentes divergem: VISAO diz que expiração é "raramente suportada"; PITCH diz "recurso pago/limitado" no Bit.ly. Não há fonte citada. | [VISAO](../produto/VISAO.md) §Diferenciais × [PITCH](../produto/PITCH.md) §Diferencial | Nenhum requisito | Tratar como posicionamento; citar fonte ou suavizar o texto |
| Q-16 | Lacuna | Cliques de bots/crawlers (pré-visualização de links em redes sociais) entram nas métricas? | Não documentado | RF-03, RF-05 | Fora do Marco 1; registrar como está |
| Q-17 | Lacuna | O mapeamento `link:{short_code}` só existe no Redis (em memória). Se ele for perdido, os links deixam de redirecionar — o oposto do compromisso central. Qual a durabilidade exigida? | [ARQUITETURA](../arquitetura/ARQUITETURA.md) Passo 4 (só o contador é declarado *soft state*) | RNF-01, RN-08 | Persistência AOF ligada no Redis + réplica (ADR-0009) |
| Q-22 | Lacuna | Clique em link expirado (`410`) é registrado como evento ou conta no contador? | Q-06 | RN-03, RF-03, RF-04 | Não registrar nem contar |

## Respondidas

| ID | Questão | Resposta | Registrada em |
| --- | --- | --- | --- |
| Q-01 | Haverá aplicação executável, e quando? | Sim. Primeiro previsto para o Marco 1, depois revisto: o sistema é entregue no Marco 2 | [ADR-0008](../decisoes/ADR-0008-aplicacao-no-marco-1.md), substituída por [ADR-0011](../decisoes/ADR-0011-marco-1-so-documentacao.md) |
| Q-02 | Os documentos atuais podem ser movidos ou alterados? | Sim, para a melhor organização | [docs/README.md](../README.md) (nova estrutura) |
| Q-03 | Metas de disponibilidade, latência e defasagem | Disponibilidade mensal ≥ 99,9%; p95 do redirecionamento < 50 ms; defasagem do painel ≤ 60 s | RNF-01, RNF-02, RNF-03 em [REQUISITOS.md](REQUISITOS.md) |
| Q-04 | Como o canal de um clique é determinado? | Um link curto por canal | RF-05 em [REQUISITOS.md](REQUISITOS.md) (detalhe em Q-18) |
| Q-05 | "Master-Slave" para o sistema todo, com Cassandra *masterless* | Seguir o checklist da disciplina: Redis Master-Slave, Cassandra Master-Master | [ADR-0009](../decisoes/ADR-0009-replicacao-por-banco.md) |
| Q-06 | Resposta para link inexistente e expirado | `404` para inexistente, `410` para expirado | RN-03 em [REQUISITOS.md](REQUISITOS.md) (registro do clique em Q-22) |
| Q-07 | Fluxo Git | PR obrigatório com revisão obrigatória (autor, colega ou agente), squash merge, branch apagada após o merge | [CONTRIBUTING](../../CONTRIBUTING.md) |
| Q-08 | Onde organizar as tarefas e o andamento? | Todo no GitHub: uma issue por tarefa do roadmap, milestone por marco, sub-issue para tarefa complementar; andamento pelo estado da issue e do PR | [roadmap](../roadmap/README.md) |
| Q-19 | Prazo do Marco 1 | Vencimento no AVA: 29/09/2026 às 00:00 — enviar até a noite de 28/09 | [DISCIPLINA](../produto/DISCIPLINA.md) |
| Q-20 | Stack da aplicação | Python + FastAPI, `redis-py`, `cassandra-driver`, Docker Compose com Redis (master + réplica) e Cassandra | [ADR-0010](../decisoes/ADR-0010-stack-da-aplicacao.md) |
| Q-21 | Forma do painel de analytics | Página HTML servida pela própria aplicação, gráfico via biblioteca em CDN | RF-06 em [REQUISITOS.md](REQUISITOS.md); [ADR-0010](../decisoes/ADR-0010-stack-da-aplicacao.md) |
| Q-18 | Com "canal = link", como o painel sabe o nome do canal e quais links são de um cliente? | Campo opcional `canal` no Hash `link:{short_code}` e Set `links:cliente:{cliente_id}` no Redis | RF-01, RF-05 em [REQUISITOS.md](REQUISITOS.md); [ARQUITETURA](../arquitetura/ARQUITETURA.md) Passo 4 |
| Q-23 | O que a aplicação precisa cumprir no Marco 1? | Nada: o Marco 1 entrega só descrição do problema, modelagem e justificativa; o sistema fica para o Marco 2 | [ADR-0011](../decisoes/ADR-0011-marco-1-so-documentacao.md) |
