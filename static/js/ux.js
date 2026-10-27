import { esc } from "./format.js";
import { state } from "./state.js";

const TITLES = {
  cco: "Central",
  inteligencia: "Fila de decisões",
  ordens: "Ordens de serviço",
  rotas: "Rotas",
  inventario: "Equipamentos",
  agentes: "Agentes",
  previsao: "Previsões",
  impacto: "Impacto",
  acessos: "Configurações",
  ocorrencias: "Ocorrências",
  frota: "Veículos",
  regioes: "Regiões",
  alertas: "Alertas",
  linha: "Linha do tempo",
  historico: "Histórico",
  campo: "Modo campo",
  financeiro: "Financeiro",
  conformidade: "Conformidade",
  dimensionamento: "Equipes",
  conhecimento: "Conhecimento",
  integridade: "Auditoria",
  valor: "Valor entregue",
};

const GLYPH = {
  cco: "M4 10l8-6 8 6v9H4z",
  inteligencia: "M12 4v2M12 18v2M4 12h2M18 12h2M6 6l1.5 1.5M16.5 16.5L18 18M18 6l-1.5 1.5M7.5 16.5L6 18M12 8a4 4 0 100 8 4 4 0 000-8z",
  ordens: "M6 4h9l3 3v13H6zM9 12h6M9 16h6",
  rotas: "M6 18c4-8 8-8 12 0M8 8h.1M16 8h.1",
  inventario: "M5 8h14v11H5zM8 8V5h8v3",
  agentes: "M12 8a3 3 0 110-6 3 3 0 010 6zM5 20c1-4 3.5-6 7-6s6 2 7 6",
  previsao: "M4 16l4-5 4 3 6-7",
  impacto: "M5 19V9M12 19V5M19 19v-7",
  acessos: "M12 3l7 3v6c0 4-3 6.5-7 8-4-1.5-7-4-7-8V6z",
  ocorrencias: "M12 4l8 14H4z",
  frota: "M4 14h16v3H4zM6 14l2-4h8l2 4",
  regioes: "M4 8l8-4 8 4-8 4zM4 14l8 4 8-4",
  alertas: "M6 16V10a6 6 0 1112 0v6H6zM10 18a2 2 0 004 0",
  linha: "M5 7h14M5 12h14M5 17h8",
  historico: "M12 7v6l4 2M12 4a8 8 0 100 16 8 8 0 000-16z",
  campo: "M8 4h8v16H8z",
  financeiro: "M5 19V9M12 19V5M19 19v-7",
  conformidade: "M12 3l7 3v6c0 4-3 6.5-7 8-4-1.5-7-4-7-8V6z",
  dimensionamento: "M5 20V10M12 20V6M19 20v-8",
  conhecimento: "M6 5h9a3 3 0 013 3v12H9a3 3 0 00-3 3z",
  integridade: "M8 12l3 3 5-6",
  valor: "M4 16l5-5 3 3 8-8",
};

export function title(view) {
  return TITLES[view] || "Central";
}

export function glyph(id) {
  return `<svg viewBox="0 0 24 24" aria-hidden="true"><path d="${GLYPH[id] || GLYPH.cco}"/></svg>`;
}

export function openPalette(go, openTarget) {
  let node = document.getElementById("palette");
  if (!node) {
    node = document.createElement("div");
    node.id = "palette";
    node.className = "palette";
    node.setAttribute("role", "dialog");
    node.setAttribute("aria-label", "Busca e comandos");
    node.innerHTML = `
      <h2>Ir para ou buscar</h2>
      <label class="sr" for="palette-q">Comando</label>
      <input id="palette-q" placeholder="Equipamento, bairro, agente, OS ou tela" />
      <div id="palette-list"></div>`;
    document.body.appendChild(node);
    node.querySelector("#palette-q").addEventListener("input", (event) => paintPalette(event.target.value, go, openTarget));
    node.querySelector("#palette-q").addEventListener("keydown", (event) => {
      if (event.key === "Escape") closePalette();
    });
  }
  node.hidden = false;
  const input = node.querySelector("#palette-q");
  input.value = "";
  input.focus();
  paintPalette("", go, openTarget);
}

export function closePalette() {
  const node = document.getElementById("palette");
  if (node) node.hidden = true;
}

export function openHelp() {
  let node = document.getElementById("help");
  if (!node) {
    node = document.createElement("div");
    node.id = "help";
    node.className = "help";
    node.innerHTML = `
      <h2>Atalhos</h2>
      <p><b>Ctrl+K</b> busca e comandos</p>
      <p><b>/</b> abre o chat</p>
      <p><b>g</b> depois <b>m</b> abre a central</p>
      <p><b>?</b> esta ajuda</p>
      <p><b>Esc</b> fecha o painel</p>
      <button type="button" class="ghost" id="help-close">Fechar</button>`;
    document.body.appendChild(node);
    node.querySelector("#help-close").addEventListener("click", () => node.remove());
  }
}

export function maybeTour(show) {
  if (localStorage.getItem("fogo-tour") === "done") return;
  const open = state.user?.views || [];
  if (open.length && ["cco", "inteligencia", "ordens", "rotas"].some((view) => !open.includes(view))) return;
  const steps = [
    ["cco", "Central", "O mapa fica no centro. A coluna da direita responde o que exige atenção agora."],
    ["inteligencia", "Fila de decisões", "Até 7 ações, com motivo e responsável."],
    ["ordens", "Ordens de serviço", "Quadro, lista ou mapa. O detalhe fica à direita."],
    ["rotas", "Rotas", "Otimizar mostra a diferença em km e minutos."],
    ["inteligencia", "Demonstração", "O botão Rodar cenário de demonstração percorre o roteiro do vídeo."],
  ];
  let index = 0;
  const node = document.createElement("div");
  node.className = "tour";
  node.setAttribute("role", "dialog");
  node.setAttribute("aria-label", "Tour da central");
  document.body.appendChild(node);
  const draw = () => {
    const [view, name, text] = steps[index];
    show(view);
    node.innerHTML = `
      <h2>${index + 1} de ${steps.length} · ${esc(name)}</h2>
      <p>${esc(text)}</p>
      <div class="actions">
        <button type="button" class="ghost" id="tour-skip">Pular</button>
        <button type="button" class="primary" id="tour-next">${index === steps.length - 1 ? "Concluir" : "Próximo"}</button>
      </div>`;
    node.querySelector("#tour-skip").onclick = finish;
    node.querySelector("#tour-next").onclick = () => {
      if (index === steps.length - 1) finish();
      else { index += 1; draw(); }
    };
  };
  const finish = () => {
    localStorage.setItem("fogo-tour", "done");
    node.remove();
    show("cco");
  };
  draw();
}

function paintPalette(query, go, openTarget) {
  const list = document.getElementById("palette-list");
  if (!list) return;
  const q = query.trim().toLowerCase();
  const open = state.user?.views;
  const destination = { equipment: "inventario", agent: "agentes", order: "ordens", region: "regioes" };
  const canOpen = (item) => {
    if (!Array.isArray(open) || !open.length) return true;
    if (item.kind === "view") return open.includes(item.id);
    const view = destination[item.kind];
    return !view || open.includes(view);
  };
  const commands = Object.entries(TITLES).map(([id, label]) => ({ kind: "view", id, label: `Ir para ${label}` }));
  const pack = state.bootstrap || {};
  const rows = [
    ...commands,
    ...(pack.equipment || []).slice(0, 80).map((item) => ({ kind: "equipment", id: item.id, label: `${item.serial} · ${item.neighborhood || ""}` })),
    ...(pack.agents || []).map((item) => ({ kind: "agent", id: item.id, label: `${item.name} · ${item.team}` })),
    ...(pack.orders || []).slice(0, 40).map((item) => ({ kind: "order", id: item.id, label: `${item.number} · ${item.serial || ""}` })),
    ...(pack.regions || []).map((item) => ({ kind: "region", id: item.region, label: item.region })),
  ].filter((item) => canOpen(item) && (!q || item.label.toLowerCase().includes(q))).slice(0, 8);
  list.innerHTML = rows.map((item) => `<button type="button" data-palette="${esc(item.kind)}" data-id="${esc(item.id)}">${esc(item.label)}</button>`).join("") || "<p class='hint'>Nada encontrado. Limpe a busca para ver as telas.</p>";
  list.querySelectorAll("button").forEach((button) => {
    button.addEventListener("click", () => {
      closePalette();
      if (button.dataset.palette === "view") go(button.dataset.id);
      else if (button.dataset.palette === "order") go("ordens");
      else openTarget(button.dataset.palette === "equipment" ? "equipment" : button.dataset.palette, button.dataset.id);
    });
  });
}
