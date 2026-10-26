import { api } from "./api.js";
import { esc, toast } from "./format.js";
import { state } from "./state.js";

let map;
let paintedAt = "";
let playing = false;

export function paint(node) {
  if (!node) return;
  const plan = state.bootstrap.day_plan || { crews: [] };
  if (node.dataset.at === plan.created_at && node.childElementCount) return;
  node.dataset.at = plan.created_at || "";
  paintedAt = plan.created_at || "";
  const crews = plan.crews || [];
  node.innerHTML = `
    <section class="route-section">
      <h2>Rotas do dia</h2>
      <p class="hint">${esc(plan.factor_note || "Calcule para ver distância, ETA e o comparativo com a rota ingênua.")} ${esc(plan.matrix_note || "")}</p>
      <p class="hint">${plan.stop_count ? `${plan.stop_count} paradas. Ingênua ${plan.naive_min} min · otimizada ${plan.optimized_min} min · ${_delta(plan.saved_min)} na mesma matriz.` : "Ainda sem rota calculada. O cenário deixa pelo menos 12 OS abertas e 3 equipes."}</p>
      <div class="actions">
        <button type="button" class="primary" data-action="optimize-all">Otimizar tudo</button>
        <button type="button" class="ghost" data-action="undo-routes">Desfazer</button>
        <label class="field slim">Demonstração
          <select id="route-speed"><option value="2">lenta</option><option value="6" selected>normal</option><option value="14">rápida</option></select>
        </label>
      </div>
      <div class="day-layout">
        <div>
          ${crews.map(crewBlock).join("") || "<p class='hint'>Nenhuma equipe na rota.</p>"}
          ${(plan.unassigned || []).length ? `<p class="hint">Sem equipe compatível ou sem folga na jornada: ${(plan.unassigned || []).length}.</p>` : ""}
        </div>
        <div id="day-map"></div>
      </div>
    </section>`;
  draw(crews);
  node.querySelectorAll(".stop-list").forEach(bindDrag);
}

export function afterReload() {
  if (playing) return;
  const node = document.getElementById("day-board");
  if (!node) return;
  const stamp = state.bootstrap.day_plan?.created_at || "";
  if (stamp !== paintedAt) paint(node);
}

export async function handle(action, button) {
  if (action === "optimize-all" || action === "optimize-crew") {
    button.disabled = true;
    try {
      const result = await api.optimizeRoutes(action === "optimize-crew" ? button.dataset.id : "");
      toast(result.message);
    } catch (error) {
      toast(error.message, "bad");
      button.disabled = false;
    }
    return true;
  }
  if (action === "undo-routes") {
    try { toast((await api.undoRoutes()).message); } catch (error) { toast(error.message, "bad"); }
    return true;
  }
  if (action === "release-crew") {
    if (!window.confirm("Tirar esta equipe e redistribuir as paradas?")) return true;
    try { toast((await api.releaseCrew(button.dataset.id)).message); } catch (error) { toast(error.message, "bad"); }
    return true;
  }
  if (action === "play-route") {
    play(button.dataset.id);
    return true;
  }
  if (action === "route-pdf") {
    await download(button.dataset.id);
    return true;
  }
  if (action === "focus-stop") {
    const crew = (state.bootstrap.day_plan?.crews || []).find((item) => item.id === button.dataset.crew);
    const stop = crew?.stops?.find((item) => item.id === button.dataset.id);
    if (map && stop) map.setView([stop.lat, stop.lng], 15);
    return true;
  }
  return false;
}

function crewBlock(crew) {
  const warn = crew.approximate ? "estimativa aproximada" : "pelas vias";
  return `
    <article class="os-card ${crew.active === false ? "is-late" : ""}">
      <h3 style="color:${esc(crew.color)}">${esc(crew.name)}</h3>
      <p class="hint">${esc(crew.agent_name || "")} · ${crew.distance_km || 0} km · ${crew.duration_min || 0} min · volta ${esc(crew.return_label || "-")} · ${warn}</p>
      <p class="hint" title="A ingênua reparte na ordem de abertura. A otimizada usa o menor desvio e 2-opt, com a crítica na frente.">Ingênua ${crew.naive_min || 0} min · nesta equipe ${_delta(crew.saved_min)}</p>
      <ol class="stop-list" data-crew="${esc(crew.id)}">
        ${(crew.stops || []).map((stop) => `
          <li draggable="true" data-stop="${esc(stop.id)}" class="${stop.late ? "is-late" : ""}">
            <b>${stop.order}.</b> ${esc(stop.label)}
            <small>ETA ${esc(stop.eta_label || "-")} · ${esc(stop.priority || "")}${stop.late ? " · SLA em risco" : ""}</small>
            <button type="button" class="ghost" data-action="focus-stop" data-crew="${esc(crew.id)}" data-id="${esc(stop.id)}">Ver no mapa</button>
          </li>`).join("")}
      </ol>
      <div class="actions">
        <button type="button" class="ghost" data-action="optimize-crew" data-id="${esc(crew.id)}">Otimizar esta equipe</button>
        <button type="button" class="ghost" data-action="play-route" data-id="${esc(crew.id)}">Percorrer</button>
        <button type="button" class="ghost" data-action="release-crew" data-id="${esc(crew.id)}">Equipe indisponível</button>
        ${crew.maps_url ? `<a class="ghost" href="${esc(crew.maps_url)}" target="_blank" rel="noopener">Google Maps</a>` : ""}
        <button type="button" class="ghost" data-action="route-pdf" data-id="${esc(crew.id)}">Folha PDF</button>
      </div>
    </article>`;
}

function draw(crews) {
  const node = document.getElementById("day-map");
  if (!node || !window.L) return;
  map?.remove();
  map = L.map(node, { zoomControl: false }).setView([-22.48, -50.15], 9);
  L.tileLayer("https://tile.openstreetmap.org/{z}/{x}/{y}.png", { maxZoom: 19, attribution: "&copy; OpenStreetMap" }).addTo(map);
  const bounds = [];
  for (const crew of crews) {
    const line = crew.polyline || [];
    if (line.length >= 2) {
      const drawn = L.polyline(line, { color: crew.color, weight: 4, dashArray: crew.approximate ? "2 8" : null }).addTo(map);
      bounds.push(drawn.getBounds());
    }
    (crew.stops || []).forEach((stop) => {
      const icon = L.divIcon({
        className: "stop-num",
        html: `<span class="${stop.late ? "late" : ""}" style="background:${crew.color}">${stop.order}</span>`,
        iconSize: [22, 22],
        iconAnchor: [11, 11],
      });
      L.marker([stop.lat, stop.lng], { icon }).addTo(map).bindTooltip(`${stop.order}. ${stop.label}`);
      bounds.push(L.latLngBounds([[stop.lat, stop.lng]]));
    });
  }
  if (bounds.length) map.fitBounds(bounds.reduce((all, item) => all.extend(item), bounds[0]), { padding: [24, 24] });
  setTimeout(() => map?.invalidateSize(), 80);
}

function bindDrag(list) {
  let from = null;
  list.querySelectorAll("li").forEach((item) => {
    item.addEventListener("dragstart", () => { from = item.dataset.stop; });
    item.addEventListener("dragover", (event) => event.preventDefault());
    item.addEventListener("drop", async (event) => {
      event.preventDefault();
      const ids = [...list.querySelectorAll("li")].map((li) => li.dataset.stop);
      const target = item.dataset.stop;
      const next = ids.filter((id) => id !== from);
      next.splice(next.indexOf(target), 0, from);
      try {
        toast((await api.reorderRoute(list.dataset.crew, next)).message);
      } catch (error) {
        toast(error.message, "bad");
      }
    });
  });
}

function play(crewId) {
  const crew = (state.bootstrap.day_plan?.crews || []).find((item) => item.id === crewId);
  const line = crew?.polyline || [];
  if (!map || line.length < 2) {
    toast("Sem geometria para percorrer.", "bad");
    return;
  }
  playing = true;
  const marker = L.circleMarker(line[0], { radius: 7, color: "#1c2430" }).addTo(map);
  let index = 0;
  const speed = Number(document.getElementById("route-speed")?.value || 6);
  const timer = setInterval(() => {
    index += speed;
    if (index >= line.length) {
      clearInterval(timer);
      playing = false;
      map.removeLayer(marker);
      return;
    }
    marker.setLatLng(line[index]);
  }, 90);
}

async function download(id) {
  const response = await fetch(`/api/day-routes/${id}/pdf`, { headers: { "X-Session": sessionStorage.getItem("fogo-session") || "" } });
  if (!response.ok) {
    toast("Não foi possível gerar a folha.", "bad");
    return;
  }
  const blob = await response.blob();
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = `${id}.pdf`;
  link.click();
  URL.revokeObjectURL(url);
}

function _delta(value) {
  const number = Number(value) || 0;
  if (number > 0) return `economia de ${number} min`;
  if (number < 0) return `${Math.abs(number)} min a mais por causa do SLA`;
  return "sem diferença de tempo";
}
