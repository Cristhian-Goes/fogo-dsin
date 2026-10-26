import { api } from "./api.js";
import { clockLabel, esc, pill } from "./format.js";
import * as routes from "./routes.js";
import { state } from "./state.js";

let fieldMap;
let routeMap;
let routeAgentId = "";
let routeStops = [];
let routeRegion = "";

const FILTERS = [
  ["todas", "Todas"],
  ["criticas", "Críticas"],
  ["alta", "Alta"],
  ["media", "Média"],
  ["baixa", "Baixa"],
  ["atendimento", "Em atendimento"],
  ["aguardando", "Aguardando equipe"],
  ["encerradas", "Encerradas"],
];

export function destroy() {
  fieldMap?.remove();
  routeMap?.remove();
  fieldMap = null;
  routeMap = null;
}

export function mountOcorrencias(main) {
  const rows = state.bootstrap.incidents.filter(matchIncident).sort((a, b) => (b.queue_score || 0) - (a.queue_score || 0));
  const filterLabel = FILTERS.find(([id]) => id === state.incidentFilter)?.[1] || "Todas";
  main.innerHTML = `
    <section class="page">
      <p class="crumb"><button type="button" data-action="go" data-view="cco">Visão geral</button> / Ocorrências · ${esc(filterLabel)}${state.region ? ` · ${esc(state.region)}` : ""}</p>
      <h1>Ocorrências</h1>
      <p class="hint">${rows.length} registro(s) neste filtro. A linha abre o resumo ao lado. O mapa sinóptico fica para quando você pedir.</p>
      ${state.region ? `<p class="hint">Contexto territorial: ${esc(state.region)}. <button type="button" class="ghost" data-action="clear-region">Limpar região</button></p>` : ""}
      <div class="filters" role="tablist">
        ${FILTERS.map(([id, label]) => `<button type="button" data-action="incident-filter" data-filter="${id}" class="${state.incidentFilter === id ? "is-on" : ""}">${label}</button>`).join("")}
      </div>
      <ul class="rows">
        ${rows.map((item) => `
          <li><button type="button" class="row" data-action="select" data-kind="incident" data-id="${esc(item.id)}">
            <b>${esc(item.number)} · ${esc(item.priority_label)} · ${esc(item.kind_label)}</b>
            <span>${esc(item.title)}</span>
            <small>${esc(item.street)}, ${esc(item.region)} · ${esc(clockLabel(item.at))} · ${esc(item.assigned_team || "sem equipe")} · ${esc(item.status_label)}</small>
          </button></li>`).join("") || "<li>Nenhuma ocorrência neste filtro. Troque o filtro ou limpe a região.</li>"}
      </ul>
    </section>`;
}

export function mountAgentes(main) {
  const agents = [...state.bootstrap.agents]
    .filter((agent) => !state.region || agent.region === state.region || agent.base_region === state.region)
    .filter((agent) => {
      if (state.agentFilter === "disponivel") return agent.duty === "disponivel";
      if (state.agentFilter === "missao") return agent.duty === "em_deslocamento" || agent.duty === "em_atendimento";
      return true;
    })
    .sort((a, b) => a.duty.localeCompare(b.duty) || a.name.localeCompare(b.name));
  const filters = [["todos", "Todos"], ["disponivel", "Disponíveis"], ["missao", "Em missão"]];
  main.innerHTML = `
    <section class="page">
      <p class="crumb"><button type="button" data-action="go" data-view="cco">Visão geral</button> / Agentes</p>
      <h1>Agentes</h1>
      <p class="hint">${agents.length} pessoa(s) neste filtro. A linha abre o perfil ao lado, com a localização deste agente.</p>
      <div class="filters">
        ${filters.map(([id, label]) => `<button type="button" data-action="agent-filter" data-filter="${id}" class="${state.agentFilter === id ? "is-on" : ""}">${label}</button>`).join("")}
      </div>
      <ul class="rows">
        ${agents.map((agent) => `
          <li><button type="button" class="row" data-action="select" data-kind="agent" data-id="${esc(agent.id)}">
            <b>${esc(agent.name)} · ${esc(agent.duty_label)}</b>
            <small>${esc(agent.registration)} · ${esc(agent.team)} · ${esc(agent.agency)} · ${esc(agent.region)} · ${esc(agent.shift)}</small>
            <small>${agent.stale ? "Disponibilidade não confirmada" : "Sinal recente"} · ${agent.mission ? "Missão em andamento" : "Sem missão"}</small>
          </button></li>`).join("") || "<li>Nenhum agente neste filtro.</li>"}
      </ul>
    </section>`;
}

export function mountRegioes(main) {
  main.innerHTML = `
    <section class="page">
      <h1>Regiões</h1>
      <p class="hint">Abra a região para ver agentes, veículos e ocorrências. O mapa sinóptico só entra quando você pedir.</p>
      <div class="region-board">
        ${state.bootstrap.regions.map((region) => `
          <article class="region-card">
            <h2>${esc(region.region)}</h2>
            <p class="state state-${esc(region.state)}">${esc(region.state_label)}</p>
            <p>${region.incidents_open} ocorrência(s) aberta(s)</p>
            <p>${region.agents_free} equipe(s) disponível(is)</p>
            <p>${region.equipment_down} equipamento(s) indisponível(is)</p>
            <p>${region.cover || ""} · capacidade ${esc(region.capacity || "")}</p>
            ${region.blind ? "<p>Baixa capacidade de observação.</p>" : ""}
            <button type="button" class="primary" data-action="select" data-kind="region" data-id="${esc(region.region)}">Abrir região</button>
            <button type="button" class="ghost" data-action="jump-region" data-region="${esc(region.region)}">Ocorrências</button>
            <button type="button" class="ghost" data-action="open-route" data-region="${esc(region.region)}">Criar rota</button>
          </article>`).join("")}
      </div>
    </section>`;
}

export function mountAlertas(main) {
  const alerts = state.bootstrap.alerts;
  main.innerHTML = `
    <section class="page">
      <h1>Alertas</h1>
      <p class="hint">Cada alerta abre o registro correspondente, com o mapa só daquele ponto.</p>
      <ul class="rows">
        ${alerts.map((alert) => `
          <li><button type="button" class="row" data-action="select" data-kind="${esc(alert.target_type)}" data-id="${esc(alert.target_id)}">
            <b>${esc(category(alert))} · ${esc(alert.title)}</b>
            <small>${esc(alert.detail)}</small>
          </button></li>`).join("") || "<li>Nenhum alerta aberto.</li>"}
      </ul>
    </section>`;
}

function category(alert) {
  if (alert.id.startsWith("an-")) return "Fora do padrão";
  if (alert.id.startsWith("cov-")) return "Equipe sobrecarregada";
  if (alert.target_type === "region") return "Região";
  if (alert.level === "critico" && alert.target_type === "incident") return "Ocorrência crítica";
  if (alert.target_type === "equipment") return alert.level === "critico" ? "Equipamento offline" : "Manutenção";
  return alert.level === "critico" ? "Crítico" : "Atenção";
}

export function mountLinha(main) {
  const rows = timelineRows();
  main.innerHTML = `
    <section class="page">
      <h1>Linha do tempo</h1>
      <p class="hint">Eventos reais da fita, da jornada e do histórico dos veículos. O clique abre o registro, não o mapa inteiro.</p>
      <div class="filters">
        <input id="time-q" type="search" placeholder="Agente, equipe, veículo ou região" />
        <select id="time-kind">
          <option value="">Todos os tipos</option>
          <option value="jornada">Jornada</option>
          <option value="fita">Fita operacional</option>
          <option value="veiculo">Veículo</option>
        </select>
      </div>
      <ul class="rows" id="time-rows"></ul>
    </section>`;
  const paint = () => {
    const text = document.getElementById("time-q").value.trim().toLowerCase();
    const kind = document.getElementById("time-kind").value;
    const shown = rows.filter((item) => (!kind || item.group === kind) && (!text || item.blob.includes(text))).slice(0, 80);
    document.getElementById("time-rows").innerHTML = shown.map((item) => `
      <li><button type="button" class="row" data-action="select" data-kind="${esc(item.kind)}" data-id="${esc(item.id)}">
        <b>${esc(clockLabel(item.at))}</b>
        <span>${esc(item.title)}</span>
        <small>${esc(item.meta)}</small>
      </button></li>`).join("") || "<li>Nenhum evento com esse filtro.</li>";
  };
  document.getElementById("time-q").addEventListener("input", paint);
  document.getElementById("time-kind").addEventListener("change", paint);
  paint();
}

function timelineRows() {
  const rows = [];
  for (const item of state.bootstrap.feed || []) {
    rows.push({ at: item.at, group: "fita", kind: "region", id: item.region, title: item.text, meta: item.region || "Operação", blob: `${item.text} ${item.region}`.toLowerCase() });
  }
  for (const item of state.bootstrap.events || []) {
    rows.push({ at: item.at, group: "jornada", kind: "agent", id: item.agent_id, title: `${item.agent_name} · ${item.label}`, meta: `${item.team} · ${item.region}`, blob: `${item.agent_name} ${item.team} ${item.region} ${item.label}`.toLowerCase() });
  }
  for (const vehicle of state.bootstrap.vehicles || []) {
    for (const item of vehicle.history || []) {
      rows.push({ at: item.at, group: "veiculo", kind: "vehicle", id: vehicle.id, title: item.text, meta: vehicle.name, blob: `${item.text} ${vehicle.name} ${vehicle.plate}`.toLowerCase() });
    }
  }
  return rows.sort((a, b) => String(b.at).localeCompare(String(a.at)));
}

export function mountRotas(main) {
  routeMap?.remove();
  routeMap = null;
  const records = routeRecords();
  const live = records.filter((item) => item.mode === "live").length;
  const planned = records.filter((item) => item.mode === "plan").length;
  const delayed = state.bootstrap.incidents.filter((item) => (item.response?.compare || "").includes("passou")).length;
  const withIncident = records.filter((item) => item.hasIncident).length;
  const agents = state.bootstrap.agents.filter((agent) => agent.duty !== "indisponivel");
  if (!routeAgentId && agents[0]) routeAgentId = agents[0].id;
  const agent = state.bootstrap.agents.find((item) => item.id === routeAgentId);
  const choices = routeChoices();
  main.innerHTML = `
    <div id="day-board"></div>
    <section class="page">
      <h1>Rotas</h1>
      <p class="hint">Em andamento ${live} · Planejadas ${planned} · Encerradas com atraso registrado ${delayed} · Com ocorrência ${withIncident}. Só entram percursos com geometria viária.</p>
      <ul class="rows">
        ${records.map((item) => `
          <li><button type="button" class="row" data-action="select" data-kind="route" data-id="${esc(item.id)}">
            <b>${esc(item.name)} · ${esc(item.status)}</b>
            <span>${esc(item.team)} · ${esc(item.agent)} · ${esc(item.vehicle)}</span>
            <small>${esc(item.region)} · ${String(item.km).replace(".", ",")} km · ${item.minutes} min · ${item.stops} parada(s)</small>
          </button></li>`).join("") || "<li>Nenhuma rota viária neste momento. Gere uma sequência abaixo.</li>"}
      </ul>
      <h2>Nova sequência</h2>
      <p class="hint">Escolha a equipe e os destinos. Sem resposta do serviço em 3 s, a tela mostra uma estimativa aproximada e não trata o traço como rua.</p>
      ${routeRegion ? `<p class="hint">Origem sugerida pela região ${esc(routeRegion)}. Os pontos abaixo estão filtrados por ela.</p>` : ""}
      <div class="route-layout">
        <form id="route-form">
          <label class="field">Equipe
            <select name="agent" id="route-agent">
              ${agents.map((item) => `<option value="${esc(item.id)}" ${item.id === routeAgentId ? "selected" : ""}>${esc(item.team)} · ${esc(item.name)} · ${esc(item.duty_label)}</option>`).join("")}
            </select>
          </label>
          <fieldset>
            <legend>Pontos</legend>
            ${choices.map((item) => `
              <label class="check"><input type="checkbox" data-stop-kind="${esc(item.kind)}" data-stop-id="${esc(item.id)}" ${routeStops.some((stop) => stop.id === item.id) ? "checked" : ""}/> ${esc(item.label)}</label>`).join("")}
          </fieldset>
          <div class="actions">
            <button type="button" class="ghost" data-action="suggest-route">Rota de inspeção sugerida</button>
            <button type="button" class="primary" data-action="plan-route">Gerar sequência</button>
          </div>
          <div id="route-result">${routeResult(agent)}</div>
        </form>
        <div>
          <div id="route-map"></div>
          <p class="hint">O mapa desta tela mostra a rota da equipe selecionada, quando ela tiver geometria viária.</p>
        </div>
      </div>
    </section>`;
  const select = document.getElementById("route-agent");
  select?.addEventListener("change", () => {
    routeAgentId = select.value;
    const chosen = state.bootstrap.agents.find((item) => item.id === routeAgentId);
    routeStops = (chosen?.plan?.stops || []).map((stop) => ({ kind: stop.kind, id: stop.id }));
    mountRotas(main);
  });
  drawRouteMap(agent);
  routes.paint(document.getElementById("day-board"));
}

function routeRecords() {
  const rows = [];
  for (const agent of state.bootstrap.agents) {
    const vehicle = (state.bootstrap.vehicles || []).find((item) => item.agent_id === agent.id || (item.incident_id && item.incident_id === agent.mission?.incident_id));
    if (agent.route?.road && agent.route.polyline?.length >= 3) {
      rows.push({
        id: `${agent.id}:live`,
        mode: "live",
        name: agent.route.label || agent.team,
        status: "Em andamento",
        team: agent.team,
        agent: agent.name,
        vehicle: agent.route.vehicle_name || vehicle?.name || "Sem veículo vinculado",
        region: agent.region,
        km: agent.route.distance_km,
        minutes: agent.route.eta_min,
        stops: agent.route.steps?.length || 1,
        hasIncident: true,
      });
    }
    if (agent.plan?.road && agent.plan.polyline?.length >= 3) {
      rows.push({
        id: `${agent.id}:plan`,
        mode: "plan",
        name: `Rota de ${agent.name}`,
        status: agent.plan.status === "aprovada" ? "Confirmada" : "Planejada",
        team: agent.team,
        agent: agent.name,
        vehicle: vehicle?.name || "Sem veículo vinculado",
        region: agent.region,
        km: agent.plan.distance_km,
        minutes: agent.plan.duration_min,
        stops: agent.plan.stops?.length || 0,
        hasIncident: (agent.plan.stops || []).some((stop) => stop.kind === "incident"),
      });
    }
  }
  return rows;
}

function routeChoices() {
  const incidents = state.bootstrap.incidents
    .filter((item) => item.status !== "encerrada" && item.status !== "ciencia")
    .filter((item) => !routeRegion || item.region === routeRegion)
    .map((item) => ({ kind: "incident", id: item.id, label: `Ocorrência ${item.number} · ${item.street}` }));
  const equipment = state.bootstrap.equipment
    .filter((item) => ["radar", "camera", "balanca", "cancela", "totem"].includes(item.type))
    .filter((item) => item.status !== "operacional" || item.maintenance_flag)
    .filter((item) => !routeRegion || item.region === routeRegion)
    .map((item) => ({ kind: "equipment", id: item.id, label: `${item.serial} · ${item.street}` }));
  return [...incidents, ...equipment];
}

function routeResult(agent) {
  const plan = agent?.plan;
  if (!plan) return "<p class='hint'>Nenhuma rota gerada para esta equipe.</p>";
  const status = plan.status === "aprovada" ? "Aprovada" : "Planejada";
  return `
    <h2>${status} · ${plan.stops.length} pontos · ${String(plan.distance_km).replace(".", ",")} km · ${plan.duration_min} min</h2>
    <p class="hint">Origem: ${esc(plan.origin || agent.region)}. ${esc(plan.traffic_note || "Sem leitura de trânsito em tempo real.")} ${plan.approximate ? "estimativa aproximada" : ""} ${plan.comparison ? `Ingênua ${plan.comparison.naive_min} min, otimizada economiza ${plan.comparison.saved_min} min na mesma conta.` : ""}</p>
    <ol>
      ${plan.stops.map((stop, index) => `
        <li class="stop">
          <span>${stop.order}. ${esc(stop.label)} <small>(${String(stop.leg_km).replace(".", ",")} km)</small></span>
          <span>
            <button type="button" class="ghost" data-action="route-move" data-dir="-1" data-index="${index}">Subir</button>
            <button type="button" class="ghost" data-action="route-move" data-dir="1" data-index="${index}">Descer</button>
          </span>
        </li>`).join("")}
    </ol>
    ${plan.status === "aprovada" ? "" : `<button type="button" class="primary" data-action="confirm-route">Confirmar rota</button>`}
    <button type="button" class="ghost" data-action="clear-plan" data-id="${esc(agent.id)}">Remover rota</button>`;
}

function drawRouteMap(agent) {
  const node = document.getElementById("route-map");
  if (!node || !window.L) return;
  routeMap?.remove();
  routeMap = L.map(node, { zoomControl: false }).setView([-22.48, -50.15], 9);
  L.tileLayer("https://tile.openstreetmap.org/{z}/{x}/{y}.png", { maxZoom: 19, attribution: "&copy; OpenStreetMap" }).addTo(routeMap);
  if (agent) L.circleMarker([agent.lat, agent.lng], { radius: 6, color: "#1f4e79" }).addTo(routeMap).bindTooltip(agent.name);
  if (agent?.plan?.polyline?.length >= 2 && (agent.plan.road || agent.plan.approximate)) {
    const line = L.polyline(agent.plan.polyline, { color: agent.plan.approximate ? "#8a5a00" : "#1f4e79", dashArray: agent.plan.approximate ? "2 8" : "6 6" }).addTo(routeMap);
    routeMap.fitBounds(line.getBounds(), { padding: [20, 20] });
  }
  setTimeout(() => routeMap.invalidateSize(), 60);
}

export function suggestRoute() {
  const agent = state.bootstrap.agents.find((item) => item.id === routeAgentId);
  if (!agent) return [];
  return state.bootstrap.equipment
    .filter((item) => item.region === agent.base_region || item.region === agent.region)
    .filter((item) => ["radar", "camera", "balanca"].includes(item.type))
    .filter((item) => item.status !== "operacional" || item.maintenance_flag)
    .slice(0, 4)
    .map((item) => ({ kind: "equipment", id: item.id }));
}

export function checkedStops() {
  return [...document.querySelectorAll("[data-stop-id]:checked")].map((input) => ({
    kind: input.dataset.stopKind,
    id: input.dataset.stopId,
  }));
}

export function currentRouteAgent() {
  return document.getElementById("route-agent")?.value || routeAgentId;
}

export function rememberRoute(agentId, stops) {
  routeAgentId = agentId;
  routeStops = stops;
}

export function prepareRoute(options = {}) {
  routeRegion = options.region || "";
  if (options.agentId) routeAgentId = options.agentId;
  else if (routeRegion) {
    const local = state.bootstrap.agents.find((item) => item.region === routeRegion && item.duty === "disponivel");
    if (local) routeAgentId = local.id;
  }
  routeStops = options.stops || [];
}

export function currentPlan() {
  const agent = state.bootstrap.agents.find((item) => item.id === routeAgentId);
  if (!agent?.plan?.stops?.length) return null;
  return { agentId: agent.id, stops: agent.plan.stops.map((stop) => ({ kind: stop.kind, id: stop.id })) };
}

export function moveStop(index, dir) {
  const agent = state.bootstrap.agents.find((item) => item.id === routeAgentId);
  const stops = (agent?.plan?.stops || []).map((stop) => ({ kind: stop.kind, id: stop.id }));
  const next = index + dir;
  if (!stops.length || next < 0 || next >= stops.length) return null;
  const [item] = stops.splice(index, 1);
  stops.splice(next, 0, item);
  return { agentId: routeAgentId, stops };
}

export function mountHistorico(main) {
  main.innerHTML = `
    <section class="page">
      <h1>Histórico</h1>
      <p class="hint">Escolha um horário para ver o mapa como estava. A linha de baixo é a fita da cidade.</p>
      <div id="replay-list"><p>Carregando horários…</p></div>
      <h2>Fita</h2>
      <ul class="timeline">
        ${state.bootstrap.feed.map((item) => `<li><time>${esc(clockLabel(item.at))}</time>${esc(item.text)}</li>`).join("")}
      </ul>
      <h2>Exercitar a operação</h2>
      <div class="actions">
        <button type="button" class="ghost" data-action="scenario" data-scenario="acidente">Lançar sinistro</button>
        <button type="button" class="ghost" data-action="scenario" data-scenario="falha-radar">Pane de radar</button>
        <button type="button" class="ghost" data-action="scenario" data-scenario="furto">Furto de câmera</button>
        <button type="button" class="ghost" data-action="scenario" data-scenario="surto">Surto em Assis</button>
        <button type="button" class="ghost" data-action="scenario" data-scenario="silencio">Silêncio de sinal</button>
        <button type="button" class="ghost" data-action="scenario" data-scenario="chuva">E se chover forte</button>
        <button type="button" class="ghost" data-action="briefing">Resumo do turno</button>
        ${state.user?.can_admin ? `<button type="button" class="danger" data-action="reset">Restaurar demonstração</button>` : `<p class="hint">Restaurar a demonstração é uma ação do administrador geral.</p>`}
      </div>
    </section>`;
  api.replay().then((payload) => {
    const node = document.getElementById("replay-list");
    if (!node) return;
    const frames = [...(payload.frames || [])].reverse();
    node.innerHTML = `<div class="filters">${frames.map((frame) => `<button type="button" data-action="replay" data-at="${esc(frame.at)}">${esc(clockLabel(frame.at))}</button>`).join("")}</div>`;
  }).catch((error) => {
    const node = document.getElementById("replay-list");
    if (node) node.textContent = error.message;
  });
}

export function mountCampo(main) {
  fieldMap?.remove();
  fieldMap = null;
  const agents = state.bootstrap.agents.filter((agent) => agent.status !== "fora_de_servico");
  const agent = agents.find((item) => item.id === state.fieldAgentId) || null;
  if (!agent) {
    main.innerHTML = `
      <section class="mission">
        <h1>Modo campo</h1>
        <p>Escolha quem está na rua. A tela mostra só a missão.</p>
        <ul class="rows">
          ${agents.map((item) => `
            <li><button type="button" class="choice" data-action="field-open" data-id="${esc(item.id)}">
              <b>${esc(item.name)}</b>
              <small>${esc(item.team)} · ${esc(item.duty_label)} · ${esc(item.region)}</small>
            </button></li>`).join("")}
        </ul>
      </section>`;
    return;
  }
  const incident = agent.mission
    ? state.bootstrap.incidents.find((item) => item.id === agent.mission.incident_id)
    : null;
  main.innerHTML = `
    <section class="mission">
      <button type="button" class="ghost" data-action="field-clear">Trocar agente</button>
      <h1>${esc(agent.name)}</h1>
      <p class="meta">${esc(agent.team)} · ${esc(agent.registration)}</p>
      ${fieldRoute(agent)}
      <p>${pill(agent.duty)}</p>
      ${incident ? missionHtml(agent, incident) : `<p>Nenhuma missão atribuída. A central ainda não despachou esta equipe.</p><button type="button" class="primary big" data-action="select" data-kind="agent" data-id="${esc(agent.id)}">Ver minha posição</button>`}
    </section>`;
  if (incident) drawField(agent, incident);
}

function fieldRoute(agent) {
  const crew = (state.bootstrap.day_plan?.crews || []).find((item) => item.agent_id === agent.id && item.active !== false);
  const stop = (crew?.stops || []).find((item) => item.kind === "order") || crew?.stops?.[0];
  const emergency = `<button type="button" class="ghost big" data-action="safety-now" data-id="${esc(agent.id)}" data-mode="silent">Emergência</button>`;
  if (!stop) return emergency;
  const maps = crew.maps_url ? `<a class="ghost big" href="${esc(crew.maps_url)}" target="_blank" rel="noopener">Navegar</a>` : "";
  return `
    <h2>Próxima parada</h2>
    <p><b>${esc(stop.label)}</b></p>
    <p>ETA ${esc(stop.eta_label || "-")}${stop.late ? " · SLA em risco" : ""}</p>
    ${stop.kind === "order" ? `<button type="button" class="primary big" data-action="day-arrive" data-id="${esc(stop.id)}">Cheguei</button><button type="button" class="ghost big" data-action="day-done" data-id="${esc(stop.id)}">Concluir</button>` : ""}
    ${maps}
    ${emergency}`;
}

function missionHtml(agent, incident) {
  const step = incident.status;
  return `
    <h2>Minha missão</h2>
    <p><b>${esc(incident.title)}</b></p>
    <p>${esc(incident.street)} · ${esc(incident.reference)} · ${esc(incident.region)}</p>
    <p>Ocorrência ${esc(incident.number)} · ${esc(incident.priority_label)} · ${esc(clockLabel(incident.at))}</p>
    <ol class="steps">
      ${stepItem("Missão recebida", true)}
      ${stepItem("A caminho", step === "em_deslocamento", step !== "aberto")}
      ${stepItem("No local", step === "no_local", ["no_local", "em_atendimento", "encerrada"].includes(step))}
      ${stepItem("Atendimento", step === "em_atendimento", ["em_atendimento", "encerrada"].includes(step))}
      ${stepItem("Finalizada", step === "encerrada", step === "encerrada")}
    </ol>
    <div id="field-map" role="application" aria-label="Mapa da missão"></div>
    <button type="button" class="primary big" data-action="field-center">Ver local</button>
    ${step === "em_deslocamento" ? `<button type="button" class="primary big" data-action="advance" data-id="${esc(incident.id)}" data-step="chegou">Cheguei</button>` : ""}
    ${step === "no_local" ? `<label class="field">Registrar atendimento<textarea id="desk-note" rows="3"></textarea></label><button type="button" class="primary big" data-action="advance" data-id="${esc(incident.id)}" data-step="iniciar">Registrar atendimento</button>` : ""}
    ${step === "em_atendimento" || step === "no_local" ? `<button type="button" class="ghost big" data-action="advance" data-id="${esc(incident.id)}" data-step="finalizar">Finalizar</button>` : ""}
    ${step === "encerrada" ? "<p>Missão encerrada.</p>" : ""}`;
}

function stepItem(label, current, done) {
  const mark = current ? ' aria-current="step"' : "";
  return `<li${mark}>${done || current ? "●" : "○"} ${esc(label)}</li>`;
}

function drawField(agent, incident) {
  const node = document.getElementById("field-map");
  if (!node || !window.L) return;
  fieldMap?.remove();
  fieldMap = L.map(node, { zoomControl: false }).setView([incident.lat, incident.lng], 14);
  L.tileLayer("https://tile.openstreetmap.org/{z}/{x}/{y}.png", { maxZoom: 19, attribution: "&copy; OpenStreetMap" }).addTo(fieldMap);
  L.circleMarker([agent.lat, agent.lng], { radius: 7, color: "#1f4e79" }).addTo(fieldMap).bindTooltip(agent.name);
  L.circleMarker([incident.lat, incident.lng], { radius: 7, color: "#a11d2b" }).addTo(fieldMap).bindTooltip(incident.title);
  if (agent.route?.road && agent.route.polyline?.length >= 3) L.polyline(agent.route.polyline, { color: "#1b6b45" }).addTo(fieldMap);
  setTimeout(() => fieldMap?.invalidateSize(), 80);
}

export function centerField() {
  const agent = state.bootstrap.agents.find((item) => item.id === state.fieldAgentId);
  const incident = agent?.mission && state.bootstrap.incidents.find((item) => item.id === agent.mission.incident_id);
  if (fieldMap && incident) fieldMap.setView([incident.lat, incident.lng], 16);
}

function matchIncident(item) {
  if (state.region && item.region !== state.region) return false;
  const filter = state.incidentFilter;
  if (filter === "todas") return true;
  if (filter === "criticas") return item.priority === "critica";
  if (filter === "alta") return item.priority === "alta";
  if (filter === "media") return item.priority === "media";
  if (filter === "baixa") return item.priority === "baixa";
  if (filter === "atendimento") return ["em_deslocamento", "no_local", "em_atendimento"].includes(item.status);
  if (filter === "aguardando") return item.status === "aberto";
  if (filter === "encerradas") return item.status === "encerrada" || item.status === "ciencia";
  return true;
}
