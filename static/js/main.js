import { api } from "./api.js";
import * as admin from "./admin.js";
import * as cco from "./cco.js";
import * as context from "./context.js";
import * as desk from "./desk.js";
import * as forecast from "./forecast.js";
import { clockLabel, esc, toast } from "./format.js";
import * as fleet from "./fleet.js";
import * as inventory from "./inventory.js";
import * as orders from "./orders.js";
import { go, state } from "./state.js";

const views = {
  cco: { mount: cco.mount, destroy: cco.destroy },
  linha: { mount: desk.mountLinha, destroy: () => {} },
  ocorrencias: { mount: desk.mountOcorrencias, destroy: desk.destroy },
  agentes: { mount: desk.mountAgentes, destroy: desk.destroy },
  inventario: { mount: inventory.mount, destroy: inventory.destroy },
  ordens: { mount: orders.mount, destroy: orders.destroy },
  frota: { mount: fleet.mount, destroy: fleet.destroy },
  rotas: { mount: desk.mountRotas, destroy: desk.destroy },
  regioes: { mount: desk.mountRegioes, destroy: desk.destroy },
  alertas: { mount: desk.mountAlertas, destroy: desk.destroy },
  previsao: { mount: forecast.mount, destroy: forecast.destroy },
  historico: { mount: desk.mountHistorico, destroy: desk.destroy },
  campo: { mount: desk.mountCampo, destroy: desk.destroy },
  acessos: { mount: admin.mount, destroy: admin.destroy },
};

const NAV = [
  ["Operação", [["cco", "Mapa sinóptico"], ["ocorrencias", "Ocorrências"], ["rotas", "Rotas"], ["linha", "Linha do tempo"]]],
  ["Recursos", [["agentes", "Agentes"], ["frota", "Veículos"], ["inventario", "Equipamentos"], ["ordens", "Ordens"]]],
  ["Território", [["regioes", "Regiões"], ["alertas", "Alertas"], ["previsao", "Previsão"]]],
  ["Registro", [["historico", "Histórico"], ["campo", "Modo campo"], ["acessos", "Acessos"]]],
];

export async function boot() {
  const app = document.getElementById("app");
  try {
    await ensureSession();
    state.bootstrap = await api.bootstrap();
    if (!state.bootstrap.user) {
      sessionStorage.removeItem("fogo-session");
      await ensureSession();
      state.bootstrap = await api.bootstrap();
    }
    state.user = state.bootstrap.user;
    state.baseline = {
      incidents: state.bootstrap.incidents.map((item) => ({ id: item.id, status: item.status })),
      equipment: state.bootstrap.equipment.map((item) => ({ id: item.id, status: item.status })),
      agents: state.bootstrap.agents.map((item) => ({ id: item.id, duty: item.duty })),
    };
  } catch (error) {
    app.innerHTML = `
      <div class="boot-error">
        <h1>A central precisa do servidor.</h1>
        <p>Na pasta do projeto, execute <code>py -3 server.py</code> ou dê dois cliques em <code>iniciar.bat</code>.</p>
        <p>${esc(error.message)}</p>
      </div>`;
    return;
  }
  renderShell();
  state._go = show;
  show("cco");
  connect();
  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape") {
      state.selected = null;
      if (state.view === "cco") cco.refresh();
    }
  });
}

function renderShell() {
  const health = state.bootstrap.health;
  document.getElementById("app").innerHTML = `
    <a class="skip" href="#main">Ir para o conteúdo</a>
    <div class="shell view-cco" id="shell">
      <header>
        <div class="brand">
          <strong>F.O.G.O.</strong>
          <span>Central de operações</span>
        </div>
        <button type="button" class="health" id="health" data-action="jump" data-jump="health" title="${esc(health.basis)}">
          <span>Saúde operacional</span>
          <b>${health.value}%</b>
          <span class="band-${esc(health.band)}">${esc(health.label)}</span>
        </button>
        <form class="find" id="find" role="search">
          <label class="sr" for="find-q">Buscar ocorrência, agente, veículo ou equipamento</label>
          <input id="find-q" type="search" placeholder="Buscar na operação" autocomplete="off" />
          <div id="find-list" hidden></div>
        </form>
        <div class="header-end">
          <p id="who" class="who">${esc(state.user ? state.user.name + " · " + state.user.role_label : "Sem sessão")}</p>
          <p id="clock" class="clock">${esc(clockLabel(state.bootstrap.clock))}</p>
          <p class="live" id="live"><i></i> conectando</p>
          <button type="button" class="ghost" data-action="toggle-chat">Chat</button>
          <button type="button" class="ghost" data-action="toggle-theme">Tema</button>
        </div>
      </header>
      <nav aria-label="Seções">
        <div class="nav-links">
          ${NAV.map(([group, items]) => `<p class="nav-label">${esc(group)}</p>${items.map(([id, label]) => `<button type="button" data-action="go" data-view="${id}">${label}</button>`).join("")}`).join("")}
        </div>
        <p class="credit">Desenvolvido por Cristhian</p>
      </nav>
      <main id="main" tabindex="-1"></main>
      <aside id="dock" class="dock" hidden aria-label="Contexto do registro"></aside>
    </div>
    <section id="chat" class="chat" hidden>
      <header><h2>PROMETHEUS Chat</h2><button type="button" class="ghost" data-action="toggle-chat">Fechar</button></header>
      <div id="chat-log" class="chat-log"></div>
      <form id="chat-form">
        <label class="sr" for="chat-q">Pergunta operacional</label>
        <input id="chat-q" placeholder="O que está crítico agora?" />
        <button type="submit" class="primary">Enviar</button>
      </form>
    </section>`;
  document.body.addEventListener("click", onClick);
  const find = document.getElementById("find-q");
  let findTimer = 0;
  find.addEventListener("input", () => {
    window.clearTimeout(findTimer);
    findTimer = window.setTimeout(() => paintFind(find.value), 180);
  });
  window.addEventListener("error", (event) => {
    const main = document.getElementById("main");
    if (main && !main.childElementCount) main.innerHTML = `<section class="page"><h1>A central não abriu</h1><p>${esc(event.message || "Erro inesperado.")}</p><p><button type="button" class="primary" onclick="location.reload()">Tentar de novo</button></p></section>`;
  });
  if (localStorage.getItem("fogo-theme") === "dark") document.documentElement.dataset.theme = "dark";
  document.getElementById("chat-form").addEventListener("submit", async (event) => {
    event.preventDefault();
    const input = document.getElementById("chat-q");
    const message = input.value.trim();
    if (!message) return;
    input.value = "";
    await askChat(message, false);
  });
  document.addEventListener("keydown", (event) => {
    const typing = ["INPUT", "TEXTAREA", "SELECT"].includes(document.activeElement?.tagName);
    if (event.key === "/" && !typing) {
      event.preventDefault();
      document.getElementById("chat").hidden = false;
      document.getElementById("chat-q").focus();
    }
    if (typing) return;
    if (event.key === "g") state.chord = "g";
    else if (state.chord === "g" && event.key === "m") {
      state.chord = "";
      show("cco");
    } else state.chord = "";
  });
  document.getElementById("find").addEventListener("submit", (event) => {
    event.preventDefault();
    document.querySelector("#find-list button")?.click();
  });
}

function show(view) {
  if (!views[view]) return;
  if (view === "campo" && state.user?.role === "agente" && state.user.registration) {
    const mine = state.bootstrap.agents.find((item) => item.registration === state.user.registration);
    if (mine) state.fieldAgentId = mine.id;
  }
  views[state.view]?.destroy?.();
  state.view = view;
  const shell = document.getElementById("shell");
  shell.className = `shell view-${view}`;
  document.querySelectorAll("nav button").forEach((button) => {
    const on = button.dataset.view === view;
    button.classList.toggle("is-on", on);
    if (on) button.setAttribute("aria-current", "page");
    else button.removeAttribute("aria-current");
  });
  views[view].mount(document.getElementById("main"));
  context.sync();
}

async function reload(focus) {
  state.bootstrap = await api.bootstrap();
  state.user = state.bootstrap.user;
  if (focus?.kind === "clear") state.selected = null;
  else if (focus?.kind && focus.kind !== "forecast") state.selected = focus;
  paintHeader();
  if (state.view === "cco") {
    cco.refresh();
    if (focus && focus.kind !== "clear") cco.focusSelection();
  } else if (state.view === "inventario") {
    inventory.afterReload();
  } else if (state.view === "frota") {
    fleet.afterReload();
  } else if (state.view === "previsao") {
    forecast.reload();
  } else {
    views[state.view]?.mount(document.getElementById("main"));
  }
  context.sync();
}

function paintHeader() {
  const health = state.bootstrap.health;
  const node = document.getElementById("health");
  const clock = document.getElementById("clock");
  if (!node) return;
  node.title = health.basis;
  node.innerHTML = `<span>Saúde operacional</span><b>${health.value}%</b><span class="band-${esc(health.band)}">${esc(health.label)}</span>`;
  if (clock) clock.textContent = clockLabel(state.bootstrap.clock);
  const who = document.getElementById("who");
  if (who && state.user) who.textContent = `${state.user.name} · ${state.user.role_label}`;
}

function paintLiveFlag() {
  const node = document.getElementById("live");
  if (!node) return;
  node.className = state.live ? "live is-on" : "live";
  node.innerHTML = `<i></i> ${state.live ? "ao vivo" : "sem sinal"}`;
}

function connect() {
  const source = new EventSource("/api/stream");
  source.onopen = () => {
    state.live = true;
    paintLiveFlag();
  };
  source.onerror = () => {
    state.live = false;
    paintLiveFlag();
  };
  source.onmessage = (event) => {
    const message = JSON.parse(event.data);
    if (message.kind === "reload") {
      reload(message.focus);
      return;
    }
    if (message.kind === "tick") applyTick(message);
  };
}

function applyTick(message) {
  const pack = state.bootstrap;
  pack.clock = message.clock;
  pack.kpis = message.kpis;
  pack.city_index = message.city_index;
  pack.alerts = message.alerts;
  pack.feed = message.feed;
  pack.incidents = message.incidents;
  pack.regions = message.regions;
  pack.health = message.health;
  pack.now = message.now;
  pack.attention = message.attention;
  pack.changes = message.changes;
  pack.preview = message.preview;
  const equipment = new Map(pack.equipment.map((item) => [item.id, item]));
  const agents = new Map(pack.agents.map((item) => [item.id, item]));
  for (const move of message.moves) {
    const target = move.kind === "agent" ? agents.get(move.id) : equipment.get(move.id);
    if (!target) continue;
    if (typeof move.lat === "number") target.lat = move.lat;
    if (typeof move.lng === "number") target.lng = move.lng;
    if (move.last_seen) target.last_seen = move.last_seen;
    if (move.duty) {
      target.duty = move.duty;
      target.status = move.status;
    }
  }
  paintHeader();
  if (state.view === "cco" && !state.replay) cco.paintLive();
}

async function onClick(event) {
  const button = event.target.closest("[data-action]");
  if (!button) return;
  const action = button.dataset.action;
  if (action === "find-open") {
    document.getElementById("find-list").hidden = true;
    document.getElementById("find-q").value = "";
    openTarget(button.dataset.kind, button.dataset.id);
    return;
  }
  if (action === "go") show(button.dataset.view);
  if (action === "jump") jump(button.dataset.jump);
  if (action === "jump-region") {
    state.region = button.dataset.region || "";
    state.incidentFilter = "todas";
    show("ocorrencias");
  }
  if (action === "toggle-layers") {
    state.layersOpen = !state.layersOpen;
    const drawer = document.getElementById("layer-drawer");
    if (drawer) drawer.hidden = !state.layersOpen;
    button.setAttribute("aria-expanded", state.layersOpen ? "true" : "false");
  }
  if (action === "layers-none") {
    for (const key of Object.keys(state.layers)) state.layers[key] = false;
    state.heat = "";
    document.querySelectorAll("[data-layer]").forEach((input) => { input.checked = false; });
    document.querySelectorAll("input[name=heat]").forEach((input) => { input.checked = input.value === ""; });
    if (state.view === "cco") cco.refresh();
  }
  if (action === "layers-reset") {
    Object.assign(state.layers, {
      agents: true, fleet: true, vehicles: true, incidents: true, cameras: false, radars: true,
      maintenance: true, areas: true, routes: true, others: false, coverage: false, events: false,
    });
    state.heat = "";
    document.querySelectorAll("[data-layer]").forEach((input) => { input.checked = !!state.layers[input.dataset.layer]; });
    document.querySelectorAll("input[name=heat]").forEach((input) => { input.checked = input.value === ""; });
    if (state.view === "cco") cco.refresh();
  }
  if (action === "map-home") cco.focusHome();
  if (action === "open-forecast") {
    state.region = button.dataset.region || "";
    state.selected = state.region ? { kind: "region", id: state.region } : null;
    show("previsao");
  }
  if (action === "schedule") inventory.schedule(button.dataset.id);
  if (action === "open-route") {
    desk.prepareRoute({ region: button.dataset.region || "", agentId: button.dataset.agent || "" });
    show("rotas");
  }
  if (action === "geo-search") {
    const query = document.getElementById("geo-q")?.value || "";
    button.disabled = true;
    try {
      const place = await api.geo(query);
      state.place = place;
      if (state.view !== "cco") show("cco");
      cco.showPlace(place);
      toast(place.note);
    } catch (error) {
      toast(error.message, "bad");
    }
    button.disabled = false;
  }
  if (action === "clear-place") {
    state.place = null;
    cco.refresh();
  }
  if (action === "back") {
    state.selected = null;
    cco.refresh();
  }
  if (action === "select") openTarget(button.dataset.kind, button.dataset.id);
  if (action === "clear-region") {
    state.region = "";
    if (state.view === "cco") cco.refresh();
    else views[state.view]?.mount(document.getElementById("main"));
  }
  if (action === "filter-region" || action === "open-record") {
    openTarget(button.dataset.kind || "region", button.dataset.region || button.dataset.id);
  }
  if (action === "close-dock") {
    state.selected = null;
    context.sync();
  }
  if (action === "show-on-map") {
    state.selected = { kind: button.dataset.kind, id: button.dataset.id };
    show("cco");
    cco.focusSelection();
  }
  if (action === "toggle-chat") {
    const panel = document.getElementById("chat");
    panel.hidden = !panel.hidden;
    if (!panel.hidden) document.getElementById("chat-q").focus();
  }
  if (action === "toggle-theme") {
    const next = document.documentElement.dataset.theme === "dark" ? "" : "dark";
    document.documentElement.dataset.theme = next;
    localStorage.setItem("fogo-theme", next || "light");
  }
  if (action === "briefing") {
    try {
      const pack = await api.briefing();
      document.getElementById("chat").hidden = false;
      pushChat("Resumo do turno", pack.text, []);
    } catch (error) {
      toast(error.message, "bad");
    }
  }
  if (action === "chat-confirm") {
    button.disabled = true;
    await askChat(button.dataset.message, true);
  }
  if (action === "os-assign") {
    button.disabled = true;
    try {
      const result = await api.assignOrder(button.dataset.id);
      toast(result.message);
    } catch (error) {
      toast(error.message, "bad");
      button.disabled = false;
    }
  }
  if (action === "os-status") {
    if (button.dataset.status === "cancelada" && !window.confirm("Cancelar esta OS?")) return;
    button.disabled = true;
    try {
      const result = await api.orderStatus(button.dataset.id, button.dataset.status);
      toast(result.message);
    } catch (error) {
      toast(error.message, "bad");
      button.disabled = false;
    }
  }
  if (action === "os-pdf") {
    try {
      const response = await fetch(`/api/orders/${button.dataset.id}/pdf`, { headers: { "X-Session": sessionStorage.getItem("fogo-session") || "" } });
      if (!response.ok) throw new Error("Não foi possível gerar o PDF.");
      const blob = await response.blob();
      const url = URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = url;
      link.download = `${button.dataset.id}.pdf`;
      link.click();
      URL.revokeObjectURL(url);
    } catch (error) {
      toast(error.message, "bad");
    }
  }
  if (action === "mark-event") {
    button.disabled = true;
    try {
      const result = await api.markEvent(button.dataset.id, button.dataset.kind);
      toast(result.message);
    } catch (error) {
      toast(error.message, "bad");
      button.disabled = false;
    }
  }
  if (action === "incident-filter") {
    state.incidentFilter = button.dataset.filter;
    desk.mountOcorrencias(document.getElementById("main"));
  }
  if (action === "agent-filter") {
    state.agentFilter = button.dataset.filter;
    desk.mountAgentes(document.getElementById("main"));
  }
  if (action === "crisis") {
    state.crisis = button.dataset.id;
    state.selected = { kind: "incident", id: button.dataset.id };
    if (state.view !== "cco") show("cco");
    else cco.refresh();
  }
  if (action === "crisis-exit") {
    state.crisis = null;
    cco.refresh();
  }
  if (action === "vehicle-compare") {
    button.disabled = true;
    try {
      await cco.loadVehicleQuotes(button.dataset.incident);
    } catch (error) {
      toast(error.message, "bad");
      button.disabled = false;
    }
    return;
  }
  if (action === "vehicle-pick") {
    cco.previewChoice(button.dataset.vehicle, button.dataset.choice);
    return;
  }
  if (action === "vehicle-go") {
    const name = button.dataset.name || "este veículo";
    if (!window.confirm(`Despachar ${name} por este percurso?`)) return;
    button.disabled = true;
    try {
      const result = await api.dispatchVehicle(button.dataset.incident, button.dataset.vehicle, button.dataset.choice);
      cco.clearRoadPreview();
      toast(result.message);
    } catch (error) {
      toast(error.message, "bad");
      button.disabled = false;
    }
    return;
  }
  if (action === "dispatch") {
    const team = button.dataset.team || "esta equipe";
    if (!window.confirm(`Atribuir ${team} a esta ocorrência?`)) return;
    button.disabled = true;
    try {
      const result = await api.dispatch(button.dataset.incident, button.dataset.agent);
      toast(result.message);
    } catch (error) {
      toast(error.message, "bad");
      button.disabled = false;
    }
  }
  if (action === "advance") {
    if (button.dataset.step === "finalizar" && !window.confirm("Finalizar este atendimento?")) return;
    const note = button.closest(".detail, .mission")?.querySelector("textarea")?.value || "";
    button.disabled = true;
    try {
      const result = await api.advance(button.dataset.id, button.dataset.step, note);
      toast(result.message);
    } catch (error) {
      toast(error.message, "bad");
      button.disabled = false;
    }
  }
  if (action === "field-open") {
    state.fieldAgentId = button.dataset.id;
    show("campo");
  }
  if (action === "field-clear") {
    state.fieldAgentId = null;
    show("campo");
  }
  if (action === "field-center") desk.centerField();
  if (action === "edit") inventory.edit(button.dataset.kind, button.dataset.id);
  if (action === "suggest-route") {
    const stops = desk.suggestRoute();
    desk.rememberRoute(desk.currentRouteAgent(), stops);
    document.querySelectorAll("[data-stop-id]").forEach((input) => {
      input.checked = stops.some((stop) => stop.id === input.dataset.stopId);
    });
    if (!stops.length) toast("Nenhum ponto de inspeção pendente na região desta equipe.", "bad");
  }
  if (action === "plan-route") {
    const agentId = desk.currentRouteAgent();
    const stops = desk.checkedStops();
    if (!stops.length) {
      toast("Selecione ao menos um destino.", "bad");
      return;
    }
    if (!window.confirm("Gerar a rota com estes pontos? Ela fica planejada até a confirmação.")) return;
    button.disabled = true;
    try {
      const result = await api.planRoute({ agent_id: agentId, stops });
      desk.rememberRoute(agentId, stops);
      toast(result.message);
    } catch (error) {
      toast(error.message, "bad");
      button.disabled = false;
    }
  }
  if (action === "route-move") {
    const moved = desk.moveStop(Number(button.dataset.index), Number(button.dataset.dir));
    if (!moved) return;
    try {
      await api.planRoute({ agent_id: moved.agentId, stops: moved.stops, keep_order: true });
      desk.rememberRoute(moved.agentId, moved.stops);
    } catch (error) {
      toast(error.message, "bad");
    }
  }
  if (action === "confirm-route") {
    const moved = desk.currentPlan();
    if (!moved) return;
    if (!window.confirm("Confirmar esta rota planejada?")) return;
    try {
      const result = await api.planRoute({ agent_id: moved.agentId, stops: moved.stops, keep_order: true, status: "aprovada" });
      toast(result.message);
    } catch (error) {
      toast(error.message, "bad");
    }
  }
  if (action === "clear-plan") {
    try {
      const result = await api.clearRoute(button.dataset.id);
      desk.rememberRoute(button.dataset.id, []);
      toast(result.message);
    } catch (error) {
      toast(error.message, "bad");
    }
  }
  if (action === "replay") {
    try {
      const payload = await api.replay(button.dataset.at);
      state.replay = payload.frame;
      show("cco");
      cco.refresh();
    } catch (error) {
      toast(error.message, "bad");
    }
  }
  if (action === "replay-live") {
    state.replay = null;
    cco.refresh();
  }
  if (action === "scenario") {
    button.disabled = true;
    try {
      const result = await api.scenario(button.dataset.scenario);
      toast(result.message);
    } catch (error) {
      toast(error.message, "bad");
      button.disabled = false;
    }
  }
  if (action === "reset") {
    if (!window.confirm("Restaurar a cidade de demonstração? O que foi cadastrado nesta sessão sai.")) return;
    try {
      const result = await api.reset();
      state.replay = null;
      state.selected = null;
      toast(result.message || "Demonstração restaurada.");
    } catch (error) {
      toast(error.message, "bad");
    }
  }
}

function openTarget(kind, id) {
  if (kind === "forecast") {
    show("previsao");
    return;
  }
  const normalized = kind === "region" ? "region" : kind;
  state.selected = { kind: normalized, id };
  const view = context.homeFor(normalized);
  if (normalized === "vehicle") fleet.focus(id);
  if (state.view !== view) show(view);
  else {
    views[view]?.mount(document.getElementById("main"));
    context.sync();
  }
  if (view === "cco") cco.focusSelection();
}

function jump(name) {
  if (name === "critical") {
    state.region = "";
    state.incidentFilter = "criticas";
    show("ocorrencias");
  } else if (name === "service") {
    state.region = "";
    state.incidentFilter = "atendimento";
    show("ocorrencias");
  } else if (name === "waiting") {
    state.region = "";
    state.incidentFilter = "aguardando";
    show("ocorrencias");
  } else if (name === "closed") {
    state.region = "";
    state.incidentFilter = "encerradas";
    show("ocorrencias");
  } else if (name === "free") {
    state.agentFilter = "disponivel";
    show("agentes");
  } else if (name === "mission") {
    state.agentFilter = "missao";
    show("agentes");
  } else if (name === "down") {
    state.equipmentStatus = "indisponivel";
    state.editor = null;
    show("inventario");
  } else if (name === "health" || name === "regions") {
    state.regionWatch = true;
    show("regioes");
  }
}

function paintFind(raw) {
  const box = document.getElementById("find-list");
  const text = raw.trim().toLowerCase();
  if (!box) return;
  if (text.length < 2 || !state.bootstrap) {
    box.hidden = true;
    box.innerHTML = "";
    return;
  }
  const hits = [];
  for (const item of state.bootstrap.incidents || []) {
    if (`${item.number} ${item.title} ${item.street}`.toLowerCase().includes(text)) hits.push({ kind: "incident", id: item.id, title: item.title, meta: `Ocorrência ${item.number}` });
  }
  for (const item of state.bootstrap.agents || []) {
    if (`${item.name} ${item.team}`.toLowerCase().includes(text)) hits.push({ kind: "agent", id: item.id, title: item.name, meta: item.team });
  }
  for (const item of state.bootstrap.vehicles || []) {
    if (`${item.name} ${item.plate} ${item.model}`.toLowerCase().includes(text)) hits.push({ kind: "vehicle", id: item.id, title: item.name, meta: item.base_region });
  }
  for (const item of state.bootstrap.regions || []) {
    if (`${item.region} ${item.city || ""}`.toLowerCase().includes(text)) hits.push({ kind: "region", id: item.region, title: item.region, meta: "Região" });
  }
  for (const item of state.bootstrap.agents || []) {
    if (item.plan?.road || item.route?.road) {
      const label = item.route?.label || item.plan?.label || item.team;
      if (`${label} ${item.team} ${item.name}`.toLowerCase().includes(text)) hits.push({ kind: "route", id: `${item.id}:${item.route?.road ? "live" : "plan"}`, title: label, meta: "Rota" });
    }
  }
  for (const item of state.bootstrap.equipment || []) {
    if (`${item.serial} ${item.street} ${item.type_label}`.toLowerCase().includes(text)) hits.push({ kind: "equipment", id: item.id, title: item.serial, meta: item.type_label });
  }
  const shown = hits.slice(0, 8);
  box.hidden = false;
  box.innerHTML = shown.length
    ? shown.map((item) => `<button type="button" data-action="find-open" data-kind="${esc(item.kind)}" data-id="${esc(item.id)}"><b>${esc(item.title)}</b><span>${esc(item.meta)}</span></button>`).join("")
    : `<p>Nenhum registro encontrado.</p>`;
}

async function askChat(message, confirm) {
  if (!confirm) pushChat("Você", message, []);
  try {
    const result = await api.chat(message, confirm);
    pushChat("Central", result.reply, result.targets || [], result.confirm ? message : "");
  } catch (error) {
    pushChat("Central", error.message, []);
  }
}

function pushChat(who, text, targets, confirmMessage = "") {
  const log = document.getElementById("chat-log");
  if (!log) return;
  const links = (targets || []).filter((item) => item.id).map((item) => `<button type="button" class="ghost" data-action="open-record" data-kind="${esc(item.kind)}" data-id="${esc(item.id)}">Ver ${esc(item.label || "registro")}</button>`).join("");
  const confirm = confirmMessage ? `<button type="button" class="primary" data-action="chat-confirm" data-message="${esc(confirmMessage)}">Confirmar</button>` : "";
  log.insertAdjacentHTML("beforeend", `<article><p><b>${esc(who)}.</b> ${esc(text)}</p><div class="actions">${links}${confirm}</div></article>`);
  log.scrollTop = log.scrollHeight;
}

async function ensureSession() {
  if (!sessionStorage.getItem("fogo-session")) {
    const session = await api.login("operador@fogo.local", "demonstracao");
    sessionStorage.setItem("fogo-session", session.token);
    state.user = session.user;
  }
}

boot();
