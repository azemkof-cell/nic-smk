window.addEventListener("error", function (e) {
  var v = document.getElementById("view");
  if (v && !v.textContent.trim()) {
    v.innerHTML = '<div class="card"><div class="pad"><div class="verdict bad">' +
      'Ошибка загрузки: ' + (e.message || "неизвестно") +
      '</div><div class="small mt8">Обновите страницу: Ctrl+F5. Если не помогает — очистите данные сайта.</div></div></div>';
  }
});
/* НИЦ СМК · автоматизация документов — клиент */
const $ = (sel, root = document) => root.querySelector(sel);
const $$ = (sel, root = document) => [...root.querySelectorAll(sel)];
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));

const S = {
  data: null,
  route: "dashboard",
  proto: null,   // текущий протокол
  report: null,  // текущий отчёт
  dirTab: "objects",
  settingsTab: "company",
  calc: null,
  stack: [],
  navSuppress: false,
};

const KIND_ICONS = { asphalt: "▤", concrete: "◼", soil: "◈", rebar: "⛓" };

function todayISO() {
  const d = new Date();
  return new Date(d.getTime() - d.getTimezoneOffset() * 60000).toISOString().slice(0, 10);
}
function fmtDate(iso) {
  if (!iso) return "—";
  const d = new Date(iso);
  if (isNaN(d)) return iso;
  return d.toLocaleDateString("ru-RU", { day: "2-digit", month: "2-digit", year: "numeric" });
}
function period(a, b) { return `${fmtDate(a)} — ${fmtDate(b)}`; }
const fmtN = (v) => (v === null || v === undefined || v === "" ? "" : String(v).replace(".", ","));

async function api(path, body) {
  const opt = body === undefined ? {} : {
    method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body),
  };
  const r = await fetch(path, opt);
  let j;
  try { j = await r.json(); } catch (e) { throw new Error("Сервер вернул некорректный ответ"); }
  if (!j.ok) throw new Error(j.error || "Ошибка");
  return j;
}

let toastTimer;
function toast(msg, isError = false) {
  const t = $("#toast");
  t.textContent = msg;
  t.className = "toast show" + (isError ? " err" : "");
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => (t.className = "toast"), 4200);
}

async function loadState() {
  const j = await api("/api/state");
  S.data = j.data;
  S.groups = null;
  const totalDocs = (j.data.stats.protocols || 0) + (j.data.stats.reports || 0);
  const sbDocs = document.getElementById("sb-docs");
  if (sbDocs) sbDocs.textContent = "";
  const sbAi = document.getElementById("sb-ai");
  if (sbAi) sbAi.textContent = "ИИ: " + ((j.data.ai && j.data.ai.key) ? "подключён" : "локальный разбор");
  S.phoneUrl = j.data.phone_url || location.origin;
  applyRole(j.data.user);
  const sbLeft = document.getElementById("sb-left");
  if (sbLeft) {
    const u = j.data.user;
    sbLeft.innerHTML = u
      ? `Сотрудник: <b>${esc(u.name)}</b> · ${esc(roleNames(u))} · <a href="#" id="sb-logout">выйти</a>`
      : (j.data.company.name || "НИЦ СМК") + " · локальная база";
    const lo = document.getElementById("sb-logout");
    if (lo) lo.onclick = async (e) => { e.preventDefault(); await api("/api/logout", {}); location.reload(); };
  }
  const d = new Date();
  $("#today").textContent = d.toLocaleDateString("ru-RU", { weekday: "long", day: "numeric", month: "long", year: "numeric" });
}

/* ------------------------------------------------------------------ router */
function go(route) { location.hash = "#/" + route; }

function goBack() {
  if (S.stack.length > 1) {
    S.stack.pop();
    const prev = S.stack[S.stack.length - 1] || (S.allowed || ROLE_ROUTES.auth)[0];
    S.navSuppress = true;
    location.hash = "#/" + prev;
  } else {
    go((S.allowed || ROLE_ROUTES.auth)[0]);
  }
}

const ROLE_ROUTES = {
  auth: ["field", "lab", "documents", "protocols", "reports", "archive", "directory", "object", "settings"],
  admin: ["field", "lab", "documents", "kp", "protocols", "reports", "archive", "directory", "object", "settings"],
  engineer: ["field", "lab", "documents", "kp", "protocols", "reports", "archive", "directory", "object"],
  lab_head: ["lab", "documents", "protocols", "archive", "object"],
  viewer: ["documents", "protocols", "reports", "archive", "directory", "object"],
};

function rolesOf(u) {
  if (!u) return [];
  if (Array.isArray(u.roles)) return u.roles.filter(Boolean);
  return u.role ? [u.role] : [];
}

function roleNames(u) {
  const names = rolesOf(u).map(roleLabel);
  return names.length ? names.join(", ") : "—";
}

function applyRole(user) {
  S.user = user || null;
  const roles = rolesOf(user);
  S.roleSet = roles.length ? roles : ["auth"];
  const set = new Set();
  S.roleSet.forEach(r => (ROLE_ROUTES[r] || []).forEach(x => set.add(x)));
  S.allowed = [...set];
  S.isAdmin = roles.includes("admin");
  $$("#nav a").forEach(a => {
    a.style.display = S.allowed.includes(a.dataset.route) ? "" : "none";
  });
  const show = (id, on) => { const el = $(id); if (el) el.style.display = on ? "" : "none"; };
  const canWrite = !roles.length || !roles.every(r => r === "viewer");
  const labOnly = roles.length > 0 && !roles.some(r => r === "admin" || r === "engineer");
  show("#tb-proto", canWrite);
  show("#tb-report", canWrite && !labOnly);
  show("#tb-field", canWrite && !labOnly);
  show("#btn-folder", canWrite && !labOnly);
}

function roleLabel(r) {
  return ({admin: "администратор", engineer: "инженер СК",
           lab_head: "руководитель лаборатории", lab: "лаборант",
           viewer: "просмотр"})[r] || r || "";
}

async function renderLogin() {
  setTitle("Вход в программу", "Телефон и код или логин администратора");
  $("#view").innerHTML = `<div style="max-width:420px;margin:40px auto">
    <div class="card"><div class="pad">
      <div class="segmented mb8" id="lg-tabs">
        <button data-lg="phone" class="active">Телефон</button>
        <button data-lg="pass">Логин</button>
      </div>
      <div id="lg-body"></div>
      <div class="hintline">Новый сотрудник регистрируется по телефону — администратор активирует аккаунт.</div>
    </div></div></div>`;

  const phoneForm = () => {
    $("#lg-body").innerHTML = `
      <div class="field"><label class="f">Телефон</label><input id="lg-phone" inputmode="tel" placeholder="+7 900 000-00-00"></div>
      <div class="field"><label class="f">Код из Telegram</label><input id="lg-code" inputmode="numeric" placeholder="6 цифр"></div>
      <div class="flex"><button class="btn" id="lg-go-phone">Войти</button>
        <button class="btn ghost" id="lg-reg">Регистрация</button></div>`;
    $("#lg-go-phone").onclick = async () => {
      try {
        await api("/api/login", { phone: $("#lg-phone").value.trim(), code: $("#lg-code").value.trim() });
        await loadState();
        if (rolesOf(S.data.user).length && !rolesOf(S.data.user).some(r => r === "admin" || r === "engineer")) {
          location.hash = "#/lab"; return router();
        }
        router();
      } catch (e) { toast(e.message, true); }
    };
    $("#lg-reg").onclick = regForm;
  };

  const regForm = () => {
    $("#lg-body").innerHTML = `
      <div class="field"><label class="f">ФИО</label><input id="rg-name" placeholder="Иванов Иван"></div>
      <div class="field"><label class="f">Телефон</label><input id="rg-phone" inputmode="tel" placeholder="+7 900 000-00-00"></div>
      <div class="flex"><button class="btn" id="rg-go">Отправить заявку</button>
        <button class="btn ghost" id="rg-back">Назад</button></div>
      <div id="rg-out" class="mt8"></div>`;
    $("#rg-back").onclick = phoneForm;
    $("#rg-go").onclick = async () => {
      try {
        const r = await api("/api/register", { name: $("#rg-name").value.trim(), phone: $("#rg-phone").value.trim() });
        $("#rg-out").innerHTML = `<div class="verdict ok">Заявка создана. Администратор активирует аккаунт и выдаст код.</div>
          ${r.telegram_link ? `<div class="mt8"><a class="btn ghost" target="_blank" href="${esc(r.telegram_link)}">Привязать Telegram</a>
          <div class="hintline">Откройте ссылку и нажмите «Start» — код придёт в Telegram.</div></div>` : ""}`;
      } catch (e) { toast(e.message, true); }
    };
  };

  const passForm = () => {
    $("#lg-body").innerHTML = `
      <div class="field"><label class="f">Логин</label><input id="lg-login" autocomplete="username"></div>
      <div class="field"><label class="f">Код</label><input id="lg-pin" type="password" autocomplete="current-password"></div>
      <button class="btn" id="lg-go">Войти</button>`;
    const go = async () => {
      try {
        await api("/api/login", { login: $("#lg-login").value.trim(), pin: $("#lg-pin").value.trim() });
        await loadState(); router();
      } catch (e) { toast(e.message, true); }
    };
    $("#lg-go").onclick = go;
    $("#lg-pin").onkeydown = (e) => { if (e.key === "Enter") go(); };
  };

  $("#lg-tabs").onclick = (e) => {
    const b = e.target.closest("button[data-lg]"); if (!b) return;
    $$("#lg-tabs button").forEach(x => x.classList.toggle("active", x === b));
    b.dataset.lg === "phone" ? phoneForm() : passForm();
  };
  phoneForm();
}

async function router() {
  if (S.data && S.data.auth_required && !S.data.user) return renderLogin();
  showLoading(true);
  const allowed = S.allowed || ROLE_ROUTES.auth;
  const hash = location.hash.replace(/^#\//, "") || allowed[0];
  if (!allowed.includes(hash.split("/")[0])) {
    showLoading(false);
    location.hash = "#/" + allowed[0];
    return;
  }
  const prev = S.stack[S.stack.length - 1];
  if (!S.navSuppress && hash !== prev) {
    if (S.stack.length > 1 && hash === S.stack[S.stack.length - 2]) {
      S.stack.pop();
    } else {
      S.stack.push(hash);
      if (S.stack.length > 50) S.stack.shift();
    }
  }
  S.navSuppress = false;
  const bb = $("#btn-back");
  if (bb) bb.disabled = S.stack.length <= 1;
  S.route = hash;
  if (hash !== "protocols/new") S.labMode = false;
  $$("#nav a").forEach((a) => a.classList.toggle("active", a.dataset.route === hash.split("/")[0]));
  $$("#mobilenav a").forEach((a) => a.classList.toggle("active", a.dataset.r === hash.split("/")[0]));
  try {
    if (hash === "dashboard") { location.hash = "#/" + allowed[0]; return; }
    else if (hash === "protocols") await viewProtocols();
    else if (hash === "protocols/new") await viewProtocolForm();
    else if (hash === "reports") await viewReports();
    else if (hash === "reports/new") await viewReportForm();
    else if (hash === "archive") await viewArchive();
    else if (hash === "field") await viewField();
    else if (hash === "lab") await viewLab();
    else if (hash === "documents") await viewDocuments();
    else if (hash === "kp") await viewKp();
    else if (hash.startsWith("object/")) await viewObject(parseInt(hash.split("/")[1], 10));
    else if (hash === "directory") await viewDirectory();
    else if (hash === "settings" || hash.startsWith("settings/")) {
      if (hash.includes("/")) S.settingsTab = hash.split("/")[1];
      await viewSettings();
    }
    else await viewDashboard();
  } catch (e) {
    console.error(e);
    $("#view").innerHTML = `<div class="card"><div class="pad"><div class="verdict bad">Ошибка: ${esc(e.message)}</div></div></div>`;
  } finally {
    showLoading(false);
  }
  window.scrollTo(0, 0);
}

function setTitle(title, sub = "") {
  $("#page-title").textContent = title;
  $("#page-sub").textContent = sub;
}

/* ------------------------------------------------------------------ dashboard */
async function viewDashboard() {
  const d = S.data;
  const st = d.stats;
  const objects = d.objects || [];
  const today = todayISO();
  const active = objects.filter(o => (o.status || "active") === "active");
  const overdue = active.filter(o => o.report_next && o.report_next <= today && o.report_freq);
  const soon = active.filter(o => o.report_next && o.report_next > today && o.report_next <= addDays(today, 7));
  const noFolder = active.filter(o => !o.folder).length;
  const drafts = (d.protocols || []).filter(p => p.draft).length;
  const noPdf = [...(d.protocols || []), ...(d.reports || [])].filter(x => x.file && !x.pdf).length;

  setTitle("Рабочее место", "Документы, задачи и объекты");

  if (!S.kpList) {
    try { S.kpList = (await api("/api/kp/list")).items || []; } catch (e) { S.kpList = []; }
  }
  const docs = [
    ...(d.protocols || []).map(p => ({ type: "Протокол", num: p.number, date: p.pdate, obj: p.object_name, file: p.file, pdf: p.pdf, kind: p.kind_label })),
    ...(d.reports || []).map(r => ({ type: "Отчёт", num: r.number, date: r.date_to, obj: r.object_name, file: r.file, pdf: r.pdf, kind: "СК" })),
  ].sort((a, b) => String(b.date || "").localeCompare(String(a.date || ""))).slice(0, 10);

  const alerts = [];
  overdue.forEach(o => alerts.push(`<div class="doc-row"><span class="badge bad">срок</span>
    <div class="doc-name"><b>${esc(o.name)}</b><div class="small">отчёт за ${fmtDate(o.report_next)} не сформирован</div></div>
    <a class="btn ghost sm" href="#/object/${o.id}">Открыть</a></div>`));
  soon.slice(0, 4).forEach(o => alerts.push(`<div class="doc-row"><span class="badge neutral">скоро</span>
    <div class="doc-name"><b>${esc(o.name)}</b><div class="small">следующий отчёт ${fmtDate(o.report_next)}</div></div>
    <a class="btn ghost sm" href="#/object/${o.id}">Открыть</a></div>`));
  if (noFolder) alerts.push(`<div class="doc-row"><span class="badge draft">папка</span>
    <div class="doc-name"><b>Объектов без папки: ${noFolder}</b><div class="small">документы не подтягиваются автоматически</div></div>
    <a class="btn ghost sm" href="#/directory">К объектам</a></div>`);
  if (drafts) alerts.push(`<div class="doc-row"><span class="badge draft">черновик</span>
    <div class="doc-name"><b>Черновиков: ${drafts}</b><div class="small">нажмите «Готовый протокол» перед подписанием</div></div>
    <a class="btn ghost sm" href="#/documents">К документам</a></div>`);
  if (noPdf) alerts.push(`<div class="doc-row"><span class="badge neutral">PDF</span>
    <div class="doc-name"><b>Документов без PDF: ${noPdf}</b><div class="small">кнопка «Сделать PDF» в журнале</div></div>
    <a class="btn ghost sm" href="#/documents">К документам</a></div>`);
  if (!alerts.length) alerts.push(`<div class="empty">Замечаний нет — все отчёты в срок</div>`);

  $("#view").innerHTML = `
    <div class="flex mb8" style="justify-content:flex-end">
      <span class="small">${overdue.length ? "⚠ просрочено отчётов: " + overdue.length : "отчёты по расписанию: в срок"}</span>
    </div>

    <div class="split">
      <div class="panel">
        <div class="panel-head"><span>Последние документы</span><a class="small" href="#/documents">все →</a></div>
        <div class="panel-body">
          ${docs.length ? `<table class="tbl"><thead><tr><th>Тип</th><th>№</th><th>Дата</th><th>Объект</th><th></th></tr></thead>
          <tbody>${docs.map(x => `<tr>
            <td class="small">${esc(x.type)}</td>
            <td class="mono"><b>${esc(x.num)}</b></td>
            <td>${fmtDate(x.date)}</td>
            <td class="small">${esc((x.obj || "—").slice(0, 60))}</td>
            <td class="right">${x.pdf ? `<a class="btn sm" target="_blank" href="/api/download?inline=1&f=${encodeURIComponent(x.pdf)}">PDF</a>`
              : `<button class="btn ghost sm" data-mkpdf="${esc(x.file || "")}">PDF</button>`}</td>
          </tr>`).join("")}</tbody></table>` : `<div class="empty">Документов пока нет</div>`}
        </div>
      </div>

      <div class="panel">
        <div class="panel-head"><span>Требуют внимания</span><span class="small">${alerts.length}</span></div>
        <div class="panel-body pad">${alerts.join("")}</div>
      </div>
    </div>`;

  $$("#view [data-go]").forEach(b => b.onclick = () => go(b.dataset.go));
  $$("#view [data-mkpdf]").forEach(b => b.onclick = async () => {
    if (!b.dataset.mkpdf) return;
    b.disabled = true; b.textContent = "…";
    try { await api("/api/pdf", { file: b.dataset.mkpdf }); toast("PDF готов"); await loadState(); await viewDashboard(); }
    catch (e) { toast(e.message, true); b.disabled = false; b.textContent = "PDF"; }
  });
}

function addDays(iso, days) {
  const d = new Date(iso + "T00:00:00");
  d.setDate(d.getDate() + days);
  return new Date(d.getTime() - d.getTimezoneOffset() * 60000).toISOString().slice(0, 10);
}

/* ------------------------------------------------------------------ protocols list */
async function viewDocuments() {
  setTitle("Документы", "Поиск по номеру, ИНН, заказчику, объекту");
  const q = (S.docQuery || "").trim().toLowerCase();
  const type = S.docType || "all";
  const docs = [
    ...(S.data.protocols || []).map(p => ({ t: "protocol", type: "Протокол", number: p.number,
      date: p.pdate, name: p.object_name, customer: p.customer, kind: p.kind_label,
      file: p.file, pdf: p.pdf, id: p.id })),
    ...(S.data.reports || []).map(r => ({ t: "report", type: "Отчёт", number: r.number,
      date: r.date_to || r.rdate, name: r.object_name, customer: r.customer, kind: "СК",
      file: r.file, pdf: r.pdf, id: r.id })),
    ...((S.kpList || []).map(k => ({ t: "kp", type: "КП", number: k.number,
      date: k.kdate, name: k.object || "", customer: k.customer,
      kind: ({nic:"НИЦ СМК",ing:"Инжиниринг Лаб",loft:"ЛОФТ"})[k.company] || "НИЦ СМК",
      file: k.file, pdf: (k.file || "").replace(/\.docx$/i, ".pdf"), id: k.id }))),
  ].filter(d => type === "all" || d.t === type);

  const innByName = {};
  (S.data.objects || []).forEach(o => { innByName[o.name] = o.customer_inn || ""; });
  docs.forEach(d => { d.inn = innByName[d.name] || ""; });
  const found = docs.filter(d => !q || [d.number, d.name, d.customer, d.kind, d.type, d.inn]
    .join(" ").toLowerCase().includes(q));

  const rows = found.map(d => `<tr>
    <td class="small">${esc(d.type)}</td>
    <td class="mono"><b>${esc(d.number)}</b></td>
    <td>${fmtDate(d.date)}</td>
    <td class="small">${esc((d.name || "—").slice(0, 70))}</td>
    <td class="small">${esc((d.customer || "—").slice(0, 40))}${d.inn ? `<br><span class="small">ИНН ${esc(d.inn)}</span>` : ""}</td>
    <td class="right">
      ${d.pdf ? `<button class="btn ghost sm" data-prev="${esc(d.pdf)}">Просмотр</button>` : ""}
      ${d.pdf ? `<a class="btn ghost sm" href="/api/download?f=${encodeURIComponent(d.pdf)}">PDF</a>` : ""}
      ${d.file ? `<a class="btn ghost sm" href="/api/download?f=${encodeURIComponent(d.file)}">DOCX</a>` : ""}
      ${d.t === "report" ? `<button class="btn sm" data-send="${d.id}">Отправить</button>` : ""}
      ${d.t === "protocol" ? `<button class="btn ghost sm" data-edit="${d.id}">Изменить</button>` : ""}
      ${d.t === "report" ? `<button class="btn ghost sm" data-editrep="${d.id}">Изменить</button>` : ""}
    </td></tr>`).join("");

  $("#view").innerHTML = `<div class="panel">
    <div class="panel-head"><span>Поиск документов</span><span class="small">${found.length}</span></div>
    <div class="panel-body pad">
      <div class="flex mb8">
        ${rolesOf(S.data.user).some(r => r === "admin" || r === "engineer" || r === "lab" || r === "lab_head")
          ? `<button class="btn" id="doc-new-proto">＋ Протокол</button>` : ""}
        ${rolesOf(S.data.user).some(r => r === "admin" || r === "engineer")
          ? `<button class="btn ghost" id="doc-new-report">＋ Отчёт</button>` : ""}
        <div class="spacer"></div>
      </div>
      <div class="row c2">
        <div><label class="f">Номер, ИНН, заказчик, объект</label>
          <input id="doc-q" value="${esc(S.docQuery || "")}" placeholder="например: 2884, 9715522474, ДУБНА"></div>
        <div><label class="f">Тип</label>
          <select id="doc-type">
            <option value="all" ${type === "all" ? "selected" : ""}>Все документы</option>
            <option value="protocol" ${type === "protocol" ? "selected" : ""}>Протоколы</option>
            <option value="report" ${type === "report" ? "selected" : ""}>Отчёты</option>
            <option value="kp" ${type === "kp" ? "selected" : ""}>КП</option>
          </select></div>
      </div>
      <div class="hintline">ИНН и заказчик берутся из карточки объекта и контракта. Поиск идёт по номеру, объекту, заказчику и виду испытания.</div>
    </div>
    <div class="panel-body">${found.length ? `<table class="tbl"><thead><tr>
      <th>Тип</th><th>Номер</th><th>Дата</th><th>Объект</th><th>Заказчик</th><th></th></tr></thead>
      <tbody>${rows}</tbody></table>` : `<div class="empty">Ничего не найдено</div>`}</div>
  </div>`;
  if ($("#doc-new-proto")) $("#doc-new-proto").onclick = () => go("protocols/new");
  if ($("#doc-new-report")) $("#doc-new-report").onclick = () => go("reports/new");
  $("#doc-q").oninput = (e) => { S.docQuery = e.target.value; };
  $("#doc-q").onkeydown = (e) => { if (e.key === "Enter") viewDocuments(); };
  $("#doc-type").onchange = (e) => { S.docType = e.target.value; viewDocuments(); };
}

async function viewLab() {
  setTitle("Лаборатория", "Выберите испытание — откроется форма для заполнения");
  const kinds = S.data.kinds || {};
  const groups = [
    ["Бетон и раствор", ["concrete", "concrete_core", "concrete_ndt", "mortar_cube", "protective_layer"]],
    ["Асфальтобетон", ["asphalt", "asphalt_euro", "asphalt_core", "asphalt_euro_core"]],
    ["Грунт, песок, щебень", ["soil", "soil_proctor", "soil_fms_sand", "soil_fms_soil", "crushed_stone", "pdu"]],
    ["Прочее", ["rebar", "waterproofing"]],
  ];
  const used = new Set(groups.flatMap(g => g[1]));
  const rest = Object.keys(kinds).filter(k => !used.has(k));
  if (rest.length) groups.push(["Другое", rest]);
  $("#view").innerHTML = `<div class="lab-grid">${groups.map(([label, keys]) => `
    <div class="lab-group"><div class="sub-h">${esc(label)}</div>
      <div class="lab-tiles">${keys.filter(k => kinds[k]).map(k => `
        <button class="lab-tile" data-lab="${k}">
          <span class="lab-ico">${KIND_ICONS[k] || "🧪"}</span>
          <span class="lab-name">${esc(kinds[k].short)}</span>
          <span class="lab-sub">${esc((S.data.norms[k] || {}).label || "")}</span>
        </button>`).join("")}</div>
    </div>`).join("")}</div>`;
  $$("#view [data-lab]").forEach(b => b.onclick = () => {
    const k = b.dataset.lab;
    if (k === "asphalt" || k === "asphalt_euro") viewLabAsphalt(k);
    else viewLabForm(k);
  });
}

async function viewProtocols() {
  setTitle("Протоколы испытаний", "Журнал сформированных документов");
  const list = S.data.protocols;
  $("#view").innerHTML = `
    <div class="toolbar">
      <div class="left"></div>
      <div class="small"></div>
    </div>
    <div class="card">
      ${list.length ? `<table class="tbl">
        <thead><tr><th>№ протокола</th><th>Лаб. №</th><th>Акт</th><th>Дата</th><th>Испытание</th><th>Объект</th><th>Статус</th><th></th></tr></thead>
        <tbody>${list.map(p => `<tr>
          <td class="mono"><b>${esc(p.number)}</b></td>
          <td class="mono">${esc(p.lab_no || "—")}</td>
          <td class="mono">${esc(p.act_no || "—")}</td>
          <td>${fmtDate(p.pdate)}</td>
          <td><span class="chip">${esc(p.kind_label)}</span></td>
          <td>${esc(p.object_name || "—")}</td>
          <td>${p.draft ? '<span class="badge draft">черновик</span>' : '<span class="badge ok">готов</span>'}</td>
          <td class="right">
            ${p.pdf ? `<a class="btn sm" target="_blank" href="/api/download?inline=1&f=${encodeURIComponent(p.pdf)}">PDF</a>`
              : (p.file ? `<button class="btn soft sm" data-mkpdf="${esc(p.file)}">Сделать PDF</button>` : "")}
            ${p.file ? `<a class="btn ghost sm" href="/api/download?f=${encodeURIComponent(p.file)}">DOCX</a>` : ""}
          </td>
        </tr>`).join("")}</tbody></table>` : `<div class="empty">Протоколов пока нет. Нажмите «Новый протокол».</div>`}
    </div>`;
  if ($("#new-protocol")) $("#new-protocol").onclick = () => go("protocols/new");
  $$("[data-mkpdf]").forEach(b => b.onclick = async () => {
    b.disabled = true; b.textContent = "Делаю…";
    try {
      const j = await api("/api/pdf", { file: b.dataset.mkpdf });
      toast("PDF готов"); await loadState(); await viewProtocols();
    } catch (e) { toast(e.message, true); b.disabled = false; b.textContent = "Сделать PDF"; }
  });
}

/* ------------------------------------------------------------------ protocol form */
function blankAsphalt() {
  return {
    customer: "", customer_address: "", object_name: "", contractor: "",
    material: "а/б смесь А8Вл", purpose: "Верхний слой", sampled_at: "",
    manufacturer: "", recipe: "", nd: "ГОСТ 58406.2-2020",
    grain: Array(13).fill(""),
    physical: { binder_over: "", pb: "", gmm: "", gmb: "", pa: "", pmz: "", pnb: "" },
    operational: { rut: "", water: "" },
  };
}

function blankMeta(kind) {
  if (kind === "asphalt") return blankAsphalt();
  const n = S.data.norms[kind] || {};
  const meta = {};
  (n.meta || []).forEach(f => meta[f.key] = f.default || "");
  (n.extra_inputs || []).forEach(f => { if (meta[f.key] === undefined) meta[f.key] = f.default || ""; });
  (n.fields || []).forEach(f => meta[f.key] = "");
  return meta;
}

async function viewProtocolForm() {
  setTitle("Новый протокол испытаний", "Заполните данные — документ сформируется автоматически");
  const kinds = S.data.kinds;
  const labKind = S.labKind && S.data.kinds[S.labKind] ? S.labKind : "asphalt";
  S.proto = {
    kind: labKind,
    meta: blankMeta(labKind),
    object_name: "", customer: "", pdate: todayISO(),
    number: "", lab_no: "", act_no: "", need_act: true,
    draft: true, internal: false, engineer: "", lab_head: S.data.company.lab_head || "",
  };
  S.calc = null;
  if (S.editProtocolId) {
    try {
      const j = await api("/api/protocol/get?id=" + S.editProtocolId);
      const d = j.data || {};
      const pl = JSON.parse(d.payload || "{}");
      S.proto.kind = d.kind || "concrete";
      S.proto.meta = pl.meta || blankMeta(S.proto.kind);
      S.proto.object_name = d.object_name || "";
      S.proto.customer = d.customer || "";
      S.proto.pdate = d.pdate || todayISO();
      S.proto.number = d.number || "";
      S.proto.lab_no = d.lab_no || "";
      S.proto.act_no = d.act_no || "";
      S.proto.draft = !!(d.draft);
      toast("Редактирование протокола № " + (d.number || ""));
    } catch (e) { toast(e.message, true); S.editProtocolId = null; }
  }

  $("#view").innerHTML = `
    <div class="toolbar">
      <button class="btn ghost" onclick="go('documents')">← К документам</button>
      <div class="small">Номер присваивается автоматически при сохранении</div>
    </div>
    <div class="split">
      <div class="card"><div class="pad" id="proto-form"></div></div>
      <div class="sticky"><div class="card"><div class="pad" id="proto-preview"></div></div></div>
    </div>`;
  renderProtoForm();
  if (S.labMode) {
    $("#view").classList.add("lab-mode");
    $$("#proto-form input[data-meta], #proto-form input[data-a]").forEach(inp => {
      const b = document.createElement("button");
      b.type = "button"; b.className = "mic-btn"; b.textContent = "🎤";
      b.title = "Заполнить голосом";
      b.onclick = () => listenInto(inp);
      inp.parentElement.insertBefore(b, inp.nextSibling);
    });
  } else {
    $("#view").classList.remove("lab-mode");
  }
  await refreshProtoCalc();
}

function listenInto(input) {
  const SR = window.SpeechRecognition || window.webkitSpeechRecognition;
  if (!SR) { toast("Голосовой ввод не поддерживается браузером", true); return; }
  const r = new SR();
  r.lang = "ru-RU"; r.interimResults = false; r.maxAlternatives = 1;
  r.onresult = (e) => {
    let t = e.results[0][0].transcript || "";
    const nums = t.replace(/[^0-9.,;\-]/g, " ").replace(/,/g, ".").trim();
    input.value = nums || t;
    input.dispatchEvent(new Event("input", { bubbles: true }));
    toast("Записано: " + input.value);
  };
  r.onerror = () => toast("Не расслышал, попробуйте ещё", true);
  r.start();
}

function asphaltFields(m) {
  if (!Array.isArray(m.grain)) m.grain = Array(13).fill("");
  m.physical = m.physical || {};
  m.operational = m.operational || {};
  const sieves = ["22,4","16,0","11,2","8,0","5,6","4,0","2,0","1,0","0,5","0,25","0,125","0,063","<0,063"];
  const phys = [
    ["binder_over", "Вяжущее сверх 100%, %"], ["pb", "Содержание вяжущего Pb, %"],
    ["gmm", "Gmm, г/см³"], ["gmb", "Gmb, г/см³"],
    ["pa", "Воздушные пустоты Pa, %"], ["pmz", "ПМЗ, %"], ["pnb", "ПНБ, %"],
  ];
  const ops = [["rut", "Глубина колеи, мм"], ["water", "Коэффициент водостойкости"]];
  return `
    <div class="row c2">
      <div class="field"><label class="f">Юридический адрес заказчика</label>
        <input type="text" data-a="customer_address" value="${esc(m.customer_address || "")}"></div>
      <div class="field"><label class="f">Подрядчик</label>
        <input type="text" data-a="contractor" value="${esc(m.contractor || "")}"></div>
    </div>
    <div class="row c3">
      <div class="field"><label class="f">Наименование материала</label>
        <input type="text" data-a="material" value="${esc(m.material || "")}" placeholder="а/б смесь А8Вл"></div>
      <div class="field"><label class="f">Назначение</label>
        <input type="text" data-a="purpose" value="${esc(m.purpose || "")}" placeholder="Верхний слой"></div>
      <div class="field"><label class="f">Производитель материала</label>
        <input type="text" data-a="manufacturer" value="${esc(m.manufacturer || "")}"></div>
    </div>
    <div class="row c3">
      <div class="field"><label class="f">Дата отбора пробы</label>
        <input type="text" data-a="sampled_at" value="${esc(m.sampled_at || "")}" placeholder="02.10.2026"></div>
      <div class="field"><label class="f">Утвержденный рецепт</label>
        <input type="text" data-a="recipe" value="${esc(m.recipe || "")}" placeholder="№10/08-26А"></div>
      <div class="field"><label class="f">НД на продукцию</label>
        <input type="text" data-a="nd" value="${esc(m.nd || "")}" placeholder="ГОСТ 58406.2-2020"></div>
    </div>

    <h4 class="sub-h">Зерновой состав, полные проходы %</h4>
    <div class="grain-grid">
      ${sieves.map((s, i) => `<div>
        <label class="f">${s}</label>
        <input type="text" data-grain="${i}" value="${esc(m.grain[i] ?? "")}" placeholder="—">
      </div>`).join("")}
    </div>

    <h4 class="sub-h">Физические показатели</h4>
    <div class="row c4">
      ${phys.map(([k, label]) => `<div class="field"><label class="f">${label}</label>
        <input type="text" data-phys="${k}" value="${esc(m.physical[k] ?? "")}"></div>`).join("")}
    </div>

    <h4 class="sub-h">Эксплуатационные показатели</h4>
    <div class="row c2">
      ${ops.map(([k, label]) => `<div class="field"><label class="f">${label}</label>
        <input type="text" data-op="${k}" value="${esc(m.operational[k] ?? "")}"></div>`).join("")}
    </div>`;
}

function renderProtoForm() {
  const p = S.proto;
  const n = S.data.norms[p.kind] || {};
  const kinds = S.data.kinds;
  const objects = S.data.objects;

  let fields = "";
  if (p.kind === "asphalt") {
    fields = asphaltFields(p.meta);
  }
  const inputFields = p.kind === "soil" ? (n.extra_inputs || []) : [];
  if (p.kind === "soil") {
    fields = inputFields.map(f => `
      <div class="field">
        <label class="f">${esc(f.name)}, ${esc(f.unit)}</label>
        <input type="text" data-meta="${f.key}" value="${esc(p.meta[f.key] ?? "")}" placeholder="результат измерения, напр. 2,1">
        <div class="hintline">${f.lo != null && f.hi != null ? `Норма: ${fmtN(f.lo)}–${fmtN(f.hi)} ${f.unit}` : f.lo != null ? `Норма: не менее ${fmtN(f.lo)} ${f.unit}` : f.hi != null ? `Норма: не более ${fmtN(f.hi)} ${f.unit}` : ""}${f.gost ? " · " + esc(f.gost) : ""}</div>
      </div>`).join("");
  } else if ((n.fields || []).length) {
    fields = n.fields.map(f => `
      <div class="field">
        <label class="f">${esc(f.name)}, ${esc(f.unit)}</label>
        <input type="text" data-meta="${f.key}" value="${esc(p.meta[f.key] ?? "")}" placeholder="результат">
        <div class="hintline">${f.lo != null || f.hi != null ? "Норма: " + (f.lo != null ? "от " + fmtN(f.lo) : "") + (f.hi != null ? " до " + fmtN(f.hi) : "") + " " + esc(f.unit) : "не нормируется"}${f.gost ? " · " + esc(f.gost) : ""}</div>
      </div>`).join("");
  } else if (p.kind !== "asphalt") {
    fields = (n.meta || []).filter(f => f.key !== "cls" || true).map(f => {
      const isLoads = f.key === "loads";
      return `<div class="field">
        <label class="f">${esc(f.name)}</label>
        <input type="text" data-meta="${f.key}" value="${esc(p.meta[f.key] ?? "")}"
          placeholder="${isLoads ? "например: 640; 655; 648" : esc(f.default || "")}">
      </div>`;
    }).join("");
  }

  $("#proto-form").innerHTML = `
    <div class="form-section">
      <div class="head"><h3>Вид испытания</h3></div>
      <select id="kind-select">
        ${(() => {
          const groups = [
            ["Асфальтобетон", ["asphalt", "asphalt_euro", "asphalt_core", "asphalt_euro_core"]],
            ["Бетон и раствор", ["concrete", "concrete_core", "concrete_ndt", "mortar_cube", "protective_layer"]],
            ["Грунт, песок, щебень, основание", ["soil", "soil_proctor", "soil_fms_sand", "soil_fms_soil", "crushed_stone", "pdu"]],
            ["Прочее", ["rebar", "waterproofing"]],
          ];
          const used = new Set(groups.flatMap(g => g[1]));
          let html = groups.map(([label, keys]) => `<optgroup label="${esc(label)}">` +
            keys.filter(k => kinds[k]).map(k => `<option value="${k}" ${p.kind === k ? "selected" : ""}>${esc(kinds[k].short)}</option>`).join("") +
            `</optgroup>`).join("");
          const rest = Object.entries(kinds).filter(([k]) => !used.has(k));
          if (rest.length) html += `<optgroup label="Другое">` + rest.map(([k, v]) => `<option value="${k}" ${p.kind === k ? "selected" : ""}>${esc(v.short)}</option>`).join("") + `</optgroup>`;
          return html;
        })()}
      </select>
      <div class="hintline">${esc(n.label || "")}</div>
    </div>

    <div class="form-section">
      <div class="head"><h3>Объект и заказчик</h3></div>
      <div class="row c2">
        <div class="field">
          <label class="f">Объект</label>
          <input type="text" list="objects-list" id="f-object" value="${esc(p.object_name)}" placeholder="начните вводить адрес">
          <datalist id="objects-list">${objects.map(o => `<option value="${esc(o.name)}">`).join("")}</datalist>
        </div>
        <div class="field">
          <label class="f">Заказчик</label>
          <input type="text" id="f-customer" value="${esc(p.customer)}" placeholder="наименование организации">
        </div>
      </div>
      <div class="row c4">
        <div class="field"><label class="f">Дата протокола</label>
          <input type="date" id="f-date" value="${esc(p.pdate)}"></div>
        <div class="field"><label class="f">№ протокола</label>
          <input type="text" id="f-number" value="${esc(p.number)}" placeholder="авто: ${S.data.numbering.protocol}"></div>
        <div class="field"><label class="f">Лабораторный №</label>
          <input type="text" id="f-labno" value="${esc(p.lab_no)}" placeholder="авто: ${S.data.numbering.lab}"></div>
        <div class="field"><label class="f">Акт отбора №</label>
          <input type="text" id="f-actno" value="${esc(p.act_no)}" placeholder="авто: ${S.data.numbering.act}"
            ${p.need_act ? "" : "disabled"}></div>
      </div>
      <div class="row c2">
        <div class="field"><label class="f">Место отбора</label>
          <input type="text" data-meta="place" value="${esc(p.meta.place || "")}" placeholder="например: ПК 12+50, покрытие"></div>
        <div class="field" style="display:flex;align-items:flex-end;padding-bottom:8px">
          <label class="flex" style="gap:8px;font-size:13px;color:var(--text)">
            <input type="checkbox" id="f-needact" ${p.need_act ? "checked" : ""}> нужен акт отбора проб
          </label>
        </div>
      </div>
      <div class="hintline">Номера выдаются автоматически по сквозной нумерации из «прот №лаб №.xlsx»:
        протокол ${S.data.numbering.protocol}, лабораторный ${S.data.numbering.lab}, акт ${S.data.numbering.act}.
        Оставьте поле пустым — подставится следующий.</div>
    </div>

    <div class="form-section">
      <div class="head"><h3>${p.kind === "asphalt" ? "Данные протокола (асфальтобетон)" : p.kind === "soil" ? "Результаты измерений" : "Данные испытания"}</h3>
        <button class="btn soft sm" id="btn-demo">${p.kind === "asphalt" ? "Заполнить случайными" : "Заполнить примером"}</button></div>
      ${fields}
    </div>

    <div class="form-section">
      <div class="head"><h3>Подписи и статус</h3></div>
      <div class="row c3">
        <div class="field"><label class="f">Начальник лаборатории</label>
          <input type="text" id="f-labhead" value="${esc(p.lab_head)}"></div>
        <div class="field"><label class="f">Инженер-испытатель</label>
          <input type="text" id="f-engineer" value="${esc(p.engineer)}" placeholder="ФИО"></div>
        <div class="field"><label class="f">Статус документа</label>
          <select id="f-draft">
            <option value="1" ${p.draft ? "selected" : ""}>Черновик (водяной знак)</option>
            <option value="0" ${!p.draft ? "selected" : ""}>Готовый протокол</option>
          </select></div>
      </div>
      <div class="field" style="margin-top:6px">
        <label class="flex" style="gap:8px;font-size:13px;color:var(--text)">
          <input type="checkbox" id="f-internal" ${p.internal ? "checked" : ""}>
          внутренний экземпляр (случайные данные, без водяного знака)
        </label>
      </div>
      <div class="hintline">«Черновик» помечает документ водяным знаком, пока значения не проверены специалистом.
        «Внутренний экземпляр» — для учебных/внутренних документов: водяного знака нет, в подвале пометка «Внутренний экземпляр».</div>
    </div>

    <div class="flex mt16">
      <button class="btn ok" id="btn-save">Сформировать Word</button>
      <button class="btn ghost" id="btn-check">Пересчитать</button>
      <div class="spacer"></div>
      <div class="small">${esc(n.intro || "")}</div>
    </div>`;

  $("#kind-select").onchange = (e) => {
    S.proto.kind = e.target.value;
    S.proto.meta = blankMeta(e.target.value);
    renderProtoForm();
    refreshProtoCalc();
  };
  $$("#proto-form [data-meta]").forEach(inp => inp.oninput = () => {
    S.proto.meta[inp.dataset.meta] = inp.value;
    debounceCalc();
  });
  $("#f-object").oninput = (e) => S.proto.object_name = e.target.value;
  $("#f-customer").oninput = (e) => S.proto.customer = e.target.value;
  $("#f-date").onchange = (e) => S.proto.pdate = e.target.value;
  $("#f-number").oninput = (e) => S.proto.number = e.target.value;
  $("#f-labno").oninput = (e) => S.proto.lab_no = e.target.value;
  $("#f-actno").oninput = (e) => S.proto.act_no = e.target.value;
  $("#f-needact").onchange = (e) => {
    S.proto.need_act = e.target.checked;
    const a = $("#f-actno");
    if (a) { a.disabled = !e.target.checked; if (!e.target.checked) { a.value = ""; S.proto.act_no = ""; } }
  };
  $("#f-labhead").oninput = (e) => S.proto.lab_head = e.target.value;
  $("#f-engineer").oninput = (e) => S.proto.engineer = e.target.value;
  $("#f-draft").onchange = (e) => S.proto.draft = e.target.value === "1";
  $("#f-internal").onchange = (e) => S.proto.internal = e.target.checked;
  $$("#proto-form [data-a]").forEach(inp => inp.oninput = () => {
    S.proto.meta[inp.dataset.a] = inp.value; debounceCalc();
  });
  $$("#proto-form [data-grain]").forEach(inp => inp.oninput = () => {
    if (!Array.isArray(S.proto.meta.grain)) S.proto.meta.grain = Array(13).fill("");
    S.proto.meta.grain[+inp.dataset.grain] = inp.value; debounceCalc();
  });
  $$("#proto-form [data-phys]").forEach(inp => inp.oninput = () => {
    S.proto.meta.physical = S.proto.meta.physical || {};
    S.proto.meta.physical[inp.dataset.phys] = inp.value; debounceCalc();
  });
  $$("#proto-form [data-op]").forEach(inp => inp.oninput = () => {
    S.proto.meta.operational = S.proto.meta.operational || {};
    S.proto.meta.operational[inp.dataset.op] = inp.value; debounceCalc();
  });
  $("#btn-demo").onclick = fillDemo;
  $("#btn-check").onclick = () => refreshProtoCalc();
  $("#btn-save").onclick = saveProtocol;
}

let calcTimer;
function debounceCalc() {
  clearTimeout(calcTimer);
  calcTimer = setTimeout(() => refreshProtoCalc(true), 550);
}

async function fillDemo() {
  try {
    const j = await api("/api/protocol/fill", { kind: S.proto.kind, meta: S.proto.meta });
    S.proto.meta = j.meta;
    S.calc = j.calc;
    S.proto.internal = true;
    S.proto.draft = false;
    renderProtoForm();
    renderProtoPreview(true);
    toast("Данные заполнены случайными значениями. Это внутренний экземпляр.");
  } catch (e) { toast(e.message, true); }
}

async function refreshProtoCalc(silent = false) {
  try {
    const j = await api("/api/protocol/preview", { kind: S.proto.kind, meta: S.proto.meta });
    S.calc = j.calc;
    renderProtoPreview(silent);
  } catch (e) { if (!silent) toast(e.message, true); }
}

function renderProtoPreview(silent) {
  const c = S.calc;
  if (!c) { $("#proto-preview").innerHTML = `<div class="empty">Расчёт появится здесь</div>`; return; }
  const rows = c.rows.map(r => `<tr>
      <td>${esc(r.name)}</td>
      <td class="small">${esc(r.req)}</td>
      <td class="num">${esc(r.value)}</td>
      <td class="${r.missing ? "" : (r.ok ? "ok" : "bad")}">${r.missing ? "—" : (r.ok ? "✓" : "✕")}</td>
    </tr>`).join("");
  const state = c.complete === false ? "neutral" : (c.ok ? "ok" : "bad");
  const stateText = c.complete === false
      ? "<b>Заполните показатели</b> — часть данных отсутствует"
      : (c.ok ? "<b>Соответствует</b> требованиям нормативных документов"
              : "<b>Не соответствует</b> — проверьте выделенные показатели");
  $("#proto-preview").innerHTML = `
    <h2>Предпросмотр</h2>
    <div class="verdict ${state}">
      <span style="font-size:18px">${c.complete === false ? "…" : (c.ok ? "✓" : "✕")}</span>
      <div>${stateText}</div>
    </div>
    <table class="tbl res-table mt16"><thead><tr><th>Показатель</th><th>Требование</th><th>Факт</th><th></th></tr></thead>
      <tbody>${rows}</tbody></table>
    <div class="form-section">
      <div class="head"><h3>Заключение</h3></div>
      <div class="small" style="line-height:1.55">${esc(c.conclusion)}</div>
    </div>
    ${S.proto.draft ? `<div class="hintline">Будет добавлен водяной знак «ЧЕРНОВИК» и примечание о необходимости проверки.</div>` : ""}`;
}

async function saveProtocol() {
  if (!S.calc || S.calc.complete === false) { toast("Сначала заполните все показатели (или нажмите «Заполнить примером»)", true); return; }
  const btn = $("#btn-save");
  btn.disabled = true;
  try {
    const j = await api("/api/protocol/save", {
      id: S.editProtocolId || 0,
      kind: S.proto.kind, meta: S.proto.meta, object_name: S.proto.object_name,
      customer: S.proto.customer, pdate: S.proto.pdate, number: S.proto.number,
      lab_no: S.proto.lab_no, act_no: S.proto.act_no, need_act: S.proto.need_act,
      draft: S.proto.draft, internal: S.proto.internal, lab_head: S.proto.lab_head, engineer: S.proto.engineer,
    });
    await loadState();
    showSaved("Протокол", j);
    S.editProtocolId = null;
  } catch (e) { toast(e.message, true); }
  btn.disabled = false;
}

function showSaved(title, j) {
  const url = "/api/download?f=" + encodeURIComponent(j.file);
  openModal(`
    <h2 style="margin-top:0">${title} № ${esc(j.number)} сформирован</h2>
    <p class="small">${j.lab_no ? "Лабораторный № " + esc(j.lab_no) + " · " : ""}${j.act_no ? "Акт отбора № " + esc(j.act_no) + " · " : ""}
      файл сохранён в папке «Документы».</p>
    <div class="flex mt16">
      ${title.indexOf("Отчёт") === 0 ? `<button class="btn ok" data-send="${j.id}">Отправить заказчику</button>` : ""}
      ${j.pdf ? `<button class="btn ok" data-prev="${esc(j.pdf)}">Просмотр</button>
        <a class="btn ghost" href="/api/download?f=${encodeURIComponent(j.pdf)}">Скачать PDF</a>` : ""}
      <a class="btn ghost" href="${url}">Скачать .docx</a>
      <button class="btn ghost" onclick="closeModal()">Закрыть</button>
    </div>
    ${j.pdf ? "" : '<div class="hintline">PDF не сформирован: проверьте, что установлен Microsoft Word.</div>'}`);
}

/* ------------------------------------------------------------------ reports */
async function viewReports() {
  setTitle("Отчёты по контрактам", "Отчёты строительного контроля по форме НИЦ СМК");
  const list = S.data.reports;
  $("#view").innerHTML = `
    <div class="toolbar">
      <div class="left"></div>
      <div class="small"></div>
    </div>
    <div class="card">
      ${list.length ? `<table class="tbl">
        <thead><tr><th>№</th><th>Период</th><th>Объект</th><th>Контракт</th><th></th></tr></thead>
        <tbody>${list.map(r => `<tr>
          <td class="mono"><b>${esc(r.number)}</b></td>
          <td>${period(r.date_from, r.date_to)}</td>
          <td>${esc(r.object_name || "—")}</td>
          <td class="small">${esc((r.contract || "—").slice(0, 60))}</td>
          <td class="right">
            <button class="btn ghost sm" data-send="${r.id}">Отправить</button>
            ${r.pdf ? `<button class="btn sm" data-prev="${esc(r.pdf)}">Просмотр</button>
              <a class="btn ghost sm" href="/api/download?f=${encodeURIComponent(r.pdf)}">PDF</a>` : ""}
            ${r.file ? `<a class="btn ghost sm" href="/api/download?f=${encodeURIComponent(r.file)}">DOCX</a>` : ""}
          </td>
        </tr>`).join("")}</tbody></table>` : `<div class="empty">Отчётов пока нет.</div>`}
    </div>`;
  if ($("#new-report")) $("#new-report").onclick = () => go("reports/new");
}

function defaultPeriod() {
  const d = new Date();
  const to = new Date(d);
  const from = new Date(d.getTime() - 6 * 86400000);
  const iso = (x) => new Date(x.getTime() - x.getTimezoneOffset() * 60000).toISOString().slice(0, 10);
  return { from: iso(from), to: iso(to) };
}

function blankReport() {
  const comp = S.data.company || {};
  const p = defaultPeriod();
  return {
    date_from: p.from, date_to: p.to,
    customer: "", executor: comp.executor || comp.name || "",
    object_title: "", contract: "", address: "",
    specialist: (S.data.employees[0] || {}).name || comp.lab_head || "",
    ks: "", ks_date: p.to,
    acts: "", works: [{ section: "", name: "", unit: "м²", total: "", period: "" }],
    tests: [], passports: [{ material: "", doc: "", date: "" }],
    conclusion: "", verdict: "", photos: [], ai_text: "",
  };
}

async function viewReportForm() {
  await loadGroups();
  setTitle("Новый отчёт строительного контроля", "По форме вашего отчёта: разделы, таблицы, подпись и печать");
  S.report = blankReport();
  if (S.editReportId) {
    try {
      const j = await api("/api/report/get?id=" + S.editReportId);
      const pl = JSON.parse(j.data.payload || "{}");
      S.report = Object.assign(blankReport(), pl);
      toast("Редактирование отчёта " + (j.data.number || ""));
    } catch (e) { toast(e.message, true); S.editReportId = null; }
  }
  $("#view").innerHTML = `
    <div class="toolbar">
      <button class="btn ghost" onclick="go('documents')">← К документам</button>
      <div class="flex"><button class="btn" id="rep-collect">Собрать из объекта</button>
        <span class="small">Номер присваивается автоматически · подпись и печать из настроек</span></div>
    </div>
    <div class="split">
      <div class="card"><div class="pad" id="rep-form"></div></div>
      <div class="sticky"><div class="card"><div class="pad" id="rep-preview">
        <h2>Предпросмотр</h2><div class="empty">Заполните данные и нажмите «Показать текст»</div>
      </div></div></div>
    </div>`;
  renderReportForm();
  $("#rep-collect").onclick = async () => {
    const objs = (S.data.objects || []).filter(o => (o.status || "active") === "active");
    openModal(`<h2 style="margin-top:0">Собрать отчёт из объекта</h2>
      <div class="field"><label class="f">Объект</label><select id="rc-obj">
        ${objectOptions(objs, 0)}</select></div>
      <div class="hintline">Подтянутся объёмы по КС-2, протоколы, замечания и фото.</div>
      <div class="flex mt16"><button class="btn" id="rc-go">Собрать</button>
        <button class="btn ghost" onclick="closeModal()">Отмена</button></div>`);
    $("#rc-go").onclick = async () => {
      const b = $("#rc-go"); b.disabled = true; b.textContent = "Собираю…";
      try {
        const r = await api("/api/report/collect", { object_id: +$("#rc-obj").value,
          date_from: S.report.date_from, date_to: S.report.date_to });
        const rep = S.report;
        rep.object_title = r.object.title; rep.customer = r.object.customer;
        rep.contract = r.object.contract; rep.address = r.object.address;
        rep.works = (r.works || []).slice() || rep.works;
        rep.tests = r.tests || [];
        rep.photos = (r.photos || []).map(p => p.path).filter(Boolean);
        rep.acts = r.acts || "";
        rep.conclusion = (r.issues && r.issues.length)
          ? "Замечания: " + r.issues.join("; ")
          : "Замечаний не выявлено.";
        closeModal(); renderReportForm();
        toast(`Собрано: работ ${(r.works || []).length}, протоколов ${(r.tests || []).length}, фото ${(r.photos || []).length}`);
      } catch (e) { toast(e.message, true); b.disabled = false; b.textContent = "Собрать"; }
    };
  };
}

function renderReportForm() {
  const r = S.report;
  const contracts = S.data.contracts;
  const employees = S.data.employees;
  $("#rep-form").innerHTML = `
    <div class="form-section">
      <div class="head"><h3>Период и объект</h3></div>
      <div class="row c2">
        <div class="field"><label class="f">Начало периода</label><input type="date" id="r-from" value="${r.date_from}"></div>
        <div class="field"><label class="f">Конец периода</label><input type="date" id="r-to" value="${r.date_to}"></div>
      </div>
      <div class="field"><label class="f">Контракт (подставит заказчика и объект)</label>
        <select id="r-contract">
          <option value="">— выбрать из справочника —</option>
          ${contracts.map(c => `<option value="${esc(c.id)}">${esc(c.number)} · ${esc((c.subject || "").slice(0, 60))}</option>`).join("")}
        </select>
      </div>
      <div class="field"><label class="f">Заказчик</label><input type="text" id="r-customer" value="${esc(r.customer)}"></div>
      <div class="field"><label class="f">Исполнитель (кто выдаёт отчёт)</label><input type="text" id="r-executor" value="${esc(r.executor)}"></div>
      <div class="field"><label class="f">Объект (наименование работ по контракту)</label>
        <textarea id="r-objecttitle" rows="2">${esc(r.object_title)}</textarea></div>
      <div class="field"><label class="f">Муниципальный контракт</label>
        <textarea id="r-contracttext" rows="2">${esc(r.contract)}</textarea></div>
      <div class="field"><label class="f">Адрес объекта (пешеходной коммуникации и т. п.)</label>
        <input type="text" id="r-address" value="${esc(r.address)}" placeholder="м.о. г. Дубна, проспект Боголюбова д. 45"></div>
      <div class="row c3">
        <div class="field"><label class="f">КС-2 №</label><input type="text" id="r-ks" value="${esc(r.ks)}" placeholder="3"></div>
        <div class="field"><label class="f">Дата акта КС-2</label><input type="date" id="r-ksdate" value="${r.ks_date}"></div>
        <div class="field"><label class="f">Специалист</label>
          <input type="text" id="r-spec" list="emp-list" value="${esc(r.specialist)}">
          <datalist id="emp-list">${employees.map(e => `<option value="${esc(e.name)}">`).join("")}</datalist></div>
      </div>
    </div>

    <div class="form-section">
      <div class="head"><h3>Объёмы работ</h3><button class="btn soft sm" id="add-work">＋ Добавить</button></div>
      <div id="works-list"></div>
      <div class="hintline">«Раздел» заполняйте, чтобы получить строку-заголовок раздела. «Нарастающим итогом» и «Остаток» считаются сами.</div>
    </div>

    <div class="form-section">
      <div class="head"><h3>Акты скрытых работ</h3></div>
      <textarea id="r-acts" rows="5" placeholder="№1 от 22.09.2026 «Демонтажные работы…»;&#10;№2 от 22.09.2026 «Разработка грунта…»;">${esc(r.acts)}</textarea>
      <div class="hintline">Каждый акт — с новой строки. Попадут в раздел «Объёмы работ».</div>
    </div>

    <div class="form-section">
      <div class="head"><h3>Испытания (форма Ф-7)</h3>
        <div class="flex"><button class="btn soft sm" id="fill-tests">Взять протоколы по объекту</button>
        <button class="btn soft sm" id="add-test">＋ Строка</button></div></div>
      <div id="tests-list"></div>
      <div class="hintline">Если строк нет — раздел в отчёт не попадёт.</div>
    </div>

    <div class="form-section">
      <div class="head"><h3>Паспорта и сертификаты</h3><button class="btn soft sm" id="add-passport">＋ Строка</button></div>
      <div id="passports-list"></div>
    </div>

    <div class="form-section">
      <div class="head"><h3>Заключение и вывод</h3></div>
      <div class="field"><label class="f">Заключение</label>
        <textarea id="r-conclusion" rows="4" placeholder="оставьте пустым — сформируется автоматически">${esc(r.conclusion)}</textarea></div>
      <div class="field"><label class="f">Вывод</label>
        <textarea id="r-verdict" rows="3" placeholder="оставьте пустым — сформируется автоматически">${esc(r.verdict)}</textarea></div>
    </div>

    <div class="form-section">
      <div class="head"><h3>ИИ-помощник</h3><span class="small">нужен ключ в «Настройках»</span></div>
      <div class="flex mb8">
        <button class="btn soft sm" id="ai-text">Сформировать текст</button>
        <button class="btn soft sm" id="ai-photos">Проанализировать фото</button>
      </div>
      <textarea id="r-ai" rows="3" placeholder="Дополнительные сведения — можно написать вручную или сгенерировать">${esc(r.ai_text)}</textarea>
    </div>

    <div class="form-section">
      <div class="head"><h3>Фотографии</h3><span class="small">${r.photos.length} шт.</span></div>
      <div class="dropzone" id="drop">Перетащите фотографии сюда или нажмите, чтобы выбрать<br>
        <span class="small">JPG, PNG · до 20 файлов за раз</span></div>
      <input type="file" id="file-input" accept="image/*" multiple hidden>
      <div class="thumbs" id="thumbs"></div>
    </div>

    <div class="flex mt16">
      <button class="btn ok" id="btn-save-report">Сформировать отчёт</button>
      <button class="btn ghost" id="btn-text">Показать текст</button>
    </div>`;

  renderWorks(); renderTests(); renderPassports(); renderThumbs();

  const bind = (id, key, ev = "input") => { const el = $(id); if (el) el.addEventListener(ev, e => r[key] = e.target.value); };
  bind("#r-from", "date_from", "change"); bind("#r-to", "date_to", "change");
  bind("#r-customer", "customer"); bind("#r-executor", "executor");
  bind("#r-objecttitle", "object_title"); bind("#r-contracttext", "contract");
  bind("#r-address", "address"); bind("#r-ks", "ks"); bind("#r-ksdate", "ks_date", "change");
  bind("#r-spec", "specialist"); bind("#r-acts", "acts");
  bind("#r-conclusion", "conclusion"); bind("#r-verdict", "verdict"); bind("#r-ai", "ai_text");

  $("#r-contract").onchange = e => {
    const c = S.data.contracts.find(x => String(x.id) === e.target.value);
    if (!c) return;
    r.customer = c.customer || r.customer;
    r.object_title = c.subject || r.object_title;
    const dt = c.cdate ? " от " + fmtDate(c.cdate) : "";
    r.contract = `№${c.number}${dt} «${c.subject || ""}»`;
    renderReportForm();
    toast("Данные контракта подставлены");
  };

  $("#add-work").onclick = () => { r.works.push({ section: "", name: "", unit: "м²", total: "", period: "" }); renderWorks(); };
  $("#add-test").onclick = () => { r.tests.push({ date: "", material: "", place: "", requirement: "", result: "Соответствует", mark: "+" }); renderTests(); };
  $("#add-passport").onclick = () => { r.passports.push({ material: "", doc: "", date: "" }); renderPassports(); };
  $("#fill-tests").onclick = fillTestsFromProtocols;
  $("#btn-text").onclick = previewReport;
  $("#btn-save-report").onclick = saveReport;
  $("#ai-text").onclick = () => aiReport("text");
  $("#ai-photos").onclick = () => aiReport("photos");

  const drop = $("#drop"), fi = $("#file-input");
  drop.onclick = () => fi.click();
  fi.onchange = () => uploadPhotos(fi.files);
  ["dragenter", "dragover"].forEach(ev => drop.addEventListener(ev, e => { e.preventDefault(); drop.style.borderColor = "var(--accent)"; }));
  ["dragleave", "drop"].forEach(ev => drop.addEventListener(ev, e => { e.preventDefault(); drop.style.borderColor = ""; }));
  drop.addEventListener("drop", e => { if (e.dataTransfer.files.length) uploadPhotos(e.dataTransfer.files); });
}

function renderWorks() {
  const r = S.report;
  const box = $("#works-list");
  if (!box) return;
  box.innerHTML = `
    <div class="row work-row head"><div class="small">Раздел</div><div class="small">Наименование работ</div>
      <div class="small">Ед.</div><div class="small">По контракту</div><div class="small">За период</div><div></div></div>
    ${r.works.map((w, i) => `
    <div class="row work-row" style="margin-bottom:8px">
      <input type="text" data-w="${i}" data-k="section" value="${esc(w.section)}" placeholder="Раздел 1">
      <input type="text" data-w="${i}" data-k="name" value="${esc(w.name)}" placeholder="Работа">
      <input type="text" data-w="${i}" data-k="unit" value="${esc(w.unit)}" placeholder="ед.">
      <input type="text" data-w="${i}" data-k="total" value="${esc(w.total)}" placeholder="0">
      <input type="text" data-w="${i}" data-k="period" value="${esc(w.period)}" placeholder="0">
      <button class="iconbtn" data-rm="${i}">✕</button>
    </div>`).join("")}`;
  $$("#works-list [data-w]").forEach(inp => inp.oninput = () => {
    S.report.works[+inp.dataset.w][inp.dataset.k] = inp.value;
  });
  $$("#works-list [data-rm]").forEach(b => b.onclick = () => {
    S.report.works.splice(+b.dataset.rm, 1);
    if (!S.report.works.length) S.report.works.push({ section: "", name: "", unit: "м²", total: "", period: "" });
    renderWorks();
  });
}

function renderTests() {
  const r = S.report;
  const box = $("#tests-list");
  if (!box) return;
  if (!r.tests.length) { box.innerHTML = `<div class="hintline">Строк нет — раздел Ф-7 не будет включён.</div>`; return; }
  box.innerHTML = r.tests.map((t, i) => `
    <div class="row test-row" style="margin-bottom:8px">
      <input type="text" data-t="${i}" data-k="date" value="${esc(t.date)}" placeholder="дата">
      <input type="text" data-t="${i}" data-k="material" value="${esc(t.material)}" placeholder="материал">
      <input type="text" data-t="${i}" data-k="place" value="${esc(t.place)}" placeholder="участок">
      <input type="text" data-t="${i}" data-k="requirement" value="${esc(t.requirement)}" placeholder="требование">
      <input type="text" data-t="${i}" data-k="result" value="${esc(t.result)}" placeholder="результат">
      <button class="iconbtn" data-trm="${i}">✕</button>
    </div>`).join("");
  $$("#tests-list [data-t]").forEach(inp => inp.oninput = () => {
    S.report.tests[+inp.dataset.t][inp.dataset.k] = inp.value;
  });
  $$("#tests-list [data-trm]").forEach(b => b.onclick = () => { S.report.tests.splice(+b.dataset.trm, 1); renderTests(); });
}

function renderPassports() {
  const r = S.report;
  const box = $("#passports-list");
  if (!box) return;
  box.innerHTML = r.passports.map((t, i) => `
    <div class="row passport-row" style="margin-bottom:8px">
      <input type="text" data-p="${i}" data-k="material" value="${esc(t.material)}" placeholder="материал">
      <input type="text" data-p="${i}" data-k="doc" value="${esc(t.doc)}" placeholder="паспорт / сертификат">
      <input type="text" data-p="${i}" data-k="date" value="${esc(t.date)}" placeholder="дата">
      <button class="iconbtn" data-prm="${i}">✕</button>
    </div>`).join("");
  $$("#passports-list [data-p]").forEach(inp => inp.oninput = () => {
    S.report.passports[+inp.dataset.p][inp.dataset.k] = inp.value;
  });
  $$("#passports-list [data-prm]").forEach(b => b.onclick = () => { S.report.passports.splice(+b.dataset.prm, 1); renderPassports(); });
}

function fillTestsFromProtocols() {
  const addr = (S.report.address || "").toLowerCase().trim();
  let list = S.data.protocols || [];
  if (addr) {
    const hit = list.filter(p => (p.object_name || "").toLowerCase().includes(addr) || addr.includes((p.object_name || "").toLowerCase()));
    if (hit.length) list = hit;
  }
  if (!list.length) { toast("В журнале пока нет протоколов", true); return; }
  S.report.tests = list.slice(0, 12).map(p => ({
    date: fmtDate(p.pdate),
    material: `${p.kind_label}: ${p.sample || "образцы"}`,
    place: p.object_name || S.report.address,
    requirement: "СП 82.13330.2016, ГОСТ",
    result: "Соответствует",
    mark: "+",
  }));
  renderTests();
  toast("Добавлено протоколов: " + S.report.tests.length);
}

async function uploadPhotos(files) {
  const arr = [...files].slice(0, 20);
  for (const f of arr) {
    try {
      const res = await fetch("/api/upload?name=" + encodeURIComponent(f.name), { method: "POST", body: f });
      const j = await res.json();
      if (!j.ok) throw new Error(j.error);
      S.report.photos.push({ path: j.path, rel: j.rel, name: f.name, caption: "", date: "" });
    } catch (e) { toast("Не удалось загрузить " + f.name + ": " + e.message, true); }
  }
  renderThumbs();
  const counter = $("#rep-form .head .small");
  if (counter) counter.textContent = S.report.photos.length + " шт.";
}

function renderThumbs() {
  const box = $("#thumbs");
  if (!box) return;
  box.innerHTML = S.report.photos.map((p, i) => `
    <div class="thumb">
      <img src="/api/photo?f=${encodeURIComponent(p.rel)}" alt="">
      <button class="rm" data-prm="${i}">✕</button>
      <div class="cap">
        <input type="text" data-pc="${i}" value="${esc(p.caption)}" placeholder="подпись к фото">
        <input type="text" data-pd="${i}" value="${esc(p.date)}" placeholder="дата">
      </div>
    </div>`).join("");
  $$("#thumbs [data-pc]").forEach(i => i.oninput = () => S.report.photos[+i.dataset.pc].caption = i.value);
  $$("#thumbs [data-pd]").forEach(i => i.oninput = () => S.report.photos[+i.dataset.pd].date = i.value);
  $$("#thumbs [data-prm]").forEach(b => b.onclick = () => { S.report.photos.splice(+b.dataset.prm, 1); renderThumbs(); });
}

async function aiReport(mode) {
  const r = S.report;
  const works = r.works.filter(w => w.name.trim()).map(w => `${w.name} — ${w.period} ${w.unit}`).join("; ");
  const base = `Объект: ${r.address || r.object_title}. Заказчик: ${r.customer}. Контракт: ${r.contract}. ` +
    `Период: ${r.date_from} — ${r.date_to}. Работы: ${works || "не указаны"}.`;
  const prompt = mode === "photos"
    ? base + " Опиши по фотографиям, какие работы выполняются, качество и замечания. " +
      "Сформулируй 3–5 предложений официальным языком для отчёта строительного контроля."
    : base + " Сформулируй связный текст раздела отчёта строительного контроля (3–5 предложений). " +
      "Официальный стиль, без вымысла.";
  try {
    toast("Запрос к ИИ…");
    const j = await api("/api/ai", { prompt, photos: mode === "photos" ? r.photos.map(p => p.path) : [] });
    r.ai_text = j.text;
    const el = $("#r-ai");
    if (el) el.value = j.text;
    toast("Текст получен — проверьте и при необходимости отредактируйте");
  } catch (e) { toast(e.message, true); }
}

async function previewReport() {
  try {
    const j = await api("/api/report/preview", { data: S.report });
    $("#rep-preview").innerHTML = `<h2>Предпросмотр</h2>` +
      j.sections.map(([t, b]) => `<div class="form-section"><div class="head"><h3>${esc(t)}</h3></div>
        <div class="small" style="line-height:1.6">${esc(b)}</div></div>`).join("") +
      `<div class="hintline">В документ войдут таблицы объёмов и дневника, подпись, печать и фотографии.</div>`;
  } catch (e) { toast(e.message, true); }
}

async function saveReport() {
  const r = S.report;
  if (!r.works.some(w => (w.name || "").trim())) { toast("Добавьте хотя бы одну работу", true); return; }
  const payload = {
    ...r,
    acts: String(r.acts || "").split("\n").map(s => s.trim()).filter(Boolean),
    tests: (r.tests || []).filter(t => (t.material || "").trim()),
    passports: (r.passports || []).filter(p => (p.material || "").trim()),
  };
  const btn = $("#btn-save-report");
  btn.disabled = true;
  try {
    const j = await api("/api/report/save", { data: payload, id: S.editReportId || 0 });
    await loadState();
    showSaved("Отчёт", j);
    S.editReportId = null;
  } catch (e) { toast(e.message, true); }
  btn.disabled = false;
}

/* ------------------------------------------------------------------ directory */
async function viewDirectory() {
  setTitle("Объекты и контракты", "Справочники, которые подставляются в документы");
  const tab = S.dirTab;
  const objects = S.data.objects;
  const objType = S.dirType || "contract";
  const statusFilter = S.dirStatus || "active";
  const contracts = S.data.contracts;
  $("#view").innerHTML = `
    <div class="segmented mb8" id="dir-type">
      <button data-type="contract" class="${objType === "contract" ? "active" : ""}">Контрактные (гос)</button>
      <button data-type="commercial" class="${objType === "commercial" ? "active" : ""}">Неконтрактные (коммерческие)</button>
    </div>
    <div class="tabs" id="dir-tabs">
      <button data-tab="objects" class="${tab === "objects" ? "active" : ""}">Объекты (${objects.length})</button>
      <button data-tab="import" class="${tab === "import" ? "active" : ""}">＋ Объект по папке</button>
      <button data-tab="folders" class="${tab === "folders" ? "active" : ""}">Папки на диске</button>
      <button data-tab="contracts" class="${tab === "contracts" ? "active" : ""}">Контракты (${contracts.length})</button>
    </div>
    <div id="dir-body"></div>`;
  if ($("#dir-type")) $("#dir-type").onclick = e => {
    const b = e.target.closest("button[data-type]"); if (!b) return;
    S.dirType = b.dataset.type; viewDirectory();
  };
  $("#dir-tabs").onclick = e => {
    const b = e.target.closest("button[data-tab]"); if (!b) return;
    S.dirTab = b.dataset.tab; viewDirectory();
  };
  if (tab === "manual") {
    $("#dir-body").innerHTML = `<div class="card"><div class="pad">
      <h2 style="margin-top:0">Новый объект</h2>
      <p class="small">Объект появится в списке сразу. Папку можно привязать позже.</p>
      <div class="row c2">
        <div><label class="f">Название объекта</label><input id="mn-name" placeholder="Дворовые территории"></div>
        <div><label class="f">Адрес</label><input id="mn-addr" placeholder="г. Дубна, ..."></div>
      </div>
      <div class="row c3 mt8">
        <div><label class="f">Тип</label><select id="mn-type">
          <option value="contract">Контрактный (гос)</option>
          <option value="commercial">Неконтрактный</option></select></div>
        <div><label class="f">Заказчик</label><input id="mn-cust"></div>
        <div><label class="f">Контракт</label><select id="mn-contract"><option value="0">— не выбран —</option>
          ${contracts.map(c => `<option value="${c.id}">${esc(c.number)} — ${esc((c.customer || "").slice(0, 40))}</option>`).join("")}</select></div>
      </div>
      <div class="flex mt16"><button class="btn ok" id="mn-go">Создать объект</button></div>
    </div></div>`;
    $("#mn-go").onclick = async () => {
      try {
        const r = await api("/api/object/manual", { name: $("#mn-name").value, address: $("#mn-addr").value,
          customer: $("#mn-cust").value, type: $("#mn-type").value, contract_id: +$("#mn-contract").value });
        await loadState(); toast("Объект создан");
        location.hash = "#/object/" + r.id;
      } catch (e) { toast(e.message, true); }
    };
    return;
  }
  if (tab === "folders") {
    let data = { path: "", parent: "", dirs: [], files: [], object_id: null };
    try { data = await api("/api/fs/list?path=" + encodeURIComponent(S.fsPath || "")); }
    catch (e) { $("#dir-body").innerHTML = `<div class="card"><div class="pad"><div class="verdict bad">${esc(e.message)}</div></div></div>`; return; }
    S.fsPath = data.path;
    const parts = data.path.split("\\");
    const crumbs = parts.map((x, i) => `<a href="#" data-fs="${esc(parts.slice(0, i + 1).join("\\"))}">${esc(x)}</a>`).join(" / ");
    $("#dir-body").innerHTML = `<div class="card">
      <div class="panel-head"><span>Структура папок</span>
        <span class="flex"><button class="btn sm" id="fs-add">＋ Объект в этой папке</button>
        <span class="small">${data.dirs.length} папок · ${data.files.length} файлов</span></span></div>
      <div class="panel-body pad"><div class="small mb8">${crumbs}</div>
        ${data.object_id ? `<div class="verdict ok mb8">Эта папка уже привязана к объекту
          <a class="btn sm" href="#/object/${data.object_id}">Открыть объект</a></div>` : ""}
        <table class="tbl"><thead><tr><th>Папка</th><th>Элементов</th><th>Объект</th><th></th></tr></thead><tbody>
        ${data.dirs.map(d => `<tr>
          <td><a href="#" data-fs="${esc(d.path)}"><b>${esc(d.name)}</b></a></td>
          <td class="num">${d.count}</td>
          <td class="small">${d.object_id ? "привязана" : "—"}</td>
          <td class="right">${d.object_id
            ? `<a class="btn ghost sm" href="#/object/${d.object_id}">Открыть</a>`
            : `<button class="btn sm" data-link="${esc(d.path)}" data-name="${esc(d.name)}">＋ Объект</button>`}</td>
        </tr>`).join("") || `<tr><td colspan="4" class="empty">Папок нет</td></tr>`}
        </tbody></table>
        ${data.files.length ? `<div class="small mt8">Файлы: ${data.files.slice(0, 10).map(f => esc(f.name)).join(" · ")}${data.files.length > 10 ? " …" : ""}</div>` : ""}
      </div></div>`;
    $$("#dir-body [data-fs]").forEach(a => a.onclick = (e) => {
      e.preventDefault(); S.fsPath = a.dataset.fs; viewDirectory();
    });
    $("#fs-add").onclick = () => {
      const parent = data.path;
      openModal(`<h2 style="margin-top:0">Новый объект в папке</h2>
        <div class="small mb8">${esc(parent)}</div>
        <div class="field"><label class="f">Название объекта</label><input id="nf-name" placeholder="Дворовые территории"></div>
        <div class="row c2">
          <div><label class="f">Тип</label><select id="nf-type">
            <option value="contract">Контрактный (гос)</option>
            <option value="commercial">Неконтрактный</option></select></div>
          <div><label class="f">Заказчик</label><input id="nf-cust"></div>
        </div>
        <div class="flex mt16"><button class="btn ok" id="nf-go">Создать</button>
          <button class="btn ghost" onclick="closeModal()">Отмена</button></div>`);
      $("#nf-go").onclick = async () => {
        try {
          const r = await api("/api/object/in-folder", { parent, name: $("#nf-name").value,
            type: $("#nf-type").value, customer: $("#nf-cust").value });
          closeModal(); await loadState(); toast("Объект создан");
          location.hash = "#/object/" + r.id;
        } catch (e) { toast(e.message, true); }
      };
    };
    $$("#dir-body [data-link]").forEach(b => b.onclick = async () => {
      try {
        const r = await api("/api/object/import", { path: b.dataset.link, name: b.dataset.name });
        await loadState();
        toast(r.existed ? "Объект уже был создан" : "Объект создан");
        if (r.id) location.hash = "#/object/" + r.id;
      } catch (e) { toast(e.message, true); }
    });
    return;
  }
  if (tab === "import") {
    $("#dir-body").innerHTML = `<div class="card"><div class="pad">
      <h2 style="margin-top:0">Добавить объект по папке</h2>
      <div class="hintline">Специалист указывает папку — программа копирует документы, фото и КС-2 в себя,
      определяет тип объекта. Яндекс.Диск больше не нужен.</div>
      <div class="row c2 mt8">
        <div><label class="f">Путь к папке</label><input id="im-path" placeholder="C:\...\Объект"></div>
        <div><label class="f">Название объекта (если пусто — имя папки)</label><input id="im-name" placeholder="оставьте пустым"></div>
      </div>
      <div class="row c4 mt8">
        <div><label class="f">Тип</label><select id="im-type">
          <option value="contract">Контрактный (гос)</option>
          <option value="commercial">Неконтрактный (коммерческий)</option></select></div>
        <div><label class="f">Заказчик</label><input id="im-customer" placeholder="организация"></div>
        <div><label class="f">Контракт</label><select id="im-contract"><option value="0">— не выбран —</option>
          ${contracts.map(c => `<option value="${c.id}">${esc(c.number)} — ${esc((c.customer || "").slice(0, 40))}</option>`).join("")}</select></div>
        <div style="display:flex;align-items:flex-end"><button class="btn" id="im-go">Импортировать</button></div>
      </div>
      <div class="flex mt16">
        <button class="btn soft" id="im-tree">Загрузить дерево «Строительный контроль 2026»</button>
        <span class="small">каждый адрес станет отдельным объектом, файлы не копируются</span>
      </div>
      <div id="im-result" class="mt8"></div>
    </div></div>`;
    $("#im-tree").onclick = async () => {
      const b = $("#im-tree"); b.disabled = true; b.textContent = "Сканирую 2026…";
      try {
        const r = await api("/api/objects/import-tree", {});
        await loadState();
        $("#im-result").innerHTML = `<div class="verdict ok">Создано объектов: ${r.created}, уже были: ${r.skipped}.
          ${(r.items || []).length ? "<div class='small mt8'>" + r.items.map(x => esc(x.name)).join(" · ") + "</div>" : ""}</div>`;
        toast("Объекты добавлены: " + r.created);
      } catch (e) { toast(e.message, true); }
      b.disabled = false; b.textContent = "Загрузить дерево «Строительный контроль 2026»";
    };
    $("#im-go").onclick = async () => {
      const b = $("#im-go"); b.disabled = true; b.textContent = "Копирую…";
      try {
        const r = await api("/api/object/import", {
          path: $("#im-path").value, name: $("#im-name").value,
          type: $("#im-type").value, customer: $("#im-customer").value,
          contract_id: $("#im-contract").value,
        });
        $("#im-result").innerHTML = `<div class="verdict ok">Объект «${esc(r.name)}» добавлен:
          файлов ${r.files}, из них КС-2 ${r.acts}, фото ${r.photos}, пропущено ${r.skipped}.</div>`;
        await loadState();
        setTimeout(() => { S.dirTab = "objects"; viewDirectory(); }, 900);
      } catch (e) { toast(e.message, true); b.disabled = false; b.textContent = "Импортировать"; }
    };
    return;
  }
  if (tab === "objects") {
    const list = objects.filter(o => (o.status || "active") === statusFilter && (o.obj_type || "contract") === objType);
    let groups = [];
    try { groups = (await api("/api/groups")).items || []; } catch (e) { groups = []; }
    const gsel = S.objGroup || 0;
    const list2 = gsel ? list.filter(o => (o.group_id || 0) === gsel) : list;
    $("#dir-body").innerHTML = `
      <div class="card"><div class="pad">
        <div class="dropzone" id="o-dropzone">
          <div class="dz-title">Перетащите сюда документы по объекту</div>
          <div class="small">PDF, DOCX, XLSX, фото, ZIP — можно папку или несколько файлов</div>
          <button class="btn ok mt8" id="o-upload">Выбрать файлы</button>
        </div>
      </div></div>
      <div class="flex mt16" style="flex-wrap:wrap">
        <button class="btn ${gsel === 0 ? "" : "ghost"} sm" data-grp="0">Все объекты (${objects.length})</button>
        ${groups.map(g => `<button class="btn ${gsel === g.id ? "" : "ghost"} sm" data-grp="${g.id}">${esc(g.name)} (${g.cnt})</button>`).join("")}
      </div>
      <div class="tabs mt8" id="obj-status-tabs">
        <button data-s="active" class="${statusFilter === "active" ? "active" : ""}">Активные (${objects.filter(o => (o.status || "active") === "active").length})</button>
        <button data-s="archive" class="${statusFilter === "archive" ? "active" : ""}">Архив (${objects.filter(o => o.status === "archive").length})</button>
      </div>
      <div class="card">${list2.length ? `<table class="tbl"><thead><tr><th>Объект</th><th>Группа</th><th>Записей</th><th></th></tr></thead>
        <tbody>${list2.map(o => `<tr>
          <td><a href="#/object/${o.id}" style="color:var(--text);text-decoration:none"><b>${esc(o.name)}</b></a></td>
          <td class="small">${esc(o.city || "—")}</td>
          <td class="num">${o.entries_count || 0}</td>
          <td class="right"><a class="btn ghost sm" href="#/object/${o.id}">Открыть</a></td></tr>`).join("")}</tbody></table>`
        : `<div class="empty">Объектов нет. Загрузите документы — объект появится сам.</div>`}</div>`;
    $$("#dir-body [data-grp]").forEach(b => b.onclick = () => { S.objGroup = +b.dataset.grp; viewDirectory(); });
    $("#obj-status-tabs").onclick = e => {
      const b = e.target.closest("button[data-s]"); if (!b) return;
      S.dirStatus = b.dataset.s; viewDirectory();
    };
    $("#o-upload").onclick = () => {
      const inp = document.createElement("input");
      inp.type = "file"; inp.multiple = true;
      inp.accept = ".pdf,.docx,.doc,.xlsx,.xls,.jpg,.jpeg,.png,.tif,.tiff,.zip";
      inp.onchange = () => createObjectFromFiles([...inp.files]);
      inp.click();
    };
    const dz = $("#o-dropzone");
    ["dragenter", "dragover"].forEach(ev => dz.addEventListener(ev, e => {
      e.preventDefault(); dz.classList.add("over");
    }));
    ["dragleave", "drop"].forEach(ev => dz.addEventListener(ev, e => {
      e.preventDefault(); dz.classList.remove("over");
    }));
    dz.addEventListener("drop", async e => {
      const files = await filesFromDrop(e.dataTransfer);
      if (files.length) createObjectFromFiles(files);
    });

  } else {
    $("#dir-body").innerHTML = `
      <div class="toolbar">
        <button class="btn soft" id="import-contracts">Импортировать из «Контракты ПИК 2026.xlsx»</button>
        <button class="btn ghost" id="add-contract">＋ Добавить вручную</button>
      </div>
      <div class="card">${contracts.length ? `<table class="tbl"><thead><tr><th>№ контракта</th><th>Дата</th><th>Предмет</th><th>Сумма</th><th>Заказчик</th><th>Объекты</th><th>Статус</th></tr></thead>
        <tbody>${contracts.map(c => `<tr>
          <td class="mono">${esc(c.number)}</td><td>${fmtDate(c.cdate)}</td>
          <td class="small" style="max-width:420px">${esc((c.subject || "").slice(0, 140))}</td>
          <td class="num">${c.price ? Number(c.price).toLocaleString("ru-RU") + " ₽" : "—"}</td>
          <td class="small">${esc((c.customer || "").slice(0, 60))}</td>
          <td class="small">${(c.objects || []).length ? `<b>${c.objects_count}</b> · ` + c.objects.slice(0, 3).map(o => `<a href="#/object/${o.id}">${esc(o.name)}</a>`).join(", ") + (c.objects.length > 3 ? " …" : "") : "—"}</td>
          <td><span class="badge neutral">${esc(c.status || "")}</span></td>
        </tr>`).join("")}</tbody></table>` : `<div class="empty">Контрактов нет. Импортируйте из Excel или добавьте вручную.</div>`}</div>`;
    $("#import-contracts").onclick = async () => {
      try {
        const j = await api("/api/contracts/import", {});
        await loadState(); viewDirectory();
        toast(`Импортировано контрактов: ${j.added}`);
      } catch (e) { toast(e.message, true); }
    };
    $("#add-contract").onclick = () => openModal(`
      <h2 style="margin-top:0">Новый контракт</h2>
      <div class="field"><label class="f">Номер</label><input id="c-num"></div>
      <div class="field"><label class="f">Предмет</label><textarea id="c-subj"></textarea></div>
      <div class="row c2">
        <div class="field"><label class="f">Дата</label><input type="date" id="c-date" value="${todayISO()}"></div>
        <div class="field"><label class="f">Сумма, ₽</label><input type="number" id="c-price"></div>
      </div>
      <div class="field"><label class="f">Заказчик</label><input id="c-cust"></div>
      <div class="flex"><button class="btn" id="c-save">Сохранить</button>
      <button class="btn ghost" onclick="closeModal()">Отмена</button></div>`);
    setTimeout(() => {
      const b = $("#c-save"); if (!b) return;
      b.onclick = async () => {
        await api("/api/contract", {
          number: $("#c-num").value, subject: $("#c-subj").value, cdate: $("#c-date").value,
          price: $("#c-price").value, customer: $("#c-cust").value, status: "Актуальные",
        });
        closeModal(); await loadState(); viewDirectory(); toast("Контракт добавлен");
      };
    }, 0);
  }
}

/* ------------------------------------------------------------------ settings */
async function viewSettings() {
  setTitle("Настройки", "Реквизиты, сотрудники, нормативы и искусственный интеллект");
  const c = S.data.company;
  const tab = S.settingsTab;
  $("#view").innerHTML = `
    <div class="tabs" id="set-tabs">
      <button data-tab="company" class="${tab === "company" ? "active" : ""}">Организация</button>
      <button data-tab="employees" class="${tab === "employees" ? "active" : ""}">Сотрудники</button>
      <button data-tab="access" class="${tab === "access" ? "active" : ""}">Доступы</button>
      <button data-tab="phone" class="${tab === "phone" ? "active" : ""}">Телефон</button>
      <button data-tab="backup" class="${tab === "backup" ? "active" : ""}">Резервные копии</button>
      <button data-tab="mail" class="${tab === "mail" ? "active" : ""}">Почта</button>
      <button data-tab="audit" class="${tab === "audit" ? "active" : ""}">Журнал</button>
      <button data-tab="norms" class="${tab === "norms" ? "active" : ""}">Нормативы</button>
      <button data-tab="ai" class="${tab === "ai" ? "active" : ""}">Искусственный интеллект</button>
      <button data-tab="numbering" class="${tab === "numbering" ? "active" : ""}">Нумерация</button>
    </div><div id="set-body"></div>`;
  $("#set-tabs").onclick = e => {
    const b = e.target.closest("button[data-tab]"); if (!b) return;
    S.settingsTab = b.dataset.tab; viewSettings();
  };
  const body = $("#set-body");

  if (tab === "company") {
    const f = (k, label, ph = "") => `<div class="field"><label class="f">${label}</label>
      <input type="text" data-c="${k}" value="${esc(c[k] || "")}" placeholder="${esc(ph)}"></div>`;
    body.innerHTML = `<div class="card"><div class="pad">
      <h2>Реквизиты организации</h2>
      <div class="row c2">${f("name", "Краткое наименование")}${f("full_name", "Полное наименование")}</div>
      <div class="row c2">${f("inn", "ИНН")}${f("kpp", "КПП")}</div>
      <div class="row c2">${f("ogrn", "ОГРН")}${f("address", "Адрес")}</div>
      <div class="row c2">${f("phone", "Телефон")}${f("email", "E-mail")}</div>
      <div class="row c2">${f("accreditation", "Аттестат аккредитации")}${f("lab_head", "Начальник лаборатории")}</div>
      <div class="field"><label class="f">Исполнитель по умолчанию (для отчётов)</label>
        <input type="text" data-c="executor" value="${esc(c.executor || "")}" placeholder="ООО «НИЦ СМК» или ИП …"></div>
      <h3 style="margin:18px 0 10px">Файлы оформления</h3>
      <div class="row c3">
        ${f("logo", "Логотип для шапки (путь к файлу)")}
        ${f("signature", "Подпись (PNG с прозрачным фоном)")}
        ${f("stamp", "Печать (PNG с прозрачным фоном)")}
      </div>
      <div class="flex" style="gap:20px;margin-bottom:14px">
        ${["logo", "signature", "stamp"].map(k => `<div style="text-align:center">
          <img src="/api/asset?f=${encodeURIComponent(c[k] || "")}" alt="" style="height:64px;display:block;margin:0 auto 4px">
          <span class="small">${k === "logo" ? "логотип" : k === "signature" ? "подпись" : "печать"}</span></div>`).join("")}
      </div>
      <div class="hintline">Путь указывается от папки программы, например <code>data/branding/logo.png</code>.
        Файлы можно заменить своими — документ подхватит их при следующей генерации.</div>
      <button class="btn mt16" id="save-company">Сохранить</button>
    </div></div>`;
    $("#save-company").onclick = async () => {
      const company = {};
      $$("[data-c]").forEach(i => company[i.dataset.c] = i.value);
      await api("/api/settings", { company });
      await loadState(); toast("Реквизиты сохранены");
    };
  }

  if (tab === "employees") {
    body.innerHTML = `<div class="card"><div class="pad">
      <div class="flex mb8"><h2 style="margin:0">Сотрудники</h2><div class="spacer"></div>
        <button class="btn soft sm" id="emp-add">＋ Добавить</button></div>
      <div id="emp-list"></div>
      <button class="btn mt16" id="save-emp">Сохранить</button>
    </div></div>`;
    const renderEmps = (list) => {
      $("#emp-list").innerHTML = list.map((e, i) => `<div class="row c2" style="margin-bottom:8px">
        <input data-e="${i}" data-k="name" value="${esc(e.name)}" placeholder="ФИО">
        <input data-e="${i}" data-k="position" value="${esc(e.position)}" placeholder="должность">
      </div>`).join("");
      $$("#emp-list input").forEach(i => i.oninput = () => list[+i.dataset.e][i.dataset.k] = i.value);
    };
    const list = S.data.employees.map(e => ({ ...e }));
    renderEmps(list);
    $("#emp-add").onclick = () => { list.push({ name: "", position: "" }); renderEmps(list); };
    $("#save-emp").onclick = async () => {
      await api("/api/settings", { employees: list });
      await loadState(); toast("Список сотрудников сохранён");
    };
  }

  if (tab === "access") {
    if (!rolesOf(S.data.user).includes("admin")) {
      body.innerHTML = `<div class="card"><div class="pad"><div class="empty">Раздел доступен администратору.</div></div></div>`;
    } else {
      const r = await api("/api/users", { action: "list" });
      body.innerHTML = `<div class="card"><div class="pad">
        <h2 style="margin-top:0">Доступы сотрудников</h2>
        <table class="tbl"><thead><tr><th>Сотрудник</th><th>Логин</th><th>Роль</th><th>Подпись</th><th>Статус</th><th></th></tr></thead>
        <tbody>${(r.items || []).map(u => `<tr><td>${esc(u.name)}</td><td class="mono">${esc(u.login)}</td>
          <td>${esc(roleNames(u))}</td>
          <td class="small">${u.signature ? `<img src="/api/asset?f=${encodeURIComponent(u.signature)}" style="height:26px;vertical-align:middle">` : "—"}
            <button class="btn ghost sm" data-sign="${u.id}">${u.signature ? "Заменить" : "Загрузить"}</button></td>
          <td>${u.active ? '<span class="badge ok">активен</span>' : '<span class="badge neutral">выключен</span>'}</td>
          <td class="right"><button class="btn ghost sm" data-utoggle="${u.id}">${u.active ? "Выключить" : "Включить"}</button></td></tr>`).join("") || `<tr><td colspan="6" class="empty">Пока никого нет</td></tr>`}</tbody></table>
        <div class="row c4 mt16">
          <div><label class="f">ФИО</label><input id="u-name"></div>
          <div><label class="f">Логин</label><input id="u-login"></div>
          <div><label class="f">Код</label><input id="u-pin" type="password"></div>
          <div style="grid-column:span 2"><label class="f">Роли (можно несколько)</label>
            <div class="flex" style="gap:14px;flex-wrap:wrap;padding-top:4px">
              <label class="flex" style="gap:5px"><input type="checkbox" data-newrole="engineer"> инженер СК</label>
              <label class="flex" style="gap:5px"><input type="checkbox" data-newrole="lab_head"> руководитель лаборатории</label>
              <label class="flex" style="gap:5px"><input type="checkbox" data-newrole="lab"> лаборант</label>
              <label class="flex" style="gap:5px"><input type="checkbox" data-newrole="admin"> администратор</label>
            </div></div>
        </div>
        <button class="btn mt8" id="u-add">Добавить сотрудника</button>
        <div class="hintline">Пока нет ни одного сотрудника — вход свободный. Первый созданный становится администратором.
          Сотрудники могут зарегистрироваться по телефону — активируйте заявку ниже.</div>
        <h3 class="mt16">Заявки на регистрацию</h3>
        ${(r.items || []).filter(u => (u.status || "active") === "pending").length ? `<table class="tbl"><thead><tr>
          <th>ФИО</th><th>Телефон</th><th>Код</th><th>Telegram</th><th></th></tr></thead>
          <tbody>${(r.items || []).filter(u => (u.status || "active") === "pending").map(u => `<tr>
            <td>${esc(u.name)}</td><td class="mono">${esc(u.phone || "—")}</td>
            <td class="mono">${esc(u.otp || "—")}</td>
            <td class="small">${u.tg_chat ? "привязан" : "нет"}</td>
            <td class="right"><button class="btn sm" data-activate="${u.id}">Активировать</button></td>
          </tr>`).join("")}</tbody></table>` : `<div class="empty">Заявок нет</div>`}
      </div></div>`;
      $("#u-add").onclick = async () => {
        try {
          const roles = $$("#users-box [data-newrole]:checked").map(c => c.dataset.newrole);
          await api("/api/users", { action: "add", name: $("#u-name").value, login: $("#u-login").value,
            pin: $("#u-pin").value, roles });
          toast("Сотрудник добавлен"); viewSettings();
        } catch (e) { toast(e.message, true); }
      };
      $$("#users-box [data-sign]").forEach(b => b.onclick = () => {
        const uid = +b.dataset.sign;
        const u = (r.items || []).find(x => x.id === uid) || {};
        openModal(`<h2 style="margin-top:0">Подпись сотрудника</h2>
          <div class="small mb8">${esc(u.name || "")}</div>
          ${u.signature ? `<img src="/api/asset?f=${encodeURIComponent(u.signature)}" style="height:70px;display:block;margin-bottom:10px">` : ""}
          <div class="field"><label class="f">Должность в подписи</label>
            <input id="sg-pos" value="${esc(u.position || "")}" placeholder="Инженер строительного контроля"></div>
          <input type="file" id="sg-file" accept="image/png,image/*">
          <div class="hintline">PNG с прозрачным фоном, ширина 600–1200 px.</div>
          <div class="flex mt16"><button class="btn" id="sg-save">Сохранить</button>
          <button class="btn ghost" onclick="closeModal()">Отмена</button></div>`);
        $("#sg-save").onclick = async () => {
          const b2 = $("#sg-save"); b2.disabled = true; b2.textContent = "Сохраняю…";
          try {
            let path = u.signature || "";
            const f = $("#sg-file").files[0];
            if (f) {
              const res = await fetch("/api/attach?name=" + encodeURIComponent("sign_" + uid + ".png"), { method: "POST", body: f });
              const j = await res.json();
              if (!j.ok) throw new Error(j.error || "Не удалось загрузить");
              path = j.rel;
            }
            await api("/api/users/signature", { id: uid, path, position: $("#sg-pos").value });
            closeModal(); toast("Подпись сохранена"); viewSettings();
          } catch (e) { toast(e.message, true); b2.disabled = false; b2.textContent = "Сохранить"; }
        };
      });
      $$("#users-box [data-activate]").forEach(b => b.onclick = () => {
        const id = +b.dataset.activate;
        openModal(`<h2 style="margin-top:0">Активировать сотрудника</h2>
          <div class="flex" style="gap:14px;flex-wrap:wrap">
            <label class="flex" style="gap:5px"><input type="checkbox" data-actrole="engineer" checked> инженер СК</label>
            <label class="flex" style="gap:5px"><input type="checkbox" data-actrole="lab_head"> руководитель лаборатории</label>
            <label class="flex" style="gap:5px"><input type="checkbox" data-actrole="lab"> лаборант</label>
            <label class="flex" style="gap:5px"><input type="checkbox" data-actrole="admin"> администратор</label>
          </div>
          <div class="flex mt16"><button class="btn" id="act-go">Активировать</button>
          <button class="btn ghost" onclick="closeModal()">Отмена</button></div>`);
        $("#act-go").onclick = async () => {
          const roles = $$(".modal [data-actrole]:checked").map(c => c.dataset.actrole);
          if (!roles.length) return toast("Выберите хотя бы одну роль", true);
          try {
            const res = await api("/api/users/activate", { id, roles });
            closeModal();
            openModal(`<h2 style="margin-top:0">Сотрудник активирован</h2>
              <div class="verdict ok">Код для входа: <b>${esc(res.code)}</b></div>
              <div class="hintline">${res.telegram_sent ? "Код отправлен в Telegram." : "Передайте код сотруднику — Telegram не привязан."}</div>
              <div class="flex mt16"><button class="btn" onclick="closeModal(); viewSettings()">Готово</button></div>`);
          } catch (e) { toast(e.message, true); }
        };
      });
      $$("#view [data-utoggle]").forEach(b => b.onclick = async () => {
        await api("/api/users/toggle", { id: +b.dataset.utoggle }); viewSettings();
      });
    }
  }

  if (tab === "backup") {
    const r = await api("/api/backup/list");
    const items = r.items || [];
    const cfg = S.data.backupCfg || { auto: true, keep: 14 };
    body.innerHTML = `<div class="card"><div class="pad">
      <h2 style="margin-top:0">Резервные копии</h2>
      <p class="small">Копия включает базу, фотографии, документы объектов и сформированные документы.</p>
      <div class="flex mb8"><button class="btn" id="bk-create">Создать копию сейчас</button>
        <span class="small">папка: ${esc(r.dir || "")}</span></div>
      <div class="row c2">
        <div><label class="flex" style="gap:8px;font-size:13px"><input type="checkbox" id="bk-auto" ${cfg.auto !== false ? "checked" : ""}> делать автоматически раз в день</label></div>
        <div><label class="f">Сколько копий хранить</label><input id="bk-keep" type="number" min="3" max="90" value="${cfg.keep || 14}"></div>
      </div>
      <button class="btn ghost sm mt8" id="bk-save">Сохранить настройки</button>
      <h3 class="mt16">Сохранённые копии</h3>
      ${items.length ? `<table class="tbl"><thead><tr><th>Файл</th><th>Дата</th><th>Размер</th></tr></thead>
        <tbody>${items.map(x => `<tr><td class="mono small">${esc(x.name)}</td>
          <td>${esc((x.date || "").replace("T", " "))}</td>
          <td class="num">${(x.size / 1048576).toFixed(1)} МБ</td></tr>`).join("")}</tbody></table>`
        : `<div class="empty">Копий пока нет</div>`}
      <div class="hintline">Для облака копии можно дополнительно складывать на Яндекс.Диск или внешний диск.</div>
    </div></div>`;
    $("#bk-create").onclick = async () => {
      const b = $("#bk-create"); b.disabled = true; b.textContent = "Копирую…";
      try { const j = await api("/api/backup/create", {}); toast("Копия создана: " + j.name); viewSettings(); }
      catch (e) { toast(e.message, true); b.disabled = false; b.textContent = "Создать копию сейчас"; }
    };
    $("#bk-save").onclick = async () => {
      await api("/api/settings", { backup: { auto: $("#bk-auto").checked, keep: +$("#bk-keep").value } });
      toast("Настройки копий сохранены");
    };
  }

  if (tab === "phone") {
    const url = S.phoneUrl || location.origin;
    body.innerHTML = `<div class="card"><div class="pad">
      <h2 style="margin-top:0">Программа на телефоне</h2>
      <p class="small">Приложение ставится на телефон как обычное: иконка на экране, полноэкранный режим.</p>
      <div class="flex mb8"><button class="btn" onclick="installPwa()" id="pwa-install">Установить приложение</button>
        <span class="small">на телефоне откройте этот адрес и нажмите кнопку</span></div>
      <div class="row c2">
        <div>
          <label class="f">Адрес для телефона</label>
          <div class="flex"><input id="ph-url" value="${esc(url)}" readonly>
            <button class="btn ghost sm" id="ph-copy">Копировать</button></div>
          <img src="/api/qr?text=${encodeURIComponent(url)}" alt="QR" style="width:220px;height:220px;margin-top:10px;border:1px solid var(--line);border-radius:6px">
          <div class="hintline">Наведите камеру телефона на QR — откроется программа.</div>
        </div>
        <div>
          <h3>Android</h3>
          <ol class="small" style="padding-left:18px;line-height:1.6">
            <li>Откройте адрес или отсканируйте QR.</li>
            <li>Меню браузера → «Добавить на главный экран».</li>
            <li>Разрешите камеру и микрофон.</li>
          </ol>
          <h3 class="mt16">iPhone</h3>
          <ol class="small" style="padding-left:18px;line-height:1.6">
            <li>Откройте адрес в Safari.</li>
            <li>«Поделиться» → «На экран Домой».</li>
            <li>Разрешите камеру и микрофон.</li>
          </ol>
          <div class="hintline mt8">Если телефон не открывает адрес — разрешите программе доступ в брандмауэре Windows
            (файл «Открыть порт для телефона.bat», запуск от администратора).</div>
        </div>
      </div>
    </div></div>`;
    $("#ph-copy").onclick = async () => {
      try { await navigator.clipboard.writeText(url); toast("Адрес скопирован"); }
      catch (e) { toast("Скопируйте вручную: " + url, true); }
    };
  }

  if (tab === "mail") {
    const r = await api("/api/settings/mail");
    const s = r.smtp || {}, m = r.messenger || {};
    body.innerHTML = `<div class="card"><div class="pad">
      <h2 style="margin-top:0">Почта (SMTP)</h2>
      <div class="row c4">
        <div><label class="f">Сервер</label><input id="m-host" value="${esc(s.host || "smtp.yandex.ru")}"></div>
        <div><label class="f">Порт</label><input id="m-port" value="${esc(s.port || 465)}"></div>
        <div><label class="f">Логин</label><input id="m-user" value="${esc(s.user || "")}"></div>
        <div><label class="f">Пароль</label><input id="m-pass" type="password" placeholder="${s.password === "***" ? "сохранён" : ""}"></div>
      </div>
      <div class="row c2 mt8">
        <div><label class="f">Адрес отправителя</label><input id="m-from" value="${esc(s.from || "")}"></div>
        <div><label class="f">TLS</label><select id="m-tls">
          <option value="1" ${s.tls !== false ? "selected" : ""}>да</option>
          <option value="0" ${s.tls === false ? "selected" : ""}>нет</option></select></div>
      </div>
      <h2 class="mt16">Telegram</h2>
      <div class="row c3">
        <div><label class="f">Токен бота</label><input id="m-tg" value="${esc(m.telegram_token || "")}"></div>
        <div><label class="f">Имя бота (без @)</label><input id="m-bot" value="${esc(m.telegram_bot || "")}" placeholder="nic_smk_bot"></div>
        <div><label class="f">chat_id администратора</label><input id="m-chat" value="${esc(m.telegram_chat || "")}"></div>
      </div>
      <div class="flex mt8"><button class="btn" id="m-save">Сохранить</button></div>
      <div class="hintline">Пароль Яндекс.Почты — «пароль приложения». Telegram нужен для кодов входа и отправки отчётов.</div>
    </div></div>`;
    $("#m-save").onclick = async () => {
      const smtp = { host: $("#m-host").value, port: +$("#m-port").value, user: $("#m-user").value,
        from: $("#m-from").value, tls: $("#m-tls").value === "1" };
      const pwd = $("#m-pass").value;
      if (pwd) smtp.password = pwd;
      await api("/api/settings", { smtp, messenger: {
        telegram_token: $("#m-tg").value, telegram_chat: $("#m-chat").value,
        telegram_bot: $("#m-bot").value.replace("@", "") } });
      toast("Настройки почты сохранены");
    };
  }

  if (tab === "audit") {
    if (!rolesOf(S.data.user).includes("admin")) {
      body.innerHTML = `<div class="card"><div class="pad"><div class="empty">Журнал доступен администратору.</div></div></div>`;
    } else {
      const r = await api("/api/audit?q=" + encodeURIComponent(S.auditQuery || ""));
      const items = r.items || [];
      body.innerHTML = `<div class="card"><div class="pad">
        <div class="flex mb8"><h2 style="margin:0">Журнал действий</h2><div class="spacer"></div>
          <label class="flex" style="gap:6px;font-size:12px"><input type="checkbox" id="au-on" ${r.enabled ? "checked" : ""}> вести журнал</label></div>
        <input id="au-q" value="${esc(S.auditQuery || "")}" placeholder="Фильтр: сотрудник, действие, документ">
        <div class="mt8" id="au-list"></div>
        <div class="hintline">Пишутся вход, создание и изменение документов, отправка. Пароли и ключи не сохраняются.</div>
      </div></div>`;
      const render = (list) => {
        $("#au-list").innerHTML = list.length ? `<table class="tbl"><thead><tr>
          <th>Когда</th><th>Сотрудник</th><th>Роль</th><th>Действие</th><th>Документ</th><th>Детали</th></tr></thead>
          <tbody>${list.map(a => `<tr>
            <td class="mono small">${esc((a.ts || "").replace("T", " ").slice(0, 16))}</td>
            <td>${esc(a.user_name || "—")}</td>
            <td class="small">${esc(roleNames({ role: a.role }))}</td>
            <td>${esc(a.action || "")}</td>
            <td class="small">${esc(a.entity || "")}</td>
            <td class="small">${esc((a.details || "").slice(0, 80))}</td>
          </tr>`).join("")}</tbody></table>` : `<div class="empty">Записей пока нет</div>`;
      };
      render(items);
      $("#au-q").onkeydown = (e) => { if (e.key === "Enter") { S.auditQuery = e.target.value; viewSettings(); } };
      $("#au-on").onchange = async (e) => {
        await api("/api/settings", { audit: { enabled: e.target.checked } });
        toast(e.target.checked ? "Журнал включён" : "Журнал выключен");
      };
    }
  }

  if (tab === "norms") {
    const norms = S.data.norms;
    body.innerHTML = `<div class="card"><div class="pad">
      <h2>Нормативы по видам испытаний</h2>
      <p class="small">Значения подставлены в документы и используются для проверки. Сверьте их с действующими редакциями ГОСТ перед работой.</p>
      ${Object.entries(norms).map(([k, n]) => `<div class="form-section"><div class="head"><h3>${esc(n.label)}</h3></div>
        ${(n.fields || []).length ? `
          <table class="tbl"><thead><tr><th>Показатель</th><th>Ед.</th><th>Мин.</th><th>Макс.</th><th>НД</th></tr></thead><tbody>
          ${n.fields.map((f, idx) => `<tr>
            <td>${esc(f.name)}</td><td>${esc(f.unit)}</td>
            <td><input style="width:90px" data-n="${k}.${idx}.lo" value="${f.lo ?? ""}"></td>
            <td><input style="width:90px" data-n="${k}.${idx}.hi" value="${f.hi ?? ""}"></td>
            <td class="small">${esc(f.gost || "")}</td></tr>`).join("")}
          </tbody></table>` : `<div class="hintline">Для этого вида испытания нормативы задаются в полях расчёта (требуемая прочность, нормативная нагрузка).</div>`}
      </div>`).join("")}
      <button class="btn" id="save-norms">Сохранить нормативы</button>
    </div></div>`;
    $("#save-norms").onclick = async () => {
      const next = JSON.parse(JSON.stringify(norms));
      $$("[data-n]").forEach(inp => {
        const [k, idx, bound] = inp.dataset.n.split(".");
        const val = inp.value.trim();
        next[k].fields[+idx][bound] = val === "" ? null : parseFloat(val.replace(",", "."));
      });
      await api("/api/settings", { norms: next });
      await loadState(); toast("Нормативы сохранены");
    };
  }

  if (tab === "numbering") {
    const n = S.data.numbering || {};
    const kinds = S.data.number_kinds || {};
    const log = S.data.number_log || [];
    body.innerHTML = `<div class="card"><div class="pad">
      <h2>Сквозная нумерация</h2>
      <p class="small">Логика взята из файла «прот №лаб №.xlsx»: у протоколов, лабораторных номеров,
      актов отбора и экспертных заключений — отдельные сквозные счётчики. Номера не сбрасываются
      при смене года и не пересекаются.</p>
      <table class="tbl"><thead><tr><th>Вид</th><th>Следующий номер</th><th>Последняя выдача</th><th></th></tr></thead>
        <tbody>${Object.entries(kinds).map(([k, label]) => {
          const last = log.find(x => x.kind === k);
          return `<tr><td>${esc(label)}</td>
            <td><input type="text" id="num-${k}" value="${n[k] || 1}" style="width:110px"></td>
            <td class="small">${last ? esc(last.value) + " · " + fmtDate(last.created_at) : "—"}</td>
            <td class="right"><button class="btn ghost sm" data-num-save="${k}">Сохранить</button></td></tr>`;
        }).join("")}</tbody></table>
      <div class="flex mt16">
        <button class="btn" id="num-sync">Синхронизировать из «прот №лаб №.xlsx»</button>
        <span class="small">Синхронизировано: ${S.data.numbering_synced_at ? fmtDate(S.data.numbering_synced_at) : "—"}</span>
      </div>
      <div class="hintline">Синхронизация читает все листы реестра и берёт максимальный номер по каждому виду.
        Счётчик не уменьшается: программа продолжит с большего значения.</div>
    </div></div>

    <div class="card mt16"><div class="pad">
      <h2>Журнал выдачи номеров</h2>
      ${log.length ? `<table class="tbl"><thead><tr><th>Когда</th><th>Вид</th><th>Номер</th><th>Объект</th></tr></thead>
        <tbody>${log.map(x => `<tr><td class="small">${esc(x.created_at || "")}</td>
          <td class="small">${esc(kinds[x.kind] || x.kind)}</td>
          <td class="mono"><b>${esc(x.value)}</b></td><td class="small">${esc(x.object_name || "—")}</td></tr>`).join("")}</tbody></table>`
        : `<div class="empty">Номера ещё не выдавались</div>`}
    </div></div>`;

    $$("[data-num-save]").forEach(b => b.onclick = async () => {
      const kind = b.dataset.numSave;
      const val = parseInt($("#num-" + kind).value, 10) || 1;
      await api("/api/numbering/set", { kind, value: val });
      await loadState(); viewSettings(); toast("Счётчик обновлён");
    });
    $("#num-sync").onclick = async () => {
      try {
        const j = await api("/api/numbering/sync", {});
        await loadState(); viewSettings();
        toast("Синхронизировано. Протоколы: " + (j.found.protocol || 0) + ", лаб.: " + (j.found.lab || 0));
      } catch (e) { toast(e.message, true); }
    };
  }

  if (tab === "ai") {
    const ai = S.data.aiCfg || {};
    const tx = ai.text || {}, vi = ai.vision || {};
    const block = (prof, title, hint, obj, defBase, defModel) => `
      <h2 class="${prof === "vision" ? "mt16" : ""}">${title}</h2>
      <p class="small">${hint}</p>
      <div class="field"><label class="f">API-ключ</label>
        <input id="ai-${prof}-key" value="" placeholder="${obj.key_set ? "ключ сохранён — введите новый" : "sk-..."}"></div>
      <div class="row c2">
        <div class="field"><label class="f">Адрес API</label>
          <input id="ai-${prof}-base" value="${esc(obj.base || defBase)}"></div>
        <div class="field"><label class="f">Модель</label>
          <input id="ai-${prof}-model" value="${esc(obj.model || defModel)}"></div>
      </div>
      <div class="flex mb8" style="flex-wrap:wrap">
        <span class="small">Быстро:</span>
        ${[["DeepSeek","https://api.deepseek.com/v1","deepseek-chat"],
           ["OpenAI","https://api.openai.com/v1","gpt-4o-mini"],
           ["ProxyAPI","https://api.proxyapi.ru/openai/v1","gpt-4o-mini"],
           ["VseGPT","https://api.vsegpt.ru/v1","openai/gpt-4o-mini"],
           ["OpenRouter","https://openrouter.ai/api/v1","openai/gpt-4o-mini"],
           ["Groq","https://api.groq.com/openai/v1","llama-3.3-70b-versatile"],
           ["Ollama","http://localhost:11434/v1","llama3.2-vision"]]
          .map(([n,b,m]) => `<button class="btn ghost sm" data-preset="${prof}|${b}|${m}">${n}</button>`).join("")}
      </div>
      <div class="flex mb8"><button class="btn ghost sm" id="ai-${prof}-check">Проверить</button>
        <span class="small" id="ai-${prof}-out"></span></div>`;
    body.innerHTML = `<div class="card"><div class="pad">
      <h2>Искусственный интеллект</h2>
      <p class="small">Можно подключить две разные модели: одну для текста, другую для фото.
      Подходит любой OpenAI-совместимый сервис.</p>
      ${block("text", "Текст: протоколы, отчёты, письма", "Например DeepSeek: https://api.deepseek.com/v1, deepseek-chat",
              tx, "https://api.deepseek.com/v1", "deepseek-chat")}
      ${block("vision", "Фото: распознавание показаний", "Например GPT-4o-mini через ProxyAPI/VseGPT/OpenRouter",
              vi, "https://api.openai.com/v1", "gpt-4o-mini")}
      <div class="flex mt16">
        <button class="btn" id="save-ai">Сохранить</button>
        <button class="btn ghost" id="ai-both-proxy">Оба блока — ProxyAPI</button>
        <button class="btn ghost" id="ai-both-deepseek">Текст — DeepSeek, фото — ProxyAPI</button>
      </div>
      <div class="hintline">Адрес API в браузере открывать не нужно — там будет «Not Found», это нормально.
        Проверяйте кнопкой «Проверить». Ключи хранятся только на этом компьютере в data/app.db.</div>
    </div></div>`;
    const test = async (prof) => {
      const out = $("#ai-" + prof + "-out"); out.textContent = "Проверяю…";
      try {
        const r = await api("/api/ai/test", { profile: prof,
          key: $("#ai-" + prof + "-key").value, base: $("#ai-" + prof + "-base").value,
          model: $("#ai-" + prof + "-model").value });
        out.innerHTML = `<span class="badge ok">подключено</span> ${esc(r.model)}`;
      } catch (e) { out.innerHTML = `<span class="badge bad">ошибка</span> ${esc(e.message)}`; }
    };
    $$("#view [data-preset]").forEach(b => b.onclick = () => {
      const [prof, base, model] = b.dataset.preset.split("|");
      $("#ai-" + prof + "-base").value = base;
      $("#ai-" + prof + "-model").value = model;
      toast("Подставлено: " + base);
    });
    $("#ai-text-check").onclick = () => test("text");
    $("#ai-vision-check").onclick = () => test("vision");
    $("#ai-both-proxy").onclick = () => {
      ["text","vision"].forEach(pr => {
        $("#ai-" + pr + "-base").value = "https://api.proxyapi.ru/openai/v1";
        $("#ai-" + pr + "-model").value = "gpt-4o-mini";
      });
      toast("Адреса и модели ProxyAPI подставлены в оба блока");
    };
    $("#ai-both-deepseek").onclick = () => {
      $("#ai-text-base").value = "https://api.deepseek.com/v1";
      $("#ai-text-model").value = "deepseek-chat";
      $("#ai-vision-base").value = "https://api.proxyapi.ru/openai/v1";
      $("#ai-vision-model").value = "gpt-4o-mini";
      toast("Текст — DeepSeek, фото — ProxyAPI");
    };
    $("#save-ai").onclick = async () => {
      await api("/api/settings", { ai: {
        text: { key: $("#ai-text-key").value.trim(), base: $("#ai-text-base").value.trim(),
                model: $("#ai-text-model").value.trim() },
        vision: { key: $("#ai-vision-key").value.trim() || $("#ai-text-key").value.trim(),
                  base: $("#ai-vision-base").value.trim(),
                  model: $("#ai-vision-model").value.trim() },
      } });
      await loadState(); toast("Настройки ИИ сохранены");
    };
  }
}

/* ------------------------------------------------------------------ поле */
function fieldState() {
  if (!S.field) {
    const busy = (S.data.objects || []).find(o => (o.entries_count || 0) > 0);
    S.field = {
      object_id: (busy || S.data.objects[0] || {}).id || 0,
      photos: [], comment: "", author: S.data.company.lab_head || "",
      edate: todayISO(), activity: "test",
    };
  }
  return S.field;
}

async function loadGroups() {
  if (!S.groups) {
    try { S.groups = (await api("/api/groups")).items || []; } catch (e) { S.groups = []; }
  }
  return S.groups;
}

function objectOptions(objects, selectedId, blank) {
  const groups = S.groups || [];
  const gname = (gid) => (groups.find(g => g.id === gid) || {}).name || "Без округа";
  const by = {};
  (objects || []).forEach(o => { const k = o.group_id || 0; (by[k] = by[k] || []).push(o); });
  let html = blank ? `<option value="0">— выберите объект —</option>` : "";
  Object.keys(by).sort((a, b) => gname(+a).localeCompare(gname(+b), "ru")).forEach(k => {
    html += `<optgroup label="${esc(gname(+k))}">` +
      by[k].map(o => `<option value="${o.id}" ${o.id === selectedId ? "selected" : ""}>${esc(o.name)}</option>`).join("") +
      "</optgroup>";
  });
  return html;
}

function objById(id) { return (S.data.objects || []).find(o => o.id === Number(id)); }

async function uploadTo(files, bucket) {
  for (const f of [...files].slice(0, 20)) {
    try {
      const res = await fetch("/api/upload?name=" + encodeURIComponent(f.name), { method: "POST", body: f });
      const j = await res.json();
      if (!j.ok) throw new Error(j.error);
      bucket.push({ path: j.path, rel: j.rel, name: j.name });
    } catch (e) { toast("Не удалось загрузить " + f.name + ": " + e.message, true); }
  }
}

function photoUrl(p) {
  if (!p) return "";
  if (typeof p === "string") return "";
  if (p.rel) return "/api/photo?f=" + encodeURIComponent(p.rel);
  if (p.path) return "/api/photo?path=" + encodeURIComponent(p.path);
  return "";
}

function entryCard(e, withDelete) {
  const photos = (e.photos || []).map(p => {
    const src = photoUrl(p);
    if (!src) return "";
    const cap = p.caption ? `<figcaption>${esc(p.caption)}</figcaption>` : "";
    return `<figure class="ph"><img src="${src}" loading="lazy" data-full="${src}">${cap}</figure>`;
  }).join("");
  const fileList = (e.files || []).map(f => {
    const name = typeof f === "string" ? f.split(/[\\/]/).pop() : (f.name || "файл");
    const rel = typeof f === "string" ? "" : f.rel;
    const href = rel ? "/api/file?f=" + encodeURIComponent(rel) : (f.path ? "/api/download?f=" + encodeURIComponent(f.path) : "#");
    return `<a class="file-chip" href="${href}" target="_blank">📎 ${esc(name)}</a>`;
  }).join("");
  const hasPoints = (e.files || []).some(f => /\.(csv|txt|dat)$/i.test(typeof f === "string" ? f : (f.name || "")));
  return `<div class="entry">
    <div class="entry-head">
      <b>${fmtDate(e.edate)}</b>
      <span class="chip">${esc(e.author || "—")}</span>
      <div class="spacer"></div>
      ${withDelete ? `<button class="iconbtn" data-del="${e.id}">✕</button>` : ""}
    </div>
    ${e.comment ? `<div class="entry-text">${esc(e.comment)}</div>` : ""}
    ${photos ? `<div class="entry-photos">${photos}</div>` : ""}
    ${fileList ? `<div class="entry-files">${fileList}</div>` : ""}
    ${hasPoints ? `<div class="mt8"><button class="btn soft sm" data-schema="${e.id}">Сформировать исполнительную схему</button></div>` : ""}
  </div>`;
}

function bindEntryPhotos(root) {
  $$("img[data-full]", root).forEach(img => img.onclick = () => window.open(img.dataset.full, "_blank"));
  $$("[data-schema]", root).forEach(b => b.onclick = () => buildSchema(+b.dataset.schema));
}

async function buildSchema(entryId) {
  try {
    toast("Разбираю точки и рисую схему…");
    const j = await api("/api/survey/build", { entry_id: entryId });
    openModal(`<h2 style="margin-top:0">Исполнительная схема готова</h2>
      <p class="small">Точек на схеме: ${j.points}. Исполнитель: ${esc(j.author || "—")}.</p>
      <div class="flex mt16"><a class="btn ok" href="/api/download?f=${encodeURIComponent(j.file)}">Скачать .docx</a>
      <button class="btn ghost" onclick="closeModal()">Закрыть</button></div>`);
    await loadState();
  } catch (e) { toast(e.message, true); }
}

function bindDeletes(root, after) {
  $$("[data-del]", root).forEach(b => b.onclick = async () => {
    if (!confirm("Удалить запись?")) return;
    await api("/api/entry/delete", { id: +b.dataset.del });
    toast("Запись удалена");
    if (after) await after();
  });
}

function startVoice(textarea) {
  const SR = window.SpeechRecognition || window.webkitSpeechRecognition;
  if (!SR) { toast("Голосовой ввод не поддерживается этим браузером", true); return; }
  const rec = new SR();
  rec.lang = "ru-RU";
  rec.interimResults = false;
  rec.onresult = (e) => {
    const txt = e.results[0][0].transcript;
    textarea.value = (textarea.value ? textarea.value + " " : "") + txt;
    S.field.comment = textarea.value;
  };
  rec.onerror = () => toast("Не удалось распознать речь", true);
  try { rec.start(); toast("Говорите…"); } catch (e) { toast("Микрофон недоступен", true); }
}

function addGeo(textarea) {
  if (!navigator.geolocation) { toast("Геолокация недоступна", true); return; }
  navigator.geolocation.getCurrentPosition(pos => {
    const { latitude, longitude } = pos.coords;
    const txt = `N ${latitude.toFixed(6)}, E ${longitude.toFixed(6)}`;
    textarea.value = (textarea.value ? textarea.value + " " : "") + txt;
    S.field.comment = textarea.value;
  }, () => toast("Не удалось определить координаты", true), { timeout: 8000 });
}

async function viewField() {
  setTitle("Поле", "Фото и комментарий на объекте — ИИ соберёт отчёт");
  const f = fieldState();
  const objs = S.data.objects || [];
  if (!objs.length) {
    $("#view").innerHTML = `<div class="card"><div class="pad"><div class="empty">Сначала добавьте объект в справочнике.</div></div></div>`;
    return;
  }
  let entries = [];
  try {
    const j = await api(`/api/object?id=${f.object_id}`);
    entries = j.data.entries;
  } catch (e) { }
  const groups = await loadGroups();
  const gname = (gid) => (groups.find(g => g.id === gid) || {}).name || "Без округа";
  const objOptions = objectOptions(objs, f.object_id);
  const curObj = objs.find(o => o.id === f.object_id) || {};

  $("#view").innerHTML = `
    <div class="field-wrap">
      <div class="card"><div class="pad">
        <label class="f">Объект</label>
        <select id="fld-object">${objOptions}</select>
        <div class="small mt4" id="fld-district">Округ: <b>${esc(gname(curObj.group_id || 0))}</b></div>
        <div class="flex mt8">
          <button class="btn soft sm" id="fld-act-sampling">＋ Акт отбора проб</button>
          <button class="btn ghost sm" id="fld-act-other">＋ Прочий акт</button>
        </div>
        <div class="camera-box" id="fld-camera">
          <div class="cam-ico">📷</div>
          <div class="cam-t">Снять фото</div>
          <div class="small">камера телефона или выбрать из галереи</div>
        </div>
        <input type="file" id="fld-file" accept="image/*" capture="environment" multiple hidden>
        <div class="thumbs" id="fld-thumbs"></div>
        <div class="flex mt8">
          <button class="btn ghost sm" id="fld-attach">📎 Прикрепить файлы (CSV, PDF, DXF…)</button>
          <span class="small" id="fld-files-count"></span>
        </div>
        <input type="file" id="fld-attach-input" multiple hidden>
        <div class="entry-files" id="fld-files"></div>

        <label class="f mt16">Комментарий</label>
        <textarea id="fld-comment" rows="4" placeholder="Что сделано, что замечено, какие материалы привезли…">${esc(f.comment)}</textarea>
        <label class="flex mt8" style="gap:8px;font-size:12.5px">
          <input type="checkbox" id="fld-defect"> <span>Это дефект — внести в дефектную ведомость</span>
        </label>
        <div class="flex mt8">
          <button class="btn ghost sm" id="fld-mic">🎤 Голосом</button>
          <button class="btn ghost sm" id="fld-geo">📍 Координаты</button>
          <button class="btn ghost sm" id="fld-today">Сегодня</button>
          <div class="spacer"></div>
          <button class="btn ok" id="fld-save">Сохранить запись</button>
        </div>
      </div></div>

      <details class="adv mt16">
        <summary>Записи по объекту (${entries.length}) — они же в карточке объекта</summary>
        <div id="fld-entries" class="mt8"></div>
      </details>
    </div>`;

  const renderTh = () => {
    $("#fld-thumbs").innerHTML = f.photos.map((p, i) => `
      <div class="thumb"><img src="${photoUrl(p)}" data-full="${photoUrl(p)}">
        <button class="rm" data-rp="${i}">✕</button></div>`).join("");
    $$("#fld-thumbs [data-full]").forEach(img => img.onclick = () => window.open(img.dataset.full, "_blank"));
    $$("#fld-thumbs [data-rp]").forEach(b => b.onclick = () => { f.photos.splice(+b.dataset.rp, 1); renderTh(); });
  };
  renderTh();

  const list = () => {
    $("#fld-entries").innerHTML = entries.length
      ? entries.map(e => entryCard(e, true)).join("")
      : `<div class="card"><div class="pad"><div class="empty">Пока нет записей. Снимите первое фото.</div></div></div>`;
    bindEntryPhotos($("#fld-entries"));
    bindDeletes($("#fld-entries"), async () => { await loadState(); await viewField(); });
  };
  list();

  $("#fld-object").onchange = async (e) => {
    f.object_id = +e.target.value;
    await viewField();
  };
  $("#fld-camera").onclick = () => $("#fld-file").click();
  const renderFiles = () => {
    f.files = f.files || [];
    $("#fld-files").innerHTML = f.files.map((x, i) =>
      `<span class="file-chip">📎 ${esc(x.name)} <b data-file-rm="${i}" style="cursor:pointer">✕</b></span>`).join("");
    $("#fld-files-count").textContent = f.files.length ? f.files.length + " файл(ов)" : "";
    $$("#fld-files [data-file-rm]").forEach(b => b.onclick = () => { f.files.splice(+b.dataset.fileRm, 1); renderFiles(); });
  };
  renderFiles();
  $("#fld-attach").onclick = () => $("#fld-attach-input").click();
  $("#fld-attach-input").onchange = async (e) => {
    for (const file of [...e.target.files].slice(0, 20)) {
      try {
        const res = await fetch("/api/attach?name=" + encodeURIComponent(file.name), { method: "POST", body: file });
        const j = await res.json();
        if (!j.ok) throw new Error(j.error);
        f.files = f.files || [];
        f.files.push({ path: j.path, rel: j.rel, name: j.name, size: j.size });
      } catch (err) { toast("Не удалось: " + file.name + " — " + err.message, true); }
    }
    renderFiles();
  };
  $("#fld-file").onchange = async (e) => {
    await uploadTo(e.target.files, f.photos);
    renderTh();
    toast("Фото добавлено: " + f.photos.length);
  };
  $("#fld-comment").oninput = (e) => f.comment = e.target.value;
  $("#fld-act-sampling").onclick = () => openSamplingAct(f.object_id, "sampling");
  $("#fld-act-other").onclick = () => openSamplingAct(f.object_id, "inspection");
  $("#fld-mic").onclick = () => startVoice($("#fld-comment"));
  $("#fld-geo").onclick = () => addGeo($("#fld-comment"));
  $("#fld-today").onclick = () => { f.edate = todayISO(); toast("Дата: сегодня"); };
  $("#fld-save").onclick = async () => {
    if (!f.comment.trim() && !f.photos.length) { toast("Добавьте фото или комментарий", true); return; }
    const o = objById(f.object_id) || {};
    await api("/api/entry", {
      object_id: f.object_id, object_name: o.name || "", edate: f.edate,
      author: f.author, comment: f.comment, photos: f.photos, files: f.files || [],
      tags: $("#fld-defect") && $("#fld-defect").checked ? "дефект" : "",
      activity: f.activity || "test",
    });
    f.photos = []; f.comment = ""; f.files = [];
    await loadState();
    await viewField();
    toast("Запись сохранена");
  };
}

/* ------------------------------------------------------------------ карточка объекта */
async function viewObject(id) {
  if (!id) { go("directory"); return; }
  const j = await api(`/api/object?id=${id}`);
  S.obj = { id, ...j.data };
  try { S.obj.works = (await api(`/api/object/works?id=${id}`)).items || []; }
  catch (e) { S.obj.works = []; }
  try { S.obj.defects = (await api(`/api/object/defects?id=${id}`)).items || []; }
  catch (e) { S.obj.defects = []; }
  S.objTab = S.objTab || "entries";
  setTitle(S.obj.object.name, S.obj.object.customer || "Карточка объекта");
  renderObject();
}

function renderObject() {
  const o = S.obj.object;
  const tab = S.objTab;
  const ents = S.obj.entries || [];
  const docs = S.obj.docs || [];
  const reports = (S.data.reports || []).filter(r => (r.object_name || "").includes(o.name));

  $("#view").innerHTML = `
    <div class="toolbar">
      <button class="btn ghost" onclick="location.hash='#/directory'">← К объектам</button>
      <div class="flex">
        ${(S.allowed || []).includes("field") ? `<button class="btn sm" id="obj-field">＋ Запись</button>` : ""}
        ${(S.allowed || []).includes("reports") ? `<button class="btn soft sm" id="obj-final">Итоговый отчёт</button>` : ""}
      </div>
    </div>

    <div class="obj-head">
      <div>
        <h2>${esc(o.name)} ${o.status === "archive" ? '<span class="badge neutral">архив</span>' : '<span class="badge ok">активный</span>'}</h2>
        <div class="small">${esc(o.customer || "заказчик не указан")}${o.address ? " · " + esc(o.address) : ""}</div>
        ${o.city ? `<div class="small mt4">Округ: <b>${esc(o.city)}</b></div>` : `<div class="small mt4">округ не определён</div>`}
      </div>
      <div class="obj-stats">
        <div><b>${ents.length}</b><span>записей</span></div>
        <div><b>${docs.length}</b><span>документов</span></div>
        <div><b>${reports.length}</b><span>отчётов</span></div>
      </div>
    </div>
    <details class="adv mb8"><summary>Ещё: папка, документы, архив</summary>
      <div class="flex" style="flex-wrap:wrap">
        <button class="btn ghost sm" id="obj-scan">Сканировать документы</button>
        <button class="btn ghost sm" id="obj-find">Найти папку</button>
        <button class="btn ghost sm" id="obj-open" ${o.folder ? "" : "disabled"}>Открыть папку</button>
        <button class="btn ghost sm" id="obj-export" ${o.folder ? "" : "disabled"}>Отгрузить документы в папку</button>
        <button class="btn ghost sm" id="obj-doc-up">Загрузить документацию</button>
        <button class="btn ghost sm" id="obj-doc-ai">Разобрать документацию заново</button>
        <button class="btn ghost sm" id="obj-localize">Хранить на сервере</button>
        <button class="btn ghost sm" id="obj-photo-ai">Подписать фото</button>
        <button class="btn ghost sm" id="obj-extract">Заполнить из документов</button>
        <button class="btn ghost sm" id="obj-ai">ИИ-отчёт</button>
        <button class="btn ghost sm" id="obj-archive">${o.status === "archive" ? "Вернуть из архива" : "В архив"}</button>
        ${S.isAdmin ? `<button class="btn ghost sm" id="obj-delete">Удалить объект</button>` : ""}
      </div>
    </details>

    <details class="adv mb8"><summary>Реквизиты и отчётность</summary>
    <div class="card mb8"><div class="pad">
      <div class="row c3">
        <div><label class="f">Контракт</label>
          <select id="obj-contract"><option value="0">— без контракта —</option>
          ${(S.data.contracts || []).map(c => `<option value="${c.id}" ${o.contract_id === c.id ? "selected" : ""}>${esc(c.number)} — ${esc((c.customer || "").slice(0, 30))}</option>`).join("")}</select></div>
        <div><label class="f">ИНН заказчика</label>
          <input id="obj-inn" type="text" value="${esc(o.customer_inn || "")}" placeholder="10 или 12 цифр"></div>
        <div><label class="f">E-mail заказчика</label>
          <input id="obj-email" type="text" value="${esc(o.customer_email || "")}" placeholder="mail@example.ru"></div>
        <div><label class="f">Телефон для мессенджера</label>
          <input id="obj-phone" type="text" value="${esc(o.customer_phone || "")}" placeholder="+7..."></div>
        <div><label class="f">Тип объекта</label>
          <select id="obj-type"><option value="contract" ${(o.obj_type || "contract") === "contract" ? "selected" : ""}>Контрактный (гос)</option>
          <option value="commercial" ${o.obj_type === "commercial" ? "selected" : ""}>Неконтрактный (коммерческий)</option></select></div>
        <div style="display:flex;align-items:flex-end"><button class="btn ghost sm" id="obj-save-org">Сохранить</button></div>
      </div>
    </div></div>

    <div class="card mb8"><div class="pad">
      <div class="flex" style="justify-content:space-between;align-items:flex-start">
        <div>
          <h3 style="margin:0 0 6px">Отчётность по объекту</h3>
          <div class="small">${o.report_freq === "weekly" ? "еженедельно" : o.report_freq === "monthly" ? "ежемесячно" : "не настроена"}
            ${o.report_next ? " · следующий отчёт: <b>" + fmtDate(o.report_next) + "</b>" : ""}</div>
        </div>
        <div class="flex"><button class="btn soft sm" id="rep-now">Сформировать отчёт сейчас</button></div>
      </div>
      <div class="row c4 mt8">
        <div class="field"><label class="f">Периодичность</label>
          <select id="rep-freq">
            <option value="none" ${!o.report_freq ? "selected" : ""}>не нужна</option>
            <option value="weekly" ${o.report_freq === "weekly" ? "selected" : ""}>каждую неделю</option>
            <option value="monthly" ${o.report_freq === "monthly" ? "selected" : ""}>каждый месяц</option>
          </select></div>
        <div class="field"><label class="f">Начало периода</label>
          <input type="date" id="rep-start" value="${o.report_start || todayISO()}"></div>
        <div class="field"><label class="f">Следующий отчёт</label>
          <input type="date" id="rep-next" value="${o.report_next || ""}"></div>
        <div class="field" style="display:flex;align-items:flex-end;padding-bottom:8px">
          <label class="flex" style="gap:8px;font-size:13px;color:var(--text)">
            <input type="checkbox" id="rep-auto" ${o.report_auto ? "checked" : ""}> автоматически
          </label>
        </div>
      </div>
      <div class="flex"><button class="btn sm" id="rep-save">Сохранить расписание</button>
        <span class="small">В срок программа сама соберёт отчёт, DOCX и PDF, и положит в папку объекта.</span></div>
    </div></div>
    </details>

    <div class="tabs" id="obj-tabs">
      <button data-t="entries" class="${tab === "entries" ? "active" : ""}">Записи (${ents.length})</button>
      <button data-t="docs" class="${tab === "docs" ? "active" : ""}">Документы проекта (${docs.length})</button>
      <button data-t="defects" class="${tab === "defects" ? "active" : ""}">Дефекты (${(S.obj.defects || []).length})</button>
      <button data-t="works" class="${tab === "works" ? "active" : ""}">Объёмы (${(S.obj.works || []).length})</button>
      <button data-t="reports" class="${tab === "reports" ? "active" : ""}">Отчёты (${reports.length})</button>
    </div>
    <div id="obj-body"></div>`;

  $("#obj-tabs").onclick = e => {
    const b = e.target.closest("button[data-t]");
    if (!b) return;
    S.objTab = b.dataset.t; renderObject();
  };
  $("#obj-find").onclick = async () => {
    try {
      const j = await api("/api/object/folder", { id: o.id });
      toast(j.folder ? "Папка: " + j.folder : "Папка не найдена", !j.folder);
      await viewObject(o.id);
    } catch (e) { toast(e.message, true); }
  };
  $("#obj-open").onclick = async () => {
    try { await api("/api/object/open-folder", { id: o.id }); } catch (e) { toast(e.message, true); }
  };
  $("#obj-export").onclick = async () => {
    try {
      const j = await api("/api/object/export", { id: o.id });
      toast("Отгружено файлов: " + j.count);
    } catch (e) { toast(e.message, true); }
  };
  $("#obj-archive").onclick = async () => {
    const next = o.status === "archive" ? "active" : "archive";
    await api("/api/object/status", { id: o.id, status: next });
    await loadState();
    toast(next === "archive" ? "Объект в архиве" : "Объект возвращён");
    if (next === "archive") go("directory"); else await viewObject(o.id);
  };

  const ofin = $("#obj-final");
  if (ofin) ofin.onclick = async () => {
    const b = $("#obj-final"); b.disabled = true; b.textContent = "Формирую…";
    try {
      const r = await api("/api/object/final-report", { id: o.id });
      await loadState();
      previewDoc(r.pdf || r.file);
    } catch (e) { toast(e.message, true); }
    b.disabled = false; b.textContent = "Итоговый отчёт";
  };

  $("#rep-save").onclick = async () => {
    try {
      await api("/api/object/schedule", {
        id: o.id, freq: $("#rep-freq").value, start: $("#rep-start").value,
        auto: $("#rep-auto").checked,
      });
      await loadState(); await viewObject(o.id);
      toast("Расписание сохранено");
    } catch (e) { toast(e.message, true); }
  };
  $("#rep-now").onclick = async () => {
    const b = $("#rep-now"); b.disabled = true; b.textContent = "Формирую…";
    try {
      const j = await api("/api/object/report-now", { id: o.id });
      await loadState();
      openModal(`<h2 style="margin-top:0">Отчёт ${esc(j.number)} готов</h2>
        <p class="small">Период ${fmtDate(j.date_from)} — ${fmtDate(j.date_to)}.</p>
        <div class="flex"><a class="btn ok" target="_blank" href="/api/download?inline=1&f=${encodeURIComponent(j.pdf || j.file)}">Открыть PDF</a>
        <a class="btn ghost" href="/api/download?f=${encodeURIComponent(j.file)}">DOCX</a>
        <button class="btn ghost" onclick="closeModal()">Закрыть</button></div>`);
    } catch (e) { toast(e.message, true); b.disabled = false; b.textContent = "Сформировать отчёт сейчас"; }
  };

  $("#obj-save-org").onclick = async () => {
    try {
      await api("/api/object/update", { id: o.id, contract_id: +$("#obj-contract").value,
        obj_type: $("#obj-type").value, customer_email: $("#obj-email").value,
        customer_inn: $("#obj-inn").value,
        customer_phone: $("#obj-phone").value });
      await loadState(); await viewObject(o.id); toast("Сохранено");
    } catch (e) { toast(e.message, true); }
  };

  const loc = $("#obj-localize");
  if (loc) loc.onclick = async () => {
    if (!confirm("Скопировать все документы объекта в хранилище программы? Это может занять время.")) return;
    loc.disabled = true; loc.textContent = "Копирую…";
    try {
      const r = await api("/api/object/localize", { id: o.id });
      toast(`Скопировано файлов: ${r.copied || 0}`);
      await loadState(); await viewObject(o.id);
    } catch (e) { toast(e.message, true); loc.disabled = false; loc.textContent = "Хранить на сервере"; }
  };

  $("#obj-doc-up").onclick = () => {
    const inp = document.createElement("input");
    inp.type = "file"; inp.multiple = true;
    inp.accept = ".pdf,.docx,.doc,.xlsx,.xls,.jpg,.jpeg,.png,.tif,.tiff";
    inp.onchange = async () => {
      const files = [...inp.files];
      if (!files.length) return;
      toast("Загружаю " + files.length + " файл(ов)…");
      for (const f of files) {
        try {
          const fd = new FormData(); fd.append("file", f);
          const r = await fetch("/api/attach?name=" + encodeURIComponent(f.name), { method: "POST", body: fd, credentials: "same-origin" });
          const j = await r.json();
          if (!r.ok) throw new Error(j.error || "ошибка");
          await api("/api/object/upload-doc", { id: o.id, rel: j.rel, name: f.name });
        } catch (e) { toast(f.name + ": " + e.message, true); }
      }
      await viewObject(o.id);
      toast("Документация загружена. Нажмите «ИИ: разобрать документацию».");
    };
    inp.click();
  };

  const dai = $("#obj-doc-ai");
  if (dai) dai.onclick = async () => {
    const b = $("#obj-doc-ai"); b.disabled = true; b.textContent = "Читаю документацию…";
    try {
      const r = await api("/api/object/classify", { id: o.id });
      await loadState();
      const rows = [["Наименование", r.title], ["Адрес", r.address], ["Заказчик", r.customer],
                    ["Подрядчик", r.contractor], ["Контракт", r.contract]].filter(x => x[1]);
      openModal(`<h2 style="margin-top:0">ИИ разобрал документацию</h2>
        <div class="small mb8">Прочитано документов: ${r.docs || 0}. Проверьте и сохраните.</div>
        <table class="tbl"><tbody>${rows.map(([k, v]) => `<tr><td class="small">${esc(k)}</td><td><b>${esc(v)}</b></td></tr>`).join("")}</tbody></table>
        ${(r.addresses || []).length ? `<h3 class="mt16">Найдено адресов: ${r.addresses.length}</h3>
          <div class="small mb8">Можно создать отдельные объекты в той же папке.</div>
          <div class="flex mb8"><button class="btn ok sm" id="dc-all">Создать все (${r.addresses.length})</button></div>
          <div class="flex" style="flex-wrap:wrap">${r.addresses.map(a => `<button class="btn ghost sm" data-addr="${esc(a)}">＋ ${esc(a)}</button>`).join("")}</div>` : ""}
        <div class="flex mt16"><button class="btn ok" id="dc-save">Записать в объект</button>
          <button class="btn ghost" onclick="closeModal()">Закрыть</button></div>`);
      $("#dc-save").onclick = async () => {
        closeModal(); await viewObject(o.id); toast("Данные объекта обновлены");
      };
      const allBtn = $(".modal #dc-all");
      if (allBtn) allBtn.onclick = async () => {
        const fl = o.folder || "";
        const parent = fl.replace(/[\\/][^\\/]+$/, "");
        allBtn.disabled = true;
        let ok = 0;
        for (const a of r.addresses) {
          allBtn.textContent = "Создаю " + (ok + 1) + " из " + r.addresses.length + "…";
          try {
            await api("/api/object/in-folder", { parent, name: a, type: o.obj_type || "contract" });
            ok++;
          } catch (e) { /* пропускаем дубли */ }
        }
        await loadState();
        closeModal();
        toast("Создано объектов: " + ok);
        location.hash = "#/directory";
      };
      $$(".modal [data-addr]").forEach(btn => btn.onclick = async () => {
        try {
          const fl = o.folder || "";
          const parent = fl.replace(/[\\/][^\\/]+$/, "");
          const rr = await api("/api/object/in-folder", { parent, name: btn.dataset.addr, type: o.obj_type || "contract" });
          btn.disabled = true; btn.textContent = "✓ " + btn.dataset.addr;
          await loadState(); toast("Создан объект: " + rr.folder.split("\\").pop());
        } catch (e) { toast(e.message, true); }
      });
    } catch (e) { toast(e.message, true); }
    b.disabled = false; b.textContent = "ИИ: разобрать документацию";
  };

  $("#obj-photo-ai").onclick = async () => {
    const b = $("#obj-photo-ai"); b.disabled = true; b.textContent = "Смотрю фото…";
    try {
      const r = await api("/api/object/photos/analyze", { id: o.id, limit: 12 });
      await viewObject(o.id);
      toast(r.analyzed ? `Подписано фото: ${r.analyzed}` : "Новых фото для подписи нет", !r.analyzed);
    } catch (e) { toast(e.message, true); }
    b.disabled = false; b.textContent = "ИИ: подписать фото";
  };

  $("#obj-extract").onclick = async () => {
    const b = $("#obj-extract"); b.disabled = true; b.textContent = "Разбираю…";
    try {
      const r = await api("/api/object/extract", { id: o.id });
      const f = r.found || {};
      await loadState(); await viewObject(o.id);
      toast(Object.keys(f).length ? "Найдено: " + Object.keys(f).join(", ") : "Реквизиты не найдены", !Object.keys(f).length);
    } catch (e) { toast(e.message, true); }
    b.disabled = false; b.textContent = "Заполнить из документов";
  };

  const del = $("#obj-delete");
  if (del) del.onclick = async () => {
    if (!confirm("Удалить объект «" + o.name + "»? Документы на диске останутся.")) return;
    try {
      await api("/api/object/delete", { id: o.id });
      await loadState(); toast("Объект удалён"); location.hash = "#/directory";
    } catch (e) { toast(e.message, true); }
  };

  const mig = $("#obj-migrate");
  if (mig) mig.onclick = async () => {
    const b = $("#obj-migrate"); b.disabled = true; b.textContent = "Переношу…";
    try {
      const r = await api("/api/object/migrate", { id: o.id });
      toast(r.already ? "Уже в программе" : `Перенесено файлов: ${r.files}`);
      await loadState(); await viewObject(o.id); S.objTab = "docs"; renderObject();
    } catch (e) { toast(e.message, true); b.disabled = false; b.textContent = "Перенести в программу"; }
  };

  const ofld = $("#obj-field");
  if (ofld) ofld.onclick = () => {
    S.field = { object_id: o.id, photos: [], comment: "", author: S.data.company.lab_head || "", edate: todayISO() };
    go("field");
  };
  $("#obj-ai").onclick = () => openAgentModal(o.id);
  $("#obj-scan").onclick = async () => {
    $("#obj-scan").disabled = true;
    $("#obj-scan").textContent = "Сканирую…";
    try {
      const j = await api("/api/object/scan", { object_id: o.id });
      toast("Найдено документов: " + j.total);
      await viewObject(o.id);
    } catch (e) { toast(e.message, true); $("#obj-scan").disabled = false; }
  };

  const body = $("#obj-body");
  if (tab === "entries") {
    body.innerHTML = ents.length ? ents.map(e => entryCard(e, true)).join("")
      : `<div class="card"><div class="pad"><div class="empty">Записей нет. Нажмите «＋ Запись» — можно прямо с телефона.</div></div></div>`;
    bindEntryPhotos(body);
    bindDeletes(body, async () => { await loadState(); await viewObject(o.id); });
  } else if (tab === "defects") {
    const items = S.obj.defects || [];
    body.innerHTML = `<div class="card"><div class="pad">
      <div class="flex mb8"><b>Дефектная ведомость</b><div class="spacer"></div>
        <button class="btn ghost sm" id="defect-add">＋ Записать дефект</button>
        <button class="btn sm" id="defect-doc">Сформировать ведомость</button></div>
      ${items.length ? items.map((d, i) => `<div class="entry">
        <div class="entry-head"><b>${i + 1}. ${fmtDate(d.edate)}</b><span class="small">${esc(d.author || "")}</span></div>
        <div class="entry-text">${esc(d.comment || "")}</div>
        ${(d.photos || []).length ? `<div class="entry-photos">${d.photos.map(ph => `<img src="${esc(ph.rel)}" alt="">`).join("")}</div>` : ""}
      </div>`).join("") : `<div class="empty">Дефектов нет. Нажмите «Записать дефект» — откроется «Поле» с отметкой «дефект».</div>`}
    </div></div>`;
    $("#defect-add").onclick = () => { fieldState().object_id = o.id; go("field"); };
    $("#defect-doc").onclick = async () => {
      const b = $("#defect-doc"); b.disabled = true; b.textContent = "Формирую…";
      try {
        const r = await api("/api/object/defects/doc", { id: o.id });
        await loadState();
        previewDoc(r.pdf || r.file);
      } catch (e) { toast(e.message, true); }
      b.disabled = false; b.textContent = "Сформировать ведомость";
    };
  } else if (tab === "works") {
    const works = S.obj.works || [];
    body.innerHTML = works.length ? `<div class="card"><div class="pad">
      <div class="flex mb8"><b>Объёмы по актам КС-2</b><div class="spacer"></div>
        <button class="btn ghost sm" id="works-scan">Обновить из КС-2</button>
        <button class="btn soft sm" id="vor-load">Загрузить ВОР</button>
        <input type="file" id="vor-file" accept=".xlsx,.xls" hidden></div>
      <table class="tbl"><thead><tr><th>Наименование работ</th><th>Ед.</th><th>Всего по актам</th><th>Последний акт</th></tr></thead>
      <tbody>${works.map(w => `<tr><td class="small">${esc(w.name)}</td><td class="small">${esc(w.unit || "")}</td>
        <td class="num">${Number(w.qty || 0).toLocaleString("ru-RU", {maximumFractionDigits: 2})}</td>
        <td class="small">${esc(w.last_date || "—")}</td></tr>`).join("")}</tbody></table>
      <div class="hintline">Данные берутся из актов КС-2 в папке объекта и используются в недельных отчётах.</div>
    </div></div>` : `<div class="card"><div class="pad"><div class="empty">Объёмы не загружены.
      Положите КС-2 в папку объекта и нажмите «Обновить из КС-2».</div>
      <div class="flex mt8"><button class="btn" id="works-scan">Обновить из КС-2</button></div></div></div>`;
    $("#vor-load").onclick = () => $("#vor-file").click();
    $("#vor-file").onchange = async (e) => {
      const f = e.target.files[0]; if (!f) return;
      try {
        const up = await fetch("/api/attach?name=" + encodeURIComponent(f.name), { method: "POST", body: f });
        const j = await up.json();
        if (!j.ok) throw new Error(j.error || "Не удалось загрузить файл");
        const r = await api("/api/object/vor", { id: o.id, rel: j.rel });
        toast("ВОР загружен: " + r.works + " видов работ");
        await viewObject(o.id); S.objTab = "works"; renderObject();
      } catch (err) { toast(err.message, true); }
    };
    $("#works-scan").onclick = async () => {
      const b = $("#works-scan"); b.disabled = true; b.textContent = "Читаю КС-2…";
      try {
        const r = await api("/api/object/works/scan", { id: o.id });
        toast(`Актов: ${r.acts}, видов работ: ${(r.items || []).length}`);
        await viewObject(o.id); S.objTab = "works"; renderObject();
      } catch (e) { toast(e.message, true); b.disabled = false; b.textContent = "Обновить из КС-2"; }
    };
  } else if (tab === "docs") {
    body.innerHTML = docs.length ? `<div class="card"><div class="pad">
      ${docs.map(d => `<div class="doc-row">
        <span class="doc-kind">${esc((d.kind || "").toUpperCase())}</span>
        <div class="doc-name"><b>${esc(d.title)}</b>
          <div class="small">${d.exists ? (d.size / 1048576).toFixed(2) + " МБ" : "файл не найден"}</div></div>
        ${d.exists ? (() => {
          const ext = (d.kind || "").toLowerCase();
          const viewable = ["pdf", "jpg", "jpeg", "png", "tif", "tiff"].includes(ext);
          return viewable
            ? `<button class="btn ghost sm" data-view="${esc(d.path)}">Открыть</button>`
            : `<a class="btn ghost sm" href="/api/download?f=${encodeURIComponent(d.path)}">Скачать</a>`;
        })() : ""}
      </div>`).join("")}
      </div></div>` : `<div class="card"><div class="pad"><div class="empty">Документы не найдены.
        Нажмите «Сканировать документы» — программа поищет их в папках объекта на Яндекс.Диске.</div></div></div>`;
    $$("#obj-body [data-view]").forEach(b => b.onclick = () => previewDoc(b.dataset.view));
  } else {
    body.innerHTML = reports.length ? `<div class="card">${reports.map(r => `<div class="doc-row">
      <div class="doc-name"><b>${esc(r.number)}</b><div class="small">${period(r.date_from, r.date_to)} · ${esc(r.object_name || "")}</div></div>
      ${r.pdf ? `<a class="btn sm" target="_blank" href="/api/download?inline=1&f=${encodeURIComponent(r.pdf)}">PDF</a>` : ""}
      ${r.file ? `<a class="btn ghost sm" href="/api/download?f=${encodeURIComponent(r.file)}">DOCX</a>` : ""}
    </div>`).join("")}</div>` : `<div class="card"><div class="pad"><div class="empty">Отчётов по объекту пока нет.</div></div></div>`;
  }
}

/* ------------------------------------------------------------------ ИИ-отчёт */
function openAgentModal(objectId) {
  const o = objById(objectId) || {};
  const to = todayISO();
  const from = new Date(Date.now() - 13 * 86400000).toISOString().slice(0, 10);
  openModal(`
    <h2 style="margin-top:0">ИИ-отчёт по объекту</h2>
    <p class="small">${esc(o.name || "")}</p>
    <div class="row c2">
      <div class="field"><label class="f">Начало периода</label><input type="date" id="ag-from" value="${from}"></div>
      <div class="field"><label class="f">Конец периода</label><input type="date" id="ag-to" value="${to}"></div>
    </div>
    <div class="field"><label class="f">Специалист</label><input type="text" id="ag-spec" value="${esc(S.data.company.lab_head || "")}"></div>
    <div class="hintline">Агенты: записи → документы проекта → текст отчёта. Без ключа ИИ работает локальный разбор.</div>
    <div class="flex mt16">
      <button class="btn ok" id="ag-run">Запустить агентов</button>
      <button class="btn ghost" onclick="closeModal()">Отмена</button>
    </div>
    <div id="ag-log" class="mt16"></div>`);
  $("#ag-run").onclick = async () => {
    const btn = $("#ag-run");
    btn.disabled = true;
    $("#ag-log").innerHTML = `<div class="agent-step running">⏳ Агент записей…</div>
      <div class="agent-step">Агент проекта…</div><div class="agent-step">Агент отчёта…</div>`;
    try {
      const j = await api("/api/agent/report", {
        object_id: objectId, date_from: $("#ag-from").value, date_to: $("#ag-to").value,
        specialist: $("#ag-spec").value,
      });
      $("#ag-log").innerHTML = `
        ${j.log.map(l => `<div class="agent-step done">✓ ${esc(l)}</div>`).join("")}
        <div class="verdict ok mt8"><div><b>Отчёт ${esc(j.number)} готов</b><br>
          <span class="small">${j.ai ? "Использован ИИ" : "Локальный разбор (ключ ИИ не задан)"}</span></div></div>
        <div class="flex mt16">
          <a class="btn ok" href="/api/download?f=${encodeURIComponent(j.file)}">Скачать .docx</a>
          <button class="btn ghost" onclick="closeModal(); loadState().then(()=>viewObject(${objectId}))">К объекту</button>
        </div>`;
      await loadState();
    } catch (e) {
      $("#ag-log").innerHTML = `<div class="verdict bad">${esc(e.message)}</div>`;
      btn.disabled = false;
    }
  };
}

/* ------------------------------------------------------------------ архив протоколов */
async function viewArchive() {
  setTitle("Архив протоколов", "Оцифрованные PDF из рабочих папок: номер, дата, объект, материал");
  const q = S.archQ || "";
  let items = [];
  try { items = (await api("/api/archive?q=" + encodeURIComponent(q))).items; } catch (e) { toast(e.message, true); }
  $("#view").innerHTML = `
    <div class="toolbar">
      <div class="left">
        <input type="text" id="arch-q" value="${esc(q)}" placeholder="поиск: номер, объект, материал" style="width:320px">
        <button class="btn ghost" id="arch-find">Найти</button>
      </div>
      <button class="btn soft" id="arch-scan">Оцифровать PDF из папок</button>
    </div>
    <div class="card">
      ${items.length ? `<table class="tbl"><thead><tr><th>№</th><th>Дата</th><th>Объект</th><th>Материал</th><th></th></tr></thead>
        <tbody>${items.map(x => `<tr>
          <td class="mono"><b>${esc(x.number || "—")}</b></td>
          <td>${esc(x.pdate || "—")}</td>
          <td class="small">${esc((x.object_name || "—").slice(0, 80))}</td>
          <td class="small">${esc((x.material || "—").slice(0, 40))}</td>
          <td class="right"><a class="btn ghost sm" target="_blank" href="/api/archive/file?path=${encodeURIComponent(x.path)}">PDF</a></td>
        </tr>`).join("")}</tbody></table>` : `<div class="empty">Архив пуст. Нажмите «Оцифровать PDF из папок» — программа прочитает протоколы на Яндекс.Диске.</div>`}
    </div>`;
  $("#arch-find").onclick = () => { S.archQ = $("#arch-q").value.trim(); viewArchive(); };
  $("#arch-q").onkeydown = e => { if (e.key === "Enter") { S.archQ = e.target.value.trim(); viewArchive(); } };
  $("#arch-scan").onclick = async () => {
    const b = $("#arch-scan"); b.disabled = true; b.textContent = "Читаю PDF…";
    try {
      const j = await api("/api/archive/scan", { limit: 80 });
      toast(`Добавлено ${j.added} из ${j.scanned}, всего ${j.total}`);
      await viewArchive();
    } catch (e) { toast(e.message, true); b.disabled = false; b.textContent = "Оцифровать PDF из папок"; }
  };
}

/* ------------------------------------------------------------------ modal */
async function openSendModal(reportId) {
  let j;
  try { j = await api("/api/report/letter", { id: reportId }); }
  catch (e) { return toast(e.message, true); }
  openModal(`<h2 style="margin-top:0">Отправить заказчику</h2>
    <div class="row c2">
      <div><label class="f">E-mail</label><input id="snd-to" value="${esc(j.to || "")}" placeholder="mail@example.ru"></div>
      <div><label class="f">Телефон (WhatsApp)</label><input id="snd-phone" value="${esc(j.phone || "")}" placeholder="+7..."></div>
    </div>
    <div class="field"><label class="f">Тема</label><input id="snd-subject" value="${esc(j.subject || "")}"></div>
    <div class="field"><label class="f">Письмо (подписано ИИ)</label>
      <textarea id="snd-body" rows="9">${esc(j.body || "")}</textarea></div>
    <div class="flex">
      <button class="btn ok" id="snd-email">Отправить письмо</button>
      <button class="btn ghost" id="snd-tg">В Telegram</button>
      <button class="btn ghost" id="snd-wa">WhatsApp</button>
      <button class="btn ghost" onclick="closeModal()">Закрыть</button>
    </div>
    <div class="hintline">Прикладываются PDF и DOCX отчёта. Для WhatsApp/Telegram без бота откроется чат с текстом письма.</div>`);
  $("#snd-email").onclick = async () => {
    const b = $("#snd-email"); b.disabled = true; b.textContent = "Отправляю…";
    try {
      const r = await api("/api/report/send/email", { id: reportId, to: $("#snd-to").value,
        subject: $("#snd-subject").value, body: $("#snd-body").value });
      toast("Письмо отправлено: " + r.to); closeModal();
    } catch (e) { toast(e.message, true); b.disabled = false; b.textContent = "Отправить письмо"; }
  };
  $("#snd-tg").onclick = async () => {
    try {
      const r = await api("/api/report/send/messenger", { id: reportId, channel: "telegram",
        text: $("#snd-body").value });
      if (r.sent) toast("Отправлено в Telegram");
      else { toast(r.error || "Telegram не настроен", true); }
    } catch (e) { toast(e.message, true); }
  };
  $("#snd-wa").onclick = async () => {
    try {
      const r = await api("/api/report/send/messenger", { id: reportId, channel: "whatsapp",
        text: $("#snd-body").value });
      if (r.links && r.links.whatsapp) window.open(r.links.whatsapp, "_blank");
      else toast("Укажите телефон заказчика", true);
    } catch (e) { toast(e.message, true); }
  };
}

function previewDoc(rel) {
  if (!rel) { toast("Файл ещё не сформирован", true); return; }
  const url = "/api/preview?f=" + encodeURIComponent(rel);
  openModal(`<div class="flex" style="justify-content:space-between;margin-bottom:8px">
      <b>Просмотр документа</b>
      <div class="flex">
        <a class="btn ghost sm" href="/api/download?f=${encodeURIComponent(rel)}">Скачать</a>
        <button class="btn ghost sm" onclick="closeModal()">Закрыть</button>
      </div>
    </div>
    <iframe src="${url}" style="width:100%;height:72vh;border:1px solid var(--line);border-radius:4px;background:#fff"></iframe>`);
  const m = document.querySelector(".modal");
  if (m) m.style.maxWidth = "920px";
}

function openModal(html) {
  $("#modal-body").innerHTML = html;
  $("#modal").classList.remove("hidden");
}
function closeModal() { $("#modal").classList.add("hidden"); const m = document.querySelector(".modal"); if (m) m.style.maxWidth = ""; }

/* ------------------------------------------------------------------ init */
document.addEventListener("keydown", e => { if (e.key === "Escape") closeModal(); });
$("#modal").addEventListener("click", e => { if (e.target.id === "modal") closeModal(); });
$("#btn-refresh").onclick = async () => { await loadState(); router(); toast("Данные обновлены"); };
$("#btn-back").onclick = () => goBack();
$("#btn-home").onclick = () => go((S.allowed || ROLE_ROUTES.auth)[0]);
document.addEventListener("keydown", (e) => { if (e.key === "Escape") closeModal(); });
$("#modal").addEventListener("click", (e) => { if (e.target === $("#modal")) closeModal(); });
document.addEventListener("click", (e) => {
  const b = e.target.closest("[data-prev]");
  if (b) { e.preventDefault(); previewDoc(b.dataset.prev); }
  const s = e.target.closest("[data-send]");
  if (s) { e.preventDefault(); openSendModal(+s.dataset.send); }
  const ed = e.target.closest("[data-edit]");
  if (ed) { e.preventDefault(); S.editProtocolId = +ed.dataset.edit; go("protocols/new"); }
  const er = e.target.closest("[data-editrep]");
  if (er) { e.preventDefault(); S.editReportId = +er.dataset.editrep; go("reports/new"); }
});
$("#tb-proto").onclick = () => go("protocols/new");
$("#tb-report").onclick = () => go("reports/new");
$("#tb-field").onclick = () => go("field");
$("#btn-folder").onclick = async () => {
  try { await api("/api/open-docs", {}); } catch (e) { toast(e.message, true); }
};
window.addEventListener("hashchange", () => {
  if ($("#modal") && !$("#modal").classList.contains("hidden")) closeModal();
  router();
});

function showLoading(on) {
  const v = $("#view");
  if (v) v.classList.toggle("loading", !!on);
}

(async function init() {
  try {
    await loadState();
    await router();
  } catch (e) {
    $("#view").innerHTML = `<div class="card"><div class="pad"><div class="verdict bad">
      Не удалось загрузить данные: ${esc(e.message)}</div></div></div>`;
  }
})();

/* ---------------- лабораторный ввод ---------------- */
async function viewLabForm(kind) {
  await loadGroups();
  const kinds = S.data.kinds || {};
  const n = S.data.norms[kind] || {};
  const objects = (S.data.objects || []).filter(o => (o.status || "active") === "active");
  S.labKind = kind;
  if (!S.labDraft || S.labDraft.kind !== kind) {
    S.labDraft = { kind, object_id: objects[0] ? objects[0].id : 0, place: "",
                   date: todayISO(), meta: blankMeta(kind) };
  }
  const d = S.labDraft;
  setTitle(kinds[kind] ? kinds[kind].short : "Испытание", n.label || "");

  const fields = (n.fields && n.fields.length) ? n.fields : (n.meta || []);
  const rows = fields.map(f => {
    const unit = f.unit || "";
    const norm = f.lo != null && f.hi != null ? `норма ${fmtN(f.lo)}–${fmtN(f.hi)} ${unit}`
      : f.lo != null ? `не менее ${fmtN(f.lo)} ${unit}` : f.hi != null ? `не более ${fmtN(f.hi)} ${unit}` : "";
    return `<div class="measure">
      <div class="m-label"><b>${esc(f.name)}</b><span class="m-norm">${norm}${f.gost ? " · " + esc(f.gost) : ""}</span></div>
      <div class="m-input">
        <input data-meta="${f.key}" inputmode="decimal" value="${esc(d.meta[f.key] ?? "")}" placeholder="0">
        <span class="m-unit">${esc(unit)}</span>
        <button class="mic-btn" data-mic="${f.key}" title="Голосом">🎤</button>
      </div>
    </div>`;
  }).join("");

  $("#view").innerHTML = `<div class="lab-form">
    <div class="flex mb8"><button class="btn ghost" id="lf-back">← К видам</button>
      <div class="spacer"></div>
      <button class="btn ghost" id="lf-ai">Заполнить по записи</button>
      <button class="btn ghost" id="lf-ai-photo">Заполнить по фото</button>
      <button class="btn ok" id="lf-save">Сформировать протокол</button></div>
    <div class="panel"><div class="panel-head"><span>1. Проба</span><span class="small">${esc(n.intro || "")}</span></div>
      <div class="panel-body pad"><div class="row c3">
        <div><label class="f">Объект</label><select id="lf-object">
          ${objectOptions(objects, d.object_id)}
        </select></div>
        <div><label class="f">Место отбора</label><input id="lf-place" value="${esc(d.place)}" placeholder="ПК 12+50"></div>
        <div><label class="f">Дата</label><input type="date" id="lf-date" value="${esc(d.date)}"></div>
      </div></div></div>
    <div class="panel mt16"><div class="panel-head"><span>2. Измерения</span><span class="small">${fields.length} показателей</span></div>
      <div class="panel-body pad" id="lf-fields">${rows}</div></div>
    <div class="panel mt16"><div class="panel-head"><span>3. Результат</span></div>
      <div class="panel-body pad" id="lf-result"><div class="small">Введите измерения — результат посчитается автоматически.</div></div></div>
  </div>`;

  $("#lf-back").onclick = () => go("lab");
  $("#lf-ai").onclick = () => openAiFill(kind, d.object_id);
  $("#lf-ai-photo").onclick = () => openAiPhoto(kind, d.object_id);
  $("#lf-object").onchange = (e) => { d.object_id = +e.target.value; };
  $("#lf-place").oninput = (e) => { d.place = e.target.value; };
  $("#lf-date").onchange = (e) => { d.date = e.target.value; };
  $$("#lf-fields [data-meta]").forEach(inp => inp.oninput = () => {
    d.meta[inp.dataset.meta] = inp.value; scheduleLabPreview();
  });
  $$("#lf-fields [data-mic]").forEach(b => b.onclick = () => listenInto($(`#lf-fields [data-meta="${b.dataset.mic}"]`)));

  $("#lf-save").onclick = async () => {
    const b = $("#lf-save"); b.disabled = true; b.textContent = "Формирую…";
    const obj = objects.find(o => o.id === d.object_id) || {};
    d.meta.place = d.place;
    try {
      const r = await api("/api/protocol/save", { kind, meta: d.meta, object_name: obj.name || "",
        customer: obj.customer || "", pdate: d.date, draft: false, internal: true });
      await loadState(); showSaved("Протокол", r);
    } catch (e) { toast(e.message, true); b.disabled = false; b.textContent = "Сформировать протокол"; }
  };
  labPreview();
}

async function viewLabAsphalt(kind) {
  await loadGroups();
  const kinds = S.data.kinds || {};
  const n = S.data.norms[kind] || {};
  const objects = (S.data.objects || []).filter(o => (o.status || "active") === "active");
  S.labKind = kind;
  if (!S.labDraft || S.labDraft.kind !== kind) {
    const meta = blankMeta(kind);
    meta.grain = Array(13).fill("");
    meta.physical = {};
    meta.operational = {};
    S.labDraft = { kind, object_id: objects[0] ? objects[0].id : 0, place: "",
                   date: todayISO(), meta };
  }
  const d = S.labDraft, m = d.meta;
  const sieves = ["22,4", "16,0", "11,2", "8,0", "5,6", "4,0", "2,0", "1,0",
                  "0,5", "0,25", "0,125", "0,063", "<0,063"];
  setTitle(kinds[kind] ? kinds[kind].short : "Асфальтобетон", n.label || "ГОСТ 9128 / EN 13108");

  const grain = sieves.map((s, i) => `<div class="grain-cell">
      <div class="f">${s}</div>
      <input data-grain="${i}" inputmode="decimal" value="${esc((m.grain || [])[i] ?? "")}" placeholder="—">
    </div>`).join("");
  const phys = [["binder_over", "Вяжущее сверх 100%", "%"], ["pb", "Содержание вяжущего Pb", "%"],
                ["gmm", "Макс. плотность Gmm", "г/см³"], ["gmb", "Объёмная плотность Gmb", "г/см³"],
                ["pa", "Воздушные пустоты Pa", "%"], ["pmz", "ПМЗ", "%"], ["pnb", "ПНБ", "%"]]
    .map(([k, label, unit]) => `<div class="measure"><div class="m-label"><b>${label}</b></div>
      <div class="m-input"><input data-phys="${k}" inputmode="decimal" value="${esc((m.physical || {})[k] ?? "")}" placeholder="0">
      <span class="m-unit">${unit}</span><button class="mic-btn" data-mic-phys="${k}">🎤</button></div></div>`).join("");
  const ops = [["rut", "Глубина колеи", "мм"], ["water", "Коэффициент водостойкости", "—"]]
    .map(([k, label, unit]) => `<div class="measure"><div class="m-label"><b>${label}</b></div>
      <div class="m-input"><input data-ops="${k}" inputmode="decimal" value="${esc((m.operational || {})[k] ?? "")}" placeholder="0">
      <span class="m-unit">${unit}</span><button class="mic-btn" data-mic-ops="${k}">🎤</button></div></div>`).join("");

  $("#view").innerHTML = `<div class="lab-form">
    <div class="flex mb8"><button class="btn ghost" id="la-back">← К видам</button><div class="spacer"></div>
      <button class="btn ok" id="la-save">Сформировать протокол</button></div>
    <div class="panel"><div class="panel-head"><span>1. Проба</span></div><div class="panel-body pad">
      <div class="row c2">
        <div><label class="f">Объект</label><select id="la-object">
          ${objectOptions(objects, d.object_id)}</select></div>
        <div><label class="f">Место отбора</label><input id="la-place" value="${esc(d.place)}"></div></div>
      <div class="row c3 mt8">
        <div><label class="f">Дата</label><input type="date" id="la-date" value="${esc(d.date)}"></div>
        <div><label class="f">Материал</label><input id="la-material" value="${esc(m.material || "")}" placeholder="А8Вл"></div>
        <div><label class="f">Назначение</label><input id="la-purpose" value="${esc(m.purpose || "")}" placeholder="Верхний слой"></div></div>
      <div class="row c2 mt8">
        <div><label class="f">Производитель</label><input id="la-manufacturer" value="${esc(m.manufacturer || "")}"></div>
        <div><label class="f">Подрядчик</label><input id="la-contractor" value="${esc(m.contractor || "")}"></div></div>
    </div></div>
    <div class="panel mt16"><div class="panel-head"><span>2. Зерновой состав, %</span><span class="small">прошло через сито</span></div>
      <div class="panel-body pad"><div class="grain-grid">${grain}</div></div></div>
    <div class="panel mt16"><div class="panel-head"><span>3. Вяжущее и плотность</span></div>
      <div class="panel-body pad">${phys}</div></div>
    <div class="panel mt16"><div class="panel-head"><span>4. Свойства</span></div>
      <div class="panel-body pad">${ops}</div></div>
    <div class="panel mt16"><div class="panel-head"><span>5. Результат</span></div>
      <div class="panel-body pad" id="lf-result"><div class="small">Введите данные — расчёт появится здесь.</div></div></div>
  </div>`;

  $("#la-back").onclick = () => go("lab");
  $("#la-object").onchange = (e) => { d.object_id = +e.target.value; };
  $("#la-place").oninput = (e) => { d.place = e.target.value; };
  $("#la-date").onchange = (e) => { d.date = e.target.value; };
  const bind = (id, key) => { $(id).oninput = (e) => { m[key] = e.target.value; }; };
  bind("#la-material", "material"); bind("#la-purpose", "purpose");
  bind("#la-manufacturer", "manufacturer"); bind("#la-contractor", "contractor");
  $$("[data-grain]").forEach(inp => inp.oninput = () => {
    m.grain = m.grain || Array(13).fill(""); m.grain[+inp.dataset.grain] = inp.value; scheduleLabPreview();
  });
  $$("[data-phys]").forEach(inp => inp.oninput = () => {
    m.physical = m.physical || {}; m.physical[inp.dataset.phys] = inp.value; scheduleLabPreview();
  });
  $$("[data-ops]").forEach(inp => inp.oninput = () => {
    m.operational = m.operational || {}; m.operational[inp.dataset.ops] = inp.value; scheduleLabPreview();
  });
  $$("[data-mic-phys]").forEach(b => b.onclick = () => listenInto($(`[data-phys="${b.dataset.micPhys}"]`)));
  $$("[data-mic-ops]").forEach(b => b.onclick = () => listenInto($(`[data-ops="${b.dataset.micOps}"]`)));

  $("#la-save").onclick = async () => {
    const b = $("#la-save"); b.disabled = true; b.textContent = "Формирую…";
    const obj = objects.find(o => o.id === d.object_id) || {};
    m.place = d.place;
    try {
      const r = await api("/api/protocol/save", { kind, meta: m, object_name: obj.name || "",
        customer: obj.customer || "", pdate: d.date, draft: false, internal: true });
      await loadState(); showSaved("Протокол", r);
    } catch (e) { toast(e.message, true); b.disabled = false; b.textContent = "Сформировать протокол"; }
  };
  labPreview();
}

function scheduleLabPreview() {
  clearTimeout(S.labTimer);
  S.labTimer = setTimeout(() => labPreview(), 350);
}

async function labPreview() {
  const d = S.labDraft;
  if (!d) return;
  const box = $("#lf-result");
  if (!box) return;
  try {
    const r = await api("/api/protocol/preview", { kind: d.kind, meta: d.meta });
    const calc = r.calc || {};
    const rows = calc.rows || [];
    if (!rows.length) {
      box.innerHTML = `<div class="small">${esc(calc.conclusion || "Недостаточно данных для расчёта.")}</div>`;
      return;
    }
    const ok = calc.ok !== false;
    box.innerHTML = `<div class="verdict ${ok ? "ok" : "bad"} mb8">
        <b>${ok ? "Соответствует" : "Не соответствует"}</b>
        <span>${esc(calc.conclusion || "")}</span></div>
      <table class="tbl res-table"><thead><tr><th>Показатель</th><th>Норма</th><th>Факт</th><th>Итог</th></tr></thead>
      <tbody>${rows.map(x => `<tr><td>${esc(x.name)}</td><td class="small">${esc(x.req || "—")}</td>
        <td class="num">${esc(x.value || "—")} ${esc(x.unit || "")}</td>
        <td class="${x.ok === false ? "bad" : "ok"}">${x.ok === false ? "✕" : "✓"}</td></tr>`).join("")}</tbody></table>`;
  } catch (e) {
    box.innerHTML = `<div class="small">${esc(e.message)}</div>`;
  }
}

/* ---------------- акт отбора с подписью на экране ---------------- */
function initSigPad(canvas) {
  const ctx = canvas.getContext("2d");
  ctx.lineWidth = 2.2; ctx.lineCap = "round"; ctx.strokeStyle = "#1b2430";
  let drawing = false, last = null;
  const pos = (e) => {
    const r = canvas.getBoundingClientRect();
    const pt = e.touches ? e.touches[0] : e;
    return { x: (pt.clientX - r.left) * canvas.width / r.width,
             y: (pt.clientY - r.top) * canvas.height / r.height };
  };
  const start = (e) => { e.preventDefault(); drawing = true; last = pos(e); };
  const move = (e) => {
    if (!drawing) return;
    e.preventDefault();
    const p = pos(e);
    ctx.beginPath(); ctx.moveTo(last.x, last.y); ctx.lineTo(p.x, p.y); ctx.stroke();
    last = p; canvas.dataset.ink = "1";
  };
  const end = () => { drawing = false; };
  canvas.addEventListener("mousedown", start);
  canvas.addEventListener("mousemove", move);
  window.addEventListener("mouseup", end);
  canvas.addEventListener("touchstart", start, { passive: false });
  canvas.addEventListener("touchmove", move, { passive: false });
  canvas.addEventListener("touchend", end);
}

async function sigUpload(canvas, name) {
  if (!canvas || canvas.dataset.ink !== "1") return "";
  const blob = await new Promise(res => canvas.toBlob(res, "image/png"));
  if (!blob) return "";
  const r = await fetch("/api/attach?name=" + encodeURIComponent(name), { method: "POST", body: blob });
  const j = await r.json();
  return j.ok ? j.rel : "";
}

function openSamplingAct(objectId, kind) {
  const o = objById(objectId) || {};
  const isSampling = kind === "sampling";
  openModal(`<h2 style="margin-top:0">${isSampling ? "Акт отбора проб" : "Прочий акт"}</h2>
    <div class="row c3">
      <div><label class="f">Материал / конструкция</label><input id="ac-mat" placeholder="асфальтобетонная смесь"></div>
      <div><label class="f">Нормативный документ</label><input id="ac-gost" placeholder="ГОСТ 9128-2013"></div>
      <div><label class="f">Место отбора</label><input id="ac-place" placeholder="ПК 12+50"></div>
    </div>
    <div class="row c3 mt8">
      <div><label class="f">Дата</label><input type="date" id="ac-date" value="${todayISO()}"></div>
      <div><label class="f">Партия / объём</label><input id="ac-batch" placeholder="150 т"></div>
      <div><label class="f">Цель</label><input id="ac-purpose" placeholder="испытание образцов"></div>
    </div>
    <div class="row c2 mt8">
      <div><label class="f">Представитель заказчика</label><input id="ac-cust" placeholder="ФИО"></div>
      <div><label class="f">Представитель подрядчика</label><input id="ac-cont" placeholder="ФИО"></div>
    </div>
    <div class="row c2 mt8">
      <div><label class="f">Подпись заказчика</label>
        <canvas id="sig-cust" class="sig-pad" width="600" height="180"></canvas>
        <button class="btn ghost sm mt8" data-clear="sig-cust">Очистить</button></div>
      <div><label class="f">Подпись подрядчика</label>
        <canvas id="sig-cont" class="sig-pad" width="600" height="180"></canvas>
        <button class="btn ghost sm mt8" data-clear="sig-cont">Очистить</button></div>
    </div>
    <div class="hintline">Распишитесь пальцем или мышью прямо в рамке — подпись попадёт в документ.</div>
    <div class="flex mt16"><button class="btn ok" id="ac-go">Сформировать акт</button>
      <button class="btn ghost" onclick="closeModal()">Отмена</button></div>`);
  initSigPad($("#sig-cust"));
  initSigPad($("#sig-cont"));
  $$(".modal [data-clear]").forEach(b => b.onclick = () => {
    const c = $("#" + b.dataset.clear);
    c.getContext("2d").clearRect(0, 0, c.width, c.height);
    c.dataset.ink = "";
  });
  $("#ac-go").onclick = async () => {
    const b = $("#ac-go"); b.disabled = true; b.textContent = "Формирую…";
    try {
      const custSign = $("#sig-cust").dataset.ink ? $("#sig-cust").toDataURL("image/png") : "";
      const contSign = $("#sig-cont").dataset.ink ? $("#sig-cont").toDataURL("image/png") : "";
      const r = await api("/api/act/sampling", {
        object_id: objectId, kind,
        material: $("#ac-mat").value, gost: $("#ac-gost").value, place: $("#ac-place").value,
        date: $("#ac-date").value, batch: $("#ac-batch").value, purpose: $("#ac-purpose").value,
        customer: o.customer || "", contractor: o.contractor || "",
        customer_name: $("#ac-cust").value, contractor_name: $("#ac-cont").value,
        customer_sign_data: custSign, contractor_sign_data: contSign,
      });
      closeModal();
      previewDoc(r.pdf || r.file);
    } catch (e) { toast(e.message, true); b.disabled = false; b.textContent = "Сформировать акт"; }
  };
}

async function openAiFill(kind, objectId) {
  let entries = [];
  try {
    const j = await api(`/api/object?id=${objectId}`);
    entries = (j.data.entries || []).slice(0, 12);
  } catch (e) { return toast(e.message, true); }
  if (!entries.length) return toast("У этого объекта нет записей с поля", true);
  openModal(`<h2 style="margin-top:0">Заполнить по записи</h2>
    <div class="small mb8">Выберите запись — ИИ подставит значения в показатели.</div>
    ${entries.map(e => `<div class="doc-row" data-fill="${e.id}" style="cursor:pointer">
      <div class="doc-name"><b>${fmtDate(e.edate)}</b>
        <div class="small">${esc((e.comment || "без комментария").slice(0, 120))}</div></div>
      <span class="badge neutral">${(e.photos || []).length} фото</span></div>`).join("")}
    <div class="flex mt16"><button class="btn ghost" onclick="closeModal()">Отмена</button></div>`);
  $$("#modal [data-fill]").forEach(row => row.onclick = async () => {
    try {
      const r = await api("/api/protocol/ai-fill", { kind, object_id: objectId, entry_id: +row.dataset.fill });
      const vals = r.values || {};
      const d = S.labDraft;
      Object.keys(vals).forEach(k => {
        d.meta[k] = vals[k];
        const inp = $(`#lf-fields [data-meta="${k}"]`);
        if (inp) inp.value = vals[k];
      });
      closeModal();
      labPreview();
      toast(Object.keys(vals).length
        ? `Подставлено (${r.source}): ${Object.keys(vals).length} показателей`
        : "В записи не нашлось числовых значений");
    } catch (e) { toast(e.message, true); }
  });
}

async function openAiPhoto(kind, objectId) {
  let entries = [];
  try {
    const j = await api(`/api/object?id=${objectId}`);
    entries = (j.data.entries || []).filter(e => (e.photos || []).length);
  } catch (e) { return toast(e.message, true); }
  const photos = [];
  entries.forEach(e => (e.photos || []).forEach(ph => photos.push({ ...ph, date: e.edate })));
  if (!photos.length) return toast("У объекта нет фото", true);
  openModal(`<h2 style="margin-top:0">Заполнить по фото</h2>
    <div class="small mb8">Выберите снимок прибора или ведомости.</div>
    <div class="entry-photos">${photos.slice(0, 24).map((ph, i) => `
      <img src="${esc(ph.rel || ph.path)}" data-photo="${i}" title="${esc(ph.date || "")}">`).join("")}</div>
    <div class="hintline">Нужен ключ ИИ с распознаванием изображений.</div>
    <div class="flex mt16"><button class="btn ghost" onclick="closeModal()">Отмена</button></div>`);
  $$("#modal [data-photo]").forEach(img => img.onclick = async () => {
    const ph = photos[+img.dataset.photo];
    try {
      toast("Смотрю фото…");
      const r = await api("/api/protocol/ai-photo", { kind, rel: ph.rel || ph.path });
      const vals = r.values || {};
      const d = S.labDraft;
      Object.keys(vals).forEach(k => {
        d.meta[k] = vals[k];
        const inp = $(`#lf-fields [data-meta="${k}"]`);
        if (inp) inp.value = vals[k];
      });
      closeModal(); labPreview();
      toast(Object.keys(vals).length ? `С фото взято: ${Object.keys(vals).length}` : "На фото цифры не распознаны");
    } catch (e) { toast(e.message, true); }
  });
}

async function viewKp() {
  setTitle("Коммерческие предложения", "Выберите вариант — программа сформирует документ");
  const r = await api("/api/kp/list");
  S.kpList = r.items || [];
  const services = r.services || [];
  const types = r.types || { commercial: "Коммерческое", ab: "Госзакупка — АБ",
                             euro: "Госзакупка — АБ ЕВРО", sk: "Госзакупка — СК" };
  const cards = [
    ["calc", "Калькулятор пакетов", "Пакет + срок контроля → готовое КП с PDF"],
    ["area", "Калькулятор по площади", "Дороги и благоустройство: площадь → пробы и КП"],
    ["commercial", "Коммерческое", "По прайсу НИЦ СМК: лаборатория, стройконтроль, обследование"],
    ["ab", "Госзакупка — АБ", "Асфальтобетон: запрос ЕИС, срок действия, адресный перечень"],
    ["euro", "Госзакупка — АБ ЕВРО", "Евро-асфальтобетон по форме для госзакупок"],
    ["sk", "Госзакупка — СК", "Строительный контроль: общая цена контракта"],
  ];
  $("#view").innerHTML = `<div class="lab-grid">
    <div class="lab-group"><div class="sub-h">Создать КП</div>
      <div class="lab-tiles">${cards.map(([k, title, sub]) => `
        <button class="lab-tile" data-kp="${k}">
          <span class="lab-ico">₽</span><span class="lab-name">${esc(title)}</span>
          <span class="lab-sub">${esc(sub)}</span></button>`).join("")}</div>
      <div class="flex mt16">
        <button class="btn ghost sm" id="kp-price">${r.price_loaded ? "Обновить прайс" : "Загрузить прайс"}</button>
        <button class="btn ghost sm" id="kp-import">Импорт реестра КП</button>
        <span class="small">реестр и готовые КП — в разделе «Документы»</span>
      </div>
    </div></div>`;
  $$("#view [data-kp]").forEach(b => b.onclick = () => {
    if (b.dataset.kp === "calc") openKpCalculator(services);
    else if (b.dataset.kp === "area") openAreaCalculator(services);
    else openKpForm(services, types, b.dataset.kp);
  });
  $("#kp-price").onclick = async () => {
    try {
      const j = await api("/api/kp/import-price", {});
      toast("Прайс загружен: " + j.added + " услуг"); viewKp();
    } catch (e) { toast(e.message, true); }
  };
  $("#kp-import").onclick = async () => {
    try {
      const j = await api("/api/kp/import", {});
      toast("Добавлено из реестра: " + j.added);
    } catch (e) { toast(e.message, true); }
  };
}

function openKpForm(services, types, preset) {
  types = types || { commercial: "Коммерческое", ab: "Госзакупка — АБ", euro: "Госзакупка — АБ ЕВРО", sk: "Госзакупка — СК" };
  const groups = [];
  services.forEach(s => {
    let g = groups.find(x => x.section === (s.section || "Прочее"));
    if (!g) { g = { section: s.section || "Прочее", items: [] }; groups.push(g); }
    g.items.push(s);
  });
  openModal(`<h2 style="margin-top:0">Новое коммерческое предложение</h2>
    <div class="row c4">
      <div><label class="f">От компании</label><select id="kp-company">
        <option value="nic">ООО «НИЦ СМК»</option>
        <option value="ing">ООО «Инжиниринг Лаб»</option>
        <option value="loft">ООО «ЛОФТ»</option></select></div>
      <div><label class="f">Тип</label><select id="kp-type">
        ${Object.entries(types).map(([k, v]) => `<option value="${k}" ${preset === k ? "selected" : ""}>${esc(v)}</option>`).join("")}</select></div>
      <div><label class="f">Получатель</label><input id="kp-cust" placeholder="организация"></div>
      <div><label class="f">Дата</label><input type="date" id="kp-date" value="${todayISO()}"></div>
    </div>
    <div class="row c2 mt8"><div><label class="f">Объект / адрес</label><input id="kp-obj"></div>
      <div><label class="f">Адресный перечень (для гос)</label><input id="kp-addr"></div></div>
    <div class="row c3 mt8" id="kp-gos">
      <div><label class="f">Запрос ЕИС №</label><input id="kp-eisc" placeholder="0148300021..."></div>
      <div><label class="f">Дата запроса</label><input type="date" id="kp-req"></div>
      <div><label class="f">Срок действия КП до</label><input type="date" id="kp-valid"></div>
    </div>
    <div class="row c2 mt8">
      <div><label class="f">Контактное лицо</label><input id="kp-person"></div>
      <div><label class="f">Телефон</label><input id="kp-phone" placeholder="+7 ..."></div>
    </div>
    <div class="field mt8"><label class="f">Поиск услуги</label><input id="kp-search" placeholder="бетон, керны, щебень…"></div>
    <div style="max-height:320px;overflow:auto" id="kp-services">
      ${groups.map(g => `<div class="sub-h">${esc(g.section)}</div>
        ${g.items.map(s => `<div class="measure kp-srv" data-text="${esc((s.name + " " + (s.gost || "")).toLowerCase())}">
          <div class="m-label"><b>${esc(s.name)}</b>
            <span class="m-norm">${esc(s.gost || "")} · ${esc(s.unit || "")} · ${Number(s.price).toLocaleString("ru-RU")} ₽${s.note ? " (" + esc(s.note) + ")" : ""}</span></div>
          <div class="m-input" style="flex:0 0 110px"><input data-kpid="${s.id}" inputmode="decimal" value="0" style="text-align:right"></div>
        </div>`).join("")}`).join("")}
    </div>
    <div class="flex mt8"><b>Итого: <span id="kp-total">0 ₽</span></b></div>
    <div class="flex mt16"><button class="btn ok" id="kp-go">Сформировать КП</button>
      <button class="btn ghost" onclick="closeModal()">Отмена</button></div>`);
  $("#kp-gos").style.display = $("#kp-type").value === "commercial" ? "none" : "";
  $("#kp-type").onchange = () => { $("#kp-gos").style.display = $("#kp-type").value === "commercial" ? "none" : ""; };
  const calc = () => {
    let total = 0;
    $$(".modal [data-kpid]").forEach(inp => {
      const s = services.find(x => x.id === +inp.dataset.kpid);
      total += (parseFloat((inp.value || "0").replace(",", ".")) || 0) * (s ? s.price : 0);
    });
    $("#kp-total").textContent = total.toLocaleString("ru-RU") + " ₽";
  };
  $$(".modal [data-kpid]").forEach(inp => inp.oninput = calc);
  $("#kp-search").oninput = (e) => {
    const q = e.target.value.trim().toLowerCase();
    $$(".modal .kp-srv").forEach(row => {
      row.style.display = !q || row.dataset.text.includes(q) ? "" : "none";
    });
  };
  $("#kp-go").onclick = async () => {
    const items = [];
    $$(".modal [data-kpid]").forEach(inp => {
      const s = services.find(x => x.id === +inp.dataset.kpid);
      const qty = parseFloat((inp.value || "0").replace(",", ".")) || 0;
      if (s && qty > 0) items.push({ name: s.name, unit: s.unit, price: s.price, qty });
    });
    if (!items.length) return toast("Укажите количество хотя бы по одной услуге", true);
    try {
      const r = await api("/api/kp/create", {
        company: $("#kp-company").value, type: $("#kp-type").value,
        person: $("#kp-person").value, phone: $("#kp-phone").value,
        customer: $("#kp-cust").value, object: $("#kp-obj").value,
        date: $("#kp-date").value, eisc: $("#kp-eisc").value,
        request_date: $("#kp-req").value, valid_until: $("#kp-valid").value, items });
      closeModal(); previewDoc(r.pdf || r.file);
      S.kpList = null; viewKp();
      toast("КП " + r.number + " сформировано");
    } catch (e) { toast(e.message, true); }
  };
}

function openKpCalculator(services) {
  const pkgs = (services || []).filter(s => (s.section || "").includes("Пакет"));
  if (!pkgs.length) {
    return toast("Сначала загрузите прайс (кнопка «Загрузить прайс»)", true);
  }
  openModal(`<h2 style="margin-top:0">Калькулятор пакетов</h2>
    <div class="small mb8">Выберите пакет и срок — КП сформируется сразу, с PDF.</div>
    <div class="row c2">
      <div><label class="f">Пакет</label><select id="cl-pkg">
        ${pkgs.map((s, i) => `<option value="${i}">${esc(s.name)} — ${Number(s.price).toLocaleString("ru-RU")} ₽/мес</option>`).join("")}
      </select></div>
      <div><label class="f">Срок контроля, мес.</label><input id="cl-months" type="number" min="1" max="36" value="3"></div>
    </div>
    <div class="row c2 mt8">
      <div><label class="f">Адрес объекта</label><input id="cl-object" placeholder="г. Москва, ..."></div>
      <div><label class="f">Организация</label><input id="cl-org" placeholder="заказчик"></div>
    </div>
    <div class="row c2 mt8">
      <div><label class="f">Контактное лицо</label><input id="cl-person"></div>
      <div><label class="f">Телефон</label><input id="cl-phone" placeholder="+7 ..."></div>
    </div>
    <div class="flex mt16" style="justify-content:space-between;align-items:center">
      <b>Итого: <span id="cl-total">0 ₽</span></b>
      <div class="flex"><button class="btn ok" id="cl-go">Сформировать КП</button>
        <button class="btn ghost" onclick="closeModal()">Отмена</button></div>
    </div>`);
  const calc = () => {
    const s = pkgs[+$("#cl-pkg").value] || pkgs[0];
    const m = Math.max(1, Math.min(36, parseInt($("#cl-months").value || "1", 10)));
    $("#cl-total").textContent = (s.price * m).toLocaleString("ru-RU") + " ₽";
    return { s, m };
  };
  $("#cl-pkg").onchange = calc;
  $("#cl-months").oninput = calc;
  calc();
  $("#cl-go").onclick = async () => {
    const { s, m } = calc();
    const person = $("#cl-person").value.trim();
    const phone = $("#cl-phone").value.trim();
    const itemName = `${s.name} — ${m} мес.` + (person || phone ? ` (${person}${phone ? ", " + phone : ""})` : "");
    try {
      const r = await api("/api/kp/create", {
        company: "nic", type: "commercial",
        customer: $("#cl-org").value, object: $("#cl-object").value,
        date: todayISO(),
        items: [{ name: itemName, unit: s.unit || "объект/мес", price: s.price, qty: m }],
      });
      closeModal(); previewDoc(r.pdf || r.file);
      S.kpList = null; viewKp();
      toast("КП " + r.number + " сформировано");
    } catch (e) { toast(e.message, true); }
  };
}

function openAreaCalculator(services) {
  const find = (kw) => services.find(s => (s.name || "").toLowerCase().includes(kw));
  const sVyezd = find("выезд");
  const sCore = find("отбор кернов");
  const sArea = find("замеры площади");
  const sThick = find("замеры толщины");
  const sLab = find("комплексные лаб");
  const sSeal = find("заделка мест");
  const sConcl = find("составление заключения");
  if (!sCore || !sLab) return toast("Сначала загрузите прайс", true);
  openModal(`<h2 style="margin-top:0">Калькулятор по площади</h2>
    <div class="small mb8">Дороги и благоустройство: по площади считаем количество проб и стоимость.</div>
    <div class="row c3">
      <div><label class="f">Площадь покрытия, м²</label><input id="ar-area" type="number" min="1" value="3000"></div>
      <div><label class="f">Тип</label><select id="ar-type">
        <option value="ab">Асфальтобетон</option><option value="euro">Евро-асфальтобетон</option></select></div>
      <div><label class="f">Выездов</label><input id="ar-vy" type="number" min="1" value="1"></div>
    </div>
    <div class="row c2 mt8">
      <div><label class="f">Адрес объекта</label><input id="ar-object"></div>
      <div><label class="f">Заказчик</label><input id="ar-cust"></div>
    </div>
    <div class="row c2 mt8">
      <div><label class="f">Контактное лицо</label><input id="ar-person"></div>
      <div><label class="f">Телефон</label><input id="ar-phone"></div>
    </div>
    <div class="mt16" id="ar-break"></div>
    <div class="flex mt8" style="justify-content:space-between;align-items:center">
      <b>Итого: <span id="ar-total">0 ₽</span></b>
      <div class="flex"><button class="btn ok" id="ar-go">Сформировать КП</button>
        <button class="btn ghost" onclick="closeModal()">Отмена</button></div>
    </div>`);
  const compute = () => {
    const area = Math.max(1, parseFloat($("#ar-area").value || "0"));
    const cols = Math.max(1, Math.ceil(area / 3000));
    const vy = Math.max(1, parseInt($("#ar-vy").value || "1", 10));
    const rows = [];
    const add = (s, qty, label) => { if (s && qty > 0) rows.push({ s, qty, label: label || s.name }); };
    add(sVyezd, vy, "Выезд на объект");
    add(sCore, cols, "Отбор кернов (1 проба на 3000 м²)");
    add(sArea, area, "Замеры площади покрытия");
    add(sThick, cols, "Замеры толщины слоёв");
    add(sLab, cols, "Лабораторные испытания проб");
    add(sSeal, cols, "Заделка мест отбора");
    add(sConcl, 1, "Составление заключения");
    let total = 0;
    $("#ar-break").innerHTML = `<table class="tbl"><thead><tr><th>Услуга</th><th>Кол-во</th><th>Сумма</th></tr></thead>
      <tbody>${rows.map(r => { const sum = r.s.price * r.qty; total += sum;
        return `<tr><td class="small">${esc(r.label)}</td><td class="num">${r.qty}</td>
          <td class="num">${sum.toLocaleString("ru-RU")}</td></tr>`; }).join("")}</tbody></table>`;
    $("#ar-total").textContent = total.toLocaleString("ru-RU") + " ₽";
    return { rows, total };
  };
  ["#ar-area", "#ar-vy"].forEach(id => $(id).oninput = compute);
  compute();
  $("#ar-go").onclick = async () => {
    const { rows, total } = compute();
    if (!rows.length) return toast("Нет услуг", true);
    try {
      const r = await api("/api/kp/create", {
        company: "nic", type: $("#ar-type").value === "euro" ? "euro" : "ab",
        customer: $("#ar-cust").value, object: $("#ar-object").value,
        person: $("#ar-person").value, phone: $("#ar-phone").value, date: todayISO(),
        items: rows.map(x => ({ name: x.label, unit: x.s.unit, price: x.s.price, qty: x.qty })),
      });
      closeModal(); previewDoc(r.pdf || r.file);
      S.kpList = null; viewKp();
      toast("КП " + r.number + " сформировано");
    } catch (e) { toast(e.message, true); }
  };
}


/* PWA */
let deferredInstall = null;
window.addEventListener("beforeinstallprompt", (e) => {
  e.preventDefault();
  deferredInstall = e;
  const b = document.getElementById("pwa-install");
  if (b) b.style.display = "";
});
window.addEventListener("appinstalled", () => { deferredInstall = null; toast("Приложение установлено"); });
async function installPwa() {
  if (deferredInstall) {
    deferredInstall.prompt();
    await deferredInstall.userChoice;
    deferredInstall = null;
    return;
  }
  toast("Откройте меню браузера → «Установить приложение» / «На экран Домой»", true);
}
if ("serviceWorker" in navigator) {
  window.addEventListener("load", () => {
    navigator.serviceWorker.register("/sw.js").catch(() => {});
  });
}


async function createObjectFromFiles(files) {
  files = (files || []).filter(Boolean);
  if (!files.length) return;
  toast("Загружаю " + files.length + " файл(ов)…");
  const refs = [];
  for (const f of files) {
    if (f.size > 80 * 1024 * 1024) { toast(f.name + ": больше 80 МБ", true); continue; }
    try {
      const fd = new FormData(); fd.append("file", f);
      const r = await fetch("/api/attach?name=" + encodeURIComponent(f.name),
        { method: "POST", body: fd, credentials: "same-origin" });
      const j = await r.json();
      if (!r.ok) throw new Error(j.error || "ошибка");
      refs.push({ rel: j.rel, name: f.name });
    } catch (e) { toast(f.name + ": " + e.message, true); }
  }
  if (!refs.length) return;
  toast("ИИ разбирает документы…");
  try {
    const r = await api("/api/object/upload-create", { files: refs });
    if (!r.files) throw new Error("Документы не распознаны. Подойдут PDF, DOCX, XLSX, JPG, PNG, ZIP.");
    await loadState();
    toast(r.group ? `Объект создан, группа: ${r.group}` : "Объект создан");
    location.hash = "#/object/" + r.id;
  } catch (e) { toast(e.message, true); }
}

async function addFilesToObject(oid, files) {
  files = (files || []).filter(Boolean);
  if (!files.length) return;
  let n = 0;
  for (const f of files) {
    try {
      const fd = new FormData(); fd.append("file", f);
      const r = await fetch("/api/attach?name=" + encodeURIComponent(f.name),
        { method: "POST", body: fd, credentials: "same-origin" });
      const j = await r.json();
      if (!r.ok) throw new Error(j.error || "ошибка");
      await api("/api/object/upload-doc", { id: oid, rel: j.rel, name: f.name });
      n++;
    } catch (e) { toast(f.name + ": " + e.message, true); }
  }
  toast("Загружено файлов: " + n);
  if (S.route && S.route.startsWith("object/")) await viewObject(oid);
}

/* глобальное перетаскивание в карточку объекта */
document.addEventListener("dragover", (e) => {
  if (S.route && S.route.startsWith("object/") && e.dataTransfer?.types?.includes("Files")) {
    e.preventDefault();
    document.body.classList.add("dragging");
  }
});
document.addEventListener("dragleave", (e) => {
  if (!e.relatedTarget) document.body.classList.remove("dragging");
});
document.addEventListener("drop", async (e) => {
  document.body.classList.remove("dragging");
  if (!S.route || !S.route.startsWith("object/") || !S.obj) return;
  const files = await filesFromDrop(e.dataTransfer);
  if (!files.length) return;
  e.preventDefault();
  await addFilesToObject(S.obj.id, files);
});


/* файлы и папки из drag&drop */
async function filesFromDrop(dt) {
  if (!dt) return [];
  const items = dt.items ? [...dt.items] : [];
  const entries = items.map(i => i.webkitGetAsEntry && i.webkitGetAsEntry()).filter(Boolean);
  if (!entries.length) return [...(dt.files || [])];
  const out = [];
  async function walk(entry) {
    if (entry.isFile) {
      await new Promise(res => entry.file(f => { out.push(f); res(); }, () => res()));
      return;
    }
    if (entry.isDirectory) {
      const reader = entry.createReader();
      while (true) {
        const batch = await new Promise(res => reader.readEntries(res, () => res([])));
        if (!batch || !batch.length) break;
        for (const e of batch) await walk(e);
      }
    }
  }
  for (const e of entries) await walk(e);
  return out;
}


/* маска телефона */
function fmtPhone(raw) {
  let d = String(raw || "").replace(/\D/g, "");
  if (!d) return "";
  if (d[0] === "8") d = "7" + d.slice(1);
  if (d[0] !== "7") d = "7" + d;
  d = d.slice(0, 11);
  let out = "+7";
  if (d.length > 1) out += " (" + d.slice(1, 4);
  if (d.length >= 4) out += ")";
  if (d.length > 4) out += " " + d.slice(4, 7);
  if (d.length > 7) out += "-" + d.slice(7, 9);
  if (d.length > 9) out += "-" + d.slice(9, 11);
  return out;
}
document.addEventListener("input", (e) => {
  const el = e.target;
  if (!el || el.tagName !== "INPUT") return;
  const isPhone = el.type === "tel" || el.inputMode === "tel"
    || /phone/i.test(el.id || "") || (el.placeholder || "").includes("+7");
  if (!isPhone) return;
  const atEnd = el.selectionStart === el.value.length;
  const v = fmtPhone(el.value);
  if (v === el.value) return;
  el.value = v;
  if (atEnd) { try { el.setSelectionRange(v.length, v.length); } catch (_) {} }
});

navigator.serviceWorker && navigator.serviceWorker.addEventListener("controllerchange", () => {
  if (!sessionStorage.getItem("sw-reload")) {
    sessionStorage.setItem("sw-reload", "1");
    location.reload();
  }
});
