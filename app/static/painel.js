const INTERVALO_ATUALIZACAO_MS = 5000;
const numeros = new Intl.NumberFormat("pt-BR");
const percentuais = new Intl.NumberFormat("pt-BR", { style: "percent", maximumFractionDigits: 1 });
const dataBrasilia = new Intl.DateTimeFormat("pt-BR", {
  timeZone: FUSO_BRASILIA, dateStyle: "short", timeStyle: "short",
});
const horaBrasilia = new Intl.DateTimeFormat("pt-BR", { timeZone: FUSO_BRASILIA, timeStyle: "medium" });
const dispositivos = { mobile: "Celular", desktop: "Desktop", tablet: "Tablet", outro: "Outros" };
const tema = getComputedStyle(document.documentElement);
const cor = (variavel) => tema.getPropertyValue(variavel).trim();
const coresDispositivos = Object.keys(dispositivos).map((_, indice) => cor(`--dispositivo-${indice + 1}`));
const graficos = {};
const estado = {
  clientes: null,
  clienteId: "",
  links: null,
  campanhas: null,
  codigo: "",
  historico: null,
  falhou: false,
  divergente: false,
};
let consultaAtiva;
let assinaturaLinks;
let assinaturaCampanhas;
let historicoExibido;
let diaExibido;
let tempoRetornoCopia;

const elemento = (id) => document.getElementById(id);
const cliente = elemento("cliente");
const listaLinks = elemento("lista-links");
const seletorCampanha = elemento("link-campanha");

function exibirTexto(alvo, texto) {
  if (alvo.textContent !== texto) alvo.textContent = texto;
}

function criarElemento(tag, texto, classe) {
  const no = document.createElement(tag);
  if (texto !== undefined) no.textContent = texto;
  if (classe) no.className = classe;
  return no;
}

function criarOpcao(texto, valor) {
  const opcao = criarElemento("option", texto);
  opcao.value = valor;
  return opcao;
}

class ErroApi extends Error {
  constructor(status, detalhe) {
    super(`HTTP ${status}`);
    this.status = status;
    this.detalhe = detalhe;
  }
}

async function requisitar(rota, { parametros, dados, sinal } = {}) {
  const url = parametros ? `${rota}?${new URLSearchParams(parametros)}` : rota;
  const prazo = AbortSignal.timeout(10000);
  const opcoes = { cache: "no-store", signal: sinal ? AbortSignal.any([prazo, sinal]) : prazo };
  if (dados) {
    opcoes.method = "POST";
    opcoes.headers = { "Content-Type": "application/json" };
    opcoes.body = JSON.stringify(dados);
  }
  const resposta = await fetch(url, opcoes);
  if (!resposta.ok) {
    const corpo = await resposta.json().catch(() => null);
    throw new ErroApi(resposta.status, corpo?.detail);
  }
  return resposta.json();
}

function linkEscolhido() {
  return estado.links?.find(({ short_code }) => short_code === estado.codigo);
}

function definirLink(codigo) {
  if (estado.codigo === codigo) return;
  estado.codigo = codigo;
  estado.historico = null;
  estado.divergente = false;
  elemento("detalhes-link").open = false;
  limparRetornoCopia();
}

function definirCliente(id) {
  estado.clienteId = id;
  estado.links = null;
  estado.campanhas = null;
  estado.falhou = false;
  definirLink("");
  renderizarOpcoesCampanha();
  cliente.value = id;
}

function renderizarClientes() {
  const clientes = estado.clientes ?? [];
  const rotulo = clientes.length ? "Selecione um cliente" : "Nenhum cliente cadastrado";
  cliente.replaceChildren(criarOpcao(rotulo, ""), ...clientes.map(({ nome, cliente_id }) => criarOpcao(nome, cliente_id)));
  cliente.value = estado.clienteId;
}

function renderizarOpcoesCampanha() {
  const campanhas = estado.campanhas ?? [];
  const assinatura = JSON.stringify(campanhas.map(({ nome, campanha_id }) => [nome, campanha_id]));
  // Redesenhar a cada ciclo fecharia o seletor aberto no formulário de link.
  if (assinatura === assinaturaCampanhas) return;
  assinaturaCampanhas = assinatura;
  const selecionada = seletorCampanha.value;
  const opcoes = campanhas.map(({ nome, campanha_id }) => criarOpcao(nome, campanha_id));
  seletorCampanha.replaceChildren(criarOpcao("Sem campanha", ""), ...opcoes);
  if (opcoes.some(({ value }) => value === selecionada)) seletorCampanha.value = selecionada;
}

async function carregarContexto(sinal) {
  const contexto = await buscarContexto(requisitar, estado.clienteId, sinal);
  sinal.throwIfAborted();
  if (contexto.links) {
    estado.links = contexto.links;
    if (!linkEscolhido()) definirLink(estado.links[0]?.short_code ?? "");
  }
  if (contexto.campanhas) {
    estado.campanhas = contexto.campanhas;
    renderizarOpcoesCampanha();
  }
  return contexto.falhou;
}

async function carregarHistorico(sinal) {
  const historico = await buscarHistorico(requisitar, estado.codigo, estado.clienteId, sinal);
  estado.divergente = !historico;
  if (historico) estado.historico = historico;
}

async function atualizar({ forcar = false } = {}) {
  if (consultaAtiva && !forcar) return;
  consultaAtiva?.abort();
  const consulta = new AbortController();
  consultaAtiva = consulta;
  let falhou = false;
  try {
    if (!estado.clientes) {
      const clientes = await requisitar("/clientes", { sinal: consulta.signal });
      consulta.signal.throwIfAborted();
      estado.clientes = clientes;
      if (clientes.length === 1) definirCliente(clientes[0].cliente_id);
      renderizarClientes();
    }
    if (estado.clienteId) {
      falhou = await carregarContexto(consulta.signal);
      consulta.signal.throwIfAborted();
      renderizar();
      if (estado.codigo) await carregarHistorico(consulta.signal);
    }
  } catch {
    falhou = true;
  } finally {
    if (consultaAtiva === consulta) {
      consultaAtiva = null;
      estado.falhou = falhou;
      renderizar();
    }
  }
}

function renderizarListaLinks() {
  const links = estado.links ?? [];
  const assinatura = JSON.stringify(links.map(({ short_code, canal }) => [short_code, canal]));
  if (assinatura !== assinaturaLinks) {
    assinaturaLinks = assinatura;
    const itens = links.map(({ short_code, canal }) => {
      const botao = criarElemento("button", undefined, "item-link");
      botao.type = "button";
      botao.dataset.codigo = short_code;
      const icone = elemento("icone-link").content.cloneNode(true);
      const rotulo = criarElemento("span");
      rotulo.append(criarElemento("strong", canal || short_code));
      if (canal) rotulo.append(criarElemento("small", short_code));
      botao.append(icone, rotulo);
      const item = criarElemento("li");
      item.append(botao);
      return item;
    });
    listaLinks.replaceChildren(...itens);
  }
  for (const botao of listaLinks.querySelectorAll("button")) {
    if (botao.dataset.codigo === estado.codigo) botao.setAttribute("aria-current", "true");
    else botao.removeAttribute("aria-current");
  }
  const mensagem = elemento("mensagem-links");
  mensagem.hidden = links.length > 0;
  if (!estado.clientes) mensagem.textContent = estado.falhou ? "Clientes indisponíveis." : "Carregando…";
  else if (!estado.clienteId) mensagem.textContent = "Escolha um cliente para ver os links.";
  else if (estado.links) mensagem.textContent = "Nenhum link cadastrado.";
  else mensagem.textContent = estado.falhou ? "Links indisponíveis." : "Carregando links…";
}

function renderizarVazio() {
  let titulo = "Carregando clientes…";
  let explicacao = "";
  let acao = "";
  if (!estado.clientes) {
    if (estado.falhou) titulo = "Clientes indisponíveis";
  } else if (!estado.clientes.length) {
    titulo = "Cadastre seu primeiro cliente";
    explicacao = "Escolha um nome para começar a cadastrar campanhas e links.";
    acao = "novo-cliente";
  } else if (!estado.clienteId) {
    titulo = "Selecione um cliente";
    explicacao = "Use o seletor na barra lateral para ver os links do cliente.";
  } else if (!estado.links) {
    titulo = estado.falhou ? "Links indisponíveis" : "Carregando links…";
  } else {
    titulo = "Crie o primeiro link deste cliente";
    explicacao = "Ao criar um link curto, você pode acompanhar os cliques neste painel.";
    acao = "novo-link";
  }
  exibirTexto(elemento("titulo-vazio"), titulo);
  exibirTexto(elemento("explicacao-vazio"), explicacao);
  const botao = elemento("acao-vazio");
  botao.hidden = !acao;
  botao.dataset.abrir = acao;
  if (acao) exibirTexto(botao, acao === "novo-cliente" ? "Novo cliente" : "Novo link");
}

function renderizarCampanha(link) {
  const campanha = campanhaDoLink(estado.campanhas, link.short_code);
  const nome = elemento("nome-campanha");
  const descricao = elemento("descricao-campanha");
  const tags = elemento("tags-campanha");
  nome.hidden = !campanha;
  exibirTexto(nome, campanha?.nome ?? "");
  let texto = "Sem campanha vinculada.";
  if (!estado.campanhas) texto = estado.falhou ? "Campanhas indisponíveis." : "Carregando campanhas…";
  if (campanha) texto = campanha.descricao ?? "";
  descricao.hidden = !texto;
  exibirTexto(descricao, texto);
  const nomesTags = campanha?.tags ?? [];
  tags.hidden = !nomesTags.length;
  const visiveis = Array.from(tags.children, (item) => item.textContent);
  if (JSON.stringify(visiveis) !== JSON.stringify(nomesTags)) {
    tags.replaceChildren(...nomesTags.map((tag) => criarElemento("li", tag)));
  }
}

function exibirData(data, vazio) {
  return data ? `${dataBrasilia.format(new Date(data))} (Brasília)` : vazio;
}

function renderizarResumo(link, historico) {
  const endereco = `${location.origin}/r/${encodeURIComponent(link.short_code)}`;
  const nome = elemento("nome-link");
  exibirTexto(nome, link.canal || link.short_code);
  nome.title = nome.textContent;
  const ancora = elemento("endereco-curto");
  ancora.href = endereco;
  exibirTexto(ancora, endereco);
  exibirTexto(elemento("destino-link"), link.url ?? "—");
  exibirTexto(elemento("criado-link"), exibirData(link.criado_em, "—"));
  exibirTexto(elemento("expiracao-link"), exibirData(link.expira_em, "Sem expiração"));
  exibirTexto(elemento("contador"), numeros.format(link.contador));
  exibirTexto(elemento("total"), historico ? numeros.format(historico.total) : "—");
  const { rotulo } = historico?.periodo ?? janelaDosSeteDias();
  exibirTexto(elemento("intervalo"), `${rotulo} · Brasília`);
  exibirTexto(elemento("intervalo-dia"), rotulo);
  const atualizacao = elemento("ultima-atualizacao");
  if (historico) {
    atualizacao.dateTime = historico.atualizadoEm.toISOString();
    exibirTexto(atualizacao, `Atualizado às ${horaBrasilia.format(historico.atualizadoEm)}`);
  } else {
    atualizacao.removeAttribute("datetime");
    exibirTexto(atualizacao, "Aguardando dados");
  }
  renderizarCampanha(link);
}

function renderizar() {
  cliente.disabled = !estado.clientes?.length;
  if (!estado.clientes) exibirTexto(cliente.options[0], estado.falhou ? "Clientes indisponíveis" : "Carregando clientes…");
  for (const botao of document.querySelectorAll(".acoes [data-abrir]")) {
    botao.disabled = botao.dataset.abrir === "novo-cliente" ? !estado.clientes : !estado.clienteId;
  }
  renderizarListaLinks();

  const aviso = elemento("aviso");
  const { historico } = estado;
  const mantendoDados = historico ? " O histórico anterior continua visível." : "";
  let textoAviso = "";
  if (estado.falhou) textoAviso = `Falha ao atualizar os dados.${mantendoDados} A tela tenta novamente em instantes.`;
  else if (estado.divergente) textoAviso = `Os cliques mudaram durante a leitura.${mantendoDados} A tela tenta novamente em instantes.`;
  aviso.hidden = !textoAviso;
  exibirTexto(aviso, textoAviso);
  const link = linkEscolhido();
  for (const id of ["cabecalho-link", "resumo", "dia", "dispositivos", "canais"]) elemento(id).hidden = !link;
  elemento("estado-vazio").hidden = Boolean(link);
  if (!link) {
    renderizarVazio();
    return;
  }
  renderizarResumo(link, historico);
  for (const id of ["dia", "dispositivos", "canais"]) {
    elemento(`dados-${id}`).hidden = !historico;
    const mensagem = elemento(`estado-${id}`);
    mensagem.hidden = Boolean(historico);
    let textoEstado = "Carregando cliques…";
    if (estado.falhou) textoEstado = "Cliques indisponíveis no momento.";
    else if (estado.divergente) textoEstado = "Os cliques mudaram durante a leitura. Tentando de novo…";
    exibirTexto(mensagem, textoEstado);
  }
  // Na virada do dia, um histórico mantido depois de uma falha precisa perder o "Hoje".
  const hoje = diaEmBrasilia(new Date());
  if (historico && (historico !== historicoExibido || hoje !== diaExibido)) {
    renderizarGraficos(historico);
    historicoExibido = historico;
    diaExibido = hoje;
  }
}

function atualizarGrafico(chave, configuracao) {
  if (graficos[chave]) {
    graficos[chave].data = configuracao.data;
    graficos[chave].update("none");
  } else {
    graficos[chave] = new Chart(elemento(`grafico-${chave}`), configuracao);
  }
}

const rotulosBarras = {
  id: "rotulos-barras",
  afterDatasetsDraw(grafico) {
    const { ctx } = grafico;
    const barras = grafico.getDatasetMeta(0).data;
    ctx.save();
    ctx.fillStyle = cor("--texto");
    ctx.font = `600 12px ${tema.fontFamily}`;
    ctx.textAlign = "center";
    ctx.textBaseline = "bottom";
    barras.forEach(({ x, y }, indice) => {
      ctx.fillText(numeros.format(grafico.data.datasets[0].data[indice]), x, y - 5);
    });
    ctx.restore();
  },
};

const trilhasCanais = {
  id: "trilhas-canais",
  beforeDatasetsDraw(grafico) {
    const { ctx, chartArea } = grafico;
    ctx.save();
    ctx.fillStyle = cor("--grafico-trilha");
    for (const barra of grafico.getDatasetMeta(0).data) {
      ctx.beginPath();
      ctx.roundRect(chartArea.left, barra.y - barra.height / 2, chartArea.width, barra.height, barra.height / 2);
      ctx.fill();
    }
    ctx.restore();
  },
};

const opcoesGraficos = { animation: false, maintainAspectRatio: false, locale: "pt-BR" };

function renderizarPorDia(dias) {
  const marcados = rotulosDosDias(dias);
  const rotulos = marcados.map(({ texto }) => texto);
  const tabela = elemento("tabela-dia");
  tabela.tBodies[0].replaceChildren(...dias.map(({ cliques }, indice) => {
    const linha = criarElemento("tr");
    linha.append(criarElemento("td", rotulos[indice]), criarElemento("td", numeros.format(cliques)));
    return linha;
  }));
  if (typeof Chart === "undefined") {
    elemento("quadro-dia").hidden = true;
    elemento("quadro-tabela-dia").classList.remove("sr-only");
    tabela.className = "tabela-sem-grafico";
    return;
  }
  atualizarGrafico("dia", {
    type: "bar",
    data: {
      labels: rotulos,
      datasets: [{
        label: "Cliques",
        data: dias.map(({ cliques }) => cliques),
        backgroundColor: marcados.map(({ hoje }) => cor(hoje ? "--destaque" : "--grafico-barra")),
        borderRadius: 6,
        maxBarThickness: 76,
      }],
    },
    options: {
      ...opcoesGraficos,
      layout: { padding: { top: 12 } },
      scales: {
        x: {
          grid: { display: false },
          ticks: {
            autoSkip: false, maxRotation: 0,
            // As opções ficam da criação do gráfico; o rótulo de cada ciclo diz qual barra é hoje.
            color: ({ chart, index }) => cor(chart.data.labels[index]?.endsWith(SUFIXO_HOJE) ? "--destaque" : "--secundario"),
          },
        },
        y: { beginAtZero: true, suggestedMax: 1, grace: "10%", ticks: { precision: 0 }, grid: { color: cor("--grafico-grade") } },
      },
      plugins: { legend: { display: false } },
    },
    plugins: [rotulosBarras],
  });
}

function renderizarPorDispositivo(itens) {
  const soma = itens.reduce((anterior, { cliques }) => anterior + cliques, 0);
  exibirTexto(elemento("total-dispositivos"), numeros.format(soma));
  exibirTexto(elemento("unidade-dispositivos"), soma === 1 ? "clique" : "cliques");
  elemento("rosca").classList.toggle("sem-cliques", soma === 0);
  elemento("legenda-dispositivos").replaceChildren(...itens.map(({ dispositivo, cliques }, indice) => {
    const linha = criarElemento("li");
    const amostra = criarElemento("span", undefined, "amostra");
    amostra.style.setProperty("--amostra", coresDispositivos[indice]);
    amostra.setAttribute("aria-hidden", "true");
    linha.append(amostra, criarElemento("span", dispositivos[dispositivo]), criarElemento("strong", numeros.format(cliques)));
    return linha;
  }));
  if (typeof Chart === "undefined") {
    elemento("rosca").hidden = true;
    return;
  }
  atualizarGrafico("dispositivos", {
    type: "doughnut",
    data: {
      labels: itens.map(({ dispositivo }) => dispositivos[dispositivo]),
      datasets: [{ data: itens.map(({ cliques }) => cliques), backgroundColor: coresDispositivos, borderWidth: 2 }],
    },
    options: { ...opcoesGraficos, cutout: "62%", plugins: { legend: { display: false } } },
  });
}

function renderizarPorCanal(canais) {
  const total = canais.reduce((soma, { cliques }) => soma + cliques, 0);
  const participacoes = canais.map(({ cliques }) => total ? cliques / total : 0);
  const usos = new Map();
  for (const { canal } of canais) usos.set(canal, (usos.get(canal) ?? 0) + 1);
  const rotulos = canais.map(({ canal, short_code }) => {
    if (!canal) return short_code;
    return usos.get(canal) > 1 ? `${canal} · ${short_code}` : canal;
  });
  const lista = elemento("lista-canais");
  lista.replaceChildren(...canais.map(({ cliques, short_code }, indice) => {
    const linha = criarElemento("li");
    const nome = criarElemento("span", rotulos[indice], "nome-canal");
    nome.title = rotulos[indice];
    if (short_code === estado.codigo) linha.setAttribute("aria-current", "true");
    const participacao = participacoes[indice];
    const percentual = participacao > 0 && participacao < .001
      ? `<${percentuais.format(.001)}`
      : percentuais.format(participacao);
    linha.append(nome, criarElemento("strong", numeros.format(cliques)), criarElemento("span", percentual, "percentual-canal"));
    return linha;
  }));
  if (typeof Chart === "undefined") {
    lista.classList.add("canais-sem-grafico");
    return;
  }
  atualizarGrafico("canais", {
    type: "bar",
    data: {
      labels: rotulos,
      datasets: [{
        data: participacoes,
        backgroundColor: canais.map(({ short_code, cliques }) => {
          if (!cliques) return "transparent";
          return cor(short_code === estado.codigo ? "--destaque" : "--grafico-barra");
        }),
        borderRadius: 5,
        borderSkipped: false,
        barThickness: 9,
      }],
    },
    options: {
      ...opcoesGraficos,
      indexAxis: "y", events: [], layout: { autoPadding: false },
      scales: { x: { display: false, min: 0, max: 1 }, y: { display: false } },
      plugins: { legend: { display: false }, tooltip: { enabled: false } },
    },
    plugins: [trilhasCanais],
  });
}

function renderizarGraficos(historico) {
  renderizarPorDia(historico.dias);
  renderizarPorDispositivo(historico.dispositivos);
  renderizarPorCanal(historico.canais);
}

function limparRetornoCopia() {
  clearTimeout(tempoRetornoCopia);
  exibirTexto(elemento("rotulo-copiar"), "Copiar link");
  exibirTexto(elemento("retorno-copiar"), "");
}

async function copiarLink() {
  const ancora = elemento("endereco-curto");
  const codigo = estado.codigo;
  try {
    await navigator.clipboard.writeText(ancora.href);
    if (estado.codigo !== codigo) return;
    exibirTexto(elemento("rotulo-copiar"), "Copiado!");
    exibirTexto(elemento("retorno-copiar"), "Link copiado.");
  } catch {
    if (estado.codigo !== codigo) return;
    const selecao = window.getSelection();
    const intervalo = document.createRange();
    intervalo.selectNodeContents(ancora);
    selecao.removeAllRanges();
    selecao.addRange(intervalo);
    exibirTexto(elemento("rotulo-copiar"), "Use Ctrl+C");
    exibirTexto(elemento("retorno-copiar"), "Link selecionado. Use Ctrl+C para copiar.");
  }
  clearTimeout(tempoRetornoCopia);
  tempoRetornoCopia = setTimeout(limparRetornoCopia, 2500);
}

function limparErroCampo(campo) {
  campo.removeAttribute("aria-invalid");
  const aviso = campo.closest(".campo").querySelector(".erro-campo");
  aviso.hidden = true;
  aviso.textContent = "";
}

function limparErros(formulario) {
  for (const campo of formulario.querySelectorAll("[aria-invalid]")) limparErroCampo(campo);
  const aviso = formulario.querySelector(".erro-formulario");
  aviso.hidden = true;
  aviso.textContent = "";
}

function mostrarErroCampo(campo, mensagem) {
  campo.setAttribute("aria-invalid", "true");
  const aviso = campo.closest(".campo").querySelector(".erro-campo");
  aviso.textContent = [aviso.textContent, mensagem].filter(Boolean).join(" ");
  aviso.hidden = false;
}

function mensagemValidacao({ type, msg }) {
  if (type === "missing" || type === "string_too_short") return "Preencha este campo.";
  return msg?.replace(/^Value error, /, "") || "Confira este campo.";
}

function mostrarErroCadastro(formulario, erro) {
  const aviso = formulario.querySelector(".erro-formulario");
  let mensagem = "Não foi possível concluir o cadastro. Tente novamente.";
  if (erro.status === 422 && Array.isArray(erro.detalhe)) {
    const gerais = [];
    for (const detalhe of erro.detalhe) {
      const campo = formulario.elements.namedItem(detalhe.loc?.[1]);
      if (campo?.closest(".campo")) mostrarErroCampo(campo, mensagemValidacao(detalhe));
      else gerais.push(mensagemValidacao(detalhe));
    }
    formulario.querySelector("[aria-invalid]")?.focus();
    if (!gerais.length) return;
    mensagem = gerais.join(" ");
  } else if (erro.status === 422 && typeof erro.detalhe === "string" && erro.detalhe.startsWith("campanha_id")) {
    const motivo = erro.detalhe === "campanha_id é de outro cliente" ? "é de outro cliente" : "não existe";
    mostrarErroCampo(seletorCampanha, `Esta campanha ${motivo}. Selecione outra ou deixe o campo em branco.`);
    seletorCampanha.focus();
    return;
  } else if (erro.status === 503 && formulario.dataset.rota === "links") {
    mensagem = "A criação de links está indisponível no momento. Tente de novo em instantes.";
  } else if (erro instanceof TypeError || erro.name === "TimeoutError") {
    mensagem = "A conexão falhou. Confira se o cadastro apareceu antes de enviar novamente.";
  }
  aviso.textContent = mensagem;
  aviso.hidden = false;
}

function dadosCadastro(formulario) {
  const rota = formulario.dataset.rota;
  const campos = new FormData(formulario);
  const valor = (nome) => campos.get(nome)?.trim();
  if (rota === "clientes") return { nome: valor("nome") };
  if (rota === "campanhas") {
    return {
      cliente_id: estado.clienteId,
      nome: valor("nome"),
      descricao: valor("descricao") || null,
      tags: valor("tags").split(",").map((tag) => tag.trim()).filter(Boolean),
    };
  }
  const expiracao = valor("expira_em");
  return {
    cliente_id: estado.clienteId,
    url: valor("url"),
    canal: valor("canal") || null,
    campanha_id: valor("campanha_id") || null,
    expira_em: expiracao ? new Date(expiracao).toISOString() : null,
  };
}

function cadastroConcluido(rota, dados, retorno) {
  if (rota === "clientes") {
    estado.clientes = [...estado.clientes, { cliente_id: retorno.cliente_id, nome: dados.nome }];
    estado.clientes.sort((primeiro, segundo) => primeiro.nome.localeCompare(segundo.nome, "pt-BR"));
    definirCliente(retorno.cliente_id);
    renderizarClientes();
  } else if (rota === "links") {
    const { short_code } = retorno;
    const { url, canal, expira_em } = dados;
    estado.links = [{ short_code, url, canal, expira_em, contador: 0 }, ...(estado.links ?? [])];
    definirLink(short_code);
  }
  renderizar();
  atualizar({ forcar: true });
}

async function enviarCadastro(evento) {
  evento.preventDefault();
  const formulario = evento.currentTarget;
  const dialogo = formulario.closest("dialog");
  const botoes = [...formulario.querySelectorAll("button")];
  if (botoes.some((botao) => botao.disabled)) return;
  limparErros(formulario);
  const expiracao = formulario.elements.namedItem("expira_em");
  if (expiracao?.validity.badInput) {
    mostrarErroCampo(expiracao, "Informe uma data e hora válidas.");
    expiracao.focus();
    return;
  }
  const rota = formulario.dataset.rota;
  botoes.forEach((botao) => { botao.disabled = true; });
  dialogo.setAttribute("aria-busy", "true");
  let retorno;
  let dados;
  try {
    dados = dadosCadastro(formulario);
    retorno = await requisitar(`/${rota}`, { dados });
  } catch (erro) {
    mostrarErroCadastro(formulario, erro);
  } finally {
    botoes.forEach((botao) => { botao.disabled = false; });
    dialogo.removeAttribute("aria-busy");
  }
  if (retorno) {
    dialogo.close();
    cadastroConcluido(rota, dados, retorno);
  }
}

cliente.addEventListener("change", () => {
  definirCliente(cliente.value);
  renderizar();
  atualizar({ forcar: true });
});

listaLinks.addEventListener("click", (evento) => {
  const botao = evento.target.closest("[data-codigo]");
  if (!botao || botao.dataset.codigo === estado.codigo) return;
  definirLink(botao.dataset.codigo);
  estado.falhou = false;
  renderizar();
  atualizar({ forcar: true });
});

document.addEventListener("click", (evento) => {
  const botao = evento.target.closest("[data-abrir]");
  if (!botao?.dataset.abrir) return;
  const dialogo = elemento(botao.dataset.abrir);
  const formulario = dialogo.querySelector("form");
  formulario.reset();
  limparErros(formulario);
  dialogo.showModal();
});

for (const dialogo of document.querySelectorAll("dialog")) {
  const formulario = dialogo.querySelector("form");
  formulario.addEventListener("submit", enviarCadastro);
  formulario.addEventListener("input", ({ target }) => {
    if (target.hasAttribute("aria-invalid")) limparErroCampo(target);
  });
  formulario.querySelector("[data-fechar]").addEventListener("click", () => dialogo.close());
  dialogo.addEventListener("cancel", (evento) => {
    if (dialogo.hasAttribute("aria-busy")) evento.preventDefault();
  });
}

elemento("copiar").addEventListener("click", copiarLink);
atualizar();
setInterval(atualizar, INTERVALO_ATUALIZACAO_MS);
