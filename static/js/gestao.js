import { api } from "./api.js";
import { esc } from "./format.js";

async function downloadIntegrity() {
  const response = await fetch("/api/integridade/pdf", { headers: { "X-Session": sessionStorage.getItem("fogo-session") || "" } });
  if (!response.ok) return;
  const blob = await response.blob();
  const link = document.createElement("a");
  link.href = URL.createObjectURL(blob);
  link.download = "integridade.pdf";
  document.body.appendChild(link);
  link.click();
  link.remove();
  setTimeout(() => URL.revokeObjectURL(link.href), 1500);
}

function money(value) {
  return Number(value || 0).toLocaleString("pt-BR", { style: "currency", currency: "BRL" });
}

function cards(items) {
  return `<div class="stat-grid">${items.map(([label, value, title]) => `<article title="${esc(title || "")}"><span>${esc(label)}</span><b>${esc(String(value))}</b></article>`).join("")}</div>`;
}

function chart(series) {
  const values = series.map((item) => Number(item.total) || 0);
  const max = Math.max(...values, 1);
  const step = values.length > 1 ? 280 / (values.length - 1) : 280;
  const points = values.map((value, index) => `${20 + index * step},${140 - (value / max) * 110}`).join(" ");
  return `<svg class="chart" viewBox="0 0 320 160" role="img" aria-label="Gasto mensal">
    <polyline fill="none" stroke="#1b6b45" stroke-width="2" points="${points}" />
    ${series.map((item, index) => `<text x="${20 + index * step}" y="156" font-size="10" fill="#5c6b7a">${esc(item.month.slice(5))}</text>`).join("")}
  </svg>`;
}

export async function mount(main, view) {
  main.innerHTML = `<section class="page"><p class="hint">Carregando…</p></section>`;
  try {
    if (view === "integridade") {
      const pack = await api.integrity();
      main.innerHTML = integrity(pack);
      document.getElementById("integrity-pdf")?.addEventListener("click", downloadIntegrity);
      return;
    }
    const pack = await api.gestao();
    const painter = { financeiro: finance, conformidade: compliance, dimensionamento: staffing, conhecimento: knowledge, valor: value }[view] || finance;
    main.innerHTML = painter(pack);
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

function finance(pack) {
  const item = pack.finance;
  return `<section class="page">
    <h1>Financeiro</h1>
    <p class="hint" title="${esc(item.formula)}">${esc(item.method)}</p>
    ${cards([
      ["Manutenção no mês", money(item.month_total), item.formula],
      ["Custo médio por OS", money(item.average_order), "Soma dos custos das OS encerradas no mês, dividida pela quantidade."],
      ["Perda por indisponibilidade", money(item.downtime_loss), item.formula],
      ["Projeção do ano", money(item.projection_year), "Tendência linear dos meses exibidos, somada por 12 meses."],
      ["Orçamento anual", money(item.budget_year), "Orçamento mensal informado vezes 12."],
    ])}
    <h2>Gasto mensal</h2>
    ${item.series?.length ? chart(item.series) : "<p class='hint'>Sem série de gasto.</p>"}
    <p class="hint">${item.series?.some((row) => row.synthetic) ? "Meses marcados como demonstração completam a série quando ainda há poucas OS encerradas." : "Série tirada das OS encerradas."} Diferença para o orçamento anual: ${money(item.budget_gap)}.</p>
    <h2>Equipamentos mais caros</h2>
    <ul class="rows">${(item.top_equipment || []).map((row) => `<li><b>${esc(row.serial)}</b> ${money(row.total)}</li>`).join("") || "<li>Nenhuma OS com custo.</li>"}</ul>
    <h2>Custo por fornecedor</h2>
    <ul class="rows">${(item.suppliers || []).map((row) => `<li><b>${esc(row.supplier)}</b> ${money(row.total)}</li>`).join("") || "<li>Sem fornecedor com custo.</li>"}</ul>
    <h2>Fila do supervisor</h2>
    <ul class="rows">${(pack.suspects || []).map((row) => `<li><b>${esc(row.number)}</b> ${esc((row.motivos || []).join("; "))}</li>`).join("") || "<li>Nenhuma conclusão suspeita.</li>"}</ul>
  </section>`;
}

function compliance(pack) {
  const item = pack.compliance;
  const label = { vencida: "vencida", "7": "em 7 dias", "15": "em 15 dias", "30": "em 30 dias" };
  return `<section class="page">
    <h1>Conformidade de aferição</h1>
    <p>${esc(item.note)}</p>
    ${cards([
      ["Fora de conformidade", item.expired, item.method],
      ["Autuações simuladas", item.citations, "Quantidade vencida vezes a taxa parametrizável. Não é um auto real."],
    ])}
    <ul class="rows">${(item.rows || []).map((row) => `<li><b>${esc(row.serial)}</b> ${esc(label[row.bucket] || row.bucket)} · ${esc(row.orgao || "órgão não informado")} · validade ${esc(row.validade_afericao || "")}${row.fora_de_conformidade ? " · fora de conformidade" : ""}</li>`).join("") || "<li>Nenhum radar ou balança na janela.</li>"}</ul>
  </section>`;
}

function staffing(pack) {
  const item = pack.staffing;
  return `<section class="page">
    <h1>Dimensionamento de equipe</h1>
    <p class="hint">${esc(item.method)}</p>
    <p><b>${esc(item.sentence)}</b></p>
    <p class="hint">Chegadas ${esc(String(item.rate_per_hour))} por hora. Atendimento médio ${esc(String(item.service_min))} min. Espera aceita ${esc(String(item.wait_limit_min))} min.</p>
    ${chart((item.rows || []).map((row) => ({ month: String(row.teams), total: row.sla_pct })))}
    <ul class="rows">${(item.rows || []).map((row) => `<li><b>${row.teams} equipes</b> SLA ${row.sla_pct}% · espera ${row.wait_min} min · utilização ${row.utilization_pct}%</li>`).join("")}</ul>
  </section>`;
}

function knowledge(pack) {
  const rows = pack.knowledge || [];
  return `<section class="page">
    <h1>Base de conhecimento</h1>
    <p class="hint">A busca compara o modelo e as palavras da dica. Não é um modelo treinado.</p>
    <label class="field">Buscar modelo ou dica<input id="knowledge-q" type="search" placeholder="radar, fonte, lente" /></label>
    ${rows.map((row) => `<article data-model="${esc(row.model)}"><h2>${esc(row.model)}</h2><ul>${row.tips.map((tip) => `<li>${esc(tip)}</li>`).join("")}</ul></article>`).join("") || "<p>Nenhuma dica registrada no fechamento das OS.</p>"}
  </section>`;
}

function value(pack) {
  const item = pack.value;
  return `<section class="page">
    <h1>Valor entregue</h1>
    <p class="hint">${esc(item.premises)}</p>
    ${cards([
      ["Rotas evitadas", money(item.trip_savings), item.method],
      ["Multas contratuais identificadas", money(item.fines_identified), "Violações de SLA vezes a multa do contrato."],
      ["Equipamentos fora de conformidade", item.expired_equipment, "Cadastro de validade de aferição."],
      ["Prova de presença válida", `${item.presence_pct}%`, pack.presence?.method || ""],
    ])}
    <p>${esc(item.staff_recommendation || "")}</p>
    <p class="hint">Minutos poupados na rota do dia: ${esc(String(item.saved_min || 0))}. Diferença da projeção para o orçamento: ${money(item.budget_gap)}.</p>
  </section>`;
}

function integrity(pack) {
  const verdict = pack.verdict || {};
  return `<section class="page">
    <h1>Integridade</h1>
    <p>${verdict.ok ? "A cadeia confere." : esc(verdict.reason || "A cadeia falhou.")}</p>
    <p><button type="button" class="primary" id="integrity-pdf">Baixar PDF</button></p>
    <ul class="rows">${(pack.tail || []).map((row) => `<li><b>${esc(row.id)}</b> ${esc(row.action)} · ${esc(row.entity)}<br><small>${esc(row.hash_atual || "")}</small></li>`).join("") || "<li>Nenhum registro.</li>"}</ul>
  </section>`;
}
