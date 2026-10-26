async function request(url, options = {}) {
  const response = await fetch(url, {
    headers: {
      "Content-Type": "application/json",
      "X-Session": sessionStorage.getItem("fogo-session") || "",
      ...(options.headers || {}),
    },
    ...options,
  });
  const data = await response.json().catch(() => ({}));
  if (!response.ok) {
    throw new Error(data.error || "Não foi possível concluir a operação.");
  }
  return data;
}

export const api = {
  bootstrap: () => request("/api/bootstrap"),
  predictions: (date) => request("/api/predictions" + (date ? `?date=${date}` : "")),
  login: (email, password) => request("/api/session", { method: "POST", body: JSON.stringify({ email, password }) }),
  users: () => request("/api/users"),
  createUser: (body) => request("/api/users", { method: "POST", body: JSON.stringify(body) }),
  updateUser: (id, body) => request(`/api/users/${id}`, { method: "PATCH", body: JSON.stringify(body) }),
  audit: () => request("/api/audit"),
  geo: (q) => request("/api/geo?q=" + encodeURIComponent(q)),
  createEquipment: (body) => request("/api/equipment", { method: "POST", body: JSON.stringify(body) }),
  updateEquipment: (id, body) => request(`/api/equipment/${id}`, { method: "PUT", body: JSON.stringify(body) }),
  patchEquipment: (id, body) => request(`/api/equipment/${id}`, { method: "PATCH", body: JSON.stringify(body) }),
  deleteEquipment: (id) => request(`/api/equipment/${id}`, { method: "DELETE" }),
  createAgent: (body) => request("/api/agents", { method: "POST", body: JSON.stringify(body) }),
  updateAgent: (id, body) => request(`/api/agents/${id}`, { method: "PUT", body: JSON.stringify(body) }),
  deleteAgent: (id) => request(`/api/agents/${id}`, { method: "DELETE" }),
  ackIncident: (id) => request(`/api/incidents/${id}/ack`, { method: "POST", body: "{}" }),
  dispatch: (id, agentId) => request(`/api/incidents/${id}/dispatch`, { method: "POST", body: JSON.stringify({ agent_id: agentId }) }),
  advance: (id, step, note) => request(`/api/incidents/${id}/advance`, { method: "POST", body: JSON.stringify({ step, note: note || "" }) }),
  planRoute: (body) => request("/api/routes", { method: "POST", body: JSON.stringify(body) }),
  clearRoute: (agentId) => request(`/api/routes/${agentId}`, { method: "DELETE" }),
  replay: (at) => request("/api/replay" + (at ? `?at=${encodeURIComponent(at)}` : "")),
  scenario: (name) => request(`/api/scenarios/${name}`, { method: "POST", body: "{}" }),
  reset: () => request("/api/reset", { method: "POST", body: "{}" }),
  createVehicle: (body) => request("/api/vehicles", { method: "POST", body: JSON.stringify(body) }),
  updateVehicle: (id, body) => request(`/api/vehicles/${id}`, { method: "PUT", body: JSON.stringify(body) }),
  compareVehicles: (incidentId) => request("/api/routing/compare", { method: "POST", body: JSON.stringify({ incident_id: incidentId }) }),
  dispatchVehicle: (id, vehicleId, choice) => request(`/api/incidents/${id}/dispatch-vehicle`, { method: "POST", body: JSON.stringify({ vehicle_id: vehicleId, choice }) }),
  markEvent: (agentId, kind) => request("/api/events", { method: "POST", body: JSON.stringify({ agent_id: agentId, kind }) }),
  cep: (cep) => request("/api/cep/" + encodeURIComponent(cep)),
  createOrder: (body) => request("/api/orders", { method: "POST", body: JSON.stringify(body) }),
  assignOrder: (id, agentId) => request(`/api/orders/${id}/assign`, { method: "POST", body: JSON.stringify({ agent_id: agentId || "" }) }),
  orderStatus: (id, status, note) => request(`/api/orders/${id}/status`, { method: "POST", body: JSON.stringify({ status, note: note || "" }) }),
  chat: (message, confirm) => request("/api/chat", { method: "POST", body: JSON.stringify({ message, confirm: !!confirm }) }),
  briefing: () => request("/api/briefing"),
};
