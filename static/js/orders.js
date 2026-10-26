import { api } from "./api.js";
import { clockLabel, esc } from "./format.js";
import { state } from "./state.js";

const COLUMNS = [
  ["aberta", "Aberta"],
  ["atribuida", "Atribuída"],
  ["em_execucao", "Em execução"],
  ["concluida", "Concluída"],
  ["cancelada", "Cancelada"],
];

export function mount(main) {
  const orders = state.bootstrap.orders || [];
  const late = orders.filter((item) => item.overdue).length;
  main.innerHTML = `
    <section class="page">
      <header class="page-head">
        <h1>Ordens de serviço</h1>
        <p>${orders.length} no quadro. ${late} com o prazo estourado. A abertura automática acontece em mau funcionamento, furto ou manutenção vencida.</p>
      </header>
      <form id="os-new" class="inv-toolbar">
        <select name="equipment_id" required>
          <option value="">Equipamento</option>
          ${(state.bootstrap.equipment || []).map((item) => `<option value="${esc(item.id)}">${esc(item.serial)} · ${esc(item.street || "")}</option>`).join("")}
        </select>
        <select name="kind">
          <option value="corretiva">Corretiva</option>
          <option value="preventiva">Preventiva</option>
          <option value="instalacao">Instalação</option>
          <option value="recolhimento">Recolhimento</option>
        </select>
        <select name="priority">
          <option value="critica">Crítica · 4 h</option>
          <option value="alta" selected>Alta · 24 h</option>
          <option value="media">Média · 72 h</option>
          <option value="baixa">Baixa · 7 dias</option>
        </select>
        <input name="description" required placeholder="Descrição" />
        <button type="submit" class="primary">Abrir OS</button>
      </form>
      <div class="kanban">
        ${COLUMNS.map(([id, label]) => `
          <section data-column="${id}">
            <h2>${label} <span class="hint">${orders.filter((item) => item.status === id).length}</span></h2>
            ${orders.filter((item) => item.status === id).map((item) => card(item)).join("") || "<p class='hint'>Nenhuma.</p>"}
          </section>`).join("")}
      </div>
    </section>`;
  document.getElementById("os-new").addEventListener("submit", async (event) => {
    event.preventDefault();
    const body = Object.fromEntries(new FormData(event.target).entries());
    event.target.querySelector("button").disabled = true;
    try {
      await api.createOrder(body);
    } catch (error) {
      event.target.querySelector("button").disabled = false;
      const { toast } = await import("./format.js");
      toast(error.message, "bad");
    }
  });
  main.querySelectorAll(".os-card").forEach((cardNode) => {
    cardNode.addEventListener("dragstart", (event) => {
      event.dataTransfer.setData("text/plain", cardNode.dataset.order);
    });
  });
  main.querySelectorAll("[data-column]").forEach((column) => {
    column.addEventListener("dragover", (event) => event.preventDefault());
    column.addEventListener("drop", async (event) => {
      event.preventDefault();
      const id = event.dataTransfer.getData("text/plain");
      const status = column.dataset.column;
      if (!id || status === "cancelada" && !window.confirm("Cancelar esta OS?")) return;
      try {
        if (status === "atribuida") await api.assignOrder(id);
        else await api.orderStatus(id, status);
      } catch (error) {
        const { toast } = await import("./format.js");
        toast(error.message, "bad");
      }
    });
  });
}

function card(item) {
  const left = item.seconds_left;
  const clock = left >= 0 ? `faltam ${Math.floor(left / 3600)} h` : `vencida há ${Math.floor(-left / 3600)} h`;
  return `
    <article class="os-card${item.overdue ? " is-late" : ""}" draggable="true" data-order="${esc(item.id)}" data-status="${esc(item.status)}">
      <b>${esc(item.number)}</b>
      <p>${esc(item.serial || "")} · <span class="pill tone-${item.priority === "critica" ? "bad" : item.priority === "alta" ? "warn" : "info"}"><i></i>${esc(item.priority)}</span> · ${esc(item.kind)}</p>
      <p>${esc(item.description || "")}</p>
      <p class="hint">${esc(item.agent_name || "Sem responsável")} · ${clock} · ${esc(clockLabel(item.due_at))}</p>
      <div class="actions">
        ${item.status === "aberta" ? `<button type="button" class="primary" data-action="os-assign" data-id="${esc(item.id)}">Atribuir o mais próximo</button>` : ""}
        ${item.status === "atribuida" ? `<button type="button" class="primary" data-action="os-status" data-id="${esc(item.id)}" data-status="em_execucao">Iniciar</button>` : ""}
        ${item.status === "em_execucao" ? `<button type="button" class="primary" data-action="os-status" data-id="${esc(item.id)}" data-status="concluida">Concluir</button>` : ""}
        ${item.status !== "concluida" && item.status !== "cancelada" ? `<button type="button" class="ghost" data-action="os-status" data-id="${esc(item.id)}" data-status="cancelada">Cancelar</button>` : ""}
        <button type="button" class="ghost" data-action="os-pdf" data-id="${esc(item.id)}">PDF</button>
      </div>
    </article>`;
}

export function destroy() {}
