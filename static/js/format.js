import { state } from "./state.js";

export function esc(value) {
  return String(value ?? "").replace(/[&<>"']/g, (char) => ({
    "&": "&amp;",
    "<": "&lt;",
    ">": "&gt;",
    '"': "&quot;",
    "'": "&#39;",
  }[char]));
}

export function fmt(value, digits = 1) {
  return Number(value || 0).toLocaleString("pt-BR", {
    minimumFractionDigits: digits,
    maximumFractionDigits: digits,
  });
}

export function clockLabel(iso) {
  if (!iso) return "—";
  return new Intl.DateTimeFormat("pt-BR", {
    day: "2-digit",
    month: "short",
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
  }).format(new Date(iso));
}

export function ago(iso, nowIso) {
  if (!iso) return "sem telemetria";
  const now = nowIso ? new Date(nowIso).getTime() : Date.now();
  const seconds = Math.max(0, (now - new Date(iso).getTime()) / 1000);
  if (seconds < 20) return "agora";
  if (seconds < 60) return `há ${Math.floor(seconds)} s`;
  if (seconds < 3600) return `há ${Math.floor(seconds / 60)} min`;
  if (seconds < 86400) return `há ${Math.floor(seconds / 3600)} h`;
  return `há ${Math.floor(seconds / 86400)} dias`;
}

const STATUS = {
  operacional: ["Operacional", "ok"],
  mau_funcionamento: ["Mau funcionamento", "bad"],
  em_manutencao: ["Em manutenção", "info"],
  desativado: ["Desativado", "mute"],
  furtado: ["Furtado", "bad"],
  ainda_nao_instalado: ["Não instalado", "install"],
  em_atividade: ["Em atividade", "ok"],
  em_deslocamento: ["Em deslocamento", "info"],
  em_pausa: ["Em pausa", "warn"],
  fora_de_servico: ["Fora de serviço", "mute"],
  aberto: ["Aguardando equipe", "bad"],
  no_local: ["No local", "info"],
  em_atendimento: ["Em atendimento", "info"],
  encerrada: ["Encerrada", "mute"],
  ciencia: ["Encerrada", "mute"],
  disponivel: ["Disponível", "ok"],
  indisponivel: ["Indisponível", "mute"],
  critica: ["Crítica", "bad"],
  alta: ["Alta", "warn"],
  media: ["Média", "info"],
  baixa: ["Baixa", "mute"],
};

const FLAGS = {
  imediata: ["Manutenção imediata", "bad"],
  atrasada: ["Manutenção atrasada", "warn"],
  proxima: ["Manutenção em até 7 dias", "warn"],
};

export function statusMeta(id) {
  return STATUS[id] || [id || "—", "mute"];
}

export function flagMeta(id) {
  return FLAGS[id] || null;
}

export function isCritical(id) {
  return id === "critica";
}

export function status(id) {
  const [label, tone] = statusMeta(id);
  const critical = isCritical(id);
  return `<span class="status${critical ? " is-critical" : ""}"><i class="dot-${tone}"></i>${esc(label)}</span>`;
}

export function pill(id) {
  return status(id);
}

export function typeById(id) {
  return state.bootstrap?.schema.types.find((item) => item.id === id);
}

export function typeLabel(id) {
  return typeById(id)?.label || id;
}

const ICONS = {
  radar: '<circle cx="12" cy="12" r="2.4"/><path d="M12 3.5v3.2M12 17.3V21M3.5 12h3.2M17.3 12H21"/><path d="M6.4 6.4l2.2 2.2M15.4 15.4l2.2 2.2M17.6 6.4l-2.2 2.2M8.6 15.4l-2.2 2.2"/>',
  camera: '<path d="M3.5 8.5h9.2L15 6h5.5v12.5h-17z"/><circle cx="10" cy="13" r="2.3"/>',
  balanca: '<path d="M12 4v16M5 20h14"/><path d="M12 7l-6 5h12z"/><path d="M6 12l-2 4h4zM18 12l-2 4h4z"/>',
  veiculo_autonomo: '<path d="M4 14h16v3H4z"/><path d="M6 14l2-4h8l2 4"/><circle cx="7.5" cy="17.5" r="1.3"/><circle cx="16.5" cy="17.5" r="1.3"/>',
  cancela: '<path d="M5 18V8M5 8h14"/><path d="M5 12h9"/><path d="M16 8v4"/>',
  transporte: '<path d="M3 13h18v4H3z"/><path d="M6 13V9h7l3 4"/><circle cx="7" cy="17.5" r="1.3"/><circle cx="16" cy="17.5" r="1.3"/>',
  totem: '<rect x="8" y="3" width="8" height="18" rx="1.2"/><path d="M10 7h4M10 10h4M11 18h2"/>',
  patinete: '<circle cx="7" cy="17" r="2"/><circle cx="17" cy="17" r="2"/><path d="M7 17l3-8h5l2 4"/><path d="M12 9V5h3"/>',
  moto_agente: '<circle cx="7" cy="16" r="2.2"/><circle cx="17" cy="16" r="2.2"/><path d="M7 16l3-6h4l3 4M10 10l-2-3"/>',
  viatura_gm: '<path d="M12 3.5l6.5 3v5.2c0 3.4-2.6 5.6-6.5 7.3-3.9-1.7-6.5-3.9-6.5-7.3V6.5z"/>',
  viatura_pm: '<path d="M12 3.5l6.5 3v5.2c0 3.4-2.6 5.6-6.5 7.3-3.9-1.7-6.5-3.9-6.5-7.3V6.5z"/><path d="M12 8v6M9.5 11H14.5"/>',
  agent: '<circle cx="12" cy="8" r="3"/><path d="M5.5 19.5c1.2-3.2 3.3-4.8 6.5-4.8s5.3 1.6 6.5 4.8"/>',
  incident: '<path d="M12 4.5l7.5 13h-15z"/><path d="M12 10v3.5M12 16.2v.4"/>',
};

export function icon(name) {
  const body = ICONS[name] || ICONS.incident;
  return `<svg viewBox="0 0 24 24" aria-hidden="true">${body}</svg>`;
}

export function matchesEquipment(eq, filters) {
  if (filters.type && eq.type !== filters.type) return false;
  if (filters.status && eq.status !== filters.status) return false;
  if (filters.region && eq.region !== filters.region) return false;
  if (filters.neighborhood && `${eq.neighborhood}|${eq.city}` !== filters.neighborhood) return false;
  if (filters.agency && eq.agency !== filters.agency) return false;
  if (filters.role && typeById(eq.type)?.role !== filters.role) return false;
  if (filters.maintenance === "urgente" && !["imediata", "atrasada"].includes(eq.maintenance_flag) && eq.status !== "mau_funcionamento") {
    return false;
  }
  if (filters.maintenance === "proxima" && eq.maintenance_flag !== "proxima") return false;
  if (filters.q) {
    const blob = [eq.serial, eq.brand, eq.model, eq.street, eq.neighborhood, eq.city, eq.reference, eq.agency, typeLabel(eq.type)]
      .join(" ")
      .toLowerCase();
    if (!blob.includes(filters.q.trim().toLowerCase())) return false;
  }
  return true;
}

export function matchesAgent(agent, filters) {
  if (!filters.showAgents) return false;
  if (filters.type || filters.status || filters.maintenance || filters.role) return false;
  if (filters.region && agent.region !== filters.region) return false;
  if (filters.neighborhood && `${agent.neighborhood}|${agent.city}` !== filters.neighborhood) return false;
  if (filters.agency && agent.agency !== filters.agency) return false;
  if (filters.q) {
    const blob = [agent.name, agent.registration, agent.role, agent.team, agent.street, agent.neighborhood].join(" ").toLowerCase();
    if (!blob.includes(filters.q.trim().toLowerCase())) return false;
  }
  return true;
}

export function optionList(items, placeholder) {
  const head = `<option value="">${esc(placeholder)}</option>`;
  return head + items.map((item) => `<option value="${esc(item.id)}">${esc(item.label)}</option>`).join("");
}

export function toast(text, tone = "ok") {
  const node = document.createElement("div");
  node.className = `toast tone-${tone}`;
  node.setAttribute("role", "status");
  node.textContent = text;
  document.body.appendChild(node);
  setTimeout(() => node.remove(), 4600);
}
