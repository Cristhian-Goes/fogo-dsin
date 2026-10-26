import { api } from "./api.js";
import { ago, clockLabel, esc, pill } from "./format.js";
import { state } from "./state.js";

let map;
let pins;
let areas;
let lines;
let heat;
let fitted = false;
let bag = [];
let quotes = null;
let quoteIncident = "";
let quoteError = "";
let quoteLoading = false;
let roadPreview = null;

function roadPath(route) {
  if (!route?.road || !Array.isArray(route.polyline) || route.polyline.length < 3) return null;
  return route.polyline;
}

function money(value) {
  return Number(value || 0).toLocaleString("pt-BR", { style: "currency", currency: "BRL" });
}

const DUTY_LABEL = {
  disponivel: "Disponível",
  em_atendimento: "Em atendimento",
  em_deslocamento: "Em deslocamento",
  indisponivel: "Indisponível",
};

function dutyFrom(agent) {
  if (agent.mission?.phase) return agent.mission.phase === "deslocamento" ? "em_deslocamento" : "em_atendimento";
  if (agent.status === "fora_de_servico" || agent.status === "em_pausa") return "indisponivel";
  if (agent.status === "em_deslocamento") return "em_deslocamento";
  if (agent.status === "em_atividade") return "disponivel";
  return "indisponivel";
}
const TILES = "https://tile.openstreetmap.org/{z}/{x}/{y}.png";

export function mount(main) {
  main.innerHTML = `
    <section class="cco">
      <div class="kpi-strip" aria-label="Indicadores da operação">${kpiStrip()}</div>
      <div class="map-wrap">
        <div id="map" role="application" aria-label="Mapa operacional de Marília, Assis e Cândido Mota"></div>
        <div class="map-tools">
          <button type="button" class="ghost" data-action="toggle-layers" aria-expanded="false" aria-controls="layer-drawer">Camadas</button>
          <button type="button" class="ghost" data-action="map-home">Centralizar operação</button>
          <form class="geo-form" id="geo-form">
            <label class="sr" for="geo-q">Buscar município ou UF</label>
            <input id="geo-q" type="search" placeholder="Município ou UF" />
            <button type="button" class="primary" data-action="geo-search">Buscar</button>
          </form>
        </div>
        <div class="layer-drawer" id="layer-drawer" hidden>
          <section>
            <h2>Operação</h2>
            ${layerBox("incidents", "Ocorrências")}
            ${layerBox("agents", "Agentes")}
            ${layerBox("vehicles", "Veículos")}
            ${layerBox("fleet", "Viaturas")}
            ${layerBox("routes", "Rotas")}
            ${layerBox("events", "Jornada")}
          </section>
          <section>
            <h2>Infraestrutura</h2>
            ${layerBox("cameras", "Câmeras")}
            ${layerBox("radars", "Radares")}
            ${layerBox("others", "Outros equipamentos")}
            ${layerBox("maintenance", "Manutenção")}
          </section>
          <section>
            <h2>Análise territorial</h2>
            ${layerBox("areas", "Regiões")}
            ${layerBox("coverage", "Cobertura")}
            <fieldset class="heat-inline">
              <legend>Mapa de calor</legend>
              ${heatBox("", "Nenhum")}
              ${heatBox("incidents", "Ocorrências")}
              ${heatBox("demand", "Demanda")}
              ${heatBox("down", "Indisponibilidade")}
              ${heatBox("reinforce", "Reforço")}
            </fieldset>
          </section>
          <div class="actions">
            <button type="button" class="ghost" data-action="layers-none">Ocultar todas</button>
            <button type="button" class="ghost" data-action="layers-reset">Restaurar padrão</button>
          </div>
          <p class="legend" aria-label="Legenda">G agente · D deslocamento · A atendimento · ! ocorrência · C câmera · R radar · V viatura</p>
        </div>
        <div class="place-banner" id="place-banner" hidden></div>
        <div class="replay-banner" id="replay-banner" hidden></div>
        <div class="region-chip" id="region-chip" hidden></div>
      </div>
      <aside class="ops-panel" id="ops-panel" aria-label="Painel operacional"></aside>
    </section>`;
  map = L.map("map", { zoomControl: false }).setView([-22.48, -50.15], 9);
  L.control.zoom({ position: "topright" }).addTo(map);
  L.tileLayer(TILES, { maxZoom: 19, attribution: "&copy; OpenStreetMap" }).addTo(map);
  areas = L.layerGroup().addTo(map);
  lines = L.layerGroup().addTo(map);
  pins = L.layerGroup().addTo(map);
  map.on("zoomend", () => {
    if (fitted) drawMap();
  });
  main.querySelector("#layer-drawer").addEventListener("change", (event) => {
    const input = event.target;
    if (input.dataset.layer) {
      state.layers[input.dataset.layer] = input.checked;
      paint();
      return;
    }
    if (input.name === "heat") {
      state.heat = input.value;
      paint();
    }
  });
  paint();
  setTimeout(() => map.invalidateSize(), 60);
}

export function destroy() {
  heat = null;
  if (map) {
    map.remove();
    map = null;
  }
  fitted = false;
}

export function paintLive() {
  if (!map || state.view !== "cco") return;
  const strip = document.querySelector(".kpi-strip");
  if (strip) strip.innerHTML = kpiStrip();
  drawMap();
  const panel = document.getElementById("ops-panel");
  if (panel && panel.contains(document.activeElement)) return;
  paintPanel();
}

export function refresh() {
  if (!map || state.view !== "cco") return;
  const strip = document.querySelector(".kpi-strip");
  if (strip) strip.innerHTML = kpiStrip();
  drawMap();
  paintPanel();
  syncLayerCounts();
  paintPlace();
}

export function showPlace(place) {
  state.place = place;
  if (!map) return;
  map.setView([place.lat, place.lng], place.zoom || 11);
  refresh();
}

export function focusHome() {
  if (!map) return;
  state.region = "";
  map.fitBounds([[-22.80, -50.50], [-22.15, -49.88]]);
  refresh();
}
export function focusSelection() {
  refresh();
  const item = current();
  if (item?.lat && map) map.setView([item.lat, item.lng], 15);
}

const FLEET = new Set(["moto_agente", "viatura_gm", "viatura_pm", "transporte", "veiculo_autonomo"]);

function layerBox(key, label) {
  return `<label><input type="checkbox" data-layer="${key}" ${state.layers[key] ? "checked" : ""}/> ${label} <span data-count="${key}">0</span></label>`;
}

function syncLayerCounts() {
  const data = state.bootstrap;
  if (!data) return;
  const down = ["mau_funcionamento", "em_manutencao", "desativado", "furtado"];
  const counts = {
    incidents: data.incidents.filter((item) => !["encerrada", "ciencia"].includes(item.status)).length,
    agents: data.agents.filter((item) => item.status !== "fora_de_servico").length,
    fleet: data.equipment.filter((item) => FLEET.has(item.type)).length,
    vehicles: (data.vehicles || []).length,
    events: (data.events || []).length,
    routes: data.agents.filter((item) => item.plan || item.route).length,
    cameras: data.equipment.filter((item) => item.type === "camera").length,
    radars: data.equipment.filter((item) => item.type === "radar").length,
    others: data.equipment.filter((item) => !FLEET.has(item.type) && !["camera", "radar"].includes(item.type)).length,
    maintenance: data.equipment.filter((item) => item.maintenance_flag || down.includes(item.status)).length,
    areas: data.regions.length,
    coverage: data.regions.filter((item) => item.blind).length,
  };
  for (const [key, value] of Object.entries(counts)) {
    const node = document.querySelector(`[data-count="${key}"]`);
    if (node) node.textContent = String(value);
  }
}

function paintPlace() {
  const banner = document.getElementById("place-banner");
  if (!banner) return;
  banner.hidden = !state.place;
  if (state.place) {
    banner.innerHTML = `<span>${esc(state.place.name)} · ${esc(state.place.note)}</span><button type="button" class="ghost" data-action="clear-place">Fechar</button>`;
  }
}

function heatBox(value, label) {
  return `<label><input type="radio" name="heat" value="${value}" ${state.heat === value ? "checked" : ""}/> ${label}</label>`;
}

function paint() {
  drawMap();
  paintPanel();
  syncLayerCounts();
  paintPlace();
}

function paintPanel() {
  const panel = document.getElementById("ops-panel");
  if (panel) panel.innerHTML = panelHtml();
  const banner = document.getElementById("replay-banner");
  if (banner) {
    banner.hidden = !state.replay;
    banner.innerHTML = state.replay
      ? `<span>Replay ${esc(clockLabel(state.replay.at))}</span><button type="button" class="ghost" data-action="replay-live">Voltar ao vivo</button>`
      : "";
  }
  const chip = document.getElementById("region-chip");
  if (chip) {
    chip.hidden = !state.region;
    chip.innerHTML = state.region
      ? `<span>Região: ${esc(state.region)}</span><button type="button" class="ghost" data-action="clear-region">Limpar</button>`
      : "";
  }
}

function world() {
  const pack = state.bootstrap;
  if (!state.replay) return pack;
  const frame = state.replay;
  const agents = pack.agents.map((agent) => {
    const hit = frame.agents.find((item) => item.id === agent.id);
    if (!hit) return agent;
    const merged = { ...agent, lat: hit.lat, lng: hit.lng, status: hit.status, mission: hit.mission, route: null };
    const duty = dutyFrom(merged);
    return { ...merged, duty, duty_label: DUTY_LABEL[duty] };
  });
  const equipment = pack.equipment.map((eq) => {
    const hit = frame.equipment.find((item) => item.id === eq.id);
    return hit ? { ...eq, lat: hit.lat, lng: hit.lng, status: hit.status } : eq;
  });
  const allowed = new Set(frame.incidents.map((item) => item.id));
  const incidents = pack.incidents
    .filter((item) => allowed.has(item.id))
    .map((item) => {
      const hit = frame.incidents.find((row) => row.id === item.id);
      return { ...item, lat: hit.lat, lng: hit.lng, status: hit.status, route: null };
    });
  return { ...pack, agents, equipment, incidents };
}

function visibleRegion(item) {
  return !state.region || item.region === state.region;
}

function inCrisis(kind, item) {
  if (!state.crisis) return true;
  const incident = state.bootstrap.incidents.find((row) => row.id === state.crisis);
  if (!incident) return true;
  if (kind === "incident") return item.id === incident.id;
  if (kind === "agent") return item.id === incident.assigned_agent_id || item.region === incident.region;
  return item.region === incident.region;
}

function drawMap() {
  pins.clearLayers();
  areas.clearLayers();
  lines.clearLayers();
  bag = [];
  const data = world();
  if (state.layers.areas) {
    for (const region of data.regions) {
      if (!visibleRegion(region)) continue;
      const color = region.state === "critica" ? "#a11d2b" : region.state === "atencao" ? "#8a5a00" : "#1f4e79";
      const circle = L.circle([region.lat, region.lng], {
        radius: region.state === "normal" ? 700 : 1100,
        color,
        weight: region.state === "normal" ? 1 : 2,
        fillColor: color,
        fillOpacity: region.state === "normal" ? 0.03 : 0.08,
      });
      circle.bindTooltip(`${region.region}: ${region.state_label}`, { sticky: true });
      circle.on("click", () => {
        state.region = region.region;
        state.selected = { kind: "region", id: region.region };
        paint();
      });
      circle.addTo(areas);
    }
  }
  if (state.layers.coverage) {
    for (const agent of data.agents) {
      if (agent.duty !== "disponivel" || agent.stale) continue;
      L.circle([agent.lat, agent.lng], { radius: 2300, color: "#1f4e79", weight: 1, fillOpacity: 0.04 }).addTo(areas);
      L.circle([agent.lat, agent.lng], { radius: 4700, color: "#1f4e79", weight: 1, dashArray: "4 4", fillOpacity: 0 }).addTo(areas);
    }
    for (const region of data.regions) {
      if (!region.blind) continue;
      L.circle([region.lat, region.lng], {
        radius: 1800, color: "#8a5a00", weight: 1, fillColor: "#8a5a00", fillOpacity: 0.08,
      }).bindTooltip(`${region.region}: baixa capacidade de observação`).addTo(areas);
    }
  }
  if (state.layers.routes && !state.replay) {
    for (const agent of data.agents) {
      const driven = roadPath(agent.route);
      if (driven) {
        const line = L.polyline(driven, { color: "#1b6b45", weight: 4 });
        line.bindTooltip(`${agent.route.label || "Deslocamento"} · ${agent.name}`);
        line.on("click", () => select("agent", agent.id));
        line.addTo(lines);
      }
      const planned = roadPath(agent.plan);
      if (planned) {
        const status = agent.plan.status === "aprovada" ? "aprovada" : "planejada";
        const line = L.polyline(planned, { color: "#1f4e79", weight: 3, dashArray: "6 6" });
        line.bindTooltip(`Rota ${status} · ${agent.name}`);
        line.on("click", () => select("agent", agent.id));
        line.addTo(lines);
      }
    }
    if (roadPreview && roadPreview.length >= 3) {
      L.polyline(roadPreview, { color: "#1b6b45", weight: 5 }).addTo(lines);
    }
  }
  if (state.layers.incidents) {
    for (const incident of data.incidents) {
      if (!visibleRegion(incident) || !inCrisis("incident", incident) || incident.status === "encerrada" || incident.status === "ciencia") continue;
      addPin(incident.lat, incident.lng, incidentPin(incident), `${incident.number} ${incident.title}`, () => select("incident", incident.id));
    }
  }
  if (state.layers.vehicles) {
    for (const vehicle of data.vehicles || []) {
      if (vehicle.lat == null || vehicle.active === false) continue;
      if (state.region && vehicle.base_region !== state.region) continue;
      addPin(vehicle.lat, vehicle.lng, `<i class="pin pin-vehicle">V</i>`, `${vehicle.name} · ${vehicle.plate || ""}`, () => select("vehicle", vehicle.id));
    }
  }
  if (state.layers.events) {
    for (const item of data.events || []) {
      if (item.lat == null) continue;
      addPin(item.lat, item.lng, `<i class="pin">${item.kind === "intervalo" ? "I" : "P"}</i>`, `${item.agent_name} · ${item.label}`, () => select("agent", item.agent_id));
    }
  }
  if (state.layers.agents) {
    for (const agent of data.agents) {
      if (!visibleRegion(agent) || !inCrisis("agent", agent) || agent.duty === "indisponivel" && agent.status === "fora_de_servico") continue;
      if (!visibleRegion(agent)) continue;
      addPin(agent.lat, agent.lng, agentPin(agent), `${agent.name} · ${agent.duty_label}`, () => select("agent", agent.id));
    }
  }
  for (const eq of data.equipment) {
    if (!visibleRegion(eq) || !inCrisis("equipment", eq) || !showEquipment(eq)) continue;
    addPin(eq.lat, eq.lng, equipmentPin(eq), `${eq.serial} · ${eq.type_label}`, () => select("equipment", eq.id));
  }
  if (state.layers.maintenance) {
    for (const eq of data.equipment) {
      if (!visibleRegion(eq)) continue;
      if (!(eq.maintenance_flag || ["mau_funcionamento", "em_manutencao", "furtado"].includes(eq.status))) continue;
      L.circleMarker([eq.lat, eq.lng], {
        radius: 14, color: "#8a5a00", weight: 2, fillOpacity: 0, interactive: false,
      }).addTo(pins);
    }
  }
  flushPins();
  if (state.place?.lat) {
    L.circleMarker([state.place.lat, state.place.lng], { radius: 8, color: "#1f4e79", weight: 2, fillOpacity: 0.2 })
      .bindTooltip(`${state.place.name} · consulta territorial`)
      .addTo(pins);
  }
  drawHeat(data);
  if (!fitted) {
    fitted = true;
    const region = state.region && state.bootstrap.regions.find((item) => item.id === state.region);
    if (region) map.setView([region.lat, region.lng], 14);
    else map.fitBounds([[-22.80, -50.50], [-22.15, -49.88]]);
  }
}

function showEquipment(eq) {
  if (FLEET.has(eq.type)) return state.layers.fleet;
  if (eq.type === "camera") return state.layers.cameras;
  if (eq.type === "radar") return state.layers.radars;
  return state.layers.others;
}

function select(kind, id) {
  state.selected = { kind, id };
  paintPanel();
  drawMap();
}

function addPin(lat, lng, html, title, onClick) {
  bag.push({ lat, lng, html, title, onClick });
}

function flushPins() {
  if (!map || map.getZoom() >= 13 || bag.length < 12) {
    bag.forEach(placePin);
    return;
  }
  const groups = [];
  for (const pin of bag) {
    const point = map.latLngToContainerPoint([pin.lat, pin.lng]);
    let group = groups.find((item) => Math.hypot(item.x - point.x, item.y - point.y) < 46);
    if (!group) {
      group = { x: point.x, y: point.y, items: [] };
      groups.push(group);
    }
    group.items.push(pin);
  }
  for (const group of groups) {
    if (group.items.length === 1) {
      placePin(group.items[0]);
      continue;
    }
    const lat = group.items.reduce((sum, pin) => sum + pin.lat, 0) / group.items.length;
    const lng = group.items.reduce((sum, pin) => sum + pin.lng, 0) / group.items.length;
    const marker = L.marker([lat, lng], {
      icon: L.divIcon({
        className: "pin-wrap",
        html: `<span class="pin pin-cluster">${group.items.length}</span>`,
        iconSize: [28, 28],
        iconAnchor: [14, 14],
      }),
      title: `${group.items.length} elementos`,
    });
    marker.on("click", () => map.setView([lat, lng], Math.min(16, map.getZoom() + 2)));
    marker.addTo(pins);
  }
}

function placePin(pin) {
  const marker = L.marker([pin.lat, pin.lng], {
    icon: L.divIcon({ className: "pin-wrap", html: pin.html, iconSize: [22, 22], iconAnchor: [11, 11] }),
    keyboard: true,
    title: pin.title,
  });
  marker.bindTooltip(pin.title, { direction: "top", opacity: 0.95 });
  marker.on("click", pin.onClick);
  marker.addTo(pins);
}

function selected(kind, id) {
  return state.selected?.kind === kind && state.selected?.id === id ? " is-selected" : "";
}

function agentPin(agent) {
  const tone = agent.duty === "indisponivel" ? "pin-mute" : agent.duty === "em_atendimento" ? "pin-warn" : "pin-agent";
  const letter = agent.duty === "em_deslocamento" ? "D" : agent.duty === "em_atendimento" ? "A" : "G";
  return `<span class="pin ${tone}${selected("agent", agent.id)}">${letter}</span>`;
}

function incidentPin(incident) {
  const letter = incident.priority === "critica" ? "!" : incident.priority === "alta" ? "A" : incident.priority === "baixa" ? "B" : "M";
  const tone = incident.priority === "baixa" || incident.priority === "media" ? "pin-warn" : "pin-incident";
  return `<span class="pin ${tone}${selected("incident", incident.id)}">${letter}</span>`;
}

function equipmentPin(eq) {
  const bad = ["mau_funcionamento", "furtado", "desativado", "em_manutencao"].includes(eq.status);
  const letter = eq.type === "camera" ? "C" : eq.type === "radar" ? "R" : FLEET.has(eq.type) ? "V" : "E";
  const tone = bad ? "pin-bad" : FLEET.has(eq.type) ? "pin-fleet" : eq.type === "camera" ? "pin-camera" : eq.type === "radar" ? "pin-radar" : "pin-other";
  return `<span class="pin ${tone}${selected("equipment", eq.id)}">${letter}</span>`;
}

function drawHeat(data) {
  if (heat) {
    map.removeLayer(heat);
    heat = null;
  }
  if (!state.heat || !window.L.heatLayer) return;
  const points = [];
  if (state.heat === "incidents") {
    for (const incident of data.incidents) {
      if (!visibleRegion(incident) || incident.status === "encerrada") continue;
      const weight = incident.priority === "critica" ? 1 : incident.priority === "alta" ? 0.75 : incident.priority === "media" ? 0.45 : 0.25;
      points.push([incident.lat, incident.lng, weight]);
    }
  } else if (state.heat === "demand") {
    for (const region of data.regions) {
      if (!visibleRegion(region)) continue;
      points.push([region.lat, region.lng, Math.max(0.15, region.ipo / 100)]);
    }
  } else if (state.heat === "down") {
    for (const eq of data.equipment) {
      if (!visibleRegion(eq) || !["mau_funcionamento", "em_manutencao", "desativado", "furtado"].includes(eq.status)) continue;
      points.push([eq.lat, eq.lng, 0.85]);
    }
  } else if (state.heat === "reinforce") {
    for (const region of data.regions) {
      if (!visibleRegion(region) || region.gap < 1) continue;
      points.push([region.lat, region.lng, Math.min(1, region.gap / 3)]);
    }
  }
  if (!points.length) return;
  heat = L.heatLayer(points, { radius: 28, blur: 22, maxZoom: 15, minOpacity: 0.25 });
  heat.addTo(map);
}

function current() {
  const pack = world();
  const selectedItem = state.selected;
  if (!selectedItem) return null;
  if (selectedItem.kind === "incident") return pack.incidents.find((item) => item.id === selectedItem.id);
  if (selectedItem.kind === "agent") return pack.agents.find((item) => item.id === selectedItem.id);
  if (selectedItem.kind === "equipment") return pack.equipment.find((item) => item.id === selectedItem.id);
  if (selectedItem.kind === "region") return pack.regions.find((item) => item.id === selectedItem.id);
  if (selectedItem.kind === "vehicle") return (pack.vehicles || []).find((item) => item.id === selectedItem.id);
  if (selectedItem.kind === "route") {
    const [agentId, mode] = String(selectedItem.id).split(":");
    const agent = pack.agents.find((item) => item.id === agentId);
    const source = mode === "plan" ? agent?.plan : agent?.route;
    if (!agent || !source?.polyline?.length) return null;
    return { lat: source.polyline[0][0], lng: source.polyline[0][1], title: source.label || agent.team, agent };
  }
  return null;
}

function kpiStrip() {
  const k = state.bootstrap.kpis || {};
  const card = (value, label, hint) => `<div class="kpi" title="${esc(hint)}"><b>${esc(value)}</b><span>${esc(label)}</span></div>`;
  return [
    card(k.total ?? "—", "Total", "Equipamentos cadastrados"),
    card(k.operational ?? "—", "Operacionais", "Situação operacional"),
    card(k.unavailable ?? "—", "Indisponíveis", "Fora de operação, em manutenção, desativados ou furtados"),
    card(`${k.availability_pct ?? "—"}%`, "Disponibilidade", "Operacionais divididos pelos equipamentos já instalados"),
    card(k.agents_active ?? "—", "Agentes ativos", "Agentes em atividade neste turno"),
  ].join("");
}

function panelHtml() {
  const item = current();
  return `${nowHtml()}${item ? detailHtml(item) : queueHtml()}${changesHtml()}`;
}

function nowHtml() {
  const now = state.bootstrap.now;
  const cell = (label, value, hot, jump) => `<button type="button" class="now-cell${hot ? " is-hot" : ""}" data-action="jump" data-jump="${jump}"><span>${label}</span><strong>${value}</strong></button>`;
  return `
    <h2>Agora</h2>
    <div class="now">
      ${cell("Críticas", now.critical, now.critical > 0, "critical")}
      ${cell("Em atendimento", now.in_service, false, "service")}
      ${cell("Disponíveis", now.agents_free, false, "free")}
      ${cell("Em missão", now.agents_busy, false, "mission")}
      ${cell("Indisponíveis", now.equipment_down, now.equipment_down > 0, "down")}
      ${cell("Regiões em atenção", now.regions_watch, now.regions_watch > 0, "regions")}
    </div>`;
}

function queueHtml() {
  const items = state.bootstrap.attention || [];
  if (!items.length) return `<h2>O que precisa da sua atenção</h2><p>Nenhum item prioritário neste instante.</p>`;
  return `
    <h2>O que precisa da sua atenção</h2>
    <ol class="queue">
      ${items.map((item) => `
        <li class="rank-${item.rank}">
          <p class="why">${esc(item.why)}</p>
          <h3>${esc(item.title)}</h3>
          <p>${esc(item.where)}</p>
          <button type="button" class="primary" data-action="${item.action_id === "forecast" ? "open-forecast" : "select"}" data-view="previsao" data-region="${esc(item.region || "")}" data-kind="${esc(item.target_type)}" data-id="${esc(item.target_id)}">${esc(item.action)}</button>
        </li>`).join("")}
    </ol>`;
}

function changesHtml() {
  const changes = state.bootstrap.changes;
  const session = sessionDelta();
  return `
    <h2>O que mudou</h2>
    <p class="hint">${esc(changes.label)}</p>
    <ul class="changes">
      <li>+ ${changes.new_incidents} nova(s) ocorrência(s)</li>
      <li>+ ${changes.critical_notes} registro(s) crítico(s)</li>
      <li>+ ${changes.updates} atualização(ões) na fita</li>
    </ul>
    ${session ? `<p class="hint">Desde que esta tela foi aberta: + ${session.created} ocorrência(s), + ${session.offline} equipamento(s) fora, + ${session.started} agente(s) acionado(s), + ${session.closed} encerramento(s).</p>` : ""}
    <ul class="timeline">
      ${(changes.lines || []).map((line) => `<li><time>${esc(clockLabel(line.at))}</time>${esc(line.text)}</li>`).join("")}
    </ul>`;
}

function sessionDelta() {
  const base = state.baseline;
  const now = state.bootstrap;
  if (!base) return null;
  const before = new Map(base.incidents.map((item) => [item.id, item.status]));
  let created = 0;
  let closed = 0;
  for (const incident of now.incidents) {
    if (!before.has(incident.id)) created += 1;
    else if (before.get(incident.id) !== "encerrada" && incident.status === "encerrada") closed += 1;
  }
  const equipment = new Map(base.equipment.map((item) => [item.id, item.status]));
  let offline = 0;
  for (const eq of now.equipment) {
    if (equipment.get(eq.id) === "operacional" && !["operacional", "ainda_nao_instalado"].includes(eq.status)) offline += 1;
  }
  const agents = new Map(base.agents.map((item) => [item.id, item.duty]));
  let started = 0;
  for (const agent of now.agents) {
    if (agents.get(agent.id) === "disponivel" && ["em_deslocamento", "em_atendimento"].includes(agent.duty)) started += 1;
  }
  return { created, closed, offline, started };
}

function detailHtml(item) {
  const kind = state.selected.kind;
  const back = `<button type="button" class="ghost" data-action="back">Voltar à fila</button> <button type="button" class="ghost" data-action="open-record" data-kind="${esc(kind)}" data-id="${esc(state.selected.id)}">Abrir ficha</button>`;
  if (kind === "incident") return `${back}${incidentDetail(item)}`;
  if (kind === "equipment") return `${back}${equipmentDetail(item)}`;
  if (kind === "agent") return `${back}${agentDetail(item)}`;
  if (kind === "vehicle") return `${back}<article class="detail"><h2>${esc(item.name)}</h2><p class="meta">${esc(item.plate || "")} · ${esc(item.base_region)}</p><p>${esc(item.brand)} ${esc(item.model)}. ${esc(item.status)}.</p></article>`;
  if (kind === "route") return `${back}<article class="detail"><h2>${esc(item.title)}</h2><p class="meta">${esc(item.agent?.team || "")} · ${esc(item.agent?.name || "")}</p></article>`;
  return `${back}${regionDetail(item)}`;
}

export async function loadVehicleQuotes(incidentId) {
  quoteIncident = incidentId;
  quotes = null;
  quoteError = "";
  quoteLoading = true;
  roadPreview = null;
  paint();
  try {
    quotes = await api.compareVehicles(incidentId);
  } catch (error) {
    quoteError = error.message;
  } finally {
    quoteLoading = false;
    paint();
  }
}

export function previewChoice(vehicleId, choice) {
  const row = quotes?.rows?.find((item) => item.vehicle.id === vehicleId);
  const option = choice === "economica" ? row?.economical : row?.fastest;
  roadPreview = option?.polyline?.length >= 3 ? option.polyline : null;
  paint();
}

export function clearRoadPreview() {
  quotes = null;
  quoteIncident = "";
  roadPreview = null;
}

function optionLine(option) {
  return `${String(option.distance_km).replace(".", ",")} km · ${option.duration_min} min · ${money(option.total_cost)} · ${String(option.amount).replace(".", ",")} ${esc(option.amount_unit)}`;
}

function canDispatch() {
  return !!state.user?.can_dispatch;
}

function canWrite() {
  return !!state.user?.can_write;
}

function canOpen(view) {
  const open = state.user?.views;
  return !Array.isArray(open) || !open.length || open.includes(view);
}

function vehicleBlock(incident) {
  if (state.replay || incident.status !== "aberto" || !canDispatch()) return "";
  const current = quoteIncident === incident.id ? quotes : null;
  const rows = current?.rows || [];
  const fastestId = current?.recommendation?.fastest_vehicle_id;
  const cheapId = current?.recommendation?.economical_vehicle_id;
  const sameVehicle = fastestId && fastestId === cheapId;
  return `
    <h3>Veículos e percursos</h3>
    <p class="hint">A comparação usa o consumo e o preço de cada veículo. O tempo é uma estimativa pelas vias, sem trânsito ao vivo.</p>
    <button type="button" class="primary" data-action="vehicle-compare" data-incident="${esc(incident.id)}" ${quoteLoading ? "disabled" : ""}>${quoteLoading ? "Calculando…" : "Calcular rotas"}</button>
    ${quoteIncident === incident.id && quoteError ? `<p class="hint">${esc(quoteError)}</p>` : ""}
    ${current ? `<p class="hint">${esc(current.note || "")}</p>` : ""}
    ${sameVehicle ? `<p>O mesmo veículo reúne o menor tempo e o menor custo nesta consulta.</p>` : ""}
    ${rows.map((row) => {
      const same = row.same_route;
      const fastest = row.fastest;
      const cheap = row.economical;
      return `
        <article class="team">
          <span><b>${esc(row.vehicle.name)}</b> · ${esc(row.vehicle.type)}<br>${esc(row.origin_note)}</span>
          <p class="hint">${esc(row.profile_note || "")}</p>
          ${same
            ? `<p>Único percurso devolvido: ${optionLine(fastest)}</p>
               <div class="actions">
                 <button type="button" class="ghost" data-action="vehicle-pick" data-vehicle="${esc(row.vehicle.id)}" data-choice="rapida">Ver no mapa</button>
                 <button type="button" class="primary" data-action="vehicle-go" data-incident="${esc(incident.id)}" data-vehicle="${esc(row.vehicle.id)}" data-choice="rapida" data-name="${esc(row.vehicle.name)}">Despachar</button>
               </div>`
            : `<p>Mais rápida: ${optionLine(fastest)}</p>
               <p>Mais econômica: ${optionLine(cheap)}</p>
               <div class="actions">
                 <button type="button" class="ghost" data-action="vehicle-pick" data-vehicle="${esc(row.vehicle.id)}" data-choice="rapida">Ver a mais rápida</button>
                 <button type="button" class="ghost" data-action="vehicle-pick" data-vehicle="${esc(row.vehicle.id)}" data-choice="economica">Ver a mais econômica</button>
                 <button type="button" class="primary" data-action="vehicle-go" data-incident="${esc(incident.id)}" data-vehicle="${esc(row.vehicle.id)}" data-choice="rapida" data-name="${esc(row.vehicle.name)}">Despachar a mais rápida</button>
                 <button type="button" class="primary" data-action="vehicle-go" data-incident="${esc(incident.id)}" data-vehicle="${esc(row.vehicle.id)}" data-choice="economica" data-name="${esc(row.vehicle.name)}">Despachar a mais econômica</button>
               </div>`}
        </article>`;
    }).join("")}
    ${(current?.failures || []).map((item) => `<p class="hint">${esc(item.name)}: ${esc(item.error)}</p>`).join("")}`;
}

function incidentDetail(incident) {
  const assigned = incident.assigned_name
    ? `${esc(incident.assigned_team)} · ${esc(incident.assigned_name)} → ocorrência ${esc(incident.number)}`
    : "Nenhuma equipe atribuída";
  let actions = "";
  if (!state.replay && incident.status === "aberto") {
    actions = `
      <h3>Equipes candidatas</h3>
      <ul class="teams">
        ${(incident.nearby || []).map((team) => `
          <li class="team${team.recommended ? " is-recommended" : ""}">
            <span><b>${esc(team.team)}</b>${team.recommended ? " · recomendada" : ""}${team.stale ? " · disponibilidade não confirmada" : ""}<br>${esc(team.name)} · ${esc(team.specialty || "")}</span>
            ${canDispatch() ? `<button type="button" class="primary" data-action="dispatch" data-incident="${esc(incident.id)}" data-agent="${esc(team.id)}" data-team="${esc(team.team)}">Atribuir</button>` : ""}
            <span>${esc(String(team.km).replace(".", ","))} km · ETA ${team.eta_min} min · ${esc(team.duty_label)} · sinal ${esc(team.signal || "atualizado")}</span>
            <p class="hint">${esc(team.reason || "")}</p>
            <p class="hint">Se enviar esta equipe: ${esc(team.impact || "")}</p>
          </li>`).join("") || "<li>Nenhuma equipe livre neste turno.</li>"}
      </ul>`;
  } else if (!state.replay && incident.assigned_agent_id && incident.status !== "encerrada" && (canDispatch() || state.user?.role === "agente")) {
    actions = `
      <div class="actions">
        ${incident.status === "em_deslocamento" ? `<button type="button" class="primary" data-action="advance" data-id="${esc(incident.id)}" data-step="chegou">Chegou</button>` : ""}
        ${incident.status === "no_local" || incident.status === "em_deslocamento" ? `<button type="button" class="primary" data-action="advance" data-id="${esc(incident.id)}" data-step="iniciar">Registrar atendimento</button>` : ""}
        <button type="button" class="ghost" data-action="advance" data-id="${esc(incident.id)}" data-step="finalizar">Finalizar</button>
        ${canOpen("campo") ? `<button type="button" class="ghost" data-action="field-open" data-id="${esc(incident.assigned_agent_id)}">Modo campo</button>` : ""}
      </div>
      <label class="field">Nota do atendimento<textarea id="desk-note" rows="2"></textarea></label>`;
  }
  return `
    <article class="detail">
      <h2>${esc(incident.title)}</h2>
      <p class="meta">Ocorrência ${esc(incident.number)} · ${esc(incident.priority_label)}</p>
      <dl class="facts">
        <dt>Local</dt><dd>${esc(incident.street)} · ${esc(incident.reference)}</dd>
        <dt>Região</dt><dd>${esc(incident.region)}</dd>
        <dt>Tipo</dt><dd>${esc(incident.kind_label)}</dd>
        <dt>Prioridade</dt><dd>${pill(incident.priority)}</dd>
        <dt>Horário</dt><dd>${esc(clockLabel(incident.at))}</dd>
        <dt>Status</dt><dd>${pill(incident.status)}</dd>
        <dt>Equipe</dt><dd>${assigned}</dd>
      </dl>
      ${incident.route?.road
        ? `<p>${esc(incident.route.label)}. ${String(incident.route.distance_km).replace(".", ",")} km pelas vias, cerca de ${incident.route.eta_min} min.${incident.route.total_cost != null ? ` Custo estimado ${money(incident.route.total_cost)}.` : ""} ${esc(incident.route.traffic_note || incident.route.origin_note || "")}</p>`
        : incident.route ? `<p>${esc(incident.route.label)}. Sem geometria viária para desenhar.${incident.route.road_error ? ` ${esc(incident.route.road_error)}` : ""}</p>` : ""}
      <p>${esc(incident.detail)}</p>
      ${incident.response ? `<h3>Tempo de resposta</h3><p>Total ${incident.response.total_min ?? "–"} min. Despacho ${incident.response.dispatch_min ?? "–"} min, deslocamento ${incident.response.travel_min ?? "–"} min, atendimento ${incident.response.service_min ?? "–"} min.</p><p>${esc(incident.response.compare || "")}</p><button type="button" class="ghost" data-action="jump" data-jump="closed">Ver ocorrências encerradas</button>` : ""}
      ${actions}
      ${vehicleBlock(incident)}
      ${incident.status !== "encerrada" && incident.playbook?.length ? `<h3>Procedimento</h3><ol class="steps">${incident.playbook.map((step) => `<li>${esc(step)}</li>`).join("")}</ol>` : ""}
      <div class="actions">
        ${state.crisis === incident.id
          ? `<button type="button" class="ghost" data-action="crisis-exit">Sair do modo crise</button>`
          : `<button type="button" class="ghost" data-action="crisis" data-id="${esc(incident.id)}">Modo crise</button>`}
      </div>
      <h3>Linha do tempo</h3>
      <ul class="timeline">
        ${(incident.timeline || []).map((event) => `<li><time>${esc(clockLabel(event.at))}</time>${esc(event.text)}</li>`).join("")}
      </ul>
    </article>`;
}

function impactOf(eq) {
  const peers = (state.bootstrap.equipment || []).filter((item) => item.region === eq.region && item.type === eq.type && item.id !== eq.id && item.status === "operacional");
  if (!peers.length) return "A região perde este tipo de cobertura e não há equipamento equivalente operacional por perto. Impacto alto.";
  return `Há ${peers.length} equipamento(s) do mesmo tipo operando na região. O impacto é menor.`;
}

function equipmentDetail(eq) {
  return `
    <article class="detail">
      <h2>${esc(eq.serial)}</h2>
      <p class="meta">${esc(eq.type_label)}</p>
      <p>${esc(eq.brand)} ${esc(eq.model)}</p>
      <dl class="facts">
        <dt>Status</dt><dd>${pill(eq.status)}</dd>
        <dt>Local</dt><dd>${esc(eq.street)}, ${esc(eq.neighborhood)} · ${esc(eq.reference)}</dd>
        <dt>Região</dt><dd>${esc(eq.region)} · ${esc(eq.city)}/${esc(eq.uf)}</dd>
        <dt>Órgão</dt><dd>${esc(eq.agency)}</dd>
        <dt>Último sinal</dt><dd>${esc(ago(eq.last_seen, state.bootstrap.clock))}</dd>
        <dt>Manutenção</dt><dd>${esc(eq.next_maintenance || "sem data")}</dd>
        <dt>Se parar</dt><dd>${esc(impactOf(eq))}</dd>
      </dl>
      ${canWrite() && canOpen("inventario") ? `<div class="actions">
        <button type="button" class="ghost" data-action="edit" data-kind="equipment" data-id="${esc(eq.id)}">Editar cadastro</button>
        <button type="button" class="primary" data-action="schedule" data-id="${esc(eq.id)}">Agendar manutenção</button>
      </div>` : ""}
      <h3>Histórico</h3>
      ${(eq.history || []).length ? `<ul class="timeline">${eq.history.map((event) => `<li><time>${esc(clockLabel(event.at))}</time>${esc(event.text)}</li>`).join("")}</ul>` : "<p class='hint'>Sem eventos registrados além do estado atual.</p>"}
    </article>`;
}

function agentDetail(agent) {
  const mission = agent.mission
    ? `Ocorrência atribuída`
    : "Sem missão";
  return `
    <article class="detail">
      <h2>${esc(agent.name)}</h2>
      <p class="meta">${esc(agent.team)} · ${esc(agent.registration)}</p>
      <dl class="facts">
        <dt>Situação</dt><dd>${pill(agent.duty)}</dd>
        <dt>Órgão</dt><dd>${esc(agent.agency)}</dd>
        <dt>Função</dt><dd>${esc(agent.role)}</dd>
        <dt>Turno</dt><dd>${esc(agent.shift)}</dd>
        <dt>Região</dt><dd>${esc(agent.region)}</dd>
        <dt>Missão</dt><dd>${esc(mission)}</dd>
        <dt>Atualização</dt><dd>${esc(ago(agent.last_seen, state.bootstrap.clock))}${agent.stale ? " · disponibilidade não confirmada" : ""}</dd>
      </dl>
      ${agent.plan ? `<p>Rota ${esc(agent.plan.status || "planejada")}: ${agent.plan.stops.length} pontos, ${String(agent.plan.distance_km).replace(".", ",")} km, cerca de ${agent.plan.duration_min} min. ${esc(agent.plan.traffic_note || "")}</p>` : ""}
      <div class="actions">
        ${canOpen("campo") ? `<button type="button" class="primary" data-action="field-open" data-id="${esc(agent.id)}">Modo campo</button>` : ""}
        ${canOpen("rotas") && canDispatch() ? `<button type="button" class="ghost" data-action="open-route" data-agent="${esc(agent.id)}" data-region="${esc(agent.region)}">Criar rota</button>` : ""}
        ${canWrite() && canOpen("agentes") ? `<button type="button" class="ghost" data-action="edit" data-kind="agent" data-id="${esc(agent.id)}">Editar cadastro</button>` : ""}
      </div>
    </article>`;
}

function regionDetail(region) {
  return `
    <article class="detail">
      <h2>${esc(region.region)}</h2>
      <p class="meta">${esc(region.city)}</p>
      <p class="state state-${esc(region.state)}">${esc(region.state_label)}</p>
      <dl class="facts">
        <dt>Ocorrências</dt><dd>${region.incidents_open}</dd>
        <dt>Equipes livres</dt><dd>${region.agents_free}</dd>
        <dt>Equipamentos fora</dt><dd>${region.equipment_down}</dd>
        <dt>Demanda</dt><dd>${esc(region.trend)}</dd>
        <dt>Capacidade</dt><dd>${esc(region.capacity || "")} · ${region.incidents_open} ocorrência(s), ${region.agents_free} equipe(s)</dd>
        <dt>Cobertura</dt><dd>${esc(region.cover || "")}</dd>
        <dt>Observação</dt><dd>${region.visibility === "baixa" ? "Esta região possui baixa capacidade de observação." : esc(region.visibility || "")}</dd>
        <dt>IPO desta hora</dt><dd>${region.ipo}</dd>
      </dl>
      <div class="actions">
        <button type="button" class="primary" data-action="filter-region" data-region="${esc(region.region)}">Filtrar mapa</button>
        ${canOpen("ocorrencias") ? `<button type="button" class="ghost" data-action="jump-region" data-region="${esc(region.region)}">Ocorrências da região</button>` : ""}
        ${canOpen("rotas") && canDispatch() ? `<button type="button" class="ghost" data-action="open-route" data-region="${esc(region.region)}">Criar rota</button>` : ""}
        <button type="button" class="ghost" data-action="clear-region">Ver a operação</button>
      </div>
    </article>`;
}
