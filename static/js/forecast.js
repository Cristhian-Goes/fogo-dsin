import { api } from "./api.js";
import { bindChart, chartPanel } from "./chart.js";
import { esc } from "./format.js";
import { state } from "./state.js";

let report;
const picked = { horizon: -1, availability: -1, incidents: -1 };

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

function series(rows, mapPoint) {
  const list = Array.isArray(rows) ? rows : [];
  return list.map(mapPoint).filter((item) => item && item.label);
}

function lastDays(rows, size = 24) {
  const list = Array.isArray(rows) ? rows : [];
  return list.length > size ? list.slice(-size) : list;
}

function axisNumber(value) {
  const number = Number(value) || 0;
  return Number.isInteger(number) ? String(number) : String(number).replace(".", ",");
}

function paint(main, focusChart) {
  const days = (report.recommendations || []).filter((item) => item.scope === "dia");
  const risks = report.equipment_risks || [];
  const method = report.method || {};
  const horizon = series(report.horizon_6h, (row) => ({
    label: String(row.label || ""),
    value: Number(row.ipo) || 0,
    display: `Pressão ${row.ipo}`,
    detail: `${row.region} · ${row.level_label}${row.gap ? ` · falta ${row.gap}` : ""}`,
  }));
  const availabilityAll = report.trends?.availability?.points || [];
  const availability = series(lastDays(availabilityAll), (row) => ({
    label: String(row.date || "").slice(5),
    value: Number(row.pct) || 0,
    display: `${String(row.pct).replace(".", ",")}%`,
    detail: row.date || "",
  }));
  const incidentAll = report.trends?.incidents?.points || [];
  const incidents = series(lastDays(incidentAll), (row) => ({
    label: String(row.date || "").slice(5),
    value: Number(row.count) || 0,
    display: `${row.count} ocorrências`,
    detail: row.date || "",
  }));
  const horizonAt = picked.horizon = horizon.length ? Math.min(horizon.length - 1, picked.horizon < 0 ? horizon.length - 1 : picked.horizon) : 0;
  const availabilityAt = picked.availability = availability.length ? Math.min(availability.length - 1, picked.availability < 0 ? availability.length - 1 : picked.availability) : 0;
  const incidentsAt = picked.incidents = incidents.length ? Math.min(incidents.length - 1, picked.incidents < 0 ? incidents.length - 1 : picked.incidents) : 0;
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
      <h2>Próximas 6 horas</h2>
      ${chartPanel(horizon, horizonAt, axisNumber, "Pressão nas próximas 6 horas")}
      <h2>Anomalia agora</h2>
      ${(report.anomalies || []).length
        ? (report.anomalies || []).map((item) => `<article class="decision"><h2>${esc(item.title)}</h2><p>${esc(item.detail)}</p></article>`).join("")
        : "<p>Nenhuma região está fora do padrão desta hora.</p>"}
      <h2>Disponibilidade</h2>
      <p>${esc(report.trends?.availability?.note || "")}</p>
      ${availabilityAll.length > availability.length ? `<p class="hint">O gráfico mostra os últimos ${availability.length} dias.</p>` : ""}
      ${chartPanel(availability, availabilityAt, (value) => `${axisNumber(value)}%`, "Disponibilidade")}
      <h2>Ocorrências no histórico</h2>
      <p class="hint">${esc(report.trends?.incidents?.note || "")}</p>
      ${incidentAll.length > incidents.length ? `<p class="hint">O gráfico mostra os últimos ${incidents.length} dias.</p>` : ""}
      ${chartPanel(incidents, incidentsAt, axisNumber, "Ocorrências")}
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
      <div class="actions">
        <button type="button" class="ghost" data-action="scenario" data-scenario="chuva">E se chover forte</button>
        <button type="button" class="ghost" data-action="briefing">Resumo do turno</button>
      </div>
      <details>
        <summary>O que entra nesta conta</summary>
        <p>${esc(method.summary || "")}</p>
        <p>${esc(method.formula || "")}</p>
        <ul>${(method.inputs || []).map((item) => `<li>${esc(item)}</li>`).join("")}</ul>
      </details>
    </section>`;
  main.querySelectorAll("[data-date]").forEach((button) => {
    button.addEventListener("click", async () => {
      report = await api.predictions(button.dataset.date);
      picked.horizon = -1;
      paint(main);
    });
  });
  const panels = {
    "Pressão nas próximas 6 horas": "horizon",
    "Disponibilidade": "availability",
    "Ocorrências": "incidents",
  };
  main.querySelectorAll(".chart-panel").forEach((panel) => {
    const key = panels[panel.dataset.chart];
    if (!key) return;
    bindChart(panel, (index) => {
      picked[key] = index;
      paint(main, panel.dataset.chart);
    });
  });
  if (focusChart) main.querySelector(`[data-chart="${focusChart}"] .chart-point.is-on circle`)?.focus();
}

function shortcut(key, label) {
  const date = report.shortcuts?.[key] || "";
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
