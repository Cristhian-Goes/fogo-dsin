import { api } from "./api.js";
import { ago, esc, flagMeta, icon, matchesAgent, matchesEquipment, pill, statusMeta, toast, typeLabel } from "./format.js";
import { go, state } from "./state.js";

let map = null;
let regionLayer = null;
let heatLayer = null;
let markers = new Map();
let asideSig = "";
let fitted = false;

const LEVEL_COLOR = {
  estavel: "#3ecf8e",
  atencao: "#e6b325",
  pressao: "#f08a3e",
  critica: "#ff5d5d",
};

export function mount(main, aside) {
  main.innerHTML = `
    <section class="ops">
      <div class="kpi-row" id="kpis"></div>
      <div class="filters" id="filters"></div>
      <div class="map-wrap">
        <div id="map"></div>
        <div class="legend" id="legend"></div>
        <p class="map-note" id="map-note" hidden>Mapa de ruas indisponível. As posições continuam nas coordenadas.</p>
      </div>
    </section>`;
  renderFilters();
  renderLegend();
  renderKpis();
  renderAside(aside);
  ensureMap();
  syncMarkers();
  focusSelection();
}

export function destroy() {
  if (map) map.remove();
  map = null;
  regionLayer = null;
  heatLayer = null;
  markers = new Map();
  asideSig = "";
  fitted = false;
}

export function paintLive() {
  renderKpis();
  syncMarkers();
  const aside = document.getElementById("aside");
  const sig = signature();
  if (aside && sig !== asideSig) renderAside(aside);
  else updateRegionNumbers();
}

export function focusSelection() {
  if (!state.selected || !map) return;
  const point = locate(state.selected);
  if (!point) return;
  map.panTo([point.lat, point.lng], { animate: true });
  syncMarkers();
  renderAside(document.getElementById("aside"));
}

function signature() {
  const b = state.bootstrap;
  return [
    b.alerts.map((item) => item.id + item.level).join(","),
    b.feed[0]?.id || "",
    b.incidents.map((item) => item.id).join(","),
    state.selected ? state.selected.kind + state.selected.id : "",
  ].join("|");
}

function renderKpis() {
  const node = document.getElementById("kpis");
  if (!node) return;
  const k = state.bootstrap.kpis;
  const cards = [
    ["Equipamentos", k.total, `${k.not_installed} ainda não instalado(s)`],
    ["Operacionais", k.operational, "em serviço agora"],
    ["Indisponíveis", k.unavailable, "pane, oficina, desativado ou furto"],
    ["Disponibilidade", `${String(k.availability_pct).replace(".", ",")}%`, "operacionais entre os já instalados"],
    ["Agentes em atividade", k.agents_active, `${k.agents_total} na escala`],
  ];
  node.innerHTML = cards.map(([label, value, hint]) => `
    <article class="kpi">
      <span>${esc(label)}</span>
      <strong>${esc(value)}</strong>
      <small>${esc(hint)}</small>
    </article>`).join("") + stackBar();
}

function stackBar() {
  const by = state.bootstrap.kpis.by_status;
  const total = state.bootstrap.kpis.total || 1;
  const pieces = [
    ["operacional", "ok"],
    ["em_manutencao", "warn"],
    ["mau_funcionamento", "bad"],
    ["furtado", "bad"],
    ["desativado", "mute"],
    ["ainda_nao_instalado", "ghost"],
  ];
  return `<div class="stack" title="Composição do cadastro">${pieces.map(([key, tone]) => {
    const width = (100 * (by[key] || 0)) / total;
    return width ? `<i class="tone-${tone}" style="width:${width}%"></i>` : "";
  }).join("")}</div>`;
}

function renderFilters() {
  const node = document.getElementById("filters");
  const schema = state.bootstrap.schema;
  const neighborhoods = neighborhoodOptions();
  const f = state.filters;
  node.innerHTML = `
    <input id="f-q" type="search" placeholder="Buscar série, rua, nome…" value="${esc(f.q)}" />
    <select id="f-type">${opts(schema.types, "Tipo", f.type)}</select>
    <select id="f-status">${opts(schema.statuses, "Situação", f.status)}</select>
    <select id="f-region">${opts(schema.regions, "Região", f.region)}</select>
    <select id="f-neighborhood">${opts(neighborhoods, "Bairro", f.neighborhood)}</select>
    <select id="f-agency">${opts(schema.agencies.map((id) => ({ id, label: id })), "Órgão", f.agency)}</select>
    <select id="f-role">
      <option value="">Papel</option>
      <option value="sensor" ${f.role === "sensor" ? "selected" : ""}>Sensores</option>
      <option value="frota" ${f.role === "frota" ? "selected" : ""}>Frota</option>
    </select>
    <select id="f-maintenance">
      <option value="">Manutenção</option>
      <option value="urgente" ${f.maintenance === "urgente" ? "selected" : ""}>Imediata ou atrasada</option>
      <option value="proxima" ${f.maintenance === "proxima" ? "selected" : ""}>Nos próximos 7 dias</option>
    </select>
    <label class="check"><input id="f-agents" type="checkbox" ${f.showAgents ? "checked" : ""}/> Agentes</label>
    <label class="check"><input id="f-incidents" type="checkbox" ${f.showIncidents ? "checked" : ""}/> Ocorrências</label>
    <button type="button" class="ghost" data-action="heat">Camada de pressão</button>
    <span class="filter-count" id="filter-count"></span>`;
  node.querySelectorAll("input, select").forEach((el) => el.addEventListener("change", readFilters));
  node.querySelector("#f-q").addEventListener("input", readFilters);
}

function opts(items, placeholder, current) {
  return `<option value="">${esc(placeholder)}</option>` + items.map((item) => {
    const id = typeof item === "string" ? item : item.id;
    const label = typeof item === "string" ? item : (item.label || item.id);
    return `<option value="${esc(id)}" ${id === current ? "selected" : ""}>${esc(label)}</option>`;
  }).join("");
}

function neighborhoodOptions() {
  const seen = new Map();
  for (const item of [...state.bootstrap.equipment, ...state.bootstrap.agents]) {
    const id = `${item.neighborhood}|${item.city}`;
    seen.set(id, `${item.neighborhood} · ${item.city}`);
  }
  return [...seen.entries()].map(([id, label]) => ({ id, label })).sort((a, b) => a.label.localeCompare(b.label, "pt-BR"));
}

function readFilters() {
  const f = state.filters;
  f.q = document.getElementById("f-q").value;
  f.type = document.getElementById("f-type").value;
  f.status = document.getElementById("f-status").value;
  f.region = document.getElementById("f-region").value;
  f.neighborhood = document.getElementById("f-neighborhood").value;
  f.agency = document.getElementById("f-agency").value;
  f.role = document.getElementById("f-role").value;
  f.maintenance = document.getElementById("f-maintenance").value;
  f.showAgents = document.getElementById("f-agents").checked;
  f.showIncidents = document.getElementById("f-incidents").checked;
  syncMarkers();
}

function renderLegend() {
  const types = state.bootstrap.schema.types;
  const statuses = state.bootstrap.schema.statuses;
  document.getElementById("legend").innerHTML = `
    <div>${types.map((item) => `<span>${icon(item.id)} ${esc(item.label)}</span>`).join("")}</div>
    <div>${statuses.map((item) => `<span class="swatch tone-${statusMeta(item.id)[1]}"></span> ${esc(item.label)}`).join("")}
      <span class="swatch agent"></span> agente <span class="swatch incident"></span> ocorrência</div>`;
}

function ensureMap() {
  if (!window.L) {
    document.getElementById("map-note").hidden = false;
    return;
  }
  map = L.map("map", { zoomControl: true, minZoom: 10 }).setView([-27.55, -48.52], 11);
  const tiles = L.tileLayer("https://tile.openstreetmap.org/{z}/{x}/{y}.png", {
    maxZoom: 19,
    attribution: "&copy; OpenStreetMap",
  });
  let errors = 0;
  tiles.on("tileerror", () => {
    errors += 1;
    if (errors === 4) document.getElementById("map-note").hidden = false;
  });
  tiles.addTo(map);
  regionLayer = L.layerGroup().addTo(map);
  setTimeout(() => map.invalidateSize(), 80);
}

function syncMarkers() {
  if (!map) return;
  paintRegions();
  const wanted = new Set();
  const equipment = state.bootstrap.equipment.filter((item) => matchesEquipment(item, state.filters));
  const agents = state.bootstrap.agents.filter((item) => matchesAgent(item, state.filters));
  const incidents = state.filters.showIncidents
    ? state.bootstrap.incidents.filter((item) => !state.filters.region || item.region === state.filters.region)
    : [];
  for (const item of equipment) upsert(item, "equipment", item.type, item.status);
  for (const item of agents) upsert(item, "agent", "agent", item.status);
  for (const item of incidents) upsert(item, "incident", "incident", item.severity === "alta" ? "mau_funcionamento" : "em_manutencao");
  for (const item of equipment) wanted.add(keyOf("equipment", item.id));
  for (const item of agents) wanted.add(keyOf("agent", item.id));
  for (const item of incidents) wanted.add(keyOf("incident", item.id));
  for (const [key, marker] of markers) {
    if (!wanted.has(key)) {
      marker.remove();
      markers.delete(key);
    }
  }
  const count = document.getElementById("filter-count");
  if (count) count.textContent = `${equipment.length} equipamentos no mapa`;
  if (!fitted && markers.size) {
    map.fitBounds(L.featureGroup([...markers.values()]).getBounds().pad(0.12));
    fitted = true;
  }
}

function paintRegions() {
  regionLayer.clearLayers();
  for (const region of state.bootstrap.regions) {
    const color = LEVEL_COLOR[region.level] || "#93a1b3";
    const circle = L.circle([region.lat, region.lng], {
      radius: 850,
      color,
      weight: 1,
      fillColor: color,
      fillOpacity: 0.08,
    });
    circle.bindTooltip(`${region.id}: IPO ${region.ipo} · ${region.label}`, { sticky: true });
    circle.on("click", () => select({ kind: "region", id: region.id }));
    circle.addTo(regionLayer);
  }
  if (heatLayer && map.hasLayer(heatLayer) && window.L.heatLayer) {
    heatLayer.setLatLngs(heatPoints());
  }
}

function heatPoints() {
  const points = [];
  for (const region of state.bootstrap.regions) {
    const intensity = Math.max(0.05, region.ipo / 100);
    for (let i = 0; i < 6; i += 1) {
      const angle = (i / 6) * Math.PI * 2;
      points.push([region.lat + Math.cos(angle) * 0.012, region.lng + Math.sin(angle) * 0.012, intensity]);
    }
  }
  return points;
}

export function toggleHeat() {
  if (!map || !window.L.heatLayer) {
    toast("A camada de calor não carregou neste navegador.", "bad");
    return;
  }
  if (heatLayer && map.hasLayer(heatLayer)) {
    map.removeLayer(heatLayer);
    toast("Camada de pressão oculta.");
    return;
  }
  heatLayer = heatLayer || L.heatLayer(heatPoints(), {
    radius: 42,
    blur: 28,
    minOpacity: 0.25,
    gradient: { 0.2: "#1f6f54", 0.45: "#e6b325", 0.7: "#f08a3e", 1: "#ff5d5d" },
  });
  heatLayer.addTo(map);
  toast("A mancha repete o IPO de cada região. O número da ficha é a conta.");
}

function upsert(item, kind, iconName, status) {
  const key = keyOf(kind, item.id);
  const selected = state.selected && state.selected.kind === kind && state.selected.id === item.id;
  const html = `<div class="pin ${kind} tone-${statusMeta(status)[1]} ${selected ? "is-selected" : ""} ${item.maintenance_flag === "imediata" || status === "mau_funcionamento" || status === "furtado" ? "is-alert" : ""}">${icon(iconName)}</div>`;
  const existing = markers.get(key);
  if (!existing) {
    const marker = L.marker([item.lat, item.lng], {
      icon: L.divIcon({ className: "pin-wrap", html, iconSize: [34, 34], iconAnchor: [17, 17] }),
      zIndexOffset: kind === "incident" ? 800 : kind === "agent" ? 500 : 300,
    });
    marker.bindTooltip(tip(item, kind), { direction: "top", offset: [0, -14] });
    marker.on("click", () => select({ kind, id: item.id }));
    marker._fogoSig = `${status}|${selected}|${iconName}|${item.maintenance_flag || ""}`;
    marker.addTo(map);
    markers.set(key, marker);
    return;
  }
  existing.setLatLng([item.lat, item.lng]);
  const prev = existing._fogoSig;
  const sig = `${status}|${selected}|${iconName}|${item.maintenance_flag || ""}`;
  if (prev !== sig) {
    existing.setIcon(L.divIcon({ className: "pin-wrap", html, iconSize: [34, 34], iconAnchor: [17, 17] }));
    existing._fogoSig = sig;
  }
}

function tip(item, kind) {
  if (kind === "equipment") return `${item.serial} · ${typeLabel(item.type)} · ${statusMeta(item.status)[0]}`;
  if (kind === "agent") return `${item.name} · ${item.registration} · ${statusMeta(item.status)[0]}`;
  return item.title;
}

function keyOf(kind, id) {
  return `${kind}:${id}`;
}

function select(target) {
  state.selected = target;
  syncMarkers();
  renderAside(document.getElementById("aside"));
}

function locate(target) {
  if (target.kind === "region") return state.bootstrap.regions.find((item) => item.id === target.id);
  if (target.kind === "equipment") return state.bootstrap.equipment.find((item) => item.id === target.id);
  if (target.kind === "agent") return state.bootstrap.agents.find((item) => item.id === target.id);
  return state.bootstrap.incidents.find((item) => item.id === target.id);
}

function renderAside(aside) {
  if (!aside) return;
  asideSig = signature();
  const top = aside.scrollTop;
  aside.innerHTML = `
    ${detailCard()}
    <section>
      <h2>Alertas</h2>
      <div class="stack-list">${alertsHtml()}</div>
    </section>
    <section>
      <h2>Regiões agora</h2>
      <div class="region-list" id="region-list">${regionsHtml()}</div>
    </section>
    <section>
      <h2>Amanhã</h2>
      ${tomorrowHtml()}
    </section>
    <section>
      <h2>Fita da cidade</h2>
      <div class="feed">${feedHtml()}</div>
    </section>
    <section>
      <h2>Exercitar a central</h2>
      <p class="hint">Estes botões lançam um fato na cidade de verdade. O cadastro muda, o índice recalcula.</p>
      <div class="exercise">
        <button type="button" data-action="scenario" data-scenario="acidente">Sinistro no Centro</button>
        <button type="button" data-action="scenario" data-scenario="falha-radar">Derrubar um radar</button>
        <button type="button" data-action="scenario" data-scenario="furto">Furtar uma câmera</button>
        <button type="button" data-action="scenario" data-scenario="surto">Surto na Lagoa</button>
        <button type="button" data-action="scenario" data-scenario="silencio">Silêncio de telemetria</button>
        <button type="button" class="danger" data-action="reset">Restaurar demonstração</button>
      </div>
    </section>`;
  aside.scrollTop = top;
}

function updateRegionNumbers() {
  const list = document.getElementById("region-list");
  if (!list) return;
  list.innerHTML = regionsHtml();
}

function alertsHtml() {
  const alerts = state.bootstrap.alerts;
  if (!alerts.length) return `<p class="hint">Nenhum alerta aberto.</p>`;
  return alerts.map((item) => `
    <button type="button" class="alert tone-${item.level === "critico" ? "bad" : "warn"}" data-action="open-alert" data-target-type="${esc(item.target_type)}" data-target-id="${esc(item.target_id)}">
      <strong>${esc(item.title)}</strong>
      <span>${esc(item.detail)}</span>
    </button>`).join("");
}

function regionsHtml() {
  return state.bootstrap.regions.map((region) => `
    <button type="button" class="region tone-${region.level}" data-action="open-region" data-region="${esc(region.id)}">
      <b>${esc(region.id)}</b>
      <em>IPO ${region.ipo} · ${esc(region.label)}</em>
      <small>${region.agents_active} em campo · ${region.sensors_down}/${region.sensors_total} sensores fora</small>
    </button>`).join("");
}

function tomorrowHtml() {
  const preview = state.bootstrap.preview;
  const top = preview.top?.[0];
  if (!top) {
    return `<p class="hint">${esc(preview.framing || "")}</p><button type="button" data-action="go" data-view="preditivo">Abrir o preditivo</button>`;
  }
  return `
    <p class="hint">${esc(preview.tomorrow_label)}</p>
    <article class="rec">
      <strong>${esc(top.title)}</strong>
      <p>${esc(top.detail)}</p>
    </article>
    <button type="button" data-action="go" data-view="preditivo">Ver o dia inteiro</button>`;
}

function feedHtml() {
  return state.bootstrap.feed.map((item) => `
    <p class="feed-item tone-${item.level === "critico" ? "bad" : item.level === "atencao" ? "warn" : "info"}">
      <time>${esc(ago(item.at, state.bootstrap.clock))}</time>
      ${esc(item.text)}
    </p>`).join("");
}

function detailCard() {
  const target = state.selected;
  if (!target) return "";
  if (target.kind === "equipment") return equipmentDetail(state.bootstrap.equipment.find((item) => item.id === target.id));
  if (target.kind === "agent") return agentDetail(state.bootstrap.agents.find((item) => item.id === target.id));
  if (target.kind === "incident") return incidentDetail(state.bootstrap.incidents.find((item) => item.id === target.id));
  if (target.kind === "region") return regionDetail(state.bootstrap.regions.find((item) => item.id === target.id));
  return "";
}

function equipmentDetail(eq) {
  if (!eq) return "";
  const flag = flagMeta(eq.maintenance_flag);
  const spec = state.bootstrap.schema.types.find((item) => item.id === eq.type);
  const attrs = (spec?.fields || []).map((field) => {
    const value = eq.attrs?.[field.key];
    if (value == null || value === "") return "";
    const shown = typeof value === "boolean" ? (value ? "sim" : "não") : value;
    return `<div><dt>${esc(field.label)}</dt><dd>${esc(shown)}</dd></div>`;
  }).join("");
  return `
    <section class="detail">
      <header>
        <span>${icon(eq.type)} ${esc(typeLabel(eq.type))}</span>
        <button type="button" class="ghost" data-action="clear">Fechar</button>
      </header>
      <h3>${esc(eq.serial)}</h3>
      <p>${esc(eq.brand)} ${esc(eq.model)}</p>
      ${pill(eq.status)}
      ${flag ? `<span class="pill tone-${flag[1]}"><i></i>${esc(flag[0])}</span>` : ""}
      <dl>
        <div><dt>Órgão</dt><dd>${esc(eq.agency)}</dd></div>
        <div><dt>Onde</dt><dd>${esc(eq.street)}, ${esc(eq.reference)}<br>${esc(eq.neighborhood)} · ${esc(eq.city)}/${esc(eq.uf)} · ${esc(eq.cep)}</dd></div>
        <div><dt>Coordenadas</dt><dd>${eq.lat.toFixed(5)}, ${eq.lng.toFixed(5)}</dd></div>
        <div><dt>Próxima manutenção</dt><dd>${esc(eq.next_maintenance || "não agendada")}</dd></div>
        <div><dt>Último contato</dt><dd>${esc(ago(eq.last_seen, state.bootstrap.clock))}</dd></div>
        ${eq.notes ? `<div><dt>Notas</dt><dd>${esc(eq.notes)}</dd></div>` : ""}
        ${attrs}
      </dl>
      <div class="exercise">
        <button type="button" data-action="patch-eq" data-id="${esc(eq.id)}" data-status="operacional">Marcar operacional</button>
        <button type="button" data-action="patch-eq" data-id="${esc(eq.id)}" data-status="mau_funcionamento">Mau funcionamento</button>
        <button type="button" data-action="edit" data-kind="equipment" data-id="${esc(eq.id)}">Editar no inventário</button>
      </div>
    </section>`;
}

function agentDetail(agent) {
  if (!agent) return "";
  return `
    <section class="detail">
      <header>
        <span>${icon("agent")} Agente</span>
        <button type="button" class="ghost" data-action="clear">Fechar</button>
      </header>
      <h3>${esc(agent.name)}</h3>
      <p>${esc(agent.role)} · ${esc(agent.registration)}</p>
      ${pill(agent.status)}
      <dl>
        <div><dt>Órgão</dt><dd>${esc(agent.agency)}</dd></div>
        <div><dt>Equipe e turno</dt><dd>${esc(agent.team || "—")} · ${esc(agent.shift)}</dd></div>
        <div><dt>Base</dt><dd>${esc(agent.street)}, ${esc(agent.reference)}<br>${esc(agent.neighborhood)} · ${esc(agent.city)}/${esc(agent.uf)}</dd></div>
        <div><dt>Posição agora</dt><dd>${agent.lat.toFixed(5)}, ${agent.lng.toFixed(5)} · ${esc(ago(agent.last_seen, state.bootstrap.clock))}</dd></div>
        <div><dt>Telefone</dt><dd>${esc(agent.phone || "—")}</dd></div>
      </dl>
      <button type="button" data-action="edit" data-kind="agent" data-id="${esc(agent.id)}">Editar no inventário</button>
    </section>`;
}

function incidentDetail(incident) {
  if (!incident) return "";
  return `
    <section class="detail">
      <header>
        <span>${icon("incident")} Ocorrência</span>
        <button type="button" class="ghost" data-action="clear">Fechar</button>
      </header>
      <h3>${esc(incident.title)}</h3>
      <p>${esc(incident.detail)}</p>
      <p class="hint">${esc(incident.region)} · ${esc(ago(incident.at, state.bootstrap.clock))}</p>
      <button type="button" data-action="ack" data-id="${esc(incident.id)}">Dar ciência</button>
    </section>`;
}

function regionDetail(region) {
  if (!region) return "";
  return `
    <section class="detail">
      <header>
        <span>Região</span>
        <button type="button" class="ghost" data-action="clear">Fechar</button>
      </header>
      <h3>${esc(region.id)}</h3>
      <p>IPO ${region.ipo} · ${esc(region.label)}. ${region.agents_active} agente(s) em campo, necessidade desta hora: ${region.agents_need}. Sensores fora: ${region.sensors_down} de ${region.sensors_total}.</p>
    </section>`;
}

export async function patchEquipment(id, status) {
  const body = { status };
  if (status === "mau_funcionamento") body.maintenance_need = "imediata";
  if (status === "operacional") {
    body.maintenance_need = "nenhuma";
    body.next_maintenance = null;
  }
  try {
    await api.patchEquipment(id, body);
    toast(status === "operacional" ? "Equipamento marcado como operacional. O índice vai recalcular." : "Equipamento marcado em mau funcionamento.");
  } catch (error) {
    toast(error.message, "bad");
  }
}

export function openAlert(type, id) {
  const kind = type === "equipment" ? "equipment" : type === "incident" ? "incident" : "region";
  select({ kind, id });
  focusSelection();
}
