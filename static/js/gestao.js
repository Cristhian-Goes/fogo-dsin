import { api } from "./api.js";
import { bindChart, chartPanel } from "./chart.js";
import { esc, toast } from "./format.js";

async function downloadIntegrity() {
  const response = await fetch("/api/integridade/pdf", { headers: { "X-Session": sessionStorage.getItem("fogo-session") || "" } });
  if (!response.ok) {
    toast("Não foi possível gerar o PDF da integridade.", "bad");
    return;
  }
  const blob = await response.blob();
  const link = document.createElement("a");
  link.href = URL.createObjectURL(blob);
  link.download = "integridade.pdf";
  document.body.appendChild(link);
  link.click();
  link.remove();
  setTimeout(() => URL.revokeObjectURL(link.href), 1500);
  toast("PDF da integridade baixado.");
}

function money(value) {
  return Number(value || 0).toLocaleString("pt-BR", { style: "currency", currency: "BRL" });
}

function asList(value) {
  return Array.isArray(value) ? value : [];
}

function cards(items) {
  return `<div class="stat-grid">${asList(items).map(([label, value, title]) => `<article title="${esc(title || "")}"><span>${esc(label)}</span><b>${esc(String(value))}</b></article>`).join("")}</div>`;
}

function axisLabel(kind, value) {
  const number = Number(value) || 0;
  if (kind === "gasto" || kind === "valor") {
    const abs = Math.abs(number);
    if (abs >= 1000) {
      const mil = abs / 1000;
      const text = mil >= 10 ? String(Math.round(mil)) : String(Math.round(mil * 10) / 10).replace(".", ",");
      return `${text} mil`;
    }
    return String(Math.round(abs));
  }
  if (Number.isInteger(number)) return String(number);
  return String(number).replace(".", ",");
}

function pick(length, index) {
  if (!length) return 0;
  if (index < 0 || index >= length) return length - 1;
  return index;
}

export async function mount(main, view) {
  main.innerHTML = `<section class="page"><p class="hint">Carregando…</p></section>`;
  try {
    if (view === "integridade") {
      const pack = await api.integrity();
      main.innerHTML = integrity(pack);
      document.getElementById("integrity-pdf")?.addEventListener("click", downloadIntegrity);
      document.getElementById("integrity-refresh")?.addEventListener("click", () => mount(main, view));
      return;
    }
    const pack = await api.gestao();
    if (view === "conhecimento") {
      main.innerHTML = knowledge(pack);
    } else {
      openBoard(main, pack, { financeiro: "gasto", dimensionamento: "equipe", conformidade: "afericao", valor: "valor" }[view] || "gasto");
    }
    const search = document.getElementById("knowledge-q");
    search?.addEventListener("input", () => {
      const text = search.value.toLowerCase();
      document.querySelectorAll("[data-model]").forEach((node) => {
        node.hidden = text && !node.dataset.model.toLowerCase().includes(text) && !node.textContent.toLowerCase().includes(text);
      });
    });
  } catch (error) {
    main.innerHTML = `<section class="page"><h1>Não foi possível abrir</h1><p>${esc(error.message)}</p></section>`;
  }
}

const SERIES = [
  ["gasto", "Gasto"],
  ["equipe", "Equipes"],
  ["afericao", "Aferição"],
  ["valor", "Valor entregue"],
];

function openBoard(main, pack, seriesId) {
  const chosen = { id: seriesId, index: -1 };
  const draw = (focus) => {
    const model = boardModel(pack, chosen.id);
    chosen.index = pick(model.points.length, chosen.index);
    const point = model.points[chosen.index];
    main.innerHTML = `<section class="page dash">
      <header class="page-head">
        <h1>${esc(model.title)}</h1>
        <p>${esc(model.lede)}</p>
      </header>
      <div class="dash-switch" role="tablist" aria-label="Séries do painel">
        ${SERIES.map(([id, label]) => `<button type="button" class="ghost" role="tab" data-series="${id}" aria-selected="${id === chosen.id ? "true" : "false"}">${label}</button>`).join("")}
      </div>
      ${cards(model.stats)}
      ${chartPanel(model.points, chosen.index, (value) => axisLabel(chosen.id, value), model.title)}
      <h2>${esc(model.detailTitle)}</h2>
      ${model.detail(point)}
      <p class="hint">${esc(model.footnote)}</p>
    </section>`;
    main.querySelectorAll("[data-series]").forEach((button) => {
      button.addEventListener("click", () => {
        chosen.id = button.dataset.series;
        chosen.index = -1;
        draw(false);
      });
    });
    bindChart(main.querySelector(".chart-panel"), (index) => {
      chosen.index = index;
      draw(true);
    });
    main.querySelectorAll("[data-row]").forEach((row) => {
      row.addEventListener("click", () => {
        chosen.index = Number(row.dataset.row);
        draw(true);
      });
    });
    if (focus) main.querySelector(".chart-point.is-on circle")?.focus();
  };
  draw(false);
}

function boardModel(pack, id) {
  const finance = pack.finance || {};
  const staff = pack.staffing || {};
  const compliance = pack.compliance || {};
  const delivered = pack.value || {};
  if (id === "equipe") return teamModel(staff);
  if (id === "afericao") return calibrationModel(compliance);
  if (id === "valor") return valueModel(delivered, pack);
  return spendModel(finance, pack);
}

function spendModel(item, pack) {
  const series = asList(item.series);
  const synthetic = series.some((row) => row.synthetic);
  return {
    title: "Gasto mensal",
    lede: item.method || "Tendência do gasto de manutenção.",
    stats: [
      ["Manutenção no mês", money(item.month_total), item.formula || ""],
      ["Custo médio por OS", money(item.average_order), "Soma dos custos das OS encerradas no mês, dividida pela quantidade."],
      ["Perda por indisponibilidade", money(item.downtime_loss), item.formula || ""],
      ["Projeção do ano", money(item.projection_year), "Tendência linear dos meses exibidos, somada por 12 meses."],
      ["Orçamento anual", money(item.budget_year), "Orçamento mensal informado vezes 12."],
    ],
    points: series.map((row) => {
      const month = String(row.month || "");
      return {
        label: month.slice(5) || month || "mês",
        value: Number(row.total) || 0,
        display: money(row.total),
        detail: row.synthetic ? "Mês de demonstração, para completar a série." : "OS encerradas neste mês.",
      };
    }),
    detailTitle: "Onde o custo está",
    detail: () => `<h3>Equipamentos mais caros</h3>
      <ul class="rows">${asList(item.top_equipment).map((row) => `<li><b>${esc(row.serial)}</b> ${money(row.total)}</li>`).join("") || "<li>Nenhuma OS com custo.</li>"}</ul>
      <h3>Custo por fornecedor</h3>
      <ul class="rows">${asList(item.suppliers).map((row) => `<li><b>${esc(row.supplier)}</b> ${money(row.total)}</li>`).join("") || "<li>Sem fornecedor com custo.</li>"}</ul>
      <h3>Fila do supervisor</h3>
      <ul class="rows">${asList(pack.suspects).map((row) => `<li><b>${esc(row.number)}</b> ${esc(asList(row.motivos).join("; "))}</li>`).join("") || "<li>Nenhuma conclusão suspeita.</li>"}</ul>`,
    footnote: `${synthetic ? "Meses de demonstração completam a série quando ainda há poucas OS encerradas." : "Série tirada das OS encerradas."} Diferença para o orçamento anual: ${money(item.budget_gap)}.`,
  };
}

function teamModel(item) {
  const rows = asList(item.rows);
  return {
    title: "Equipes e espera",
    lede: item.sentence || item.method || "Simulação da espera conforme o número de equipes.",
    stats: [
      ["Chegadas por hora", String(item.rate_per_hour ?? 0).replace(".", ","), "Volume usado na simulação do turno."],
      ["Atendimento médio", `${String(item.service_min ?? 0).replace(".", ",")} min`, "Duração média das OS."],
      ["Espera aceita", `${String(item.wait_limit_min ?? 0).replace(".", ",")} min`, "Limite do SLA de espera."],
    ],
    points: rows.map((row) => ({
      label: String(row.teams),
      value: Number(row.sla_pct) || 0,
      display: `${String(row.sla_pct).replace(".", ",")}%`,
      detail: `${row.teams} equipes · espera ${String(row.wait_min).replace(".", ",")} min · utilização ${String(row.utilization_pct).replace(".", ",")}%`,
      row,
    })),
    detailTitle: "Cada quantidade de equipes",
    detail: (point) => `<div class="table-wrap"><table class="sheet">
      <thead><tr><th>Equipes</th><th>SLA</th><th>Espera</th><th>Utilização</th></tr></thead>
      <tbody>${rows.map((row, index) => `<tr class="${point && point.row === row ? "is-selected" : ""}" data-row="${index}">
        <td>${row.teams}</td><td>${String(row.sla_pct).replace(".", ",")}%</td><td>${String(row.wait_min).replace(".", ",")} min</td><td>${String(row.utilization_pct).replace(".", ",")}%</td>
      </tr>`).join("") || `<tr><td colspan="4">Sem simulação.</td></tr>`}</tbody>
    </table></div>`,
    footnote: item.method || "O gráfico mostra o SLA de espera para cada quantidade de equipes.",
  };
}

function calibrationModel(item) {
  const labels = { vencida: "Vencida", "7": "7 dias", "15": "15 dias", "30": "30 dias" };
  const rows = asList(item.rows);
  const points = Object.keys(labels).map((bucket) => {
    const found = rows.filter((row) => row.bucket === bucket);
    return {
      label: labels[bucket],
      value: found.length,
      display: labels[bucket],
      detail: found.length === 1 ? "1 equipamento nesta janela." : `${found.length} equipamentos nesta janela.`,
      bucket,
    };
  });
  return {
    title: "Aferição",
    lede: item.note || "Prazos de validade do cadastro.",
    stats: [
      ["Fora de conformidade", item.expired ?? 0, item.method || ""],
      ["Autuações simuladas", item.citations ?? 0, "Quantidade vencida vezes a taxa parametrizável. Não é um auto real."],
    ],
    points,
    detailTitle: "Equipamentos na janela",
    detail: (point) => {
      const shown = point ? rows.filter((row) => row.bucket === point.bucket) : rows;
      return `<ul class="rows">${shown.map((row) => `<li><b>${esc(row.serial)}</b> ${esc(labels[row.bucket] || row.bucket)} · ${esc(row.orgao || "órgão não informado")} · validade ${esc(row.validade_afericao || "")}${row.fora_de_conformidade ? " · fora de conformidade" : ""}</li>`).join("") || "<li>Nenhum radar ou balança na janela.</li>"}</ul>`;
    },
    footnote: item.method || "A lista usa a data de validade do cadastro.",
  };
}

function valueModel(item, pack) {
  const presence = pack.presence || {};
  const violations = Number(item.violations) || 0;
  return {
    title: "Valor entregue",
    lede: item.staff_recommendation || "Sem recomendação de equipe neste momento.",
    stats: [
      ["Rotas evitadas", money(item.trip_savings), "Minutos poupados na rota do dia vezes R$ 1,80."],
      ["Multas identificadas", money(item.fines_identified), "Violações de SLA vezes a multa do primeiro contrato."],
      ["Fora de conformidade", item.expired_equipment ?? 0, "Equipamentos com validade de aferição vencida."],
      ["Presença válida", `${item.presence_pct ?? 0}%`, presence.method || "OS encerradas com conclusão válida."],
    ],
    points: [
      { label: "Rotas", value: Number(item.trip_savings) || 0, display: money(item.trip_savings), detail: `${item.saved_min || 0} min poupados na rota do dia, a R$ 1,80.` },
      { label: "Multas", value: Number(item.fines_identified) || 0, display: money(item.fines_identified), detail: `${violations} ${violations === 1 ? "violação" : "violações"} de SLA, na multa do primeiro contrato.` },
    ],
    detailTitle: "Como a conta foi feita",
    detail: () => `<ul class="rows">
      <li><b>Rotas</b> ${esc(String(item.saved_min || 0))} min poupados na rota do dia.</li>
      <li><b>Contratos</b> ${esc(String(violations))} ${violations === 1 ? "violação" : "violações"} de SLA.</li>
      <li><b>Aferição</b> autuações simuladas: ${esc(String(item.citations_simulated || 0))}.</li>
      <li><b>Orçamento</b> diferença da projeção para o ano: ${money(item.budget_gap)}.</li>
    </ul>`,
    footnote: `${item.premises || ""} ${item.method || ""}`.trim(),
  };
}

function knowledge(pack) {
  const rows = asList(pack.knowledge);
  const tips = rows.reduce((sum, row) => sum + (row.count || asList(row.entries).length || 0), 0);
  const body = rows.map((row) => {
    const entries = asList(row.entries).length ? asList(row.entries) : asList(row.tips).map((tip) => ({ tip }));
    return `<section class="knowledge-group" data-model="${esc(row.model)}">
      <h2>${esc(row.model)} <span>${esc(row.type || "modelo")} · ${row.count || entries.length} dicas</span></h2>
      <div class="table-wrap"><table class="sheet">
        <thead><tr><th>OS</th><th>Equipamento</th><th>Região</th><th>Dica do técnico</th></tr></thead>
        <tbody>${entries.map((entry) => `<tr>
          <td>${esc(entry.order || "")}</td>
          <td>${esc(entry.serial || "")}</td>
          <td>${esc(entry.region || "")}</td>
          <td>${esc(entry.tip || "")}</td>
        </tr>`).join("")}</tbody>
      </table></div>
    </section>`;
  }).join("");
  return `<section class="page">
    <div class="knowledge-head">
      <h1>Conhecimento de campo</h1>
      <p class="hint">${rows.length} modelos · ${tips} dicas</p>
    </div>
    <p class="hint">Cada linha é a dica escrita no fechamento da OS. A busca olha modelo, equipamento, região e o texto.</p>
    <label class="field">Buscar<input id="knowledge-q" type="search" placeholder="modelo, região ou dica" /></label>
    <h2>Registrado no fechamento</h2>
    ${body || "<p>Nenhuma dica registrada no fechamento das OS.</p>"}
    <h2>Útil para as OS abertas</h2>
    ${asList(pack.knowledge_open).map((row) => `<article class="knowledge-group" data-model="${esc(row.model)} ${esc(row.order)}">
      <h2>${esc(row.order)} <span>${esc(row.model)} · ${esc(row.region)} · ${esc(row.status)}</span></h2>
      <ul class="rows">${asList(row.tips).map((tip) => `<li>${esc(tip)}</li>`).join("")}</ul>
    </article>`).join("") || "<p class='hint'>Nenhuma OS aberta aproveita uma dica já registrada.</p>"}
  </section>`;
}

function integrity(pack) {
  const verdict = pack.verdict || {};
  const rows = asList(pack.tail);
  const last = rows[rows.length - 1] || {};
  return `<section class="page">
    <h1>Auditoria</h1>
    <p><b>${verdict.ok ? "A cadeia confere." : esc(verdict.reason || "A cadeia falhou.")}</b> ${verdict.ok ? `${verdict.count || rows.length} registros encadeados.` : ""}</p>
    ${cards([
      ["Registros na cadeia", verdict.count ?? rows.length, "Cada registro guarda o hash do anterior."],
      ["Último registro", last.id || "nenhum", last.action || ""],
    ])}
    <p class="form-actions">
      <button type="button" class="primary" id="integrity-pdf">Baixar PDF</button>
      <button type="button" class="ghost" id="integrity-refresh">Verificar de novo</button>
    </p>
    <div class="table-wrap"><table class="sheet">
      <thead><tr><th>Registro</th><th>Quando</th><th>Quem</th><th>Ação</th><th>Hash</th></tr></thead>
      <tbody>${rows.map((row) => `<tr>
        <td>${esc(row.id || "")}</td>
        <td>${esc(String(row.at || "").slice(0, 16).replace("T", " "))}</td>
        <td>${esc(row.actor || "")}</td>
        <td>${esc(row.action || "")}</td>
        <td>${esc(String(row.hash_atual || "").slice(0, 12))}</td>
      </tr>`).join("") || "<tr><td colspan=\"5\">Nenhum registro na cadeia.</td></tr>"}</tbody>
    </table></div>
  </section>`;
}
