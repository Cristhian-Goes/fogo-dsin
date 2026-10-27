import { api } from "./api.js";
import { clockLabel, esc, status, toast } from "./format.js";
import { state } from "./state.js";
import { mountTable } from "./table.js";

const COLUMNS = [
  ["aberta", "Aberta"],
  ["atribuida", "Atribuída"],
  ["em_execucao", "Em execução"],
  ["concluida", "Concluída"],
  ["cancelada", "Cancelada"],
];

const filters = { q: "", status: "", priority: "", team: "", region: "", period: "" };
const closedGroups = new Set();
let viewMode = localStorage.getItem("fogo-os-view") || "board";
let groupBy = localStorage.getItem("fogo-os-group") || "";
let selectedId = "";
let drawer = false;
let osMap = null;

export function mount(main) {
  osMap?.remove();
  osMap = null;
  const all = state.bootstrap.orders || [];
  const rows = all.filter(match);
  if (!selectedId || !all.some((item) => item.id === selectedId)) selectedId = rows[0]?.id || all[0]?.id || "";
  const selected = all.find((item) => item.id === selectedId);
  const write = !!state.user?.can_write;
  main.innerHTML = `
    <section class="page">
      <header class="page-head">
        <h1>Ordens de serviço</h1>
        <div class="actions">
          <div class="view-switch" role="tablist">
            ${["board", "Quadro", "list", "Lista", "map", "Mapa"].reduce((html, item, index, source) => index % 2 ? html : `${html}<button type="button" data-view-mode="${item}" aria-selected="${viewMode === item}" role="tab">${source[index + 1]}</button>`, "")}
          </div>
          ${write ? `<button type="button" class="primary" id="os-open">Criar OS</button>` : ""}
        </div>
      </header>
      ${filterBar(all)}
      <div class="os-shell">
        <div class="os-main">${rows.length ? body(rows) : emptyState(all)}</div>
        ${selected ? detail(selected) : `<aside class="os-detail"><div class="os-body"><p class="hint">Nenhuma OS selecionada.</p></div></aside>`}
      </div>
    </section>
    ${drawer && write ? drawerHtml() : ""}`;
  bind(main);
  if (viewMode === "list") {
    mountTable(document.getElementById("os-table"), tableSpec(rows));
  }
  if (viewMode === "map") drawMap(rows);
}

export function destroy() {
  osMap?.remove();
  osMap = null;
}

function match(item) {
  if (filters.status && item.status !== filters.status) return false;
  if (filters.priority && item.priority !== filters.priority) return false;
  if (filters.team && (item.agent_name || "") !== filters.team) return false;
  if (filters.region && (item.region || "") !== filters.region) return false;
  if (filters.period === "atrasadas" && !item.overdue) return false;
  if (filters.period === "hoje" && !String(item.opened_at || "").startsWith(today())) return false;
  if (filters.period === "7d" && item.opened_at && Date.now() - new Date(item.opened_at).getTime() > 7 * 86400000) return false;
  const blob = `${item.number} ${item.description || ""} ${item.serial || ""} ${item.street || ""}`.toLowerCase();
  return !filters.q || blob.includes(filters.q.trim().toLowerCase());
}

function today() {
  const date = new Date();
  return `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, "0")}-${String(date.getDate()).padStart(2, "0")}`;
}

function filterBar(all) {
  const regions = unique(all.map((item) => item.region));
  const teams = unique(all.map((item) => item.agent_name));
  const chips = [
    filters.status && ["status", labelOf(COLUMNS, filters.status)],
    filters.priority && ["priority", labelOf([["critica", "Crítica"], ["alta", "Alta"], ["media", "Média"], ["baixa", "Baixa"]], filters.priority)],
    filters.team && ["team", filters.team],
    filters.region && ["region", filters.region],
    filters.period && ["period", { hoje: "Hoje", "7d": "7 dias", atrasadas: "Atrasadas" }[filters.period]],
    filters.q && ["q", filters.q],
  ].filter(Boolean);
  return `
    <div class="filter-bar">
      <input id="os-q" type="search" placeholder="Buscar" value="${esc(filters.q)}" aria-label="Buscar OS" />
      ${select("os-status", "Status", [["", "Status"], ...COLUMNS], filters.status)}
      ${select("os-priority", "Prioridade", [["", "Prioridade"], ["critica", "Crítica"], ["alta", "Alta"], ["media", "Média"], ["baixa", "Baixa"]], filters.priority)}
      ${select("os-team", "Equipe", [["", "Equipe"], ...teams.map((item) => [item, item])], filters.team)}
      ${select("os-region", "Região", [["", "Região"], ...regions.map((item) => [item, item])], filters.region)}
      ${select("os-period", "Período", [["", "Período"], ["hoje", "Hoje"], ["7d", "7 dias"], ["atrasadas", "Atrasadas"]], filters.period)}
      ${viewMode === "list" ? select("os-group", "Agrupar", [["", "Sem grupo"], ["priority", "Prioridade"], ["region", "Região"]], groupBy) : ""}
      ${chips.map(([key, label]) => `<button type="button" class="chip" data-clear="${key}">${esc(label)} ×</button>`).join("")}
      ${chips.length ? `<button type="button" class="ghost" id="os-clear">Limpar</button>` : ""}
    </div>`;
}

function select(id, label, options, value) {
  return `<select id="${id}" aria-label="${label}">${options.map(([idValue, text]) => `<option value="${esc(idValue)}" ${idValue === value ? "selected" : ""}>${esc(text)}</option>`).join("")}</select>`;
}

function body(rows) {
  if (viewMode === "list") return listHtml(rows);
  if (viewMode === "map") return `<div id="os-map" class="os-map"></div>`;
  return `<div class="kanban">${COLUMNS.map(([id, label]) => `
    <section data-column="${id}">
      <h2>${label} <span class="hint">${rows.filter((item) => item.status === id).length}</span></h2>
      ${rows.filter((item) => item.status === id).map(card).join("") || "<p class='hint'>Nenhuma.</p>"}
    </section>`).join("")}</div>`;
}

function listHtml(rows) {
  if (!groupBy) return `<div id="os-table"></div>`;
  const groups = new Map();
  rows.forEach((item) => {
    const key = item[groupBy] || "sem";
    if (!groups.has(key)) groups.set(key, []);
    groups.get(key).push(item);
  });
  return [...groups.entries()].map(([key, items]) => `
    <section>
      <button type="button" class="ghost" data-group="${esc(key)}">${closedGroups.has(key) ? "▸" : "▾"} ${groupBy === "priority" ? status(key) : esc(key)} <span class="hint">${items.length}</span></button>
      ${closedGroups.has(key) ? "" : `<div id="os-table-${esc(key)}" class="os-group" data-group-host="${esc(key)}"></div>`}
    </section>`).join("");
}

function tableSpec(rows, id = "orders") {
  return {
    id,
    sort: "number",
    rows,
    selectable: !!state.user?.can_write,
    rowId: (item) => item.id,
    selected: (item) => item.id === selectedId,
    critical: (item) => item.priority === "critica",
    empty: "Nenhuma OS com esses filtros.",
    columns: [
      { key: "number", label: "Número", primary: true, value: (item) => item.number },
      { key: "title", label: "Título", value: (item) => short(item.description || item.serial) },
      { key: "priority", label: "Prioridade", status: true, filter: true, value: (item) => item.priority },
      { key: "status", label: "Status", filter: true, value: (item) => labelOf(COLUMNS, item.status) },
      { key: "sla", label: "Prazo", value: (item) => slaText(item), html: (item) => slaHtml(item) },
      { key: "agent", label: "Responsável", value: (item) => item.agent_name || "" },
      { key: "region", label: "Região", filter: true, value: (item) => item.region || "" },
      { key: "menu", label: "", menu: true },
    ],
    menu: (item) => [
      `<button type="button" class="ghost" data-action="os-pdf" data-id="${esc(item.id)}">PDF</button>`,
      item.equipment_id ? `<button type="button" class="ghost" data-action="select" data-kind="equipment" data-id="${esc(item.equipment_id)}">Ficha</button>` : "",
    ].filter(Boolean),
    onRow: (item) => {
      selectedId = item.id;
      mount(document.getElementById("main"));
    },
    onBatch: batch,
  };
}

function card(item) {
  return `
    <article class="os-card lean${item.priority === "critica" ? " is-critical" : ""}${item.id === selectedId ? " is-on" : ""}" draggable="${state.user?.can_write ? "true" : "false"}" data-order="${esc(item.id)}" data-status="${esc(item.status)}">
      <b>${esc(item.number)}</b>
      <p>${esc(short(item.description || item.serial))}</p>
      <p>${status(item.priority)} · ${slaHtml(item)}</p>
      <p>${avatar(item.agent_name)}</p>
    </article>`;
}

function detail(item) {
  const write = !!state.user?.can_write;
  const next = nextAction(item);
  return `
    <aside class="os-detail os-card${item.priority === "critica" ? " is-critical" : ""}">
      <div class="os-body">
        <h2>${esc(short(item.description || item.number, 80))}</h2>
        <dl class="os-facts">
          <dt>Número</dt><dd>${esc(item.number)}</dd>
          <dt>Prioridade</dt><dd>${status(item.priority)}</dd>
          <dt>Status</dt><dd>${esc(labelOf(COLUMNS, item.status))}</dd>
          <dt>Local</dt><dd>${esc(item.street || item.serial || "—")}</dd>
          <dt>Equipe</dt><dd>${avatar(item.agent_name)} ${esc(item.agent_name || "Sem responsável")}</dd>
          <dt>Horário</dt><dd>${esc(clockLabel(item.due_at))}<br>${slaHtml(item)}</dd>
        </dl>
        ${write && item.status === "em_execucao" ? `<details open>
          <summary>Concluir</summary>
          <label class="field">Check-in lat<input name="checkin_lat" value="${esc(item.lat ?? "")}" /></label>
          <label class="field">lng<input name="checkin_lng" value="${esc(item.lng ?? "")}" /></label>
          <label class="field">Foto antes<input name="foto_antes" placeholder="arquivo" /></label>
          <label class="field">Foto depois<input name="foto_depois" placeholder="arquivo" /></label>
          <label class="field">Dica<input name="dica" maxlength="180" /></label>
        </details>` : ""}
        <details>
          <summary>Mais</summary>
          <p>${esc(item.description || "")}</p>
          <p class="hint">${esc(item.kind || "")} · ${esc(item.serial || "")} · ${esc(item.region || "")}</p>
          ${(item.events || []).slice(0, 6).map((event) => `<p class="hint">${esc(clockLabel(event.at))} ${esc(event.text || "")}</p>`).join("")}
        </details>
      </div>
      <footer>
        ${write && next ? `<button type="button" class="primary" data-action="${next.action}" data-id="${esc(item.id)}" data-status="${esc(next.status || "")}">${next.label}</button>` : ""}
        ${item.equipment_id ? `<button type="button" class="ghost" data-action="select" data-kind="equipment" data-id="${esc(item.equipment_id)}">Abrir ficha</button>` : ""}
        <button type="button" class="ghost" data-action="os-pdf" data-id="${esc(item.id)}">PDF</button>
        ${write && item.status !== "concluida" && item.status !== "cancelada" ? `<button type="button" class="ghost" data-action="os-status" data-id="${esc(item.id)}" data-status="cancelada">Cancelar</button>` : ""}
      </footer>
    </aside>`;
}

function nextAction(item) {
  if (item.status === "aberta") return { action: "os-assign", label: "Atribuir" };
  if (item.status === "atribuida") return { action: "os-status", status: "em_execucao", label: "Iniciar" };
  if (item.status === "em_execucao") return { action: "os-close", label: "Concluir" };
  return null;
}

function emptyState(all) {
  const open = all.some((item) => ["aberta", "atribuida", "em_execucao"].includes(item.status));
  if (!open) return `<p>Nenhuma OS aberta. ${state.user?.can_write ? `<button type="button" class="ghost" id="os-open-empty">Criar OS</button>` : ""}</p>`;
  return `<p>Nenhuma OS com esses filtros. <button type="button" class="ghost" id="os-clear">Limpar</button></p>`;
}

function drawerHtml() {
  return `
    <div class="drawer-back" id="os-drawer-back"></div>
    <aside class="drawer" aria-label="Criar OS">
      <header class="page-head"><h2>Criar OS</h2><button type="button" class="ghost" id="os-drawer-close">Fechar</button></header>
      <form id="os-new">
        <label class="field">Tipo
          <select name="kind">
            <option value="corretiva">Corretiva</option>
            <option value="preventiva">Preventiva</option>
            <option value="instalacao">Instalação</option>
            <option value="recolhimento">Recolhimento</option>
            <option value="afericao">Aferição</option>
          </select>
        </label>
        <label class="field">Equipamento
          <select name="equipment_id" required>
            <option value="">Escolher</option>
            ${(state.bootstrap.equipment || []).map((item) => `<option value="${esc(item.id)}">${esc(item.serial)} · ${esc(item.street || item.region || "")}</option>`).join("")}
          </select>
        </label>
        <label class="field">Prioridade
          <select name="priority">
            <option value="critica">Crítica · 4 h</option>
            <option value="alta" selected>Alta · 24 h</option>
            <option value="media">Média · 72 h</option>
            <option value="baixa">Baixa · 7 dias</option>
          </select>
        </label>
        <label class="field">Descrição
          <input name="description" required maxlength="400" />
        </label>
        <details>
          <summary>Mais opções</summary>
          <p class="hint">O prazo segue a prioridade. Preventiva consulta a janela da agenda.</p>
        </details>
        <div class="form-actions"><button type="submit" class="primary">Abrir OS</button></div>
      </form>
    </aside>`;
}

function bind(main) {
  main.querySelectorAll("[data-view-mode]").forEach((button) => {
    button.addEventListener("click", () => {
      viewMode = button.dataset.viewMode;
      localStorage.setItem("fogo-os-view", viewMode);
      mount(main);
    });
  });
  const apply = (id, key) => {
    document.getElementById(id)?.addEventListener("change", (event) => {
      filters[key] = event.target.value;
      mount(main);
    });
  };
  document.getElementById("os-q")?.addEventListener("input", (event) => {
    filters.q = event.target.value;
    mount(main);
    const field = document.getElementById("os-q");
    field?.focus();
    if (field) field.setSelectionRange(field.value.length, field.value.length);
  });
  apply("os-status", "status");
  apply("os-priority", "priority");
  apply("os-team", "team");
  apply("os-region", "region");
  apply("os-period", "period");
  document.getElementById("os-group")?.addEventListener("change", (event) => {
    groupBy = event.target.value;
    localStorage.setItem("fogo-os-group", groupBy);
    mount(main);
  });
  main.querySelectorAll("[data-clear]").forEach((button) => {
    button.addEventListener("click", () => {
      filters[button.dataset.clear] = "";
      mount(main);
    });
  });
  main.querySelectorAll("#os-clear").forEach((button) => {
    button.addEventListener("click", () => {
      Object.keys(filters).forEach((key) => { filters[key] = ""; });
      mount(main);
    });
  });
  main.querySelectorAll("[data-group]").forEach((button) => {
    button.addEventListener("click", () => {
      const key = button.dataset.group;
      if (closedGroups.has(key)) closedGroups.delete(key);
      else closedGroups.add(key);
      mount(main);
    });
  });
  main.querySelectorAll(".os-card[data-order]").forEach((cardNode) => {
    cardNode.addEventListener("click", (event) => {
      if (event.target.closest("button, a, input")) return;
      selectedId = cardNode.dataset.order;
      mount(main);
    });
    cardNode.addEventListener("dragstart", (event) => {
      if (event.target.closest("button, a, input")) {
        event.preventDefault();
        return;
      }
      event.dataTransfer.setData("text/plain", cardNode.dataset.order);
    });
  });
  main.querySelectorAll("[data-column]").forEach((column) => {
    column.addEventListener("dragover", (event) => event.preventDefault());
    column.addEventListener("drop", async (event) => {
      event.preventDefault();
      const id = event.dataTransfer.getData("text/plain");
      const next = column.dataset.column;
      if (!id) return;
      if (next === "cancelada" && !window.confirm("Cancelar esta OS?")) return;
      try {
        if (next === "atribuida") await api.assignOrder(id);
        else await api.orderStatus(id, next);
      } catch (error) {
        toast(error.message, "bad");
      }
    });
  });
  const open = () => { drawer = true; mount(main); };
  document.getElementById("os-open")?.addEventListener("click", open);
  document.getElementById("os-open-empty")?.addEventListener("click", open);
  document.getElementById("os-drawer-close")?.addEventListener("click", () => { drawer = false; mount(main); });
  document.getElementById("os-drawer-back")?.addEventListener("click", () => { drawer = false; mount(main); });
  document.getElementById("os-new")?.addEventListener("submit", async (event) => {
    event.preventDefault();
    const body = Object.fromEntries(new FormData(event.target).entries());
    event.target.querySelector("button").disabled = true;
    try {
      const result = await api.createOrder(body);
      drawer = false;
      selectedId = result.focus?.id || selectedId;
    } catch (error) {
      event.target.querySelector("button").disabled = false;
      toast(error.message, "bad");
    }
  });
  if (groupBy && viewMode === "list") {
    const groups = new Map();
    (state.bootstrap.orders || []).filter(match).forEach((item) => {
      const key = item[groupBy] || "sem";
      if (closedGroups.has(key)) return;
      if (!groups.has(key)) groups.set(key, []);
      groups.get(key).push(item);
    });
    groups.forEach((items, key) => {
      const host = main.querySelector(`[data-group-host="${CSS.escape(key)}"]`);
      if (host) mountTable(host, tableSpec(items, `orders-${key}`));
    });
  }
}

function drawMap(rows) {
  const node = document.getElementById("os-map");
  if (!node || !window.L) return;
  osMap = L.map(node, { zoomControl: false }).setView([-22.48, -50.15], 9);
  L.tileLayer("https://tile.openstreetmap.org/{z}/{x}/{y}.png", { maxZoom: 19, attribution: "&copy; OpenStreetMap" }).addTo(osMap);
  const bounds = [];
  rows.forEach((item) => {
    if (item.lat == null || item.lng == null) return;
    const marker = L.circleMarker([item.lat, item.lng], {
      radius: 6,
      color: item.priority === "critica" ? "#9d2432" : "#1d4e89",
      weight: 2,
      fillOpacity: 0.2,
    }).addTo(osMap);
    marker.bindTooltip(`${item.number}`);
    marker.on("click", () => {
      selectedId = item.id;
      mount(document.getElementById("main"));
    });
    bounds.push([item.lat, item.lng]);
  });
  if (bounds.length) osMap.fitBounds(bounds, { padding: [24, 24] });
  setTimeout(() => {
    if (osMap && document.body.contains(osMap.getContainer())) osMap.invalidateSize();
  }, 80);
}

async function batch(ids, action) {
  for (const id of ids) {
    try {
      if (action === "assign") await api.assignOrder(id);
      else await api.orderStatus(id, action);
    } catch (error) {
      toast(error.message, "bad");
    }
  }
}

function slaText(item) {
  return slaHtml(item).replace(/<[^>]+>/g, "");
}

function slaHtml(item) {
  if (!["aberta", "atribuida", "em_execucao"].includes(item.status)) return "Encerrada";
  const left = Number(item.seconds_left) || 0;
  const abs = Math.abs(left);
  const hours = Math.floor(abs / 3600);
  const minutes = Math.floor((abs % 3600) / 60);
  const text = hours ? `${hours}h ${minutes}min` : `${minutes}min`;
  if (left < 0) return `<span class="is-late">Atrasada ${text}</span>`;
  return `${text} restantes`;
}

function avatar(name) {
  const parts = String(name || "").trim().split(/\s+/).filter(Boolean);
  const letters = ((parts[0] || " ")[0] + (parts.length > 1 ? parts[parts.length - 1][0] : "")).trim().toUpperCase();
  return `<span class="avatar" title="${esc(name || "Sem responsável")}">${esc(letters || "—")}</span>`;
}

function short(value, size = 42) {
  const text = String(value || "");
  return text.length > size ? `${text.slice(0, size - 1)}…` : text;
}

function unique(values) {
  return [...new Set(values.filter(Boolean))].sort((a, b) => String(a).localeCompare(String(b), "pt-BR"));
}

function labelOf(list, id) {
  return list.find((item) => item[0] === id)?.[1] || id || "—";
}
