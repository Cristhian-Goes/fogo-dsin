import { api } from "./api.js";
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
      document.getElementById("integrity-refresh")?.addEventListener("click", () => mount(main, view));
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
  const tips = rows.reduce((sum, row) => sum + (row.count || row.entries?.length || 0), 0);
  const body = rows.map((row) => {
    const entries = row.entries || (row.tips || []).map((tip) => ({ tip }));
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
    ${(pack.knowledge_open || []).map((row) => `<article class="knowledge-group" data-model="${esc(row.model)} ${esc(row.order)}">
      <h2>${esc(row.order)} <span>${esc(row.model)} · ${esc(row.region)} · ${esc(row.status)}</span></h2>
      <ul class="rows">${(row.tips || []).map((tip) => `<li>${esc(tip)}</li>`).join("")}</ul>
    </article>`).join("") || "<p class='hint'>Nenhuma OS aberta aproveita uma dica já registrada.</p>"}
  </section>`;
}

function value(pack) {
  const item = pack.value || {};
  return `<section class="page">
    <h1>Valor entregue</h1>
    <p><b>${esc(item.staff_recommendation || "Sem recomendação de equipe neste momento.")}</b></p>
    ${cards([
      ["Rotas evitadas", money(item.trip_savings), "Minutos poupados na rota do dia vezes R$ 1,80."],
      ["Multas identificadas", money(item.fines_identified), "Violações de SLA vezes a multa do primeiro contrato."],
      ["Fora de conformidade", item.expired_equipment ?? 0, "Equipamentos com validade de aferição vencida."],
      ["Presença válida", `${item.presence_pct ?? 0}%`, pack.presence?.method || "OS encerradas com conclusão válida."],
    ])}
    <h2>Como a conta foi feita</h2>
    <ul class="rows">
      <li><b>Rotas</b> ${esc(String(item.saved_min || 0))} min poupados na rota do dia.</li>
      <li><b>Contratos</b> ${esc(String(item.violations || 0))} ${Number(item.violations) === 1 ? "violação" : "violações"} de SLA.</li>
      <li><b>Aferição</b> autuações simuladas: ${esc(String(item.citations_simulated || 0))}.</li>
      <li><b>Orçamento</b> diferença da projeção para o ano: ${money(item.budget_gap)}.</li>
    </ul>
    <p class="hint">${esc(item.premises || "")} ${esc(item.method || "")}</p>
  </section>`;
}

function integrity(pack) {
  const verdict = pack.verdict || {};
  const rows = pack.tail || [];
  const last = rows[rows.length - 1] || {};
  return `<section class="page">
    <h1>Integridade</h1>
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
