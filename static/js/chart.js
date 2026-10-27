import { esc } from "./format.js";

export function chartPanel(points, selected, formatAxis, label) {
  const rows = Array.isArray(points) ? points : [];
  if (!rows.length) {
    return `<div class="chart-panel"><p class="hint">Sem série para desenhar.</p></div>`;
  }
  const values = rows.map((item) => Number(item.value) || 0);
  const max = Math.max(...values, 1);
  const width = 640;
  const height = 220;
  const left = 52;
  const right = 16;
  const top = 16;
  const bottom = 32;
  const plotW = width - left - right;
  const plotH = height - top - bottom;
  const xAt = (index) => (rows.length === 1 ? left + plotW / 2 : left + (index * plotW) / (rows.length - 1));
  const yAt = (value) => top + plotH - (Math.max(0, value) / max) * plotH;
  const line = values.map((value, index) => `${xAt(index)},${yAt(value)}`).join(" ");
  const labelStep = rows.length > 8 ? Math.ceil(rows.length / 6) : 1;
  const grids = [0, 0.5, 1].map((part) => {
    const y = yAt(max * part);
    return `<line class="grid" x1="${left}" y1="${y}" x2="${width - right}" y2="${y}"></line><text class="axis" x="${left - 8}" y="${y + 4}" text-anchor="end">${esc(formatAxis(max * part))}</text>`;
  }).join("");
  const dots = rows.map((item, index) => {
    const on = index === selected ? " is-on" : "";
    const showLabel = index % labelStep === 0 || index === selected || index === rows.length - 1;
    const caption = `${item.label}: ${item.display || item.value}`;
    return `<g class="chart-point${on}">
      <circle data-point="${index}" role="button" tabindex="0" aria-label="${esc(caption)}" aria-pressed="${index === selected ? "true" : "false"}" cx="${xAt(index)}" cy="${yAt(values[index])}" r="${index === selected ? 6 : 4}"></circle>
      ${showLabel ? `<text class="tick" x="${xAt(index)}" y="${height - 8}" text-anchor="middle">${esc(item.label)}</text>` : ""}
    </g>`;
  }).join("");
  const current = rows[selected] || rows[rows.length - 1];
  return `<div class="chart-panel" data-chart="${esc(label || "serie")}">
    <svg class="chart" viewBox="0 0 ${width} ${height}" role="group" aria-label="${esc(label || "Série")}">
      ${grids}
      <polyline class="line" points="${line}"></polyline>
      ${dots}
    </svg>
    <p class="chart-readout" aria-live="polite"><b>${esc(current.display || String(current.value))}</b> ${esc(current.detail || current.label || "")}</p>
  </div>`;
}

export function bindChart(root, onSelect) {
  if (!root) return;
  const nodes = [...root.querySelectorAll("[data-point]")];
  const go = (index) => {
    if (index < 0 || index >= nodes.length) return;
    onSelect(index);
  };
  nodes.forEach((node) => {
    const index = Number(node.dataset.point);
    node.addEventListener("click", () => go(index));
    node.addEventListener("keydown", (event) => {
      if (event.key === "Enter" || event.key === " ") {
        event.preventDefault();
        go(index);
      }
      if (event.key === "ArrowRight") {
        event.preventDefault();
        go(Math.min(nodes.length - 1, index + 1));
      }
      if (event.key === "ArrowLeft") {
        event.preventDefault();
        go(Math.max(0, index - 1));
      }
    });
  });
}
