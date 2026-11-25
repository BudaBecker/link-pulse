"use strict";
// Tela de testes do benchmark (SPEC-005; Q-70 a Q-75). Sem framework e sem etapa de build.

const ETAPAS = {
  redirecionamento: {
    titulo: "1. Redirecionamento",
    descricao: "Leitura do link: HGETALL no Redis x SELECT pela chave no PostgreSQL.",
  },
  contador: {
    titulo: "2. Contador",
    descricao: "Incremento: INCR no Redis x UPDATE contadores SET total = total + 1 no PostgreSQL.",
  },
  registro: {
    titulo: "3. Registro de clique",
    descricao: "INSERT individual no Cassandra x no PostgreSQL, mais a curva extra fora do padrão.",
  },
  historico: {
    titulo: "4. Histórico por período",
    descricao: "Cliques de um link em 24 horas, com limite de 1.000 linhas: Cassandra x PostgreSQL.",
  },
  pico: {
    titulo: "5. Pico de tráfego",
    descricao: "Leitura, contador e registro em sequência no link popular; a vazão conta cliques completos.",
  },
  queda: {
    titulo: "6. Queda do Cassandra",
    descricao: "200 redirecionamentos por segundo pela aplicação; o Cassandra para aos 30 s e é religado aos 60 s.",
  },
};
const OPERACOES_DO_PICO = ["redirecionamento", "contador", "registro"];
const NOME_NO_PICO = { redirecionamento: "leitura", contador: "contador", registro: "registro" };
const TRACOS_DO_PICO = [[], [6, 4], [2, 3]];
const METRICAS = {
  vazao: "Vazão (ops/s)",
  p95: "p95 (ms)",
  cpu: "CPU do banco (% da cota)",
  memoria: "Memória do banco (MiB)",
};
const METRICAS_DA_QUEDA = { respostas: "Respostas e falhas por segundo", p95: "p95 no servidor (ms)" };
const TETO_P95_QUEDA_MS = 50; // RNF-02
const ORCAMENTO_PADRAO_S = 480;

const inteiro = new Intl.NumberFormat("pt-BR", { maximumFractionDigits: 0 });
const decimal = new Intl.NumberFormat("pt-BR", { maximumFractionDigits: 3 });
const percentual = new Intl.NumberFormat("pt-BR", { style: "percent", maximumFractionDigits: 3 });
const dataHora = new Intl.DateTimeFormat("pt-BR", { dateStyle: "short", timeStyle: "short" });

const $ = (id) => document.getElementById(id);
const cor = (nome) => getComputedStyle(document.documentElement).getPropertyValue(nome).trim();
const CORES = { nosql: cor("--nosql"), postgres: cor("--postgres"), falha: cor("--falha"), cinza: cor("--secundario") };

function nomeDoLado(execucao) {
  if (execucao.curva_extra) return "PostgreSQL, synchronous_commit=off (fora do padrão)";
  return execucao.lado === "nosql" ? "NoSQL" : "PostgreSQL";
}

function classeDoLado(execucao) {
  return execucao.curva_extra ? "extra" : execucao.lado;
}

const ms = (valor) => (valor == null ? "—" : decimal.format(valor));
const num = (valor) => (valor == null ? "—" : inteiro.format(valor));
const taxa = (valor) => (valor == null ? "—" : percentual.format(valor));

// Faixas sombreadas (aquecimento, janela do CA-6) e linhas verticais (parada, religamento, volta).
const pluginFaixas = {
  id: "faixas",
  beforeDatasetsDraw(grafico, _argumentos, opcoes) {
    const { ctx, chartArea: area, scales: { x } } = grafico;
    ctx.save();
    ctx.font = "11px system-ui, sans-serif";
    ctx.textBaseline = "top";
    for (const faixa of opcoes.faixas || []) {
      const de = x.getPixelForValue(faixa.de);
      const ate = x.getPixelForValue(faixa.ate);
      ctx.fillStyle = "rgba(102, 89, 106, 0.12)";
      ctx.fillRect(de, area.top, ate - de, area.bottom - area.top);
      ctx.fillStyle = CORES.cinza;
      ctx.fillText(faixa.rotulo, de + 4, area.top + 4);
    }
    (opcoes.marcos || []).forEach((marco, i) => {
      const px = x.getPixelForValue(marco.x);
      ctx.strokeStyle = CORES.cinza;
      ctx.setLineDash([3, 3]);
      ctx.beginPath();
      ctx.moveTo(px, area.top);
      ctx.lineTo(px, area.bottom);
      ctx.stroke();
      ctx.setLineDash([]);
      ctx.fillStyle = cor("--texto");
      ctx.fillText(marco.rotulo, px + 3, area.top + 20 + i * 13);
    });
    ctx.restore();
  },
};

let estado = novoEstado();

function novoEstado() {
  return {
    modo: null, // "ao_vivo" ou "gravada"
    rodando: false,
    etapas: {}, // etapa -> {execucoes, grafico, metrica, elementos}
    atual: null,
    gravacao: null,
    repeticao: 0,
    orcamento: ORCAMENTO_PADRAO_S,
    decorrido: null,
    recebidoEm: null,
    iniciadaEm: null,
    concluida: null,
  };
}

// ---------- Montagem das etapas ----------

function montar(plano) {
  for (const etapa of Object.values(estado.etapas)) etapa.grafico?.destroy();
  estado.etapas = {};
  const main = $("etapas");
  main.replaceChildren();
  for (const nome of Object.keys(ETAPAS)) {
    const execucoes = plano.filter((p) => p.etapa === nome).map((p) => ({
      etapa: nome, lado: p.lado, curva_extra: !!p.curva_extra, aquecimento_s: p.aquecimento_s ?? 0,
      duracao_s: p.duracao_s, serie: [], recursos: [], resultado: null, iniciada: false,
    }));
    if (!execucoes.length) continue;
    const metricas = nome === "queda" ? METRICAS_DA_QUEDA : METRICAS;
    const secao = document.createElement("section");
    secao.className = `etapa ${nome}`;
    secao.innerHTML = `
      <header><h2>${ETAPAS[nome].titulo}</h2><span class="estado">aguardando</span></header>
      <p class="descricao">${ETAPAS[nome].descricao}</p>
      <div class="abas" role="group" aria-label="Métrica das curvas"></div>
      <div class="grafico"><canvas role="img" aria-label="Curvas de ${ETAPAS[nome].titulo}"></canvas></div>
      <p class="ate-agora" hidden></p>
      <div class="placar-rolagem"></div>`;
    main.append(secao);
    const etapa = {
      execucoes, metrica: Object.keys(metricas)[0],
      elementos: {
        secao, estado: secao.querySelector(".estado"), abas: secao.querySelector(".abas"),
        placar: secao.querySelector(".placar-rolagem"), ateAgora: secao.querySelector(".ate-agora"),
      },
    };
    for (const [chave, rotulo] of Object.entries(metricas)) {
      const botao = document.createElement("button");
      botao.type = "button";
      botao.textContent = rotulo;
      botao.setAttribute("aria-pressed", String(chave === etapa.metrica));
      botao.addEventListener("click", () => {
        etapa.metrica = chave;
        for (const b of etapa.elementos.abas.children) b.setAttribute("aria-pressed", String(b === botao));
        desenhar(nome);
      });
      etapa.elementos.abas.append(botao);
    }
    etapa.grafico = criarGrafico(secao.querySelector("canvas"));
    estado.etapas[nome] = etapa;
    desenhar(nome);
    placar(nome);
  }
}

function criarGrafico(canvas) {
  return new Chart(canvas, {
    type: "line",
    data: { datasets: [] },
    options: {
      animation: false,
      maintainAspectRatio: false,
      parsing: false,
      interaction: { mode: "nearest", axis: "x", intersect: false },
      elements: { point: { radius: 0 }, line: { borderWidth: 2, tension: 0 } },
      scales: {
        x: { type: "linear", min: 0, title: { display: true, text: "segundos desde a partida de cada lado" } },
        y: { beginAtZero: true, title: { display: true, text: "" } },
      },
      plugins: {
        legend: { position: "bottom", labels: { boxHeight: 2 } },
        faixas: { faixas: [], marcos: [] },
        tooltip: { callbacks: { title: (itens) => (itens.length ? `${decimal.format(itens[0].parsed.x)} s` : "") } },
      },
    },
    plugins: [pluginFaixas],
  });
}

// ---------- Curvas ----------

const noMeio = (linha) => linha.s + 0.5; // a linha da série cobre o segundo [s, s + 1)

function vazaoNoSegundo(etapa, linha) {
  // No pico, um clique completo termina no registro, a última operação do ciclo (Q-71).
  const operacao = etapa === "pico" ? "registro" : etapa;
  return linha.por_operacao?.[operacao]?.ops ?? null;
}

function conjuntos(nome) {
  const etapa = estado.etapas[nome];
  if (nome === "queda") return conjuntosDaQueda(etapa);
  const lista = [];
  for (const ex of etapa.execucoes) {
    const base = {
      label: nomeDoLado(ex), borderColor: CORES[ex.lado], backgroundColor: CORES[ex.lado],
      borderDash: ex.curva_extra ? [6, 4] : [],
    };
    if (etapa.metrica === "vazao") {
      lista.push({ ...base, data: ex.serie.map((l) => ({ x: noMeio(l), y: vazaoNoSegundo(nome, l) })) });
    } else if (etapa.metrica === "p95") {
      const operacoes = nome === "pico" ? OPERACOES_DO_PICO : [nome];
      operacoes.forEach((op, i) => lista.push({
        ...base,
        label: nome === "pico" ? `${base.label} · ${NOME_NO_PICO[op]}` : base.label,
        borderDash: nome === "pico" ? TRACOS_DO_PICO[i] : base.borderDash,
        data: ex.serie.map((l) => ({ x: noMeio(l), y: l.por_operacao?.[op]?.p95_ms ?? null })),
      }));
    } else {
      const campo = etapa.metrica === "cpu" ? "cpu_pct" : "mem_mib";
      const bancos = [...new Set(ex.recursos.flatMap((r) => Object.keys(r.bancos)))];
      bancos.forEach((banco, i) => lista.push({
        ...base,
        label: `${base.label} · ${banco}`,
        borderDash: ex.curva_extra ? [6, 4] : i ? [2, 3] : [],
        data: ex.recursos.map((r) => ({ x: r.t, y: r.bancos[banco]?.[campo] ?? null })),
      }));
    }
  }
  return lista;
}

function falhasPorSegundo(serie) {
  return serie.map((l, i) => {
    const antes = i ? serie[i - 1].falhas_na_etapa : 0;
    const agora = l.falhas_na_etapa;
    return { x: noMeio(l), y: agora == null || antes == null ? null : agora - antes };
  });
}

function conjuntosDaQueda(etapa) {
  const serie = etapa.execucoes[0]?.serie ?? [];
  if (etapa.metrica === "p95") {
    return [
      { label: "p95 no servidor", borderColor: CORES.nosql, data: serie.map((l) => ({ x: noMeio(l), y: l.p95_servidor_ms })) },
      {
        label: `teto do RNF-02 (${TETO_P95_QUEDA_MS} ms)`, borderColor: CORES.cinza, borderDash: [6, 4],
        data: [{ x: 0, y: TETO_P95_QUEDA_MS }, { x: 90, y: TETO_P95_QUEDA_MS }],
      },
    ];
  }
  return [
    {
      label: "redirecionamentos com 302 por segundo", borderColor: CORES.nosql, backgroundColor: CORES.nosql,
      data: serie.map((l) => ({ x: noMeio(l), y: l.respostas_302 })),
    },
    {
      label: "cliques que falharam ao gravar, por segundo", borderColor: CORES.falha, backgroundColor: CORES.falha,
      data: falhasPorSegundo(serie),
    },
  ];
}

function desenhar(nome) {
  const etapa = estado.etapas[nome];
  if (!etapa) return;
  const grafico = etapa.grafico;
  const ex = etapa.execucoes[0];
  const metricas = nome === "queda" ? METRICAS_DA_QUEDA : METRICAS;
  grafico.data.datasets = conjuntos(nome);
  grafico.options.scales.x.max = Math.max(...etapa.execucoes.map((e) => e.aquecimento_s + e.duracao_s));
  grafico.options.scales.y.title.text = metricas[etapa.metrica];
  const opcoes = grafico.options.plugins.faixas;
  if (nome === "queda") {
    const r = ex.resultado;
    opcoes.faixas = r ? [{ de: r.queda.janela_s[0], ate: r.queda.janela_s[1], rotulo: "janela do CA-6" }] : [];
    // Montado antes de atribuir: ler de volta uma opção do Chart.js devolve uma cópia.
    const marcos = [{ x: 30, rotulo: "parada" }, { x: 60, rotulo: "religamento" }];
    if (r?.marcos?.gravacao_voltou_s != null) marcos.push({ x: r.marcos.gravacao_voltou_s, rotulo: "volta da gravação" });
    opcoes.marcos = marcos;
  } else {
    opcoes.faixas = ex.aquecimento_s ? [{ de: 0, ate: ex.aquecimento_s, rotulo: "aquecimento (descartado)" }] : [];
    opcoes.marcos = [];
  }
  grafico.update("none");
}

// ---------- Placar ----------

function celulasDeMetricas(m) {
  return `<td>${num(m.vazao_ops)}</td><td>${ms(m.p50_ms)}</td><td>${ms(m.p95_ms)}</td><td>${ms(m.p99_ms)}</td>`
    + `<td>${num(m.erros)} (${taxa(m.taxa_erro)})</td>`;
}

function rotuloDoLado(ex, extra = "") {
  return `<span class="lado ${classeDoLado(ex)}"></span>${nomeDoLado(ex)}${extra}`;
}

function placar(nome) {
  const etapa = estado.etapas[nome];
  if (nome === "queda") return placarDaQueda(etapa);
  const gravada = estado.modo === "gravada";
  // Gravada: a mediana das repetições (CA-4); ao vivo: o resultado de cada execução, quando ela termina.
  const linhas = gravada
    ? estado.gravacao.mediana.filter((m) => m.operacao === nome).map((m) => ({ ex: m, m }))
    : etapa.execucoes.map((ex) => ({ ex, m: ex.resultado }));
  let corpo = "";
  for (const { ex, m } of linhas) {
    if (!m) {
      corpo += `<tr><td>${rotuloDoLado(ex)}</td><td colspan="5">${ex.iniciada ? "medindo…" : "aguardando"}</td></tr>`;
    } else if (nome === "pico") {
      for (const op of OPERACOES_DO_PICO) {
        corpo += `<tr><td>${rotuloDoLado(ex, ` · ${NOME_NO_PICO[op]}`)}</td>${celulasDeMetricas(m.por_operacao[op])}</tr>`;
      }
    } else {
      corpo += `<tr><td>${rotuloDoLado(ex)}</td>${celulasDeMetricas(m)}</tr>`;
    }
  }
  let legenda = gravada ? `Mediana de ${estado.gravacao.repeticoes.length} repetições` : "Resultado de cada lado";
  if (nome === "pico") legenda += "; as três operações se alternam, e a vazão de cada uma é a de cliques completos";
  etapa.elementos.placar.innerHTML = `<table><caption>${legenda}</caption>
    <thead><tr><th>Lado</th><th>Vazão (ops/s)</th><th>p50 (ms)</th><th>p95 (ms)</th><th>p99 (ms)</th><th>Erros</th></tr></thead>
    <tbody>${corpo}</tbody></table>`;
}

function situacaoDoCa6(r) {
  if (r.rodada_invalida?.length) return `<span class="invalida">rodada inválida</span>`;
  return r.queda.ca6 ? `<span class="cumprido">cumprido</span>` : `<span class="nao-cumprido">não cumprido</span>`;
}

function placarDaQueda(etapa) {
  const quedas = estado.modo === "gravada"
    ? estado.gravacao.repeticoes.map((r, i) => ({ rotulo: `Repetição ${i + 1}`, r: r.execucoes.find((e) => e.operacao === "queda") }))
    : [{ rotulo: "Ao vivo", r: etapa.execucoes[0].resultado }];
  let corpo = "";
  for (const { rotulo, r } of quedas) {
    if (!r) {
      corpo += `<tr><td>${rotulo}</td><td colspan="9">${etapa.execucoes[0].iniciada ? "medindo…" : "aguardando"}</td></tr>`;
      continue;
    }
    const q = r.queda;
    const c = r.conferencia;
    corpo += `<tr><td>${rotulo}</td><td>${decimal.format(q.janela_s[0])} a ${decimal.format(q.janela_s[1])} s</td>`
      + `<td>${num(q.respostas_302)} de ${num(q.envios)}</td><td>${ms(q.p95_servidor_ms)}</td>`
      + `<td class="falhas">${num(q.falhas_somaram)}</td><td class="falhas">${num(c.falhas)}</td>`
      + `<td>${num(q.contador_somou)}</td><td>${num(c.diferenca_contador_historico)}</td>`
      + `<td>${num(c.diferenca_menos_falhas)}</td><td>${situacaoDoCa6(r)}</td></tr>`;
  }
  etapa.elementos.placar.innerHTML = `<table><caption>Queda vista pela aplicação (janela do CA-6) e conferência 10 s depois da carga</caption>
    <thead><tr><th>Execução</th><th>Janela</th><th>302</th><th>p95 no servidor (ms)</th>
    <th>Cliques que falharam na janela</th><th>Falhas na conferência</th><th>Contador somou na janela</th>
    <th>Contador − histórico</th><th>Diferença − falhas</th><th>CA-6</th></tr></thead>
    <tbody>${corpo}</tbody></table>`;
  // Ao vivo, os cliques que falharam aparecem enquanto a queda roda (Q-75).
  const ultima = etapa.execucoes[0].serie.at(-1);
  const ateAgora = etapa.elementos.ateAgora;
  ateAgora.hidden = estado.modo !== "ao_vivo" || !ultima || !!etapa.execucoes[0].resultado;
  if (!ateAgora.hidden) {
    const respostas = etapa.execucoes[0].serie.reduce((soma, l) => soma + l.respostas_302, 0);
    ateAgora.innerHTML = `Aos ${ultima.s + 1} s: ${num(respostas)} redirecionamentos com 302 · `
      + `<span class="falhas">${num(ultima.falhas_na_etapa)} cliques que falharam ao gravar</span> · `
      + `contador +${num(ultima.contador_na_etapa)}`;
  }
}

function marcarEtapas() {
  for (const [nome, etapa] of Object.entries(estado.etapas)) {
    const prontas = etapa.execucoes.filter((e) => e.resultado).length;
    const rodando = estado.modo === "ao_vivo" && estado.atual?.etapa === nome && !estado.atual.resultado;
    etapa.elementos.secao.classList.toggle("rodando", rodando);
    etapa.elementos.estado.textContent = estado.modo === "gravada" ? "gravada"
      : rodando ? `rodando: ${nomeDoLado(estado.atual)}`
        : prontas === etapa.execucoes.length ? "concluída"
          : prontas ? `${prontas} de ${etapa.execucoes.length} execuções` : "aguardando";
  }
}

// ---------- Situação ----------

function mostrarSituacao() {
  const modo = $("modo");
  modo.className = "modo";
  if (estado.modo === "gravada") {
    const g = estado.gravacao;
    modo.classList.add("gravada");
    modo.textContent = `Execução gravada em ${dataHora.format(new Date(g.gravada_em))}`
      + (g.tipo === "teste" ? " · gravação de teste, com durações curtas" : "") + " · não é ao vivo";
  } else if (estado.modo === "ao_vivo") {
    modo.classList.add("ao-vivo");
    const inicio = estado.iniciadaEm ? dataHora.format(new Date(estado.iniciadaEm)) : "";
    modo.textContent = estado.rodando ? "Ao vivo" : `Última sequência ao vivo, iniciada em ${inicio}`;
  } else {
    modo.textContent = "Nenhuma execução aberta";
  }
  const atual = estado.atual;
  $("etapa-atual").textContent = estado.modo !== "ao_vivo" ? ""
    : estado.rodando && atual && !atual.resultado ? `Etapa atual: ${ETAPAS[atual.etapa].titulo} · ${nomeDoLado(atual)}`
      : estado.rodando ? "Preparando a próxima execução…" : "";
  $("seletor-repeticao").hidden = estado.modo !== "gravada";
  mostrarRelogio();
}

function mostrarRelogio() {
  const relogio = $("relogio");
  if (estado.modo !== "ao_vivo" || estado.decorrido == null) {
    relogio.textContent = "";
    return;
  }
  const decorrido = estado.rodando ? estado.decorrido + (performance.now() - estado.recebidoEm) / 1000 : estado.decorrido;
  const limite = estado.orcamento;
  if (estado.rodando) {
    relogio.textContent = `${inteiro.format(decorrido)} s de ${limite} s`;
  } else if (estado.concluida) {
    relogio.textContent = decorrido <= limite ? `Concluída em ${inteiro.format(decorrido)} s, dentro dos ${limite} s`
      : `Concluída em ${inteiro.format(decorrido)} s, acima dos ${limite} s`;
  } else {
    relogio.textContent = `Interrompida aos ${inteiro.format(decorrido)} s`;
  }
}

function avisar(texto) {
  $("aviso").hidden = !texto;
  $("aviso").textContent = texto || "";
}

function registrarLog(texto) {
  const log = $("log");
  log.textContent += texto + "\n";
  log.scrollTop = log.scrollHeight;
}

// ---------- Eventos ao vivo ----------

function aplicar(evento) {
  if (evento.tipo === "inicio") {
    if (estado.modo === "gravada" && !estado.esperandoAoVivo) return;
    estado = novoEstado();
    Object.assign(estado, { modo: "ao_vivo", rodando: true, iniciadaEm: evento.em });
    $("log").textContent = "";
    avisar("");
    montar([]);
  }
  if (estado.modo !== "ao_vivo") return; // uma gravação aberta não é trocada pela sequência ao vivo
  estado.decorrido = evento.decorrido_s;
  estado.recebidoEm = performance.now();
  const atual = estado.atual;
  switch (evento.tipo) {
    case "sequencia":
      estado.orcamento = evento.orcamento_s ?? ORCAMENTO_PADRAO_S;
      montar(evento.plano);
      break;
    case "execucao": {
      const etapa = estado.etapas[evento.etapa];
      estado.atual = etapa?.execucoes.find((e) => !e.iniciada && e.lado === evento.lado && e.curva_extra === evento.curva_extra) ?? null;
      if (estado.atual) estado.atual.iniciada = true;
      if (etapa) placar(evento.etapa);
      break;
    }
    case "parcial":
      if (atual && !atual.resultado) {
        const { tipo, decorrido_s, ...linha } = evento;
        atual.serie.push(linha);
        desenhar(atual.etapa);
        if (atual.etapa === "queda") placar("queda");
      }
      break;
    case "recursos":
      if (atual && !atual.resultado) {
        atual.recursos.push({ t: evento.t, bancos: evento.bancos });
        if (["cpu", "memoria"].includes(estado.etapas[atual.etapa].metrica)) desenhar(atual.etapa);
      }
      break;
    case "resultado":
      if (atual) {
        atual.resultado = evento.execucao;
        atual.serie = evento.execucao.serie ?? atual.serie;
        atual.recursos = evento.execucao.serie_recursos ?? atual.recursos;
        desenhar(atual.etapa);
        placar(atual.etapa);
      }
      break;
    case "restauracao":
      $("etapa-atual").textContent = evento.fase === "inicio" ? "Restaurando a base…" : "";
      break;
    case "log":
      registrarLog(evento.texto);
      break;
    case "erro":
      avisar(`A medição falhou: ${evento.mensagem}`);
      break;
    case "fim":
      estado.concluida = evento.concluida;
      break;
    case "saida":
      estado.rodando = false;
      if (evento.codigo !== 0) {
        avisar(`A medição saiu com código ${evento.codigo}. Veja a saída da medição no fim da página.`);
        document.querySelector(".log").open = true;
      }
      atualizarEstado();
      break;
  }
  marcarEtapas();
  if (evento.tipo !== "parcial" && evento.tipo !== "recursos") mostrarSituacao();
}

function ouvir() {
  const fonte = new EventSource("/api/eventos");
  fonte.onmessage = (mensagem) => aplicar(JSON.parse(mensagem.data));
}

// ---------- Gravações ----------

async function listarGravacoes() {
  const lista = await (await fetch("/api/gravacoes")).json();
  const select = $("gravacoes");
  select.replaceChildren();
  if (!lista.length) select.append(new Option("Nenhuma execução gravada", ""));
  for (const g of lista) {
    const rotulo = `${dataHora.format(new Date(g.gravada_em))}${g.tipo === "teste" ? " · teste" : " · completa"}`;
    select.append(new Option(rotulo, g.nome));
  }
  $("abrir").disabled = !lista.length;
}

async function abrirGravacao(nome) {
  const resposta = await fetch(`/api/gravacoes/${encodeURIComponent(nome)}`);
  if (!resposta.ok) return avisar("Não foi possível abrir a gravação.");
  const gravacao = await resposta.json();
  estado = novoEstado();
  Object.assign(estado, { modo: "gravada", gravacao });
  avisar("");
  const seletor = $("repeticao");
  seletor.replaceChildren(...gravacao.repeticoes.map((_, i) => new Option(`Repetição ${i + 1} de ${gravacao.repeticoes.length}`, i)));
  mostrarRepeticao(0);
}

function mostrarRepeticao(indice) {
  const execucoes = estado.gravacao.repeticoes[indice].execucoes;
  estado.repeticao = indice;
  montar(execucoes.map((e) => ({
    etapa: e.operacao, lado: e.lado, curva_extra: e.curva_extra, aquecimento_s: e.aquecimento_s ?? 0, duracao_s: e.duracao_s,
  })));
  for (const e of execucoes) {
    const ex = estado.etapas[e.operacao].execucoes.find((x) => !x.resultado && x.lado === e.lado && x.curva_extra === !!e.curva_extra);
    Object.assign(ex, { resultado: e, serie: e.serie ?? [], recursos: e.serie_recursos ?? [], iniciada: true });
  }
  for (const nome of Object.keys(estado.etapas)) {
    desenhar(nome);
    placar(nome);
  }
  marcarEtapas();
  mostrarSituacao();
}

// ---------- Estado do servidor e botões ----------

async function atualizarEstado() {
  try {
    const { rodando, base } = await (await fetch("/api/estado")).json();
    $("iniciar").disabled = rodando;
    const texto = base.ultima_restauracao
      ? `Última restauração da base: ${dataHora.format(new Date(base.ultima_restauracao))}`
        + (base.medicoes_depois
          ? ` · ${base.medicoes_depois} medição(ões) registrada(s) depois; restaure antes com python benchmark/base.py restaurar`
          : " · nenhuma medição registrada depois")
      : "Nenhuma restauração registrada; rode python benchmark/base.py restaurar antes de iniciar";
    $("base").textContent = texto;
  } catch {
    $("base").textContent = "O servidor da tela não respondeu";
  }
}

$("iniciar").addEventListener("click", async () => {
  $("iniciar").disabled = true;
  estado.esperandoAoVivo = true; // o evento "inicio" troca a gravação aberta pela sequência ao vivo
  const resposta = await fetch("/api/ao-vivo", { method: "POST" });
  if (resposta.status === 409) avisar("A sequência ao vivo já está rodando.");
  else if (!resposta.ok) avisar("Não foi possível iniciar a sequência.");
  atualizarEstado();
});
$("abrir").addEventListener("click", () => $("gravacoes").value && abrirGravacao($("gravacoes").value));
$("repeticao").addEventListener("change", (e) => mostrarRepeticao(Number(e.target.value)));

setInterval(mostrarRelogio, 500);
setInterval(atualizarEstado, 5000);
atualizarEstado();
listarGravacoes();
ouvir();
