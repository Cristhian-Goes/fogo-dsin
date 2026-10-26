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
  let groups = [];
  let audit = [];
  let error = "";
  if (me?.can_admin) {
    try {
      const payload = await api.users();
      users = payload.users;
      roles = payload.roles;
      groups = payload.groups || [];
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
      <p class="hint">Sessão atual: ${esc(me ? `${me.name} · ${me.role_label} · ${me.group_name || "sem grupo"}` : "nenhuma")}. As contas de demonstração usam a senha <code>demonstracao</code>. O administrador entra com a própria conta.</p>
      <h2>Entrar com outro perfil</h2>
      <div class="filters">
        ${DEMOS.map(([email, label]) => `<button type="button" class="ghost" data-login="${esc(email)}">${esc(label)}</button>`).join("")}
      </div>
      ${error ? `<p class="form-error">${esc(error)}</p>` : ""}
      ${me?.can_admin ? adminBlock(users, roles, groups) : "<p>Este perfil consulta a operação. A administração de usuários fica com o administrador geral.</p>"}
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
      toast("Usuário criado. A pessoa entra com o usuário e a senha desta conta.");
      mount(main);
    } catch (err) {
      toast(err.message, "bad");
    }
  });
  document.getElementById("user-group")?.addEventListener("change", (event) => {
    const group = groups.find((item) => item.id === event.target.value);
    const role = document.getElementById("user-role");
    if (group && role) role.value = group.role;
  });
  document.getElementById("group-form")?.addEventListener("submit", async (event) => {
    event.preventDefault();
    const data = Object.fromEntries(new FormData(event.target).entries());
    try {
      await api.createGroup(data);
      toast("Grupo criado. Novos usuários já podem entrar nele.");
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
  main.querySelectorAll("[data-set-role]").forEach((select) => {
    select.addEventListener("change", async () => {
      try {
        await api.updateUser(select.dataset.setRole, { role: select.value });
        toast("Acesso atualizado.");
        mount(main);
      } catch (err) {
        toast(err.message, "bad");
      }
    });
  });
  main.querySelectorAll("[data-set-group]").forEach((select) => {
    select.addEventListener("change", async () => {
      try {
        await api.updateUser(select.dataset.setGroup, { group_id: select.value });
        toast("Grupo atualizado.");
        mount(main);
      } catch (err) {
        toast(err.message, "bad");
      }
    });
  });
}

function roleOptions(roles, selected) {
  return roles.map((role) => `<option value="${esc(role.id)}" ${role.id === selected ? "selected" : ""}>${esc(role.label)}</option>`).join("");
}

function groupOptions(groups, selected) {
  const active = groups.filter((group) => group.active);
  return active.map((group) => `<option value="${esc(group.id)}" ${group.id === selected ? "selected" : ""}>${esc(group.name)} · ${esc(group.role_label)}</option>`).join("");
}

function adminBlock(users, roles, groups) {
  return `
    <h2>Grupos</h2>
    <p class="hint">Cada grupo abre só as telas do perfil. Trocar o grupo troca o acesso da pessoa.</p>
    <ul class="rows">
      ${groups.map((group) => `
        <li class="stop">
          <span><b>${esc(group.name)}</b> · ${esc(group.role_label)}<br><small>${esc((group.screens || []).join(" · ") || "Sem telas")}</small></span>
        </li>`).join("") || "<li>Nenhum grupo.</li>"}
    </ul>
    <h2>Novo grupo</h2>
    <form class="form" id="group-form">
      <div class="fields">
        <label class="field">Nome<input name="name" required placeholder="Equipe noturna" /></label>
        <label class="field">Acesso do grupo<select name="role">${roleOptions(roles, "operador")}</select></label>
        <label class="field">UF<input name="uf" maxlength="2" placeholder="SP" /></label>
        <label class="field">Município<input name="city" placeholder="Marília" /></label>
      </div>
      <button type="submit" class="primary">Criar grupo</button>
    </form>
    <h2>Usuários</h2>
    <ul class="rows">
      ${users.map((user) => `
        <li class="stop">
          <span><b>${esc(user.name)}</b><br><small>${esc(user.email)} · ${user.active ? "ativa" : "desativada"}</small></span>
          <label class="field slim">Acesso<select data-set-role="${esc(user.id)}">${roleOptions(roles, user.role)}</select></label>
          <label class="field slim">Grupo<select data-set-group="${esc(user.id)}">${groupOptions(groups, user.group_id)}</select></label>
          <button type="button" class="ghost" data-user="${esc(user.id)}" data-active="${user.active ? "true" : "false"}">${user.active ? "Desativar" : "Ativar"}</button>
        </li>`).join("") || "<li>Nenhum usuário.</li>"}
    </ul>
    <h2>Novo usuário</h2>
    <form class="form" id="user-form">
      <div class="fields">
        <label class="field">Nome<input name="name" required /></label>
        <label class="field">Usuário<input name="email" type="text" required placeholder="nome@orgao ou fogo@adm" /></label>
        <label class="field">Senha<input name="password" type="password" required minlength="8" /></label>
        <label class="field">Grupo<select name="group_id" id="user-group">${groupOptions(groups, "GP-CCO")}</select></label>
        <label class="field">Acesso<select name="role" id="user-role">${roleOptions(roles, "operador")}</select></label>
        <label class="field">UF<input name="uf" maxlength="2" placeholder="SP" /></label>
        <label class="field">Município<input name="city" placeholder="Marília" /></label>
      </div>
      <button type="submit" class="primary">Cadastrar</button>
    </form>`;
}
