# SPEC-001 — Redirecionamento de link curto

> Exemplo mínimo do formato. O conteúdo reflete só o que já está documentado; os pontos em aberto aparecem como bloqueios.

- **Status:** Rascunho
- **Requisitos:** RF-02, RF-03, RF-04, RF-07, RNF-02, RNF-07, RN-03, RN-04, RN-07
- **Decisões:** ADR-0002, ADR-0003, ADR-0004, ADR-0006, ADR-0010
- **Bloqueios:** Q-22 (clique em link expirado), Q-09 (fonte da verdade da contagem), Q-14 (dados do clique)

## Objetivo

Resolver `GET /r/{short_code}` para a URL original, registrando o clique sem que o registro atrase a resposta.

## Fora de escopo

- Criação de links (RF-01) — spec própria.
- Consultas de analytics e painel (RF-05, RF-06).
- Filtro de bots (Q-16) e edição de URL (Q-10).

## Comportamento

Fluxo documentado em [FUNCIONALIDADES](../arquitetura/FUNCIONALIDADES.md) §Fluxo: redirecionamento:

1. Ler `link:{short_code}` no Redis com uma única operação (`HGETALL`).
2. Se a chave não existe, responder `404`. Se `expira_em` está no passado, responder `410` com página de expiração.
3. Caso contrário, responder `302` com `Location: {url}`.
4. Depois da resposta, executar `INCR contador:{short_code}` e gravar o evento em `cliques_por_link` de forma assíncrona.
5. Falha no passo 4 não altera a resposta já enviada; ela é registrada em log.

## Plano de implementação

Stack definida em [ADR-0010](../decisoes/ADR-0010-stack-da-aplicacao.md). Passos:

1. Leitura do link no Redis e decisão válido / expirado / inexistente.
2. Resposta `302` e respostas de erro.
3. Incremento do contador após a resposta.
4. Gravação assíncrona do evento no Cassandra, com tratamento de falha.
5. Testes de aceitação abaixo, incluindo o cenário com Cassandra indisponível.

## Critérios de aceitação

- [ ] **CA-1** (RF-02) — Dado um link existente sem `expira_em`, quando recebo `GET /r/{short_code}`, então a resposta é `302` com `Location` igual à `url` gravada.
- [ ] **CA-2** (RN-03, RF-07) — Dado um link com `expira_em` no passado, quando recebo `GET /r/{short_code}`, então a resposta é `410`.
- [ ] **CA-3** (RN-03) — Dado um `short_code` inexistente, quando recebo `GET /r/{short_code}`, então a resposta é `404`.
- [ ] **CA-4** (RN-04) — Dado um link sem `expira_em`, quando ele é acessado em qualquer data, então a resposta é `302`.
- [ ] **CA-5** (RF-03) — Dado um redirecionamento válido, quando o processamento assíncrono termina, então existe uma linha em `cliques_por_link` para aquele `short_code` e horário.
- [ ] **CA-6** (RF-04, RNF-07) — Dados N acessos concorrentes a um link válido, quando todos terminam, então `contador:{short_code}` aumentou exatamente N.
- [ ] **CA-7** (RNF-02, RN-07) — Dado o Cassandra indisponível, quando recebo `GET /r/{short_code}` válido, então a resposta continua `302` e a latência p95 medida no servidor fica abaixo de 50 ms.
