import { esc, status, statusMeta } from "./format.js";

const sessions = new Map();

function prefs(id) {
  try {
    return JSON.parse(localStorage.getItem(`fogo-table:${id}`) || "{}");
  } catch {
    return {};
  }
}

function savePrefs(id, session) {
  localStorage.setItem(`fogo-table:${id}`, JSON.stringify({
    density: session.density,
    hidden: session.hidden,
  }));
}

function sessionOf(spec) {
  const current = sessions.get(spec.id);
  if (current) return current;
  const stored = prefs(spec.id);
  const created = {
    sortKey: spec.sort || spec.columns[0]?.key || "",
    sortDir: spec.dir || 1,
    page: 0,
    q: "",
    density: stored.density === "compact" ? "compact" : "comfort",
    hidden: Array.isArray(stored.hidden) ? stored.hidden : [],
    filters: {},
    picked: new Set(spec.picked || []),
  };
  sessions.set(spec.id, created);
  return created;
}

function textOf(column, row) {
  const value = column.value ? column.value(row) : row[column.key];
  return value == null ? "" : String(value);
}

function shown(column, row) {
  const raw = textOf(column, row);
  return column.status ? statusMeta(raw)[0] : raw;
}

function visibleColumns(spec, session) {
  return spec.columns.filter((column) => !session.hidden.includes(column.key));
}

function filteredRows(spec, session) {
  const columns = spec.columns.filter((column) => column.key !== "menu");
  const query = session.q.trim().toLowerCase();
  return (spec.rows || []).filter((row) => {
    for (const column of columns) {
      const chosen = session.filters[column.key];
      if (chosen && shown(column, row) !== chosen) return false;
    }
    if (!query) return true;
    return columns.some((column) => shown(column, row).toLowerCase().includes(query));
  });
}

function sortedRows(rows, spec, session) {
  const column = spec.columns.find((item) => item.key === session.sortKey);
  if (!column) return rows;
  return rows.slice().sort((a, b) => shown(column, a).localeCompare(shown(column, b), "pt-BR", { numeric: true }) * session.sortDir);
}

function cellHtml(column, row) {
  if (column.menu) return "";
  if (column.html) return column.html(row);
  if (column.status) return status(textOf(column, row));
  const text = textOf(column, row) || "—";
  return esc(text);
}

function exportCsv(spec, rows, columns) {
  const head = columns.map((column) => column.label || column.key);
  const body = rows.map((row) => columns.map((column) => textOf(column, row)));
  const csv = [head, ...body].map((line) => line.map((value) => `"${String(value).replaceAll('"', '""')}"`).join(";")).join("\n");
  const blob = new Blob([`\uFEFF${csv}`], { type: "text/csv;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = `${spec.id}.csv`;
  link.click();
  URL.revokeObjectURL(url);
}

export function mountTable(host, spec) {
  if (!host) return;
  const session = sessionOf(spec);
  if (spec.loading) {
    host.innerHTML = `<div class="data-skel">${"<span></span>".repeat(8)}</div>`;
    return;
  }
  const columns = visibleColumns(spec, session);
  const dataColumns = columns.filter((column) => !column.menu);
  const rows = sortedRows(filteredRows(spec, session), spec, session);
  const pageSize = session.density === "compact" ? 24 : 16;
  const pages = Math.max(1, Math.ceil(rows.length / pageSize));
  if (session.page >= pages) session.page = pages - 1;
  const slice = rows.slice(session.page * pageSize, session.page * pageSize + pageSize);
  const picked = session.picked;
  host.innerHTML = `
    <div class="data-bar">
      <input type="search" data-table-q value="${esc(session.q)}" placeholder="Buscar" aria-label="Buscar na tabela" />
      <button type="button" class="ghost" data-table-density>${session.density === "compact" ? "Confortável" : "Compacta"}</button>
      <details class="row-menu">
        <summary>Colunas</summary>
        <div>${spec.columns.filter((column) => column.label).map((column) => `
          <label class="check"><input type="checkbox" data-table-col="${esc(column.key)}" ${session.hidden.includes(column.key) ? "" : "checked"}/> ${esc(column.label)}</label>`).join("")}</div>
      </details>
      <button type="button" class="ghost" data-table-csv>CSV</button>
      ${spec.selectable && picked.size ? `<span class="hint">${picked.size} selecionada(s)</span>
        <button type="button" class="ghost" data-table-batch="assign">Atribuir</button>
        <button type="button" class="ghost" data-table-batch="em_execucao">Iniciar</button>` : ""}
    </div>
    ${rows.length ? `
    <div class="table-wrap">
      <table class="data-table ${session.density === "compact" ? "is-compact" : ""}">
        <thead><tr>
          ${spec.selectable ? "<th></th>" : ""}
          ${columns.map((column) => {
            const on = session.sortKey === column.key;
            const mark = on ? (session.sortDir > 0 ? " ↑" : " ↓") : "";
            const choices = column.filter ? [...new Set((spec.rows || []).map((row) => shown(column, row)).filter(Boolean))].sort((a, b) => a.localeCompare(b, "pt-BR")) : [];
            return `<th class="${column.align === "right" ? "num" : ""}">
              <button type="button" class="sort" data-table-sort="${esc(column.key)}">${esc(column.label || "")}${mark}</button>
              ${choices.length ? `<select data-table-filter="${esc(column.key)}" aria-label="Filtrar ${esc(column.label)}"><option value="">Todos</option>${choices.map((item) => `<option ${session.filters[column.key] === item ? "selected" : ""}>${esc(item)}</option>`).join("")}</select>` : ""}
            </th>`;
          }).join("")}
        </tr></thead>
        <tbody>
          ${slice.map((row) => {
            const id = spec.rowId(row);
            const classes = [
              spec.selected?.(row) ? "is-selected" : "",
              spec.critical?.(row) ? "is-critical" : "",
            ].filter(Boolean).join(" ");
            return `<tr data-row="${esc(id)}" class="${classes}">
              ${spec.selectable ? `<td><input type="checkbox" data-table-pick="${esc(id)}" ${picked.has(id) ? "checked" : ""} aria-label="Selecionar"/></td>` : ""}
              ${columns.map((column) => {
                if (column.menu) {
                  const items = spec.menu?.(row) || [];
                  return `<td class="menu-cell">${items.length ? `<details class="row-menu"><summary aria-label="Ações">⋯</summary><div>${items.join("")}</div></details>` : ""}</td>`;
                }
                const raw = shown(column, row);
                return `<td class="${column.align === "right" ? "num" : "clip"}${column.primary ? " primary" : ""}" title="${esc(raw)}">${cellHtml(column, row)}</td>`;
              }).join("")}
            </tr>`;
          }).join("")}
        </tbody>
      </table>
    </div>
    <div class="pager"><button type="button" class="ghost" data-table-page="-1" ${session.page === 0 ? "disabled" : ""}>Anterior</button><span>${session.page + 1} de ${pages}</span><button type="button" class="ghost" data-table-page="1" ${session.page + 1 >= pages ? "disabled" : ""}>Próxima</button></div>` : `<p class="hint">${esc(spec.empty || "Nenhum registro.")}</p>`}`;
  const redraw = () => mountTable(host, spec);
  host.querySelector("[data-table-q]")?.addEventListener("input", (event) => {
    session.q = event.target.value;
    session.page = 0;
    redraw();
    host.querySelector("[data-table-q]")?.focus();
  });
  host.querySelector("[data-table-density]")?.addEventListener("click", () => {
    session.density = session.density === "compact" ? "comfort" : "compact";
    savePrefs(spec.id, session);
    redraw();
  });
  host.querySelector("[data-table-csv]")?.addEventListener("click", () => {
    if (spec.exportCsv) spec.exportCsv();
    else exportCsv(spec, rows, dataColumns);
  });
  host.querySelectorAll("[data-table-col]").forEach((input) => {
    input.addEventListener("change", () => {
      const key = input.dataset.tableCol;
      session.hidden = input.checked ? session.hidden.filter((item) => item !== key) : [...session.hidden, key];
      if (session.hidden.length >= spec.columns.length) session.hidden = session.hidden.filter((item) => item !== key);
      savePrefs(spec.id, session);
      redraw();
    });
  });
  host.querySelectorAll("[data-table-sort]").forEach((button) => {
    button.addEventListener("click", () => {
      const key = button.dataset.tableSort;
      if (!key) return;
      if (session.sortKey === key) session.sortDir *= -1;
      else {
        session.sortKey = key;
        session.sortDir = 1;
      }
      session.page = 0;
      redraw();
    });
  });
  host.querySelectorAll("[data-table-filter]").forEach((select) => {
    select.addEventListener("change", () => {
      session.filters[select.dataset.tableFilter] = select.value;
      session.page = 0;
      redraw();
    });
  });
  host.querySelectorAll("[data-table-page]").forEach((button) => {
    button.addEventListener("click", () => {
      session.page += Number(button.dataset.tablePage);
      redraw();
    });
  });
  host.querySelectorAll("[data-table-pick]").forEach((input) => {
    input.addEventListener("change", () => {
      if (input.checked) picked.add(input.dataset.tablePick);
      else picked.delete(input.dataset.tablePick);
      spec.onPick?.(picked);
      redraw();
    });
  });
  host.querySelectorAll("[data-table-batch]").forEach((button) => {
    button.addEventListener("click", () => spec.onBatch?.([...picked], button.dataset.tableBatch));
  });
  host.querySelectorAll("tr[data-row]").forEach((row) => {
    row.addEventListener("click", (event) => {
      if (event.target.closest("button, a, input, summary, details, select")) return;
      const item = (spec.rows || []).find((entry) => spec.rowId(entry) === row.dataset.row);
      if (item) spec.onRow?.(item);
    });
  });
}
