import { api } from "./api.js";
import { esc, fmt, toast, typeLabel } from "./format.js";
import { state } from "./state.js";

let report = null;
let chosen = null;
let riskMap = null;

const LEVEL_COLOR = {
  estavel: "#16352c",
  atencao: "#4a4318",
  pressao: "#6a3a14",
  critica: "#6e2430",
};

export async function mount(main) {
  main.innerHTML = `<section class="predict"><p class="hint">Calculando a pressão do dia…</p></section>`;
  try {
    report = await api.predictions();
    chosen = hottestCell();
    paint(main);
  } catch (error) {
    main.innerHTML = `<section class="predict"><p class="form-error">${esc(error.message)}</p></section>`;
  }
}

export function destroy() {
  if (riskMap) {
    riskMap.remove();
    riskMap = null;
  }
}

export function reload() {
  const main = document.getElementById("main");
  if (main && state.view === "preditivo") mount(main);
}

function paint(main) {
  if (riskMap) {
    riskMap.remove();
    riskMap = null;
  }
  const dayRecs = report.recommendations.filter((item) => item.scope === "dia");
  const nowRecs = report.recommendations.filter((item) => item.scope === "agora");
  main.innerHTML = `
    <section class="predict">
      <header class="predict-head">
        <div>
          <p class="eyebrow">Parte 3 · cidade preditiva</p>
          <h2>${esc(report.relation === "amanhã" ? "Amanhã" : "Dia projetado")}: ${esc(report.focus_label)}</h2>
          <p class="lead">${esc(report.framing)}</p>
        </div>
        <div class="day-switch" id="day-switch">
          ${shortcut("today", "Hoje")}
          ${shortcut("tomorrow", "Amanhã")}
          ${shortcut("saturday", "Sábado")}
          ${shortcut("weekday", "Terça")}
        </div>
      </header>
      ${hero(dayRecs[0] || nowRecs[0])}
      <div class="predict-grid">
        <section>
          <h3>Pressão por região e hora</h3>
          <p class="hint">Cada célula é o IPO daquela hora. Clique para ver de onde o número saiu.</p>
          <div class="heat-scroll">${heatGrid()}</div>
          <div class="scale"><i></i><span>estável</span><span>atenção</span><span>pressão</span><span>crítica</span></div>
          <div class="group-row">
            ${group("Exige atenção", report.groups.atencao)}
            ${group("Observar", report.groups.observar)}
            ${group("Em equilíbrio", report.groups.equilibrio)}
          </div>
        </section>
        <aside class="cell-card" id="cell-card">${cellCard()}</aside>
      </div>
      <section>
        <h3>Próximas 6 horas, a partir de agora</h3>
        <div class="horizon">${report.horizon_6h.map((item) => `
          <article class="tone-${item.level}">
            <b>${esc(item.label)}</b>
            <strong>${esc(item.region)}</strong>
            <span>IPO ${item.ipo}</span>
          </article>`).join("")}</div>
      </section>
      <section>
        <h3>Decisões</h3>
        <div class="recs">${report.recommendations.map(recCard).join("") || `<p class="hint">Nenhuma ação se destaca neste dia.</p>`}</div>
      </section>
      <div class="split">
        <section>
          <h3>Fora do padrão agora</h3>
          ${report.anomalies.length ? report.anomalies.map((item) => `
            <article class="rec">
              <strong>${esc(item.title)}</strong>
              <p>${esc(item.detail)}</p>
            </article>`).join("") : `<p class="hint">Nenhuma região está fora da própria média nas últimas 3 horas.</p>`}
        </section>
        <section>
          <h3>Risco dos equipamentos</h3>
          <div class="stack-list">${report.equipment_risks.map((item) => `
            <article class="alert">
              <strong>${esc(item.serial)} · ${item.score}</strong>
              <span>${esc(typeLabel(item.type))} · ${esc(item.region)} · ${esc(item.horizon)}</span>
              <span>${esc(item.reasons[0] || "")}</span>
            </article>`).join("")}</div>
        </section>
      </div>
      <section>
        <h3>Tendências</h3>
        <div class="trends">
          ${trendCard("Ocorrências por dia", report.trends.incidents.note, chart(report.trends.incidents.points, (p) => p.count, "#ffb15a"))}
          ${trendCard("Disponibilidade do cadastro", report.trends.availability.note, chart(report.trends.availability.points, (p) => p.pct, "#3ecf8e"))}
          ${report.trends.utilization.map((item) => trendCard(
            `${item.title}${item.delta_pct != null ? ` · ${item.delta_pct > 0 ? "+" : ""}${fmt(item.delta_pct)}%` : ""}`,
            item.note,
            chart(item.points, (p) => p.value, "#79b8ff"),
          )).join("")}
        </div>
      </section>
      <section class="method">
        <h3>O que está sendo previsto</h3>
        <p>${esc(report.method.summary)}</p>
        <p class="formula">${esc(report.method.formula)}</p>
        <details>
          <summary>Quais informações entram, e o que a conta não faz</summary>
          <ul>${report.method.inputs.map((item) => `<li>${esc(item)}</li>`).join("")}</ul>
          <ul>${report.method.assumptions.map((item) => `<li>${esc(item)}</li>`).join("")}</ul>
        </details>
        <p class="hint">Modelo ${esc(report.method.name)} ${esc(report.method.version)}. A tecnologia aqui é uma conta que dá para ler em voz alta. O valor está em ligar o cadastro, o agora e a escala.</p>
      </section>
    </section>`;
  main.querySelectorAll("[data-date]").forEach((button) => {
    button.addEventListener("click", () => loadDate(button.dataset.date, main));
  });
  main.querySelectorAll("[data-cell]").forEach((button) => {
    button.addEventListener("click", () => {
      const [region, hour] = button.dataset.cell.split("|");
      const row = report.grid.find((item) => item.region === region);
      chosen = { region, hour: Number(hour), cell: row.hours[Number(hour)], city: row.city };
      document.getElementById("cell-card").innerHTML = cellCard();
      main.querySelectorAll("[data-cell]").forEach((el) => el.classList.toggle("is-on", el === button));
    });
  });
}

function shortcut(key, label) {
  const date = report.shortcuts[key];
  const on = date === report.focus_date ? "is-on" : "";
  return `<button type="button" class="${on}" data-date="${esc(date)}">${esc(label)}</button>`;
}

async function loadDate(date, main) {
  try {
    report = await api.predictions(date);
    chosen = hottestCell();
    paint(main);
  } catch (error) {
    toast(error.message, "bad");
  }
}

function hottestCell() {
  let best = null;
  for (const row of report.grid) {
    for (const cell of row.hours) {
      if (!best || cell.ipo > best.cell.ipo) {
        best = { region: row.region, city: row.city, hour: cell.hour, cell };
      }
    }
  }
  return best;
}

function hero(rec) {
  if (!rec) return "";
  return `
    <article class="hero-rec">
      <span>Decisão mais útil deste dia</span>
      <h3>${esc(rec.title)}</h3>
      <p>${esc(rec.detail)}</p>
      <p class="action">${esc(rec.action)}</p>
    </article>`;
}

function heatGrid() {
  const hours = Array.from({ length: 24 }, (_, hour) => hour);
  const head = `<div class="heat"><div></div>${hours.map((hour) => `<div class="h">${hour}</div>`).join("")}`;
  const rows = report.grid.map((row) => `
    <div class="r">${esc(row.region)}</div>
    ${row.hours.map((cell) => `
      <button type="button" class="cell ${chosen && chosen.region === row.region && chosen.hour === cell.hour ? "is-on" : ""}" data-cell="${esc(row.region)}|${cell.hour}" data-level="${esc(cell.level)}" style="background:${LEVEL_COLOR[cell.level]}" title="${esc(row.region)} ${cell.hour}h · IPO ${cell.ipo}">${cell.ipo >= 58 ? cell.ipo : ""}</button>`).join("")}
  `).join("");
  return head + rows + `</div>`;
}

function group(title, items) {
  const body = items?.length ? items.map((name) => `<b>${esc(name)}</b>`).join("") : `<span class="muted">nenhuma</span>`;
  return `<p><span>${esc(title)}</span>${body}</p>`;
}

function cellCard() {
  if (!chosen) return "";
  const cell = chosen.cell;
  const lines = [
    `Média longa desta hora, neste dia da semana: ${fmt(cell.mean)} ocorrência por hora.`,
    `As últimas semanas desse recorte estão em ${fmt(cell.recent)}. A média combinada usada na conta é ${fmt(cell.blended)}.`,
    cell.sensors_down
      ? `${cell.sensors_down} sensor(es) indisponível(eis) elevam a estimativa (fator ${fmt(cell.equip_factor, 2)}).`
      : "Os sensores da região não acrescentam pressão extra.",
    cell.gap > 0
      ? `A escala considerada tem ${cell.have} agente(s) e a conta pede ${cell.need}.`
      : `A escala cobre a hora: ${cell.have} agente(s) para uma necessidade de ${cell.need}.`,
  ];
  return `
    <p class="eyebrow">${esc(chosen.region)} · ${esc(chosen.city)}</p>
    <h3>${chosen.hour}h · IPO ${cell.ipo}</h3>
    <p class="pill tone-${cell.level}"><i></i>${esc(cell.level_label)}</p>
    <ul>${lines.map((line) => `<li>${esc(line)}</li>`).join("")}</ul>
    <p class="hint">Isto descreve a pressão estimada. Não é um evento que já aconteceu. Se o ritmo real das últimas 3 horas fugir desta média, ele aparece como anomalia, não como esta célula.</p>`;
}

function recCard(rec) {
  return `
    <article class="rec priority-${rec.priority}">
      <span>${rec.scope === "agora" ? "Agir agora" : "Para o dia projetado"} · ${rec.priority === "alta" ? "prioridade alta" : "prioridade média"}</span>
      <strong>${esc(rec.title)}</strong>
      <p>${esc(rec.detail)}</p>
      <ul>${(rec.why || []).map((line) => `<li>${esc(line)}</li>`).join("")}</ul>
      <p class="action">${esc(rec.action)}</p>
    </article>`;
}

function trendCard(title, note, figure) {
  return `<article class="trend"><h3>${esc(title)}</h3>${figure}<p>${esc(note)}</p></article>`;
}

function chart(points, read, color) {
  if (!points?.length) return "";
  const values = points.map(read);
  const max = Math.max(...values, 1);
  const min = Math.min(...values, 0);
  const span = Math.max(max - min, 1);
  const width = 360;
  const height = 92;
  const pad = 8;
  const step = (width - pad * 2) / Math.max(1, values.length - 1);
  const coords = values.map((value, index) => {
    const x = pad + index * step;
    const y = height - pad - ((value - min) / span) * (height - pad * 2);
    return [x, y];
  });
  const line = coords.map((point, index) => `${index ? "L" : "M"}${point[0].toFixed(1)} ${point[1].toFixed(1)}`).join(" ");
  const area = `${line} L${coords.at(-1)[0].toFixed(1)} ${height - pad} L${coords[0][0].toFixed(1)} ${height - pad} Z`;
  return `<svg viewBox="0 0 ${width} ${height}" class="chart" role="img">
    <path d="${area}" fill="${color}" opacity="0.16"></path>
    <path d="${line}" fill="none" stroke="${color}" stroke-width="2"></path>
  </svg>`;
}
