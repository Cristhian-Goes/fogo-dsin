import { api } from "./api.js";
import { esc } from "./format.js";
import { state } from "./state.js";

let report;

export function destroy() {
  report = null;
}

export async function mount(main) {
  main.innerHTML = `<section class="page"><p>Carregando a previsão…</p></section>`;
  try {
    report = await api.predictions();
    paint(main);
  } catch (error) {
    main.innerHTML = `<section class="page"><p class="form-error">${esc(error.message)}</p></section>`;
  }
}

export function reload() {
  const main = document.getElementById("main");
  if (main && state.view === "previsao") mount(main);
}

function paint(main) {
  const days = report.recommendations.filter((item) => item.scope === "dia");
  const risks = report.equipment_risks || [];
  main.innerHTML = `
    <section class="page">
      <h1>Previsão operacional</h1>
      ${state.region ? `<p class="hint">Contexto: ${esc(state.region)}. A conta abaixo é do dia escolhido; o botão da região abre o mapa filtrado.</p>` : ""}
      <p>${esc(report.focus_label)}. ${esc(report.framing)}</p>
      <div class="filters" id="day-switch">
        ${shortcut("today", "Hoje")}
        ${shortcut("tomorrow", "Amanhã")}
        ${shortcut("saturday", "Sábado")}
        ${shortcut("weekday", "Terça")}
      </div>
      ${days.map((item) => card(item.region, `Pressão prevista ${item.hour}h–${Math.min(23, item.hour + 1)}h`, item.detail, item.action, item.why)).join("")
        || "<p>Nenhuma região pede reforço neste dia.</p>"}
      <h2>Equipamentos</h2>
      ${risks.slice(0, 4).map((item) => card(
        item.serial,
        item.horizon,
        `Probabilidade elevada de indisponibilidade (${item.score}).`,
        "Confirmar equipe e peça antes que o ponto saia do ar.",
        item.reasons,
        item.label,
      )).join("")}
      <h2>Machine Learning</h2>
      <p>${esc(report.ml?.note || "")}</p>
      <p class="hint">Modelo: ${esc(report.ml?.name || "")}. Variáveis: ${esc(report.ml?.features || "")}. Amostras: ${report.ml?.samples || 0}. Confiança do ajuste: ${report.ml?.confidence || 0}%.</p>
      <ul class="rows">
        ${(report.ml?.rows || []).map((row) => `<li>${esc(row.region)} às ${esc(row.hour)}: volume previsto ${String(row.predicted).replace(".", ",")}</li>`).join("")}
      </ul>
      <details>
        <summary>O que entra nesta conta</summary>
        <p>${esc(report.method.summary)}</p>
        <p>${esc(report.method.formula)}</p>
        <ul>${(report.method.inputs || []).map((item) => `<li>${esc(item)}</li>`).join("")}</ul>
      </details>
    </section>`;
  main.querySelectorAll("[data-date]").forEach((button) => {
    button.addEventListener("click", async () => {
      report = await api.predictions(button.dataset.date);
      paint(main);
    });
  });
}

function shortcut(key, label) {
  const date = report.shortcuts[key];
  const on = date === report.focus_date ? " is-on" : "";
  return `<button type="button" class="ghost${on}" data-date="${esc(date)}">${label}</button>`;
}

function card(title, when, reason, action, why, kicker) {
  const because = Array.isArray(why) ? why.join(" ") : reason;
  return `
    <article class="decision">
      <p class="meta">${esc(kicker || "Região")}</p>
      <h2>${esc(title)}</h2>
      <p>${esc(when)}</p>
      <div class="block"><b>Previsão</b>${esc(reason)}</div>
      <div class="block"><b>Motivo</b>${esc(because)}</div>
      <div class="block"><b>Recomendação</b>${esc(action)}</div>
      ${kicker ? "" : `<button type="button" class="primary" data-action="filter-region" data-region="${esc(title)}">Abrir ${esc(title)} no mapa</button>`}
    </article>`;
}
