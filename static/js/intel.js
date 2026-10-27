import { api } from "./api.js";
import { esc, toast } from "./format.js";
import { state } from "./state.js";

let logNode;

export function mount(main) {
  const intel = state.bootstrap.intel || {};
  const impact = intel.impact || {};
  const before = intel.impact_before || {};
  main.innerHTML = `
    <section class="page">
      <h1>Inteligência operacional</h1>
      <p class="hint">Zumbis agora: ${intel.zombies || 0}. OS consolidadas: ${intel.consolidated || 0}. Viagens evitadas: ${impact.trips_avoided || 0}.</p>
      <div class="actions">
        <button type="button" class="primary" data-action="run-demo">Rodar cenário de demonstração</button>
        <button type="button" class="ghost" data-action="handoff">Gerar passagem de turno</button>
      </div>
      <p id="demo-log" class="hint"></p>
      <h2>Fila de decisões</h2>
      <p class="hint" title="${esc(intel.methods?.wait || "")}">No máximo 7 ações. O custo da espera está na frase.</p>
      <ul class="rows">
        ${(intel.decisions || []).map((item) => `
          <li class="os-card">
            <b>${esc(item.what)}</b>
            <p>${esc(item.why)}</p>
            <p class="hint">Quem: ${esc(item.who)}</p>
            <div class="actions">
              <button type="button" class="primary" data-action="decide" data-choice="aceitar" data-id="${esc(item.id)}">Aceitar</button>
              <button type="button" class="ghost" data-action="decide" data-choice="adiar" data-id="${esc(item.id)}">Adiar</button>
              <button type="button" class="ghost" data-action="decide" data-choice="dispensar" data-id="${esc(item.id)}">Dispensar</button>
            </div>
          </li>`).join("") || "<li>Nenhuma ação urgente na fila.</li>"}
      </ul>
      <h2>OS-mãe</h2>
      <p class="hint" title="${esc(intel.methods?.mother || "")}">${esc(intel.methods?.mother || "")}</p>
      ${(intel.mothers || []).map((item) => `
        <article class="os-card">
          <p>${esc(item.title)}</p>
          <button type="button" class="primary" data-action="resolve-mother" data-id="${esc(item.id)}">Resolver a mãe</button>
        </article>`).join("") || "<p class='hint'>Nenhuma causa raiz aberta.</p>"}
      <h2>Zumbis</h2>
      <p class="hint" title="${esc(intel.methods?.zombie || "")}">${esc(intel.methods?.zombie || "")}</p>
      <ul class="rows">
        ${(intel.zombie_rows || []).map((item) => `
          <li>
            <b>${esc(item.serial)}</b>
            <span>${esc(item.reason)} Esperado ${item.expected}, observado ${item.observed}.</span>
            <button type="button" class="ghost" data-action="diagnose" data-id="${esc(item.id)}">Diagnóstico</button>
            <button type="button" class="ghost" data-action="remote" data-id="${esc(item.id)}">Reiniciar remoto</button>
          </li>`).join("") || "<li>Nenhum equipamento zumbi agora.</li>"}
      </ul>
      <p id="diagnosis" class="hint"></p>
      <h2>Carona de manutenção</h2>
      <p class="hint" title="${esc(intel.methods?.ride || "")}">${esc(intel.methods?.ride || "")}</p>
      <ul class="rows">
        ${(intel.piggyback || []).map((item) => `
          <li><b>${esc(item.serial)}</b> <span>${esc(item.crew)} · desvio de ${item.extra_min} min</span>
            <button type="button" class="ghost" data-action="ride" data-crew="${esc(item.crew_id)}" data-id="${esc(item.equipment_id)}">Aceitar carona</button>
          </li>`).join("") || "<li>Nenhuma preventiva perto da rota. Calcule as rotas do dia antes.</li>"}
      </ul>
      <h2>Cobertura</h2>
      <p class="hint" title="${esc(intel.methods?.cover || "")}">${esc(intel.coverage?.note || "Ainda sem buraco calculado. O cenário de demonstração gera um.")}</p>
      <h2>Segurança do agente</h2>
      <ul class="rows">
        ${(intel.safety || []).map((item) => `<li><b>${esc(item.agent)}</b> <span>${esc(item.reason)} Próximos: ${esc((item.nearest || []).join(", ") || "ninguém")}</span></li>`).join("") || "<li>Nenhum alerta de segurança.</li>"}
      </ul>
      <p class="hint">Em produção, localização de agente exige base legal e transparência, nos termos da LGPD.</p>
      <h2>Fornecedores</h2>
      <p class="hint" title="${esc(intel.methods?.vendor || "")}">${esc(intel.methods?.vendor || "")}</p>
      <ul class="rows">
        ${(intel.vendors || []).map((item) => `<li><b>${esc(item.supplier)}</b> <span>${esc(item.notice)} Violações: ${item.violations}.</span></li>`).join("") || "<li>Sem OS concluída para comparar contrato.</li>"}
      </ul>
      <h2>Equipamento problemático</h2>
      <ul class="rows">
        ${(intel.problems || []).map((item) => `<li><b>${esc(item.serial)} · ${esc(item.advice)}</b> <span>${esc(item.why)}</span></li>`).join("") || "<li>Nenhum equipamento passou do critério.</li>"}
      </ul>
      <h2 id="impacto">Impacto operacional</h2>
      <table>
        <thead><tr><th>Indicador</th><th>Antes</th><th>Depois</th></tr></thead>
        <tbody>
          ${row("Viagens evitadas", before.trips_avoided, impact.trips_avoided)}
          ${row("OS consolidadas", before.orders_consolidated, impact.orders_consolidated)}
          ${row("Km economizados", before.km_saved, impact.km_saved)}
          ${row("Horas de cegueira evitadas", before.blind_hours, impact.blind_hours)}
          ${row("Cobertura recuperada", (before.coverage_pct || 0) + "%", (impact.coverage_pct || 0) + "%")}
        </tbody>
      </table>
    </section>`;
  logNode = document.getElementById("demo-log");
}

export function afterReload() {
  if ((state.view === "inteligencia" || state.view === "impacto") && !running) mount(document.getElementById("main"));
}

let running = false;

export async function handle(action, button) {
  if (action === "run-demo") {
    await run();
    return true;
  }
  if (action === "decide") {
    const reason = button.dataset.choice === "aceitar" ? "" : window.prompt("Motivo") || "";
    if (button.dataset.choice !== "aceitar" && !reason) return true;
    try { toast((await api.decide(button.dataset.id, button.dataset.choice, reason)).message); } catch (error) { toast(error.message, "bad"); }
    return true;
  }
  if (action === "remote") {
    try { toast((await api.remoteRestart(button.dataset.id)).message); } catch (error) { toast(error.message, "bad"); }
    return true;
  }
  if (action === "ride") {
    try { toast((await api.acceptRide(button.dataset.crew, button.dataset.id)).message); } catch (error) { toast(error.message, "bad"); }
    return true;
  }
  if (action === "resolve-mother") {
    try { toast((await api.resolveMother(button.dataset.id)).message); } catch (error) { toast(error.message, "bad"); }
    return true;
  }
  if (action === "diagnose") {
    try {
      const found = await api.diagnosis(button.dataset.id);
      const node = document.getElementById("diagnosis");
      if (node) node.textContent = `${found.serial}: causa mais provável ${found.cause}. Tente primeiro: ${found.remote} Kit: ${(found.parts || []).join(", ") || "nenhum"}. ${found.method}`;
    } catch (error) { toast(error.message, "bad"); }
    return true;
  }
  if (action === "handoff") {
    try {
      const pack = await api.handoff();
      if (logNode) logNode.textContent = pack.text;
    } catch (error) { toast(error.message, "bad"); }
    return true;
  }
  if (action === "safety-now") {
    try { toast((await api.safety(button.dataset.id, button.dataset.mode || "silent")).message); } catch (error) { toast(error.message, "bad"); }
    return true;
  }
  return false;
}

async function run() {
  if (running) return;
  running = true;
  const lines = [];
  for (let step = 1; step <= 6; step += 1) {
    try {
      const result = await api.demoStep(step);
      lines.push(`${step}. ${result.message}`);
      if (logNode) logNode.textContent = lines.join("\n");
    } catch (error) {
      toast(error.message, "bad");
      break;
    }
    if (step < 6) await wait(15000);
  }
  running = false;
}

function wait(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

function row(label, before, after) {
  return `<tr><td>${esc(label)}</td><td>${esc(before ?? 0)}</td><td>${esc(after ?? 0)}</td></tr>`;
}
