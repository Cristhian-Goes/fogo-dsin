import { api } from "./api.js";
import { esc, toast } from "./format.js";
import { state } from "./state.js";

const DEMOS = [
  ["operador@fogo.local", "Operador da CCO"],
  ["supervisor@fogo.local", "Supervisor"],
  ["municipal.marilia@fogo.local", "Gestor municipal"],
  ["estadual.sp@fogo.local", "Gestor estadual"],
  ["admin@fogo.local", "Administrador"],
  ["agente@fogo.local", "Agente de campo"],
  ["auditor@fogo.local", "Auditor"],
];

export function destroy() {}

export async function mount(main) {
  main.innerHTML = `<section class="page"><p>Carregando acessos…</p></section>`;
  const me = state.user;
  let users = [];
  let roles = [];
  let audit = [];
  let error = "";
  if (me?.can_admin) {
    try {
      const payload = await api.users();
      users = payload.users;
      roles = payload.roles;
    } catch (err) {
      error = err.message;
    }
  }
  if (me && (me.role === "administrador" || me.role === "gestor_estadual")) {
    try {
      audit = (await api.audit()).audit || [];
    } catch (err) {
      error = error || err.message;
    }
  }
  main.innerHTML = `
    <section class="page">
      <p class="crumb"><button type="button" data-action="go" data-view="cco">Visão geral</button> / Acessos</p>
      <h1>Acessos</h1>
      <p class="hint">Sessão atual: ${esc(me ? me.name + " · " + me.role_label : "nenhuma")}. A senha das contas de demonstração é <code>demonstracao</code>.</p>
      <h2>Entrar com outro perfil</h2>
      <div class="filters">
        ${DEMOS.map(([email, label]) => `<button type="button" class="ghost" data-login="${esc(email)}">${esc(label)}</button>`).join("")}
      </div>
      ${error ? `<p class="form-error">${esc(error)}</p>` : ""}
      ${me?.can_admin ? adminBlock(users, roles) : "<p>Este perfil consulta a operação. A administração de usuários fica com o administrador geral.</p>"}
      ${audit.length ? `<h2>Auditoria</h2><ul class="timeline">${audit.slice(0, 20).map((item) => `<li><time>${esc(item.at)}</time>${esc(item.user)} · ${esc(item.action)} · ${esc(item.detail)}</li>`).join("")}</ul>` : ""}
    </section>`;
  main.querySelectorAll("[data-login]").forEach((button) => {
    button.addEventListener("click", async () => {
      try {
        const session = await api.login(button.dataset.login, "demonstracao");
        sessionStorage.setItem("fogo-session", session.token);
        state.user = session.user;
        toast(`Sessão de ${session.user.role_label}.`);
        location.reload();
      } catch (err) {
        toast(err.message, "bad");
      }
    });
  });
  const form = document.getElementById("user-form");
  form?.addEventListener("submit", async (event) => {
    event.preventDefault();
    const data = Object.fromEntries(new FormData(form).entries());
    try {
      await api.createUser(data);
      toast("Usuário criado. A conta ainda não entrou sozinha: a pessoa entra com o e-mail e a senha.");
      mount(main);
    } catch (err) {
      toast(err.message, "bad");
    }
  });
  main.querySelectorAll("[data-user]").forEach((button) => {
    button.addEventListener("click", async () => {
      try {
        await api.updateUser(button.dataset.user, { active: button.dataset.active !== "true" });
        toast("Situação da conta atualizada.");
        mount(main);
      } catch (err) {
        toast(err.message, "bad");
      }
    });
  });
}

function adminBlock(users, roles) {
  return `
    <h2>Usuários</h2>
    <ul class="rows">
      ${users.map((user) => `
        <li class="stop">
          <span><b>${esc(user.name)}</b> · ${esc(user.role_label)}<br><small>${esc(user.email)} · ${esc(user.uf || "sem UF")} ${esc(user.city || "")} · ${user.active ? "ativa" : "desativada"}</small></span>
          <button type="button" class="ghost" data-user="${esc(user.id)}" data-active="${user.active ? "true" : "false"}">${user.active ? "Desativar" : "Ativar"}</button>
        </li>`).join("") || "<li>Nenhum usuário.</li>"}
    </ul>
    <h2>Novo usuário</h2>
    <form class="form" id="user-form">
      <div class="fields">
        <label class="field">Nome<input name="name" required /></label>
        <label class="field">E-mail<input name="email" type="email" required /></label>
        <label class="field">Senha<input name="password" type="password" required minlength="8" /></label>
        <label class="field">Perfil<select name="role">${roles.map((role) => `<option value="${esc(role.id)}">${esc(role.label)}</option>`).join("")}</select></label>
        <label class="field">UF<input name="uf" maxlength="2" placeholder="SP" /></label>
        <label class="field">Município<input name="city" placeholder="Marília" /></label>
      </div>
      <button type="submit" class="primary">Cadastrar</button>
    </form>`;
}
