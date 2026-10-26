import { api } from "./api.js";
import { esc, pill, toast, typeLabel } from "./format.js";
import { go, state } from "./state.js";

let tab = "equipment";
let picker = null;

export function mount(main) {
  main.innerHTML = `
    <section class="inventory">
      <header class="page-head">
        <h1>Equipamentos e agentes</h1>
        <p>Consulte a lista, abra um registro para editar e salve só quando os dados estiverem certos.</p>
      </header>
      <div class="inv-toolbar">
        <div class="tabs">
          <button type="button" data-tab="equipment" class="${tab === "equipment" ? "is-on" : ""}">Equipamentos</button>
          <button type="button" data-tab="agent" class="${tab === "agent" ? "is-on" : ""}">Agentes</button>
        </div>
        <input id="inv-q" type="search" placeholder="Filtrar a lista" />
        <button type="button" class="primary" id="inv-new">${tab === "equipment" ? "Novo equipamento" : "Novo agente"}</button>
        <button type="button" class="ghost" id="inv-csv">Exportar CSV</button>
      </div>
      <div class="inv-body">
        <div class="table-wrap" id="inv-table"></div>
        <div id="inv-form"></div>
      </div>
    </section>`;
  main.querySelectorAll("[data-tab]").forEach((button) => {
    button.addEventListener("click", () => {
      tab = button.dataset.tab;
      state.editor = null;
      mount(main);
    });
  });
  document.getElementById("inv-q").addEventListener("input", () => {
    tablePage = 0;
    renderTable();
  });
  document.getElementById("inv-new").addEventListener("click", () => openNew());
  document.getElementById("inv-csv").addEventListener("click", exportCsv);
  renderTable();
  renderForm();
}

export function destroy() {
  if (picker) {
    picker.remove();
    picker = null;
  }
}

export function schedule(id) {
  edit("equipment", id);
  if (!state.editor) return;
  state.editor.values.maintenance_need = state.editor.values.maintenance_need === "nenhuma" ? "agendada" : state.editor.values.maintenance_need;
  state.editor.prefilled = true;
}

export function edit(kind, id) {
  tab = kind === "agent" ? "agent" : "equipment";
  const source = kind === "agent"
    ? state.bootstrap.agents.find((item) => item.id === id)
    : state.bootstrap.equipment.find((item) => item.id === id);
  if (!source) return;
  state.editor = { mode: "edit", kind: tab, id, values: { ...source, attrs: { ...(source.attrs || {}) } } };
  go("inventario");
}

function openNew() {
  const region = state.bootstrap.schema.regions[2];
  const base = {
    region: region.id,
    city: region.city,
    uf: region.uf,
    lat: region.lat,
    lng: region.lng,
    neighborhood: region.id,
    status: tab === "equipment" ? "operacional" : "em_atividade",
    maintenance_need: "nenhuma",
    agency: tab === "equipment" ? "Secretaria de Mobilidade" : "Secretaria de Mobilidade",
    shift: "Tarde",
    type: "camera",
    attrs: {},
  };
  state.editor = { mode: "new", kind: tab, id: null, values: base, coordsTouched: false };
  renderForm();
}

function renderTable() {
  const query = (document.getElementById("inv-q")?.value || "").trim().toLowerCase();
  const node = document.getElementById("inv-table");
  if (!node) return;
  if (tab === "equipment") node.innerHTML = equipmentTable(query);
  else node.innerHTML = agentTable(query);
  node.querySelectorAll("[data-open]").forEach((row) => {
    row.addEventListener("click", (event) => {
      if (event.target.closest("[data-action]")) return;
      const id = row.dataset.open;
      const source = tab === "equipment"
        ? state.bootstrap.equipment.find((item) => item.id === id)
        : state.bootstrap.agents.find((item) => item.id === id);
      state.editor = { mode: "edit", kind: tab, id, values: { ...source, attrs: { ...(source.attrs || {}) } }, coordsTouched: true };
      renderTable();
      renderForm();
    });
  });
  node.querySelectorAll("[data-page]").forEach((button) => {
    button.addEventListener("click", () => {
      tablePage += Number(button.dataset.page);
      renderTable();
    });
  });
}

let tablePage = 0;
const PAGE = 12;

function equipmentTable(query) {
  const rows = state.bootstrap.equipment.filter((item) => {
    if (state.equipmentStatus === "indisponivel" && !["mau_funcionamento", "em_manutencao", "desativado", "furtado", "sem_comunicacao"].includes(item.status)) return false;
    if (state.region && item.region !== state.region) return false;
    const blob = [item.serial, item.brand, item.model, typeLabel(item.type), item.neighborhood, item.city, item.street].join(" ").toLowerCase();
    return !query || blob.includes(query);
  });
  const pages = Math.max(1, Math.ceil(rows.length / PAGE));
  if (tablePage >= pages) tablePage = pages - 1;
  const slice = rows.slice(tablePage * PAGE, tablePage * PAGE + PAGE);
  return `
    <p class="hint">${state.equipmentStatus === "indisponivel" ? "Filtro: equipamentos indisponíveis. " : ""}${rows.length ? `${rows.length} registro(s).` : "Nenhum registro encontrado."}</p>
    <table>
      <thead><tr><th>Situação</th><th>Tipo</th><th>Série</th><th>Local</th><th>Manutenção</th><th></th></tr></thead>
      <tbody>
        ${slice.map((item) => `
          <tr data-open="${esc(item.id)}" class="${state.editor?.id === item.id ? "is-selected" : ""}">
            <td>${pill(item.status)}</td>
            <td>${esc(typeLabel(item.type))}</td>
            <td><b>${esc(item.serial)}</b><br><span class="muted">${esc(item.brand)} ${esc(item.model)}</span></td>
            <td>${esc(item.neighborhood)} · ${esc(item.city)}<br><span class="muted">${esc(item.street)}</span></td>
            <td>${esc(item.maintenance_flag || item.maintenance_need)}</td>
            <td><button type="button" class="ghost" data-action="select" data-kind="equipment" data-id="${esc(item.id)}">Ver</button></td>
          </tr>`).join("")}
      </tbody>
    </table>
    ${pages > 1 ? `<div class="pager"><button type="button" class="ghost" data-page="-1" ${tablePage === 0 ? "disabled" : ""}>Anterior</button><span>${tablePage + 1} de ${pages}</span><button type="button" class="ghost" data-page="1" ${tablePage + 1 >= pages ? "disabled" : ""}>Próxima</button></div>` : ""}`;
}

function agentTable(query) {
  const rows = state.bootstrap.agents.filter((item) => {
    const blob = [item.name, item.registration, item.agency, item.region, item.role].join(" ").toLowerCase();
    return !query || blob.includes(query);
  });
  return `
    ${rows.length ? "" : `<p class="hint">Nenhum agente encontrado.</p>`}
    <table>
      <thead><tr><th>Situação</th><th>Nome</th><th>Matrícula</th><th>Órgão</th><th>Região</th><th>Turno</th></tr></thead>
      <tbody>
        ${rows.map((item) => `
          <tr data-open="${esc(item.id)}" class="${state.editor?.id === item.id ? "is-selected" : ""}">
            <td>${pill(item.status)}</td>
            <td><b>${esc(item.name)}</b><br><span class="muted">${esc(item.role)}</span></td>
            <td>${esc(item.registration)}</td>
            <td>${esc(item.agency)}</td>
            <td>${esc(item.region)}</td>
            <td>${esc(item.shift)}</td>
          </tr>`).join("")}
      </tbody>
    </table>`;
}

function renderForm() {
  const node = document.getElementById("inv-form");
  if (!node) return;
  if (picker) {
    picker.remove();
    picker = null;
  }
  const editor = state.editor;
  if (!editor || editor.kind !== tab) {
    node.innerHTML = `<div class="form-empty"><h2>${tab === "equipment" ? "Cadastro de equipamentos" : "Cadastro de agentes"}</h2><p>Selecione um registro ou crie um novo. O que entrar aqui aparece na central, no mapa e na previsão.</p></div>`;
    return;
  }
  node.innerHTML = editor.kind === "equipment" ? equipmentForm(editor) : agentForm(editor);
  bindForm(node, editor);
  mountPicker(editor);
}

function equipmentForm(editor) {
  const v = editor.values;
  const schema = state.bootstrap.schema;
  return `
    <form class="form" id="editor-form">
      <h2>${editor.mode === "new" ? "Novo equipamento" : "Editar " + esc(v.serial || "equipamento")}</h2>
      ${editor.prefilled ? "<p class='hint'>Equipamento, endereço e identificação vieram da ficha. A manutenção ainda não foi salva: revise e confirme.</p>" : ""}
      <p class="form-error" id="form-error" hidden></p>
      <div class="fields">
        ${selectField("type", "Tipo", schema.types, v.type)}
        ${input("serial", "Número de série", v.serial)}
        ${input("brand", "Marca", v.brand)}
        ${input("model", "Modelo", v.model)}
        ${selectField("agency", "Órgão responsável", schema.agencies.map((id) => ({ id, label: id })), v.agency)}
        ${selectField("status", "Situação", schema.statuses, v.status)}
        ${selectField("maintenance_need", "Necessidade de manutenção", schema.maintenance, v.maintenance_need)}
        ${input("next_maintenance", "Próxima manutenção", v.next_maintenance, "date", false)}
        ${input("installed_at", "Instalado em", v.installed_at, "date", false)}
      </div>
      <fieldset>
        <legend>Características deste tipo</legend>
        <div class="fields" id="attr-fields">${attrFields(v.type, v.attrs || {})}</div>
      </fieldset>
      ${locationFields(v)}
      <label class="field field-wide"><span>Observações</span><textarea name="notes" rows="3">${esc(v.notes || "")}</textarea></label>
      <div class="form-actions">
        <button type="submit" class="primary">Salvar</button>
        ${editor.mode === "edit" ? `<button type="button" class="danger" id="delete-record">Excluir</button>` : ""}
        <button type="button" class="ghost" id="cancel-edit">Cancelar</button>
      </div>
    </form>`;
}

function agentForm(editor) {
  const v = editor.values;
  const schema = state.bootstrap.schema;
  const agencies = [
    { id: "Secretaria de Mobilidade", label: "Secretaria de Mobilidade" },
    { id: "Guarda Municipal", label: "Guarda Municipal" },
    { id: "Polícia Militar", label: "Polícia Militar" },
  ];
  return `
    <form class="form" id="editor-form">
      <h2>${editor.mode === "new" ? "Novo agente" : "Editar " + esc(v.name || "agente")}</h2>
      <p class="form-error" id="form-error" hidden></p>
      <div class="fields">
        ${input("name", "Nome", v.name)}
        ${input("registration", "Matrícula", v.registration)}
        ${selectField("agency", "Órgão", agencies, v.agency)}
        ${input("role", "Função", v.role)}
        ${selectField("shift", "Turno", schema.shifts.map((id) => ({ id, label: id })), v.shift)}
        ${selectField("status", "Situação", schema.agent_statuses, v.status)}
        ${input("phone", "Telefone", v.phone, "text", false)}
        ${input("team", "Equipe", v.team, "text", false)}
      </div>
      ${locationFields(v)}
      <label class="field field-wide"><span>Observações</span><textarea name="notes" rows="3">${esc(v.notes || "")}</textarea></label>
      <div class="form-actions">
        <button type="submit" class="primary">Salvar</button>
        ${editor.mode === "edit" ? `<button type="button" class="danger" id="delete-record">Excluir</button>` : ""}
        <button type="button" class="ghost" id="cancel-edit">Cancelar</button>
      </div>
    </form>`;
}

function locationFields(v) {
  const regions = state.bootstrap.schema.regions;
  return `
    <fieldset>
      <legend>Localização</legend>
      <div class="fields">
        ${selectField("region", "Região", regions, v.region)}
        ${input("neighborhood", "Bairro", v.neighborhood)}
        ${input("city", "Cidade", v.city)}
        ${input("uf", "UF", v.uf)}
        ${input("cep", "CEP", v.cep, "text")}
        ${input("street", "Rua", v.street)}
        ${input("reference", "Referência", v.reference)}
        ${input("lat", "Latitude", v.lat, "number")}
        ${input("lng", "Longitude", v.lng, "number")}
      </div>
      <p class="hint">Referência no formato da rua: número 181, oposto ao número 181, KM 203, S/N, em frente ao Mercado do Tio. O clique no mapa define só a coordenada.</p>
      <div id="picker-map"></div>
    </fieldset>`;
}

function input(name, label, value, type = "text", required = true) {
  const req = required ? "required" : "";
  return `<label class="field"><span>${esc(label)}</span><input name="${esc(name)}" type="${type}" value="${esc(value ?? "")}" ${req} /></label>`;
}

function selectField(name, label, items, current) {
  const options = items.map((item) => {
    const id = typeof item === "string" ? item : item.id;
    const text = typeof item === "string" ? item : (item.label || item.id);
    return `<option value="${esc(id)}" ${id === current ? "selected" : ""}>${esc(text)}</option>`;
  }).join("");
  return `<label class="field"><span>${esc(label)}</span><select name="${esc(name)}">${options}</select></label>`;
}

function attrFields(type, attrs) {
  const spec = state.bootstrap.schema.types.find((item) => item.id === type);
  if (!spec) return "";
  return spec.fields.map((field) => {
    if (field.show_if) {
      const [key, expected] = Object.entries(field.show_if)[0];
      if ((attrs[key] ?? "") !== expected) return "";
    }
    if (field.type === "bool") {
      return `<label class="check field-wide"><input type="checkbox" data-attr="${esc(field.key)}" ${attrs[field.key] ? "checked" : ""}/> ${esc(field.label)}</label>`;
    }
    if (field.type === "select") {
      const options = field.options.map((option) => `<option ${option === attrs[field.key] ? "selected" : ""}>${esc(option)}</option>`).join("");
      return `<label class="field"><span>${esc(field.label)}</span><select data-attr="${esc(field.key)}" ${field.optional ? "" : "required"}>${options}</select></label>`;
    }
    return `<label class="field"><span>${esc(field.label)}</span><input data-attr="${esc(field.key)}" type="${field.type === "number" ? "number" : "text"}" value="${esc(attrs[field.key] ?? "")}" ${field.optional ? "" : "required"} /></label>`;
  }).join("");
}

function bindForm(node, editor) {
  const form = node.querySelector("#editor-form");
  form.addEventListener("submit", (event) => {
    event.preventDefault();
    save(editor, form);
  });
  node.querySelector("#cancel-edit")?.addEventListener("click", () => {
    state.editor = null;
    renderForm();
    renderTable();
  });
  node.querySelector("#delete-record")?.addEventListener("click", () => remove(editor));
  form.querySelector('[name="type"]')?.addEventListener("change", () => {
    editor.values = readEditor(form, editor);
    editor.values.attrs = {};
    renderForm();
  });
  form.querySelectorAll("[data-attr]").forEach((el) => {
    el.addEventListener("change", () => {
      if (el.dataset.attr === "radar_kind") {
        editor.values = readEditor(form, editor);
        renderForm();
      }
    });
  });
  form.querySelector('[name="region"]')?.addEventListener("change", () => {
    const region = state.bootstrap.schema.regions.find((item) => item.id === form.region.value);
    if (!region || editor.coordsTouched) return;
    form.city.value = region.city;
    form.uf.value = region.uf;
    form.lat.value = region.lat;
    form.lng.value = region.lng;
    if (!form.neighborhood.value) form.neighborhood.value = region.id;
    if (picker) picker.setView([region.lat, region.lng], 13);
  });
  form.querySelector('[name="lat"]')?.addEventListener("input", () => {
    editor.coordsTouched = true;
  });
  form.querySelector('[name="cep"]')?.addEventListener("change", async () => {
    const cep = form.cep.value;
    if (cep.replace(/\D/g, "").length !== 8) return;
    try {
      const found = await api.cep(cep);
      if (found.street) form.street.value = found.street;
      if (found.neighborhood) form.neighborhood.value = found.neighborhood;
      if (found.city) form.city.value = found.city;
      if (found.uf) form.uf.value = found.uf;
      if (found.lat && found.lng) {
        form.lat.value = found.lat;
        form.lng.value = found.lng;
        editor.coordsTouched = true;
      }
      toast("Endereço preenchido pelo CEP.");
    } catch (error) {
      toast(error.message, "bad");
    }
  });
}

function mountPicker(editor) {
  const el = document.getElementById("picker-map");
  if (!el || !window.L) return;
  const lat = Number(editor.values.lat) || -22.214;
  const lng = Number(editor.values.lng) || -49.946;
  picker = L.map(el, { zoomControl: false }).setView([lat, lng], 13);
  L.tileLayer("https://tile.openstreetmap.org/{z}/{x}/{y}.png", {
    maxZoom: 19,
    attribution: "&copy; OpenStreetMap",
  }).addTo(picker);
  let marker = L.circleMarker([lat, lng], { radius: 7, color: "#1f4e79", fillColor: "#1f4e79", fillOpacity: 0.9 }).addTo(picker);
  picker.on("click", (event) => {
    editor.coordsTouched = true;
    const form = document.getElementById("editor-form");
    form.lat.value = event.latlng.lat.toFixed(6);
    form.lng.value = event.latlng.lng.toFixed(6);
    marker.setLatLng(event.latlng);
  });
  setTimeout(() => picker.invalidateSize(), 60);
}

function readEditor(form, editor) {
  const data = Object.fromEntries(new FormData(form).entries());
  if (editor.kind === "equipment") {
    data.attrs = {};
    form.querySelectorAll("[data-attr]").forEach((el) => {
      data.attrs[el.dataset.attr] = el.type === "checkbox" ? el.checked : el.value;
    });
  }
  data.lat = data.lat === "" ? null : Number(data.lat);
  data.lng = data.lng === "" ? null : Number(data.lng);
  return data;
}

async function save(editor, form) {
  const body = readEditor(form, editor);
  const error = document.getElementById("form-error");
  try {
    if (editor.kind === "equipment") {
      if (editor.mode === "new") await api.createEquipment(body);
      else await api.updateEquipment(editor.id, body);
    } else if (editor.mode === "new") {
      await api.createAgent(body);
    } else {
      await api.updateAgent(editor.id, body);
    }
    toast("Cadastro salvo. A central e a previsão já usam este registro.");
    state.editor = null;
    renderTable();
    renderForm();
  } catch (err) {
    error.hidden = false;
    error.textContent = err.message;
  }
}

async function remove(editor) {
  const label = editor.kind === "equipment" ? "este equipamento" : "este agente";
  if (!window.confirm(`Excluir ${label}? Ele sai do mapa e da conta da cidade.`)) return;
  try {
    if (editor.kind === "equipment") await api.deleteEquipment(editor.id);
    else await api.deleteAgent(editor.id);
    toast("Registro excluído.");
    state.editor = null;
    if (state.selected?.id === editor.id) state.selected = null;
    renderTable();
    renderForm();
  } catch (err) {
    toast(err.message, "bad");
  }
}

function exportCsv() {
  const rows = tab === "equipment" ? equipmentCsv() : agentCsv();
  const text = rows.map((row) => row.map((cell) => `"${String(cell ?? "").replace(/"/g, '""')}"`).join(";")).join("\n");
  const blob = new Blob(["\ufeff" + text], { type: "text/csv;charset=utf-8" });
  const link = document.createElement("a");
  link.href = URL.createObjectURL(blob);
  link.download = tab === "equipment" ? "fogo-equipamentos.csv" : "fogo-agentes.csv";
  link.click();
  URL.revokeObjectURL(link.href);
}

function equipmentCsv() {
  const header = ["id", "tipo", "série", "marca", "modelo", "órgão", "situação", "manutenção", "próxima", "cep", "rua", "referência", "bairro", "cidade", "uf", "latitude", "longitude", "região"];
  const body = state.bootstrap.equipment.map((item) => [
    item.id, typeLabel(item.type), item.serial, item.brand, item.model, item.agency, item.status,
    item.maintenance_need, item.next_maintenance, item.cep, item.street, item.reference,
    item.neighborhood, item.city, item.uf, item.lat, item.lng, item.region,
  ]);
  return [header, ...body];
}

function agentCsv() {
  const header = ["id", "nome", "matrícula", "órgão", "função", "turno", "situação", "cep", "rua", "referência", "bairro", "cidade", "uf", "latitude", "longitude", "região"];
  const body = state.bootstrap.agents.map((item) => [
    item.id, item.name, item.registration, item.agency, item.role, item.shift, item.status,
    item.cep, item.street, item.reference, item.neighborhood, item.city, item.uf, item.lat, item.lng, item.region,
  ]);
  return [header, ...body];
}

export function afterReload() {
  const main = document.getElementById("main");
  if (main && state.view === "inventario") {
    renderTable();
    if (!state.editor) renderForm();
  }
}
