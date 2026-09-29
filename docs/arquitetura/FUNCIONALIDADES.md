# Funcionalidades

## Lista de funcionalidades (Marco 1)

- **Criação de link curto.** Gera um código não sequencial a partir de uma URL longa, evitando previsibilidade. Cada canal de divulgação ganha o seu próprio link, identificado por um nome de canal opcional.
- **Redirecionamento de baixa latência.** Resolve `short_code → URL original` com prioridade em disponibilidade, mesmo sob pico de tráfego.
- **Registro de cliques como eventos.** Cada clique grava timestamp, dispositivo, país/região e referrer.
- **Contador de cliques em tempo real.** Métrica agregada disponível instantaneamente, sem depender de varredura do histórico completo.
- **Consultas de analytics pré-definidas.** Cliques por link/dia, cliques por canal, total de cliques em uma janela de tempo.
- **Expiração opcional de links.** Suporte a campanhas sazonais e promoções com prazo definido.

## Arquitetura geral

```mermaid
flowchart LR
    subgraph Cliente
        U[Usuário final]
        M[Time de marketing]
    end

    subgraph LinkPulse
        API[API de criação de links]
        RD[Redirecionador]
        KV[("Redis (Chave-Valor)\nlink:short_code\ncontador:short_code\nlinks:cliente:cliente_id")]
        WC[("Cassandra (Wide-Column)\ncliques_por_link")]
        AN[Serviço de Analytics]
        DASH[Painel de Analytics]
    end

    M -->|cria link| API
    API -->|grava mapeamento| KV
    U -->|clica no link curto| RD
    RD -->|lê URL original| KV
    RD -->|redireciona| U
    RD -->|INCR contador| KV
    RD -->|registra evento assíncrono| WC
    AN -->|agrega por link/período| WC
    AN --> DASH
    M -->|consulta| DASH
```

## Fluxo: criação de link

```mermaid
sequenceDiagram
    participant M as Time de marketing
    participant API as API de criação
    participant KV as Redis (Hash)

    M->>API: POST /links {url, cliente_id, canal?, expira_em?}
    API->>API: gera short_code não sequencial
    API->>KV: HSET link:{short_code} url, cliente_id, canal, criado_em, expira_em
    API->>KV: SADD links:cliente:{cliente_id} {short_code}
    KV-->>API: OK
    API-->>M: 201 Created {short_code}
```

## Fluxo: redirecionamento (caminho crítico de latência)

```mermaid
sequenceDiagram
    participant U as Usuário final
    participant RD as Redirecionador
    participant KV as Redis (Chave-Valor)
    participant WC as Cassandra (Wide-Column)

    U->>RD: GET /r/{short_code}
    RD->>KV: HGETALL link:{short_code}
    KV-->>RD: {url, expira_em}
    alt link expirado ou inexistente
        RD-->>U: 404 (inexistente) / 410 + página de expiração (expirado)
    else link válido
        RD-->>U: 302 Redirect para url
        RD->>KV: INCR contador:{short_code}
        RD->>WC: INSERT INTO cliques_por_link (async)
    end
```

O redirecionamento em si (linhas 1–3 e o `302`) não espera a escrita do histórico de cliques — ela é assíncrona, para que um pico de escrita no Wide-Column nunca aumente a latência percebida pelo usuário final.

## Fluxo: consulta de analytics

```mermaid
sequenceDiagram
    participant M as Time de marketing
    participant DASH as Painel de Analytics
    participant WC as Cassandra (Wide-Column)

    M->>DASH: "cliques do link X nos últimos 7 dias"
    DASH->>WC: SELECT * FROM cliques_por_link WHERE short_code = 'X' AND clicado_em >= ?
    WC-->>DASH: cliques ordenados (mais recente primeiro)
    DASH-->>M: gráfico agregado por dia/canal/dispositivo
```

## Funcionalidades futuras (preview do Marco 2)

- Metadados de campanha (tags, descrição, UTM) em um banco de **Documentos**, permitindo enriquecer o link sem impactar o modelo de eventos imutáveis do histórico de cliques.
