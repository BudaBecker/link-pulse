const FUSO_BRASILIA = "America/Sao_Paulo";
const TENTATIVAS_COERENTES = 3;
const diaBrasilia = new Intl.DateTimeFormat("pt-BR", {
  timeZone: FUSO_BRASILIA, year: "numeric", month: "2-digit", day: "2-digit",
});
const fusoBrasilia = new Intl.DateTimeFormat("pt-BR", {
  timeZone: FUSO_BRASILIA, timeZoneName: "longOffset",
});
const diaCurto = new Intl.DateTimeFormat("pt-BR", { timeZone: "UTC", month: "2-digit", day: "2-digit" });

function exibirDia(iso) {
  return diaCurto.format(new Date(`${iso}T12:00:00Z`));
}

function janelaDosSeteDias(agora = new Date()) {
  const partes = Object.fromEntries(diaBrasilia.formatToParts(agora).map(({ type, value }) => [type, value]));
  const hoje = `${partes.year}-${partes.month}-${partes.day}`;
  const seisDiasAtras = new Date(`${hoje}T12:00:00Z`);
  // A aritmética em UTC desloca a data civil sem depender do fuso do computador.
  seisDiasAtras.setUTCDate(seisDiasAtras.getUTCDate() - 6);
  const primeiroDia = seisDiasAtras.toISOString().slice(0, 10);
  const deslocamento = (dia) => fusoBrasilia.formatToParts(new Date(`${dia}T12:00:00Z`))
    .find(({ type }) => type === "timeZoneName").value.slice(3);
  return {
    inicio: `${primeiroDia}T00:00:00.000${deslocamento(primeiroDia)}`,
    fim: `${hoje}T23:59:59.999${deslocamento(hoje)}`,
    rotulo: `${exibirDia(primeiroDia)} a ${exibirDia(hoje)}`,
  };
}

async function buscarContexto(requisitar, clienteId, sinal) {
  const parametros = { cliente_id: clienteId };
  // As campanhas vêm a cada ciclo: um link criado em outra aba pode ter entrado numa delas.
  const [links, campanhas] = await Promise.allSettled([
    requisitar("/links", { parametros, sinal }),
    requisitar("/campanhas", { parametros, sinal }),
  ]);
  return {
    links: links.status === "fulfilled" ? links.value : null,
    campanhas: campanhas.status === "fulfilled" ? campanhas.value : null,
    falhou: links.status === "rejected" || campanhas.status === "rejected",
  };
}

function campanhaDoLink(campanhas, codigo) {
  return campanhas?.find(({ links }) => links.includes(codigo));
}

function somaDosCliques(itens) {
  return itens.reduce((soma, { cliques }) => soma + cliques, 0);
}

function historicoCoerente({ total, dias, dispositivos, canais }, codigo) {
  const doLink = canais.find(({ short_code }) => short_code === codigo);
  return somaDosCliques(dias) === total && somaDosCliques(dispositivos) === total && doLink?.cliques === total;
}

// As quatro consultas leem o Cassandra em momentos diferentes; um clique entre elas
// deixaria o total diferente da soma das barras (Q-56). Sem coerência, devolve null.
async function buscarHistorico(requisitar, codigo, clienteId, sinal, agora = new Date()) {
  const periodo = janelaDosSeteDias(agora);
  const { inicio, fim } = periodo;
  const link = { short_code: codigo, inicio, fim };
  const cliente = { cliente_id: clienteId, inicio, fim };
  for (let tentativa = 0; tentativa < TENTATIVAS_COERENTES; tentativa += 1) {
    const [total, porDia, porDispositivo, porCanal] = await Promise.all([
      requisitar("/analytics/total", { parametros: link, sinal }),
      requisitar("/analytics/por-dia", { parametros: link, sinal }),
      requisitar("/analytics/por-dispositivo", { parametros: link, sinal }),
      requisitar("/analytics/por-canal", { parametros: cliente, sinal }),
    ]);
    sinal?.throwIfAborted();
    const historico = {
      periodo, total: total.cliques, dias: porDia.dias, dispositivos: porDispositivo.dispositivos,
      canais: porCanal.canais, atualizadoEm: new Date(),
    };
    if (historicoCoerente(historico, codigo)) return historico;
  }
  return null;
}
