import { api } from "./api.js";
import { sync as syncContext } from "./context.js";
import { clockLabel, esc, toast } from "./format.js";
import { state } from "./state.js";

const TYPES = [["moto", "Moto"], ["carro", "Carro"], ["caminhonete", "Caminhonete"], ["caminhao", "Caminhão"]];
const STATUS = [
  ["disponivel", "Em operação"],
  ["em_atendimento", "Em atendimento"],
  ["parado", "Parado"],
  ["indisponivel", "Indisponível"],
  ["em_manutencao", "Em manutenção"],
];
const FUEL = [["gasolina", "Gasolina"], ["etanol", "Etanol"], ["flex", "Flex"], ["diesel", "Diesel"], ["eletrico", "Elétrico"]];

let query = "";
let type = "";
let status = "";
let base = "";
let draft = null;
let pendingId = "";

export function mount(main) {
  main.innerHTML = `
    <section class="inventory">
      <header class="page-head">
        <h1>Veículos</h1>
        <p>Cada ficha guarda o próprio consumo e o preço do combustível. O mapa só desenha o percurso quando o serviço devolve a geometria da via.</p>
      </header>
      <div class="inv-toolbar">
        <input id="fleet-q" type="search" placeholder="Buscar nome, placa ou modelo" value="${esc(query)}" />
        <select id="fleet-type">${options([["", "Tipo"], ...TYPES], type)}</select>
        <select id="fleet-status">${options([["", "Situação"], ...STATUS], status)}</select>
        <select id="fleet-base">${options(bases(), base)}</select>
        <button type="button" class="primary" id="fleet-new">Novo veículo</button>
      </div>
      <div class="fleet-stats" id="fleet-stats"></div>
      <div class="inv-body">
        <div class="table-wrap" id="fleet-table"></div>
        <div id="fleet-form"></div>
      </div>
    </section>`;
  document.getElementById("fleet-q").addEventListener("input", (event) => {
    query = event.target.value;
    renderTable();
  });
  document.getElementById("fleet-type").addEventListener("change", (event) => {
    type = event.target.value;
    render();
  });
  document.getElementById("fleet-status").addEventListener("change", (event) => {
    status = event.target.value;
    render();
  });
  document.getElementById("fleet-base").addEventListener("change", (event) => {
    base = event.target.value;
    render();
  });
  document.getElementById("fleet-new").addEventListener("click", openNew);
  render();
  if (pendingId) {
    const id = pendingId;
    pendingId = "";
    edit(id);
  }
}

export function focus(id) {
  pendingId = id;
}

export function destroy() {}

export function afterReload() {
  renderTable();
  renderStats();
  if (!draft) renderForm();
}

function render() {
  renderStats();
  renderTable();
  renderForm();
}

function vehicles() {
  return state.bootstrap?.vehicles || [];
}

function bases() {
  const names = [...new Set(vehicles().map((item) => item.base_region).concat((state.bootstrap?.schema?.regions || []).map((item) => item.id)))];
  return [["", "Base"], ...names.map((name) => [name, name])];
}

function label(list, id) {
  return list.find((item) => item[0] === id)?.[1] || id;
}

function filtered() {
  const text = query.trim().toLowerCase();
  return vehicles().filter((item) => {
    if (type && item.type !== type) return false;
    if (status && item.status !== status) return false;
    if (base && item.base_region !== base) return false;
    if (!text) return true;
    return `${item.name} ${item.plate} ${item.brand} ${item.model}`.toLowerCase().includes(text);
  });
}

function renderStats() {
  const node = document.getElementById("fleet-stats");
  if (!node) return;
  const all = vehicles();
  const count = (value) => all.filter((item) => item.status === value && item.active !== false).length;
  node.innerHTML = `
    <span><b>${all.length}</b> na frota</span>
    <span><b>${count("disponivel")}</b> disponíveis</span>
    <span><b>${count("em_atendimento")}</b> em atendimento</span>
    <span><b>${count("em_manutencao")}</b> em manutenção</span>
    <span><b>${all.filter((item) => item.active === false).length}</b> inativos</span>`;
}

function renderTable() {
  const node = document.getElementById("fleet-table");
  if (!node) return;
  const rows = filtered();
  node.innerHTML = rows.length ? `
    <table>
      <thead><tr><th>Veículo</th><th>Tipo</th><th>Placa</th><th>Consumo</th><th>R$/km</th><th>Situação</th><th>Base</th></tr></thead>
      <tbody>
        ${rows.map((item) => `
          <tr data-id="${esc(item.id)}">
            <td>${esc(item.name)}<br><span class="hint">${esc(item.brand)} ${esc(item.model)}</span></td>
            <td>${esc(label(TYPES, item.type))}</td>
            <td>${esc(item.plate || "—")}</td>
            <td>${String(item.consumption).replace(".", ",")} ${esc(item.consumption_unit)}</td>
            <td>${perKm(item)}</td>
            <td>${esc(label(STATUS, item.status))}${item.active === false ? " · inativo" : ""}</td>
            <td>${esc(item.base_region)}</td>
          </tr>`).join("")}
      </tbody>
    </table>` : `<p class="hint">Nenhum veículo com esses filtros.</p>`;
  node.querySelectorAll("tr[data-id]").forEach((row) => {
    row.addEventListener("click", () => edit(row.dataset.id));
  });
}

function perKm(item) {
  const consumption = Number(item.consumption) || 0;
  if (consumption <= 0) return "—";
  const value = Number(item.fuel_price) / consumption + Number(item.other_cost_per_km || 0);
  return value.toLocaleString("pt-BR", { style: "currency", currency: "BRL" });
}

function openNew() {
  const region = state.bootstrap.schema.regions[0];
  draft = {
    id: null,
    name: "",
    type: "carro",
    brand: "",
    model: "",
    year: 2022,
    plate: "",
    fuel: "gasolina",
    consumption: "",
    consumption_unit: "km/l",
    fuel_price: "6.29",
    other_cost_per_km: "0.20",
    status: "disponivel",
    active: true,
    base_region: region.id,
    location_source: "base",
    lat: "",
    lng: "",
    notes: "",
    history: [],
  };
  renderForm();
}

function edit(id) {
  const source = vehicles().find((item) => item.id === id);
  if (!source) return;
  draft = { ...source };
  state.selected = { kind: "vehicle", id };
  renderForm();
  syncContext();
}

function renderForm() {
  const node = document.getElementById("fleet-form");
  if (!node) return;
  if (!draft) {
    node.innerHTML = `<p class="hint">Selecione um veículo ou cadastre um novo. Nada é gravado até o envio.</p>`;
    return;
  }
  const item = draft;
  const regions = state.bootstrap.schema.regions;
  node.innerHTML = `
    <form id="fleet-editor">
      <h2>${item.id ? "Editar veículo" : "Novo veículo"}</h2>
      <label class="field">Nome<input name="name" required value="${esc(item.name)}" /></label>
      <label class="field">Tipo<select name="type">${options(TYPES, item.type)}</select></label>
      <label class="field">Marca<input name="brand" required value="${esc(item.brand)}" /></label>
      <label class="field">Modelo<input name="model" required value="${esc(item.model)}" /></label>
      <label class="field">Ano<input name="year" type="number" min="1990" max="2030" required value="${esc(item.year)}" /></label>
      <label class="field">Placa<input name="plate" required maxlength="8" value="${esc(item.plate || "")}" /></label>
      <label class="field">Cor<input name="color" value="${esc(item.color || "")}" /></label>
      <label class="field">Km atual<input name="odometer_km" type="number" min="0" step="0.1" value="${esc(item.odometer_km ?? "")}" /></label>
      <label class="field">Capacidade<input name="capacity" value="${esc(item.capacity || "")}" /></label>
      <label class="field">Responsável<input name="responsible" value="${esc(item.responsible || "")}" /></label>
      <label class="field">Combustível<select name="fuel">${options(FUEL, item.fuel)}</select></label>
      <label class="field">Consumo médio<input name="consumption" type="number" min="0.1" step="0.1" required value="${esc(item.consumption)}" /></label>
      <label class="field">Unidade<select name="consumption_unit">${options([["km/l", "km/l"], ["km/kWh", "km/kWh"]], item.consumption_unit || "km/l")}</select></label>
      <label class="field">Preço por litro ou kWh<input name="fuel_price" type="number" min="0" step="0.01" required value="${esc(item.fuel_price)}" /></label>
      <label class="field">Outros custos por km<input name="other_cost_per_km" type="number" min="0" step="0.01" value="${esc(item.other_cost_per_km || 0)}" /></label>
      <p class="hint" id="fleet-cost"></p>
      <label class="field">Disponibilidade<select name="status">${options(STATUS, item.status)}</select></label>
      <label class="check"><input name="active" type="checkbox" ${item.active === false ? "" : "checked"} /> Ativo</label>
      <label class="field">Base<select name="base_region">${regions.map((region) => `<option value="${esc(region.id)}" ${region.id === item.base_region ? "selected" : ""}>${esc(region.id)}</option>`).join("")}</select></label>
      <label class="field">Localização<select name="location_source">${options([["atual", "Localização atual"], ["base", "Somente a base"]], item.location_source || "base")}</select></label>
      <label class="field">Latitude<input name="lat" value="${esc(item.lat ?? "")}" /></label>
      <label class="field">Longitude<input name="lng" value="${esc(item.lng ?? "")}" /></label>
      <label class="field">Observações<textarea name="notes" rows="3">${esc(item.notes || "")}</textarea></label>
      <div class="actions">
        <button type="submit" class="primary">Salvar veículo</button>
        <button type="button" class="ghost" id="fleet-cancel">Cancelar</button>
      </div>
      ${item.history?.length ? `<h3>Histórico</h3><ul class="timeline">${item.history.map((event) => `<li><time>${esc(clockLabel(event.at))}</time>${esc(event.text)}</li>`).join("")}</ul>` : ""}
    </form>`;
  const form = document.getElementById("fleet-editor");
  const cost = () => {
    const data = Object.fromEntries(new FormData(form).entries());
    const consumption = Number(data.consumption);
    const nodeCost = document.getElementById("fleet-cost");
    if (!nodeCost) return;
    if (!consumption) {
      nodeCost.textContent = "Informe o consumo deste veículo para estimar o custo por km.";
      return;
    }
    const value = Number(data.fuel_price || 0) / consumption + Number(data.other_cost_per_km || 0);
    nodeCost.textContent = `Custo estimado por km deste veículo: ${value.toLocaleString("pt-BR", { style: "currency", currency: "BRL" })}. O deslocamento usa a distância viária: litros = km ÷ consumo.`;
  };
  form.addEventListener("input", (event) => {
    const data = Object.fromEntries(new FormData(form).entries());
    draft = { ...draft, ...data, active: form.elements.active.checked };
    if (event.target.name === "fuel") {
      const unit = data.fuel === "eletrico" ? "km/kWh" : "km/l";
      form.elements.consumption_unit.value = unit;
      draft.consumption_unit = unit;
    }
    cost();
  });
  cost();
  form.addEventListener("submit", save);
  document.getElementById("fleet-cancel").addEventListener("click", () => {
    draft = null;
    renderForm();
  });
}

async function save(event) {
  event.preventDefault();
  const form = event.target;
  const button = form.querySelector("[type=submit]");
  const body = Object.fromEntries(new FormData(form).entries());
  body.active = form.elements.active.checked;
  body.year = Number(body.year);
  body.consumption = Number(body.consumption);
  body.fuel_price = Number(body.fuel_price);
  body.other_cost_per_km = Number(body.other_cost_per_km || 0);
  if (body.odometer_km === "") delete body.odometer_km;
  else body.odometer_km = Number(body.odometer_km);
  if (body.lat === "") delete body.lat;
  if (body.lng === "") delete body.lng;
  button.disabled = true;
  try {
    const result = draft.id ? await api.updateVehicle(draft.id, body) : await api.createVehicle(body);
    draft = result.item;
    toast(result.message || "Veículo salvo.");
    renderTable();
    renderStats();
    renderForm();
  } catch (error) {
    toast(error.message, "bad");
    button.disabled = false;
  }
}

function options(list, current) {
  return list.map(([id, name]) => `<option value="${esc(id)}" ${id === current ? "selected" : ""}>${esc(name)}</option>`).join("");
}
