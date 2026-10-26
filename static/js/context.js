import { ago, clockLabel, esc, pill } from "./format.js";
import { state } from "./state.js";

const TILES = "https://tile.openstreetmap.org/{z}/{x}/{y}.png";
let mini;

const DEST = {
  incident: "ocorrencias",
  agent: "agentes",
  equipment: "inventario",
  region: "regioes",
  vehicle: "frota",
  route: "rotas",
};

export function homeFor(kind) {
  return DEST[kind] || "cco";
}

export function destroy() {
  mini?.remove();
  mini = null;
}

export function visible() {
  return Boolean(state.selected && !["cco", "campo", "linha"].includes(state.view));
}

export function sync() {
  const node = document.getElementById("dock");
  const shell = document.getElementById("shell");
  if (!node || !shell) return;
  const on = visible();
  shell.classList.toggle("has-dock", on);
  node.hidden = !on;
  if (!on) {
    destroy();
    node.innerHTML = "";
    return;
  }
  const card = describe(state.selected);
  if (!card) {
    state.selected = null;
    sync();
    return;
  }
  node.innerHTML = card.html;
  draw(card);
}

function describe(selected) {
  const data = state.bootstrap;
  if (!data) return null;
  if (selected.kind === "agent") return agentCard(data.agents.find((item) => item.id === selected.id));
  if (selected.kind === "vehicle") return vehicleCard(data.vehicles?.find((item) => item.id === selected.id));
  if (selected.kind === "equipment") return equipmentCard(data.equipment.find((item) => item.id === selected.id));
  if (selected.kind === "region") return regionCard(data.regions.find((item) => item.id === selected.id || item.region === selected.id));
  if (selected.kind === "incident") return incidentCard(data.incidents.find((item) => item.id === selected.id));
  if (selected.kind === "route") return routeCard(selected.id);
  return null;
}

function shell(title, meta, facts, links, extra, map) {
  return {
    html: `
      <article class="dock-card">
        <header class="dock-head">
          <h2>${esc(title)}</h2>
          <button type="button" class="ghost" data-action="close-dock">Fechar</button>
        </header>
        <p class="meta">${meta}</p>
        <dl class="facts">${facts}</dl>
        ${extra || ""}
        <div class="actions">${links}</div>
        <div id="dock-map" class="dock-map" role="application" aria-label="Mapa deste registro"></div>
      </article>`,
    map,
  };
}

function fact(label, value) {
  return `<dt>${esc(label)}</dt><dd>${value}</dd>`;
}

function link(kind, id, label) {
  if (!id) return "";
  return `<button type="button" class="ghost" data-action="open-record" data-kind="${esc(kind)}" data-id="${esc(id)}">${esc(label)}</button>`;
}

function mapButton(kind, id) {
  return `<button type="button" class="ghost" data-action="show-on-map" data-kind="${esc(kind)}" data-id="${esc(id)}">Ver no mapa sinóptico</button>`;
}

function agentCard(agent) {
  if (!agent) return null;
  const data = state.bootstrap;
  const vehicle = (data.vehicles || []).find((item) => item.agent_id === agent.id)
    || (data.vehicles || []).find((item) => item.incident_id && item.incident_id === agent.mission?.incident_id);
  const incident = agent.mission && data.incidents.find((item) => item.id === agent.mission.incident_id);
  const events = (data.events || []).filter((item) => item.agent_id === agent.id).slice(0, 3);
  const last = events[0];
  const routeName = agent.route?.label || (agent.plan ? `Rota ${agent.plan.status || "planejada"}` : "Sem rota");
  return shell(
    agent.name,
    `${esc(agent.team)} · ${esc(agent.duty_label)}`,
    [
      fact("Equipe", esc(agent.team)),
      fact("Status", pill(agent.duty)),
      fact("Região", esc(agent.region)),
      fact("Última atividade", esc(ago(agent.last_seen, data.clock))),
      fact("Veículo", vehicle ? esc(vehicle.name) : "Nenhum veículo vinculado"),
      fact("Rota", esc(routeName)),
      fact("Último evento", last ? esc(`${last.label} · ${clockLabel(last.at)}`) : "Nenhum registro de jornada"),
    ].join(""),
    [
      link("region", agent.region, "Ver região"),
      vehicle ? link("vehicle", vehicle.id, "Ver veículo") : "",
      incident ? link("incident", incident.id, "Ver ocorrência") : "",
      agent.plan?.road || agent.route?.road ? link("route", `${agent.id}:${agent.route?.road ? "live" : "plan"}`, "Ver rota") : "",
      mapButton("agent", agent.id),
    ].join(""),
    `<div class="actions">
      <button type="button" class="ghost" data-action="mark-event" data-kind="entrada" data-id="${esc(agent.id)}">Entrada</button>
      <button type="button" class="ghost" data-action="mark-event" data-kind="intervalo" data-id="${esc(agent.id)}">Intervalo</button>
      <button type="button" class="ghost" data-action="mark-event" data-kind="retorno" data-id="${esc(agent.id)}">Retorno</button>
      <button type="button" class="ghost" data-action="mark-event" data-kind="saida" data-id="${esc(agent.id)}">Saída</button>
    </div>
    <p class="hint">A jornada fica no histórico e no mapa só depois do registro. A localização usada é a deste agente agora.</p>`,
    pointsOf(agent.lat, agent.lng, agent.route?.road ? agent.route.polyline : agent.plan?.road ? agent.plan.polyline : null),
  );
}

function vehicleCard(vehicle) {
  if (!vehicle) return null;
  const data = state.bootstrap;
  const agent = data.agents.find((item) => item.id === vehicle.agent_id)
    || data.agents.find((item) => item.mission?.incident_id && item.mission.incident_id === vehicle.incident_id);
  const incident = vehicle.incident_id && data.incidents.find((item) => item.id === vehicle.incident_id);
  const perKm = Number(vehicle.consumption) > 0
    ? (Number(vehicle.fuel_price) / Number(vehicle.consumption) + Number(vehicle.other_cost_per_km || 0))
    : null;
  return shell(
    vehicle.name,
    `${esc(vehicle.plate || "sem placa")} · ${esc(statusLabel(vehicle.status))}`,
    [
      fact("Tipo", esc(vehicle.type)),
      fact("Marca", `${esc(vehicle.brand)} ${esc(vehicle.model)}`),
      fact("Status", esc(statusLabel(vehicle.status))),
      fact("Base", esc(vehicle.base_region)),
      fact("Onde está", esc(vehicle.location_source === "atual" ? "Localização atual" : "Base cadastrada")),
      fact("Responsável", esc(vehicle.responsible || "Sem responsável cadastrado")),
      fact("Equipe", agent ? esc(agent.team) : "Sem equipe vinculada"),
      fact("Rota", incident?.route?.label ? esc(incident.route.label) : "Sem rota em andamento"),
      fact("Km atual", vehicle.odometer_km != null ? esc(String(vehicle.odometer_km).replace(".", ",")) : "Não informado"),
      fact("Custo por km", perKm != null ? perKm.toLocaleString("pt-BR", { style: "currency", currency: "BRL" }) : "Sem consumo"),
    ].join(""),
    [
      agent ? link("agent", agent.id, "Ver agente") : "",
      link("region", vehicle.base_region, "Ver região"),
      incident ? link("incident", incident.id, "Ver ocorrência") : "",
      mapButton("vehicle", vehicle.id),
    ].join(""),
    `<p class="hint">${esc(vehicle.notes || "Sem observações.")} Velocidade não é medida neste cadastro.</p>`,
    pointsOf(vehicle.lat, vehicle.lng, incident?.route?.road ? incident.route.polyline : null),
  );
}

function equipmentCard(item) {
  if (!item) return null;
  return shell(
    item.serial,
    esc(item.type_label || item.type),
    [
      fact("Status", pill(item.status)),
      fact("Local", esc(`${item.street}, ${item.neighborhood}`)),
      fact("Região", esc(item.region)),
      fact("Órgão", esc(item.agency || "")),
      fact("Manutenção", esc(item.next_maintenance || item.maintenance_need || "sem data")),
    ].join(""),
    [link("region", item.region, "Ver região"), mapButton("equipment", item.id)].join(""),
    "",
    pointsOf(item.lat, item.lng, null),
  );
}

function regionCard(region) {
  if (!region) return null;
  const data = state.bootstrap;
  const agents = data.agents.filter((item) => item.region === region.region);
  const vehicles = (data.vehicles || []).filter((item) => item.base_region === region.region);
  const routes = data.agents.filter((item) => item.region === region.region && (item.route?.road || item.plan?.road));
  const meta = (data.schema?.regions || []).find((item) => item.id === region.region);
  return shell(
    region.region,
    esc(region.city || meta?.city || ""),
    [
      fact("Situação", esc(region.state_label)),
      fact("Cidade", esc(meta ? `${meta.city}/${meta.uf}` : region.city || "")),
      fact("CEP", "Sem CEP cadastrado"),
      fact("Agentes", String(agents.length)),
      fact("Veículos", String(vehicles.length)),
      fact("Rotas no mapa", String(routes.length)),
      fact("Ocorrências abertas", String(region.incidents_open)),
      fact("Responsável", "Sem responsável cadastrado"),
    ].join(""),
    [
      link("agent", agents[0]?.id, agents[0] ? `Agente ${agents[0].name}` : ""),
      vehicles[0] ? link("vehicle", vehicles[0].id, vehicles[0].name) : "",
      mapButton("region", region.region),
    ].join(""),
    `<p class="hint">${esc(region.cover || "")}. ${region.blind ? "Baixa capacidade de observação." : "Há observação nesta região."}</p>`,
    {
      lat: region.lat,
      lng: region.lng,
      path: null,
      extra: [
        ...agents.slice(0, 8).map((item) => ({ lat: item.lat, lng: item.lng, color: "#1d4e89" })),
        ...vehicles.slice(0, 8).map((item) => ({ lat: item.lat, lng: item.lng, color: "#1b6b45" })),
      ],
    },
  );
}

function incidentCard(incident) {
  if (!incident) return null;
  const vehicle = (state.bootstrap.vehicles || []).find((item) => item.id === incident.assigned_vehicle_id || item.incident_id === incident.id);
  return shell(
    incident.title,
    `Ocorrência ${esc(incident.number)} · ${esc(incident.priority_label)}`,
    [
      fact("Status", pill(incident.status)),
      fact("Quando", esc(clockLabel(incident.at))),
      fact("Local", esc(incident.street)),
      fact("Região", esc(incident.region)),
      fact("Equipe", esc(incident.assigned_team || "Sem equipe")),
      fact("Agente", esc(incident.assigned_name || "Sem agente")),
      fact("Veículo", vehicle ? esc(vehicle.name) : "Sem veículo"),
    ].join(""),
    [
      incident.assigned_agent_id ? link("agent", incident.assigned_agent_id, "Ver agente") : "",
      vehicle ? link("vehicle", vehicle.id, "Ver veículo") : "",
      link("region", incident.region, "Ver região"),
      incident.route?.road ? link("route", `${incident.assigned_agent_id}:live`, "Ver rota") : "",
      mapButton("incident", incident.id),
    ].join(""),
    incident.route?.road
      ? `<p class="hint">${esc(String(incident.route.distance_km).replace(".", ","))} km pelas vias, cerca de ${incident.route.eta_min} min.</p>`
      : `<p class="hint">${esc(incident.detail || "")}</p>`,
    pointsOf(incident.lat, incident.lng, incident.route?.road ? incident.route.polyline : null),
  );
}

function routeCard(id) {
  const [agentId, mode] = String(id).split(":");
  const agent = state.bootstrap.agents.find((item) => item.id === agentId);
  if (!agent) return null;
  const source = mode === "plan" ? agent.plan : agent.route;
  if (!source?.road || !source.polyline || source.polyline.length < 3) return null;
  const vehicle = (state.bootstrap.vehicles || []).find((item) => item.id === source.vehicle_id || item.agent_id === agent.id);
  const stops = source.stops?.length || source.steps?.length || 0;
  return shell(
    source.label || agent.team,
    mode === "plan" ? "Rota planejada" : "Rota em andamento",
    [
      fact("Status", mode === "plan" ? esc(source.status || "planejada") : "Em andamento"),
      fact("Equipe", esc(agent.team)),
      fact("Agente", esc(agent.name)),
      fact("Veículo", vehicle ? esc(`${vehicle.name} · ${vehicle.plate || ""}`) : "Sem veículo vinculado"),
      fact("Região", esc(agent.region)),
      fact("Distância", `${String(source.distance_km).replace(".", ",")} km`),
      fact("Tempo estimado", `${source.duration_min || source.eta_min || "–"} min`),
      fact("Paradas", String(stops)),
    ].join(""),
    [
      link("agent", agent.id, "Ver agente"),
      vehicle ? link("vehicle", vehicle.id, "Ver veículo") : "",
      link("region", agent.region, "Ver região"),
      mapButton("route", id),
    ].join(""),
    `<p class="hint">${esc(source.traffic_note || source.profile_note || "Tempo estimado pelas vias. Sem trânsito ao vivo.")}</p>`,
    pointsOf(source.polyline[0][0], source.polyline[0][1], source.polyline),
  );
}

function pointsOf(lat, lng, path) {
  return { lat, lng, path: path && path.length >= 3 ? path : null, extra: [] };
}

function statusLabel(status) {
  return {
    disponivel: "Em operação",
    em_atendimento: "Em atendimento",
    parado: "Parado",
    em_manutencao: "Em manutenção",
    indisponivel: "Indisponível",
  }[status] || status || "";
}

function draw(card) {
  destroy();
  const node = document.getElementById("dock-map");
  const spot = card.map;
  if (!node || !window.L || spot?.lat == null) return;
  mini = L.map(node, { zoomControl: false, attributionControl: false }).setView([spot.lat, spot.lng], 14);
  L.tileLayer(TILES, { maxZoom: 19 }).addTo(mini);
  const bounds = [];
  L.circleMarker([spot.lat, spot.lng], { radius: 7, color: "#1b6b45", weight: 2 }).addTo(mini);
  bounds.push([spot.lat, spot.lng]);
  if (spot.path) {
    const line = L.polyline(spot.path, { color: "#1b6b45", weight: 4 }).addTo(mini);
    bounds.push(...spot.path);
    mini.fitBounds(line.getBounds(), { padding: [16, 16] });
  }
  for (const mark of spot.extra || []) {
    if (mark.lat == null) continue;
    L.circleMarker([mark.lat, mark.lng], { radius: 5, color: mark.color, weight: 2 }).addTo(mini);
    bounds.push([mark.lat, mark.lng]);
  }
  if (!spot.path && bounds.length > 1) mini.fitBounds(bounds, { padding: [16, 16] });
  setTimeout(() => mini?.invalidateSize(), 40);
}
