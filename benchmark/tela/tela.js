"use strict";
// Tela de testes do benchmark (SPEC-005; Q-70 a Q-76). Sem framework e sem etapa de build.

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
const MEDICOES = new Set(["ao-vivo", "completa", "completa-teste"]);
const INTERVALO_ESTADO_MS = 5000;

const inteiro = new Intl.NumberFormat("pt-BR", { maximumFractionDigits: 0 });
const decimal = new Intl.NumberFormat("pt-BR", { maximumFractionDigits: 3 });
const percentual = new Intl.NumberFormat("pt-BR", { style: "percent", maximumFractionDigits: 3 });
const dataHora = new Intl.DateTimeFormat("pt-BR", { dateStyle: "short", timeStyle: "short" });

const $ = (id) => document.getElementById(id);
const tema = getComputedStyle(document.documentElement);
const cor = (nome) => tema.getPropertyValue(nome).trim();
const CORES = {
  nosql: cor("--nosql"), postgres: cor("--postgres"), falha: cor("--falha"), cinza: cor("--secundario"),
  texto: cor("--texto"), grade: cor("--grafico-grade"), faixa: cor("--grafico-trilha"),
};

Chart.defaults.font.family = tema.fontFamily;
Chart.defaults.color = CORES.cinza;

const ms = (valor) => (valor == null ? "—" : decimal.format(valor));
const num = (valor) => (valor == null ? "—" : inteiro.format(valor));
const taxa = (valor) => (valor == null ? "—" : percentual.format(valor));

function duracao(segundos) {
  const s = Math.max(0, Math.floor(segundos));
  return s < 60 ? `${s} s` : `${Math.floor(s / 60)} min ${String(s % 60).padStart(2, "0")} s`;
}

function nomeDoLado(execucao) {
  if (execucao.curva_extra) return "PostgreSQL, synchronous_commit=off (fora do padrão)";
  return execucao.lado === "nosql" ? "NoSQL" : "PostgreSQL";
}

const classeDoLado = (execucao) => (execucao.curva_extra ? "extra" : execucao.lado);

// ---------- Estado ----------

let aoVivo = null; // a medição pedida pelos botões, montada a partir dos eventos
let gravada = null; // a execução gravada aberta
let vista = null; // "ao_vivo" ou "gravada": o que está na tela
let tarefa = null; // a tarefa em andamento, ou a última
let servidor = { tarefa: null, base: null, ambiente: null };
let paineis = {}; // etapa -> {grafico, metrica, elementos}
let pedidoDestaAba = false; // esta aba pediu a medição: ela troca a gravação aberta pelo ao vivo

const exibida = () => (vista === "gravada" ? gravada : vista === "ao_vivo" ? aoVivo : null);

function execucoesDoPlano(plano) {
  const etapas = {};
  for (const p of plano) {
    (etapas[p.etapa] ??= []).push({
      etapa: p.etapa, lado: p.lado, curva_extra: !!p.curva_extra, aquecimento_s: p.aquecimento_s ?? 0,
      duracao_s: p.duracao_s, serie: [], recursos: [], resultado: null, iniciada: false,
    });
  }
  return etapas;
}

function decorridoDe(registro) {
  if (!registro || registro.decorrido == null) return null;
  return registro.rodando ? registro.decorrido + (performance.now() - registro.recebidoEm) / 1000 : registro.decorrido;
}

// ---------- Gráficos ----------

// Faixas sombreadas (aquecimento, janela do CA-6) e linhas verticais (parada, religamento, volta).
// Os rótulos ficam acima da área das curvas, um por linha, para não cobrirem as curvas nem uns aos outros.
const LINHA_DE_ROTULO = 14;
const pluginFaixas = {
  id: "faixas",
  beforeDatasetsDraw(grafico, _argumentos, opcoes) {
    const { ctx, chartArea: area, scales: { x } } = grafico;
    const rotulos = (opcoes.faixas || []).length + (opcoes.marcos || []).length;
    let topo = area.top - rotulos * LINHA_DE_ROTULO;
    ctx.save();
    ctx.font = `11px ${tema.fontFamily}`;
    ctx.textBaseline = "top";
    for (const faixa of opcoes.faixas || []) {
      const de = x.getPixelForValue(faixa.de);
      const ate = x.getPixelForValue(faixa.ate);
      ctx.fillStyle = CORES.faixa;
      ctx.fillRect(de, area.top, ate - de, area.bottom - area.top);
      ctx.fillStyle = CORES.cinza;
      ctx.fillRect(de, topo, 1, area.top - topo);
      ctx.fillText(faixa.rotulo, de + 4, topo);
      topo += LINHA_DE_ROTULO;
    }
    for (const marco of opcoes.marcos || []) {
      const px = x.getPixelForValue(marco.x);
      ctx.strokeStyle = CORES.cinza;
      ctx.setLineDash([3, 3]);
      ctx.beginPath();
      ctx.moveTo(px, topo);
      ctx.lineTo(px, area.bottom);
      ctx.stroke();
      ctx.setLineDash([]);
      ctx.fillStyle = CORES.texto;
      ctx.fillText(marco.rotulo, px + 4, topo);
      topo += LINHA_DE_ROTULO;
    }
    ctx.restore();
  },
};

function criarGrafico(canvas, nome) {
  return new Chart(canvas, {
    type: "line",
    data: { datasets: [] },
    options: {
      animation: false,
      maintainAspectRatio: false,
      parsing: false,
      locale: "pt-BR",
      interaction: { mode: "nearest", axis: "x", intersect: false },
      elements: { point: { radius: 0 }, line: { borderWidth: 2.25, tension: 0 } },
      scales: {
        x: {
          type: "linear", min: 0, grid: { color: CORES.grade },
          title: { display: true, text: "segundos desde a partida de cada lado" },
        },
        y: { beginAtZero: true, grace: "5%", grid: { color: CORES.grade }, title: { display: true } },
      },
      plugins: {
        legend: { position: "bottom", labels: { boxWidth: 18, boxHeight: 2 } },
        faixas: { faixas: [], marcos: [] },
        tooltip: { callbacks: { title: (itens) => (itens.length ? `${decimal.format(itens[0].parsed.x)} s` : "") } },
      },
    },
    plugins: [pluginFaixas],
  });
}

function montar() {
  for (const painel of Object.values(paineis)) painel.grafico.destroy();
  paineis = {};
  const container = $("etapas");
  container.replaceChildren();
  const fonte = exibida();
  if (!fonte) return;
  for (const nome of Object.keys(ETAPAS)) {
    if (!fonte.etapas[nome]?.length) continue;
    const metricas = nome === "queda" ? METRICAS_DA_QUEDA : METRICAS;
    const secao = document.createElement("section");
    secao.className = `cartao etapa ${nome}`;
    secao.innerHTML = `
      <div class="titulo-cartao"><h2>${ETAPAS[nome].titulo}</h2><span class="estado">aguardando</span></div>
      <p class="texto-secundario">${ETAPAS[nome].descricao}</p>
      <div class="abas" role="group" aria-label="Métrica das curvas"></div>
      <div class="grafico"><canvas role="img" aria-label="Curvas de ${ETAPAS[nome].titulo}"></canvas></div>
      <p class="ate-agora" hidden></p>
      <div class="placar"></div>`;
    container.append(secao);
    const painel = {
      metrica: Object.keys(metricas)[0],
      elementos: {
        secao, estado: secao.querySelector(".estado"), abas: secao.querySelector(".abas"),
        placar: secao.querySelector(".placar"), ateAgora: secao.querySelector(".ate-agora"),
      },
    };
    for (const [chave, rotulo] of Object.entries(metricas)) {
      const botao = document.createElement("button");
      botao.type = "button";
      botao.textContent = rotulo;
      botao.setAttribute("aria-pressed", String(chave === painel.metrica));
      botao.addEventListener("click", () => {
        painel.metrica = chave;
        for (const b of painel.elementos.abas.children) b.setAttribute("aria-pressed", String(b === botao));
        desenhar(nome);
      });
      painel.elementos.abas.append(botao);
    }
    painel.grafico = criarGrafico(secao.querySelector("canvas"), nome);
    paineis[nome] = painel;
    desenhar(nome);
    placar(nome);
  }
  marcarEtapas();
}

// ---------- Curvas ----------

const noMeio = (linha) => linha.s + 0.5; // a linha da série cobre o segundo [s, s + 1)

function vazaoNoSegundo(etapa, linha) {
  // No pico, um clique completo termina no registro, a última operação do ciclo (Q-71).
  const operacao = etapa === "pico" ? "registro" : etapa;
  return linha.por_operacao?.[operacao]?.ops ?? null;
}

function conjuntos(nome, metrica) {
  const execucoes = exibida().etapas[nome];
  if (nome === "queda") return conjuntosDaQueda(execucoes[0], metrica);
  const lista = [];
  for (const ex of execucoes) {
    const base = {
      label: nomeDoLado(ex), borderColor: CORES[ex.lado], backgroundColor: CORES[ex.lado],
      borderDash: ex.curva_extra ? [6, 4] : [],
    };
    if (metrica === "vazao") {
      lista.push({ ...base, data: ex.serie.map((l) => ({ x: noMeio(l), y: vazaoNoSegundo(nome, l) })) });
    } else if (metrica === "p95") {
      const operacoes = nome === "pico" ? OPERACOES_DO_PICO : [nome];
      operacoes.forEach((op, i) => lista.push({
        ...base,
        label: nome === "pico" ? `${base.label} · ${NOME_NO_PICO[op]}` : base.label,
        borderDash: nome === "pico" ? TRACOS_DO_PICO[i] : base.borderDash,
        data: ex.serie.map((l) => ({ x: noMeio(l), y: l.por_operacao?.[op]?.p95_ms ?? null })),
      }));
    } else {
      const campo = metrica === "cpu" ? "cpu_pct" : "mem_mib";
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

function conjuntosDaQueda(ex, metrica) {
  const serie = ex?.serie ?? [];
  if (metrica === "p95") {
    return [
      { label: "p95 no servidor", borderColor: CORES.nosql, backgroundColor: CORES.nosql,
        data: serie.map((l) => ({ x: noMeio(l), y: l.p95_servidor_ms })) },
      {
        label: `teto do RNF-02 (${TETO_P95_QUEDA_MS} ms)`, borderColor: CORES.cinza, backgroundColor: CORES.cinza,
        borderDash: [6, 4], data: [{ x: 0, y: TETO_P95_QUEDA_MS }, { x: 90, y: TETO_P95_QUEDA_MS }],
      },
    ];
  }
  return [
    {
      label: "redirecionamentos com 302 por segundo", borderColor: CORES.nosql, backgroundColor: CORES.nosql,
      data: serie.map((l) => ({ x: noMeio(l), y: l.respostas_302 })), order: 0,
    },
    {
      type: "bar", label: "cliques que falharam ao gravar, por segundo", backgroundColor: CORES.falha,
      borderWidth: 0, barPercentage: 1, categoryPercentage: 1, data: falhasPorSegundo(serie), order: 1,
    },
  ];
}

function desenhar(nome) {
  const painel = paineis[nome];
  const execucoes = exibida()?.etapas[nome];
  if (!painel || !execucoes) return;
  const grafico = painel.grafico;
  const ex = execucoes[0];
  const metricas = nome === "queda" ? METRICAS_DA_QUEDA : METRICAS;
  grafico.data.datasets = conjuntos(nome, painel.metrica);
  grafico.options.scales.x.max = Math.max(...execucoes.map((e) => e.aquecimento_s + e.duracao_s));
  grafico.options.scales.y.title.text = metricas[painel.metrica];
  // Montado antes de atribuir: ler de volta uma opção do Chart.js devolve uma cópia.
  const opcoes = { faixas: [], marcos: [] };
  if (nome === "queda") {
    const r = ex.resultado;
    if (r) opcoes.faixas.push({ de: r.queda.janela_s[0], ate: r.queda.janela_s[1], rotulo: "janela do CA-6" });
    opcoes.marcos.push({ x: 30, rotulo: "parada" }, { x: 60, rotulo: "religamento" });
    if (r?.marcos?.gravacao_voltou_s != null) opcoes.marcos.push({ x: r.marcos.gravacao_voltou_s, rotulo: "volta da gravação" });
  } else if (ex.aquecimento_s) {
    opcoes.faixas.push({ de: 0, ate: ex.aquecimento_s, rotulo: "aquecimento (descartado)" });
  }
  grafico.options.plugins.faixas = opcoes;
  grafico.options.layout = { padding: { top: (opcoes.faixas.length + opcoes.marcos.length) * LINHA_DE_ROTULO + 2 } };
  grafico.update("none");
}

// ---------- Placar ----------

// Uma execução sem resultado: ainda não começou, está rodando ou parou com a tarefa.
function semResultado(ex) {
  if (!ex.iniciada) return "aguardando";
  return vista === "ao_vivo" && !aoVivo.rodando ? "não terminou" : "medindo…";
}

function celulasDeMetricas(m) {
  return `<td>${num(m.vazao_ops)}</td><td>${ms(m.p50_ms)}</td><td>${ms(m.p95_ms)}</td><td>${ms(m.p99_ms)}</td>`
    + `<td>${num(m.erros)} (${taxa(m.taxa_erro)})</td>`;
}

function rotuloDoLado(ex, extra = "") {
  return `<span class="lado ${classeDoLado(ex)}"></span>${nomeDoLado(ex)}${extra}`;
}

function placar(nome) {
  const painel = paineis[nome];
  if (!painel) return;
  if (nome === "queda") return placarDaQueda(painel);
  const fonte = exibida();
  // Gravada: a mediana das repetições (CA-4); ao vivo: o resultado de cada execução, quando ela termina.
  const linhas = vista === "gravada"
    ? fonte.gravacao.mediana.filter((m) => m.operacao === nome).map((m) => ({ ex: m, m }))
    : fonte.etapas[nome].map((ex) => ({ ex, m: ex.resultado }));
  let corpo = "";
  for (const { ex, m } of linhas) {
    if (!m) {
      corpo += `<tr><td>${rotuloDoLado(ex)}</td><td colspan="5">${semResultado(ex)}</td></tr>`;
    } else if (nome === "pico") {
      for (const op of OPERACOES_DO_PICO) {
        corpo += `<tr><td>${rotuloDoLado(ex, ` · ${NOME_NO_PICO[op]}`)}</td>${celulasDeMetricas(m.por_operacao[op])}</tr>`;
      }
    } else {
      corpo += `<tr><td>${rotuloDoLado(ex)}</td>${celulasDeMetricas(m)}</tr>`;
    }
  }
  let legenda = vista === "gravada" ? `Mediana de ${fonte.gravacao.repeticoes.length} repetições`
    : fonte.repeticoes > 1 ? `Repetição ${fonte.repeticao} de ${fonte.repeticoes}, resultado de cada lado` : "Resultado de cada lado";
  if (nome === "pico") legenda += "; as três operações se alternam, e a vazão de cada uma é a de cliques completos";
  painel.elementos.placar.innerHTML = `<table><caption>${legenda}</caption>
    <thead><tr><th>Lado</th><th>Vazão (ops/s)</th><th>p50 (ms)</th><th>p95 (ms)</th><th>p99 (ms)</th><th>Erros</th></tr></thead>
    <tbody>${corpo}</tbody></table>`;
}

function situacaoDoCa6(r) {
  if (r.rodada_invalida?.length) return `<span class="invalida">rodada inválida</span>`;
  return r.queda.ca6 ? `<span class="cumprido">cumprido</span>` : `<span class="nao-cumprido">não cumprido</span>`;
}

function placarDaQueda(painel) {
  const ex = exibida().etapas.queda[0];
  const quedas = vista === "gravada"
    ? gravada.gravacao.repeticoes.map((r, i) => ({ rotulo: `Repetição ${i + 1}`, r: r.execucoes.find((e) => e.operacao === "queda") }))
    : [{ rotulo: aoVivo.repeticoes > 1 ? `Repetição ${aoVivo.repeticao}` : "Ao vivo", r: ex.resultado }];
  let corpo = "";
  for (const { rotulo, r } of quedas) {
    if (!r) {
      corpo += `<tr><td>${rotulo}</td><td colspan="9">${semResultado(ex)}</td></tr>`;
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
  painel.elementos.placar.innerHTML = `<table><caption>Queda vista pela aplicação (janela do CA-6) e conferência 10 s depois da carga</caption>
    <thead><tr><th>Execução</th><th>Janela</th><th>302</th><th>p95 no servidor (ms)</th>
    <th>Cliques que falharam na janela</th><th>Falhas na conferência</th><th>Contador somou na janela</th>
    <th>Contador − histórico</th><th>Diferença − falhas</th><th>CA-6</th></tr></thead>
    <tbody>${corpo}</tbody></table>`;
  // Ao vivo, os cliques que falharam aparecem enquanto a queda roda (Q-75).
  const ultima = ex.serie.at(-1);
  const ateAgora = painel.elementos.ateAgora;
  ateAgora.hidden = vista !== "ao_vivo" || !ultima || !!ex.resultado;
  if (!ateAgora.hidden) {
    const respostas = ex.serie.reduce((soma, l) => soma + l.respostas_302, 0);
    ateAgora.innerHTML = `Aos ${ultima.s + 1} s: ${num(respostas)} redirecionamentos com 302 · `
      + `<span class="falhas">${num(ultima.falhas_na_etapa)} cliques que falharam ao gravar</span> · `
      + `contador +${num(ultima.contador_na_etapa)}`;
  }
}

function marcarEtapas() {
  const fonte = exibida();
  for (const [nome, painel] of Object.entries(paineis)) {
    const execucoes = fonte.etapas[nome];
    const prontas = execucoes.filter((e) => e.resultado).length;
    const atual = vista === "ao_vivo" && aoVivo.rodando ? aoVivo.atual : null;
    const rodando = atual?.etapa === nome && !atual.resultado;
    painel.elementos.secao.classList.toggle("rodando", rodando);
    painel.elementos.estado.textContent = vista === "gravada" ? `repetição ${gravada.repeticao + 1}`
      : rodando ? `rodando: ${nomeDoLado(atual)}`
        : prontas === execucoes.length ? "concluída"
          : prontas ? `${prontas} de ${execucoes.length} execuções` : "aguardando";
  }
}

// ---------- Situação e barra lateral ----------

function mostrarSituacao() {
  const modo = $("modo");
  modo.className = "selo";
  modo.hidden = !vista;
  $("estado-vazio").hidden = !!vista;
  $("seletor-repeticao").hidden = vista !== "gravada";
  if (vista === "gravada") {
    const g = gravada.gravacao;
    modo.textContent = `Execução gravada em ${dataHora.format(new Date(g.gravada_em))}`
      + (g.tipo === "teste" ? " · gravação de teste, com durações curtas" : "") + " · não é ao vivo";
  } else if (vista === "ao_vivo") {
    modo.classList.add("ao-vivo");
    modo.classList.toggle("rodando", aoVivo.rodando);
    const nome = aoVivo.modo === "completa" ? "Execução completa" : "Ao vivo";
    modo.textContent = aoVivo.rodando ? nome : `${nome}, iniciada em ${dataHora.format(new Date(aoVivo.iniciadaEm))}`;
  }
  const atual = aoVivo?.atual;
  $("etapa-atual").textContent = vista !== "ao_vivo" || !aoVivo.rodando ? ""
    : aoVivo.restaurando ? "Restaurando a base…"
      : atual && !atual.resultado ? `Etapa atual: ${ETAPAS[atual.etapa].titulo} · ${nomeDoLado(atual)}`
        : "Preparando a próxima execução…";
  mostrarTarefa();
  mostrarExecucoes();
  mostrarRelogio();
}

function mostrarRelogio() {
  const relogio = $("relogio");
  const progresso = $("progresso");
  const decorrido = vista === "ao_vivo" ? decorridoDe(aoVivo) : null;
  progresso.hidden = decorrido == null || !aoVivo.orcamento;
  if (decorrido == null) {
    relogio.textContent = "";
  } else if (aoVivo.repeticoes > 1) {
    relogio.textContent = `Repetição ${aoVivo.repeticao} de ${aoVivo.repeticoes} · ${duracao(decorrido)}`;
  } else {
    const limite = aoVivo.orcamento;
    const estouro = limite && decorrido > limite;
    relogio.textContent = aoVivo.rodando ? `${duracao(decorrido)} de ${duracao(limite)}`
      : aoVivo.concluida ? `Concluída em ${duracao(decorrido)}${limite ? `, ${estouro ? "acima" : "dentro"} do limite de ${limite} s` : ""}`
        : `${aoVivo.falhou ? "Falhou" : "Interrompida"} aos ${duracao(decorrido)}`;
    if (limite) {
      progresso.classList.toggle("acima", !!estouro);
      progresso.firstElementChild.style.width = `${Math.min(100, (100 * decorrido) / limite)}%`;
    }
  }
  if (tarefa?.rodando) $("tarefa-tempo").textContent = `rodando há ${duracao(decorridoDe(tarefa))}`;
}

function mostrarTarefa() {
  const cartao = $("tarefa");
  const falhou = tarefa && !tarefa.rodando && (tarefa.codigo || tarefa.interrompida);
  // As medições aparecem nas etapas; o cartão fica para as outras tarefas e para as falhas.
  cartao.hidden = !tarefa || (tarefa.medicao && !falhou);
  if (cartao.hidden) return;
  cartao.classList.toggle("rodando", tarefa.rodando);
  cartao.classList.toggle("falhou", !!falhou);
  $("tarefa-titulo").textContent = tarefa.rodando ? tarefa.rotulo
    : tarefa.interrompida ? `${tarefa.rotulo}: interrompida`
      : tarefa.codigo ? `${tarefa.rotulo}: falhou (código ${tarefa.codigo})` : `${tarefa.rotulo}: concluída`;
  $("tarefa-tempo").textContent = tarefa.rodando ? `rodando há ${duracao(decorridoDe(tarefa))}`
    : `em ${duracao(tarefa.decorrido ?? 0)}`;
  $("tarefa-linha").textContent = tarefa.interrompida ? "Interrompida pelo botão. Restaure a base antes de medir de novo."
    : tarefa.erro || tarefa.ultimaLinha || "";
}

function itemDeExecucao({ titulo, detalhe, atual, rodando, aoClicar }) {
  const item = document.createElement("li");
  const botao = document.createElement("button");
  botao.type = "button";
  botao.className = "item-link";
  botao.setAttribute("aria-current", String(atual));
  botao.append(rodando ? Object.assign(document.createElement("span"), { className: "ponto rodando" })
    : document.importNode(document.querySelector("#icone-grafico").content, true));
  const textos = document.createElement("span");
  textos.innerHTML = `<strong></strong><small></small>`;
  textos.querySelector("strong").textContent = titulo;
  textos.querySelector("small").textContent = detalhe;
  botao.append(textos);
  botao.addEventListener("click", aoClicar);
  item.append(botao);
  return item;
}

let listaDeGravacoes = [];

function mostrarExecucoes() {
  const lista = $("execucoes");
  const itens = [];
  if (aoVivo) {
    itens.push(itemDeExecucao({
      titulo: aoVivo.modo === "completa" ? "Execução completa" : "Sequência ao vivo",
      detalhe: aoVivo.rodando ? "rodando agora" : `iniciada em ${dataHora.format(new Date(aoVivo.iniciadaEm))}`,
      atual: vista === "ao_vivo", rodando: aoVivo.rodando,
      aoClicar: () => { vista = "ao_vivo"; montar(); mostrarSituacao(); },
    }));
  }
  for (const g of listaDeGravacoes) {
    itens.push(itemDeExecucao({
      titulo: dataHora.format(new Date(g.gravada_em)),
      detalhe: g.tipo === "teste" ? "gravada · teste, durações curtas" : "gravada · completa",
      atual: vista === "gravada" && gravada.nome === g.nome, rodando: false,
      aoClicar: () => abrirGravacao(g.nome),
    }));
  }
  if (!itens.length) {
    itens.push(Object.assign(document.createElement("li"), { className: "texto-secundario", textContent: "Nenhuma execução ainda" }));
  }
  lista.replaceChildren(...itens);
}

const AMBIENTES = {
  desenvolvimento: "Desenvolvimento no ar",
  benchmark: "Benchmark no ar",
  benchmark_parcial: "Benchmark no ar, em parte",
  parado: "Bancos parados",
  sem_docker: "Docker indisponível",
};

function mostrarServidor() {
  const { ambiente, base } = servidor;
  const situacao = ambiente?.situacao;
  $("ambiente").textContent = situacao ? AMBIENTES[situacao] : "Consultando o Docker…";
  if (situacao === "benchmark_parcial") $("ambiente").textContent += ` (parados: ${ambiente.parados.join(", ")})`;
  $("ambiente").parentElement.classList.toggle("alerta", situacao === "sem_docker");
  let textoBase = "";
  if (base) {
    textoBase = !base.ultima_restauracao ? "Nenhuma restauração registrada"
      : `Base restaurada em ${dataHora.format(new Date(base.ultima_restauracao))}`
        + (base.medicoes_depois ? ` · ${base.medicoes_depois} medição(ões) depois; restaure antes de medir`
          : " · nenhuma medição depois");
  }
  $("base").textContent = textoBase;

  const rodando = !!(tarefa?.rodando || servidor.tarefa?.rodando);
  const dev = situacao === "desenvolvimento";
  const comDocker = !!situacao && situacao !== "sem_docker";
  const permitido = {
    parar: dev,
    restaurar: comDocker && !dev,
    "ao-vivo": situacao === "benchmark",
    conferir: situacao === "benchmark",
    completa: comDocker && !dev,
    carregar: comDocker && !dev,
    desenvolvimento: comDocker && !dev,
  };
  for (const botao of document.querySelectorAll("[data-tarefa], [data-tarefa-de]")) {
    botao.disabled = rodando || !permitido[botao.dataset.tarefa ?? botao.dataset.tarefaDe];
  }
  $("interromper").hidden = !rodando;
  $("passo-parar").classList.toggle("feito", comDocker && !dev);
  $("passo-restaurar").classList.toggle("feito",
    situacao === "benchmark" && !!base?.ultima_restauracao && !base.medicoes_depois);
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

// ---------- Eventos das tarefas ----------

function aplicar(evento) {
  if (evento.tipo === "inicio") {
    tarefa = { numero: evento.tarefa, nome: evento.nome, rotulo: evento.rotulo, medicao: evento.medicao, rodando: true, em: evento.em };
    registrarLog(`\n── ${evento.rotulo} · ${dataHora.format(new Date(evento.em))} ──`);
  }
  if (!tarefa || evento.tarefa !== tarefa.numero) return;
  Object.assign(tarefa, { decorrido: evento.decorrido_s, recebidoEm: performance.now() });
  const medicao = aoVivo?.tarefa === tarefa.numero ? aoVivo : null;
  if (medicao) Object.assign(medicao, { decorrido: evento.decorrido_s, recebidoEm: performance.now() });
  const atual = medicao?.atual;
  const naTela = medicao && vista === "ao_vivo";
  switch (evento.tipo) {
    case "log":
      registrarLog(evento.texto);
      if (evento.texto.trim()) tarefa.ultimaLinha = evento.texto;
      break;
    case "sequencia":
      aoVivo = {
        tarefa: tarefa.numero, modo: evento.modo, plano: evento.plano, etapas: execucoesDoPlano(evento.plano),
        repeticao: 1, repeticoes: evento.repeticoes ?? 1, orcamento: evento.orcamento_s, rodando: true,
        iniciadaEm: tarefa.em, decorrido: evento.decorrido_s, recebidoEm: performance.now(),
        atual: null, restaurando: false, concluida: null, gravacao: null,
      };
      // Uma gravação aberta em outra aba continua aberta; nesta aba, quem pediu vê o ao vivo.
      if (vista !== "gravada" || pedidoDestaAba) {
        vista = "ao_vivo";
        avisar("");
        montar();
      }
      pedidoDestaAba = false;
      break;
    case "repeticao":
      if (medicao && evento.numero !== medicao.repeticao) {
        Object.assign(medicao, { etapas: execucoesDoPlano(medicao.plano), atual: null, repeticao: evento.numero });
        if (naTela) montar();
      }
      break;
    case "execucao": {
      if (!medicao) break;
      medicao.atual = medicao.etapas[evento.etapa]
        ?.find((e) => !e.iniciada && e.lado === evento.lado && e.curva_extra === evento.curva_extra) ?? null;
      if (medicao.atual) medicao.atual.iniciada = true;
      if (naTela) placar(evento.etapa);
      break;
    }
    case "parcial":
      if (atual && !atual.resultado) {
        const { tipo, decorrido_s, id, tarefa: _numero, ...linha } = evento;
        atual.serie.push(linha);
        if (naTela) {
          desenhar(atual.etapa);
          if (atual.etapa === "queda") placar("queda");
        }
      }
      break;
    case "recursos":
      if (atual && !atual.resultado) {
        atual.recursos.push({ t: evento.t, bancos: evento.bancos });
        if (naTela && ["cpu", "memoria"].includes(paineis[atual.etapa]?.metrica)) desenhar(atual.etapa);
      }
      break;
    case "resultado":
      if (atual) {
        atual.resultado = evento.execucao;
        atual.serie = evento.execucao.serie ?? atual.serie;
        atual.recursos = evento.execucao.serie_recursos ?? atual.recursos;
        if (naTela) {
          desenhar(atual.etapa);
          placar(atual.etapa);
        }
      }
      break;
    case "restauracao":
      if (medicao) medicao.restaurando = evento.fase === "inicio";
      break;
    case "erro":
      tarefa.erro = evento.mensagem;
      break;
    case "fim":
      if (medicao) Object.assign(medicao, { concluida: evento.concluida, gravacao: evento.gravacao });
      break;
    case "saida":
      terminar(evento, medicao);
      break;
  }
  if (naTela) marcarEtapas();
  if (evento.tipo !== "parcial" && evento.tipo !== "recursos" && evento.tipo !== "log") mostrarSituacao();
  else if (evento.tipo === "log" && !tarefa.medicao) mostrarTarefa();
}

function terminar(evento, medicao) {
  // O cartão da tarefa mostra a falha ou a interrupção; a saída completa abre no fim da página.
  Object.assign(tarefa, { rodando: false, codigo: evento.codigo, interrompida: evento.interrompida });
  if (medicao) Object.assign(medicao, { rodando: false, restaurando: false, falhou: !!evento.codigo && !evento.interrompida });
  if (evento.codigo && !evento.interrompida) $("detalhes-log").open = true;
  if (medicao && vista === "ao_vivo") for (const nome of Object.keys(paineis)) placar(nome);
  atualizarEstado();
  // A execução completa termina gravada: a tela abre a gravação, com a mediana (Q-74).
  if (medicao?.gravacao) {
    listarGravacoes().then(() => { if (vista === "ao_vivo") abrirGravacao(medicao.gravacao); });
  }
}

function ouvir() {
  const fonte = new EventSource("/api/eventos");
  fonte.onmessage = (mensagem) => aplicar(JSON.parse(mensagem.data));
}

// ---------- Gravações ----------

async function listarGravacoes() {
  try {
    listaDeGravacoes = await (await fetch("/api/gravacoes")).json();
  } catch {
    listaDeGravacoes = [];
  }
  mostrarExecucoes();
}

function etapasDaRepeticao(execucoes) {
  const etapas = execucoesDoPlano(execucoes.map((e) => ({
    etapa: e.operacao, lado: e.lado, curva_extra: e.curva_extra, aquecimento_s: e.aquecimento_s ?? 0, duracao_s: e.duracao_s,
  })));
  for (const e of execucoes) {
    const ex = etapas[e.operacao].find((x) => !x.resultado && x.lado === e.lado && x.curva_extra === !!e.curva_extra);
    Object.assign(ex, { resultado: e, serie: e.serie ?? [], recursos: e.serie_recursos ?? [], iniciada: true });
  }
  return etapas;
}

async function abrirGravacao(nome) {
  const resposta = await fetch(`/api/gravacoes/${encodeURIComponent(nome)}`).catch(() => null);
  if (!resposta?.ok) return avisar("Não foi possível abrir a gravação.");
  const gravacao = await resposta.json();
  gravada = { nome, gravacao, repeticao: 0, etapas: etapasDaRepeticao(gravacao.repeticoes[0].execucoes) };
  vista = "gravada";
  avisar("");
  $("repeticao").replaceChildren(...gravacao.repeticoes.map((_, i) => new Option(`Repetição ${i + 1} de ${gravacao.repeticoes.length}`, i)));
  montar();
  mostrarSituacao();
}

function mostrarRepeticao(indice) {
  gravada.repeticao = indice;
  gravada.etapas = etapasDaRepeticao(gravada.gravacao.repeticoes[indice].execucoes);
  montar();
}

// ---------- Estado do servidor e botões ----------

async function atualizarEstado() {
  try {
    servidor = await (await fetch("/api/estado")).json();
  } catch {
    servidor = { tarefa: null, base: null, ambiente: null };
    $("ambiente").textContent = "O servidor da tela não respondeu";
    return;
  }
  mostrarServidor();
}

async function pedirTarefa(nome) {
  if (MEDICOES.has(nome)) pedidoDestaAba = true;
  for (const botao of document.querySelectorAll("[data-tarefa], [data-tarefa-de]")) botao.disabled = true;
  try {
    const resposta = await fetch(`/api/tarefas/${nome}`, { method: "POST" });
    if (resposta.status === 409) avisar("Outra tarefa está rodando: espere ela terminar ou interrompa.");
    else if (!resposta.ok) avisar("Não foi possível iniciar a tarefa.");
    else avisar("");
  } catch {
    avisar("O servidor da tela não respondeu.");
  }
  atualizarEstado();
}

for (const botao of document.querySelectorAll("button[data-tarefa]")) {
  botao.addEventListener("click", () => pedirTarefa(botao.dataset.tarefa));
}
for (const botao of document.querySelectorAll("[data-abrir]")) {
  botao.addEventListener("click", () => $(botao.dataset.abrir).showModal());
}
$("interromper").addEventListener("click", () => $("dialogo-interromper").showModal());
for (const botao of document.querySelectorAll("[data-fechar]")) {
  botao.addEventListener("click", () => botao.closest("dialog").close());
}
for (const formulario of document.querySelectorAll("[data-tarefa-do-formulario]")) {
  formulario.addEventListener("submit", () => pedirTarefa(new FormData(formulario).get("tarefa")));
}
$("formulario-interromper").addEventListener("submit", async () => {
  await fetch("/api/interromper", { method: "POST" }).catch(() => null);
  atualizarEstado();
});
$("repeticao").addEventListener("change", (e) => mostrarRepeticao(Number(e.target.value)));

setInterval(mostrarRelogio, 500);
setInterval(atualizarEstado, INTERVALO_ESTADO_MS);
atualizarEstado();
listarGravacoes();
mostrarSituacao();
ouvir();
