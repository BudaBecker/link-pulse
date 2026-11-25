// Roda uma função de app/static/dados.js fora do navegador (Q-56, Q-57).
// Entrada (stdin), um destes formatos:
// - {funcao, argumentos, respostas: {rota: [resposta, ...]}}: cada chamada a uma rota consome a
//   próxima resposta da fila, e a última se repete. Saída: {resultado, chamadas}.
// - {simulacao: {...}}: ciclos da tela num relógio simulado, com cliques contínuos.
//   Saída: {publicacoes: [{em, total}]}.
import { readFileSync } from "node:fs";
import vm from "node:vm";

const contexto = vm.createContext({ Intl, Date, Promise, AbortSignal, AbortController, JSON });
vm.runInContext(readFileSync(process.argv[2], "utf8"), contexto, { filename: "dados.js" });
const funcaoDosDados = (nome) => vm.runInContext(nome, contexto);
const entrada = JSON.parse(readFileSync(0, "utf8"));

async function rodarFuncao({ funcao, argumentos, respostas }) {
  const chamadas = [];
  async function requisitar(rota, { parametros } = {}) {
    chamadas.push({ rota, parametros });
    const fila = respostas[rota];
    if (!fila) throw new Error(`rota sem resposta: ${rota}`);
    return fila.length > 1 ? fila.shift() : fila[0];
  }
  const convertidos = argumentos.map((valor) => (typeof valor === "string" && valor.startsWith("data:") ? new Date(valor.slice(5)) : valor));
  const alvo = funcaoDosDados(funcao);
  const usaRequisitar = ["buscarContexto", "buscarHistorico"].includes(funcao);
  const resultado = await (usaRequisitar ? alvo(requisitar, ...convertidos) : alvo(...convertidos));
  return { resultado: resultado ?? null, chamadas };
}

// Um clique a cada cliqueACadaMs desde inicio; cada clique fica visível gravacaoMs depois de
// clicado_em, e cada consulta lê defasagemMs depois da anterior.
async function simular({ codigo, clienteId, inicio, cliqueACadaMs, gravacaoMs, defasagemMs, cicloMs, duracaoMs }) {
  const primeiro = Date.parse(inicio);
  let relogio = primeiro;
  const visiveis = (janelaInicio, janelaFim) => {
    const limite = Math.min(janelaFim, relogio - gravacaoMs);
    if (limite < Math.max(primeiro, janelaInicio)) return 0;
    return Math.floor((limite - primeiro) / cliqueACadaMs) + 1;
  };
  async function requisitar(rota, { parametros }) {
    relogio += defasagemMs;
    const cliques = visiveis(Date.parse(parametros.inicio), Date.parse(parametros.fim));
    if (rota === "/analytics/total") return { cliques };
    if (rota === "/analytics/por-dia") return { dias: [{ dia: "hoje", cliques }] };
    if (rota === "/analytics/por-dispositivo") return { dispositivos: [{ dispositivo: "mobile", cliques }] };
    return { canais: [{ short_code: codigo, canal: null, cliques }] };
  }
  const buscarHistorico = funcaoDosDados("buscarHistorico");
  const publicacoes = [];
  for (let ciclo = primeiro; ciclo < primeiro + duracaoMs; ciclo += cicloMs) {
    relogio = Math.max(relogio, ciclo);
    const historico = await buscarHistorico(requisitar, codigo, clienteId, null, new Date(relogio));
    if (historico) publicacoes.push({ em: relogio - primeiro, total: historico.total });
  }
  return { publicacoes };
}

const saida = entrada.simulacao ? await simular(entrada.simulacao) : await rodarFuncao(entrada);
process.stdout.write(JSON.stringify(saida));
