// Roda uma função de app/static/dados.js com respostas controladas da API (Q-56).
// Entrada (stdin): {funcao, argumentos, respostas: {rota: [resposta, ...]}}; cada chamada
// a uma rota consome a próxima resposta da fila, e a última se repete.
// Saída (stdout): {resultado, chamadas: [{rota, parametros}]}.
import { readFileSync } from "node:fs";
import vm from "node:vm";

const contexto = vm.createContext({ Intl, Date, Promise, AbortSignal, AbortController, JSON });
vm.runInContext(readFileSync(process.argv[2], "utf8"), contexto, { filename: "dados.js" });

const { funcao, argumentos, respostas } = JSON.parse(readFileSync(0, "utf8"));
const chamadas = [];
async function requisitar(rota, { parametros } = {}) {
  chamadas.push({ rota, parametros });
  const fila = respostas[rota];
  if (!fila) throw new Error(`rota sem resposta: ${rota}`);
  return fila.length > 1 ? fila.shift() : fila[0];
}

const alvo = vm.runInContext(funcao, contexto);
const usaRequisitar = ["buscarContexto", "buscarHistorico"].includes(funcao);
const convertidos = argumentos.map((valor) => (typeof valor === "string" && valor.startsWith("data:") ? new Date(valor.slice(5)) : valor));
const resultado = await (usaRequisitar ? alvo(requisitar, ...convertidos) : alvo(...convertidos));
process.stdout.write(JSON.stringify({ resultado: resultado ?? null, chamadas }));
