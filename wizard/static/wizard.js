/* The support decision lives in wizard/advise.py. This page collects facts. */

const state = {
  origin: "",
  authMode: "token",
  username: "",
  password: "",
  token: "",
  apiPrefix: "api/v2/",
  apiStyle: "v2",
  ping: null,
  instances: [],
  controlPlaneNodes: 0,
  executionNodes: 0,
  labOrg: null,
  labProject: null,
  projectStatus: null,
  jobTemplateCount: null,
  eeCount: null,
  auth: { ldap: null, saml: null, oidc: null },
  readError: "",
  advice: null,
  facts: null,
  hosts: [],
  precheck: null,
  selectedId: null,
  step: 1,
};

const LAB = "AAP Migration Lab";

function esc(value) {
  return String(value ?? "").replace(/[&<>"']/g, (ch) => ({
    "&": "&amp;",
    "<": "&lt;",
    ">": "&gt;",
    "\"": "&quot;",
    "'": "&#39;",
  }[ch]));
}

function setBanner(message, kind) {
  const banner = document.getElementById("banner");
  banner.hidden = !message;
  banner.textContent = message || "";
  banner.className = kind === "error" ? "banner banner--error" : "banner";
}

function setBusy(busy) {
  document.getElementById("connect-button").disabled = busy;
  document.getElementById("advise-button").disabled = busy;
  document.getElementById("precheck-button").disabled = busy;
  document.getElementById("continue-targets").disabled = busy;
  document.getElementById("add-host").disabled = busy;
  document.getElementById("recheck").disabled = busy;
}

function authHeader() {
  if (state.authMode === "token") {
    return state.token ? { Authorization: "Bearer " + state.token } : {};
  }
  if (!state.username) return {};
  const bytes = new TextEncoder().encode(state.username + ":" + state.password);
  let binary = "";
  bytes.forEach((byte) => {
    binary += String.fromCharCode(byte);
  });
  return { Authorization: "Basic " + btoa(binary) };
}

async function controllerGet(apiPath) {
  const response = await fetch("/proxy/" + String(apiPath).replace(/^\/+/, ""), {
    headers: { Accept: "application/json", ...authHeader() },
    cache: "no-store",
  });
  const text = await response.text();
  let body = null;
  if (text) {
    try {
      body = JSON.parse(text);
    } catch (err) {
      body = { error: text.slice(0, 280) };
    }
  }
  return { ok: response.ok, status: response.status, body };
}

function countOf(payload) {
  if (!payload || typeof payload !== "object") return null;
  if (typeof payload.count === "number") return payload.count;
  if (Array.isArray(payload.results)) return payload.results.length;
  return null;
}

function presence(response) {
  if (!response.ok) return null;
  const count = countOf(response.body);
  if (count === null) return null;
  return count > 0;
}

function nonEmpty(value) {
  return typeof value === "string" && value.trim().length > 0;
}

async function readFlag(path, predicate) {
  const response = await controllerGet(path);
  if (!response.ok || !response.body || typeof response.body !== "object" || Array.isArray(response.body)) {
    return null;
  }
  return Boolean(predicate(response.body));
}

function unlocked(step) {
  if (step <= 1) return true;
  if (step === 2) return Boolean(state.ping);
  if (step === 3) return Boolean(state.facts);
  if (step === 4 || step === 6) return Boolean(state.advice);
  if (step === 5) return Boolean(state.selectedId && state.advice);
  return false;
}

function showStep(step) {
  if (!unlocked(step)) return;
  state.step = step;
  document.querySelectorAll("[data-step]").forEach((section) => {
    section.hidden = Number(section.getAttribute("data-step")) !== step;
  });
  document.querySelectorAll("[data-goto]").forEach((button) => {
    const number = Number(button.getAttribute("data-goto"));
    button.disabled = !unlocked(number);
    if (number === step) button.setAttribute("aria-current", "step");
    else button.removeAttribute("aria-current");
  });
  if (step === 3) runPrecheck();
  if (step === 6) refreshValidation();
}

function inLabRange(version) {
  const parts = String(version).split(".");
  const major = parseInt(parts[0], 10);
  const minor = parseInt(parts[1], 10);
  return major === 4 && minor >= 4 && minor < 6;
}

function tri(value, yes, no) {
  if (value === true) return yes;
  if (value === false) return no;
  return "Not readable";
}

function renderFindings() {
  const ping = state.ping || {};
  const rows = state.instances.length
    ? state.instances.map((item) => (
      "<tr><td>" + esc(item.node || item.hostname || "") + "</td><td>" +
      esc(item.node_type || "") + "</td><td>" + esc(item.version || "") +
      "</td><td>" + esc(item.capacity ?? "") + "</td></tr>"
    )).join("")
    : "";
  const gateway = state.apiStyle === "gateway"
    ? "<p class=\"callout\">This URL answered on <code>/api/controller/v2/</code>. The AAP 2.4 lab uses <code>/api/v2/</code> on the controller.</p>"
    : "";
  const outside = state.apiStyle === "v2" && !inLabRange(ping.version)
    ? "<p class=\"callout\">Automation controller " + esc(ping.version) +
      " is outside the 4.4 and 4.5 releases this lab installs on.</p>"
    : "";
  const authProblem = state.readError ? "<p class=\"banner banner--error\">" + esc(state.readError) + "</p>" : "";
  document.getElementById("findings").innerHTML =
    gateway +
    outside +
    authProblem +
    "<div class=\"facts\">" +
      fact("Controller", ping.version) +
      fact("API", state.apiStyle === "gateway" ? "/api/controller/v2/" : "/api/v2/") +
      fact("Control-plane nodes", state.controlPlaneNodes) +
      fact("Execution nodes", state.executionNodes) +
      fact("Active node", ping.active_node || "") +
      fact(LAB + " organization", tri(state.labOrg, "Present", "Missing")) +
      fact(LAB + " project", tri(state.labProject, "Present", "Missing")) +
      fact("Job templates", state.jobTemplateCount ?? "Not readable") +
      fact("Execution environments", state.eeCount ?? "Not readable") +
      fact("LDAP", tri(state.auth.ldap, "Configured", "Not configured")) +
      fact("SAML", tri(state.auth.saml, "Configured", "Not configured")) +
      fact("OIDC", tri(state.auth.oidc, "Configured", "Not configured")) +
    "</div>" +
    (rows
      ? "<table><thead><tr><th>Node</th><th>Type</th><th>Version</th><th>Capacity</th></tr></thead><tbody>" + rows + "</tbody></table>"
      : "<p class=\"hint\">Ping did not list instances.</p>");
}

function fact(label, value) {
  return "<div class=\"fact\"><span>" + esc(label) + "</span><strong>" + esc(value) + "</strong></div>";
}

async function loadInventory() {
  const prefix = state.apiPrefix;
  const [orgRes, projectRes, eeRes, ldap, saml, oidc] = await Promise.all([
    controllerGet(prefix + "organizations/?name=" + encodeURIComponent(LAB)),
    controllerGet(prefix + "projects/?name=" + encodeURIComponent(LAB)),
    controllerGet(prefix + "execution_environments/?page_size=1"),
    readFlag(prefix + "settings/ldap/", (body) => nonEmpty(body.AUTH_LDAP_SERVER_URI)),
    readFlag(
      prefix + "settings/saml/",
      (body) => body.SOCIAL_AUTH_SAML_ENABLED === true ||
        nonEmpty(body.SOCIAL_AUTH_SAML_METADATA_URL) ||
        nonEmpty(body.SOCIAL_AUTH_SAML_CALLBACK_URL)
    ),
    readFlag(
      prefix + "settings/oidc/",
      (body) => nonEmpty(body.SOCIAL_AUTH_OIDC_KEY) || nonEmpty(body.SOCIAL_AUTH_OIDC_OIDC_ENDPOINT)
    ),
  ]);
  state.labOrg = presence(orgRes);
  state.labProject = presence(projectRes);
  const project = projectRes.ok && projectRes.body && projectRes.body.results
    ? projectRes.body.results[0]
    : null;
  state.projectStatus = project ? project.status || null : null;
  state.eeCount = eeRes.ok ? countOf(eeRes.body) : null;
  state.auth = { ldap, saml, oidc };
  state.readError = "";
  if (orgRes.status === 401 || projectRes.status === 401) {
    state.readError = "The controller rejected this login. Check the username, password, or token.";
  } else if (orgRes.status === 403 || projectRes.status === 403) {
    state.readError = "This login cannot read organizations or projects.";
  }
  const orgId = orgRes.ok && orgRes.body && orgRes.body.results && orgRes.body.results[0]
    ? orgRes.body.results[0].id
    : null;
  const jtPath = orgId == null
    ? prefix + "job_templates/?page_size=1"
    : prefix + "job_templates/?organization=" + encodeURIComponent(orgId) + "&page_size=1";
  const jtRes = await controllerGet(jtPath);
  state.jobTemplateCount = jtRes.ok ? countOf(jtRes.body) : null;
}

async function discover(options) {
  let ping = await controllerGet("api/v2/ping/");
  let style = "v2";
  let prefix = "api/v2/";
  if (ping.status === 404) {
    ping = await controllerGet("api/controller/v2/ping/");
    style = "gateway";
    prefix = "api/controller/v2/";
  }
  if (!ping.ok || !ping.body || typeof ping.body.version !== "string") {
    const detail = ping.body && ping.body.error ? ping.body.error : "The controller did not return a version.";
    setBanner(detail, "error");
    return false;
  }
  state.apiStyle = style;
  state.apiPrefix = prefix;
  state.ping = ping.body;
  state.instances = Array.isArray(ping.body.instances) ? ping.body.instances : [];
  let control = 0;
  let execution = 0;
  state.instances.forEach((item) => {
    if (item.node_type === "hybrid" || item.node_type === "control") control += 1;
    else if (item.node_type === "execution") execution += 1;
  });
  state.controlPlaneNodes = control;
  state.executionNodes = execution;
  if (!options || !options.keepAdvice) {
    state.advice = null;
    state.selectedId = null;
    state.facts = null;
    state.precheck = null;
  }
  await loadInventory();
  renderFindings();
  return true;
}

function captureAuth(form) {
  state.authMode = form.auth_mode.value;
  if (state.authMode === "token") {
    const token = form.token.value.trim();
    if (!token && !state.token) {
      setBanner("Enter a token, or switch to a username and password.", "error");
      return false;
    }
    if (token) state.token = token;
    state.username = "";
    state.password = "";
    form.token.value = "";
    return true;
  }
  const username = form.username.value.trim();
  const password = form.password.value;
  if (!username) {
    setBanner("Enter the controller username.", "error");
    return false;
  }
  if (!password && !(state.password && state.username === username)) {
    setBanner("Enter the controller password.", "error");
    return false;
  }
  state.username = username;
  if (password) state.password = password;
  state.token = "";
  form.password.value = "";
  return true;
}

function syncAuthFields() {
  const mode = document.querySelector("input[name='auth_mode']:checked").value;
  document.getElementById("token-fields").hidden = mode !== "token";
  document.getElementById("password-fields").hidden = mode === "token";
}

function syncRhelField() {
  const selected = document.querySelector("input[name='installer']:checked");
  const rhel = document.getElementById("rhel");
  const installer = selected ? selected.value : "";
  const operator = installer === "operator";
  rhel.disabled = operator;
  rhel.required = installer === "rpm";
  if (operator) rhel.value = "";
}

function collectFacts() {
  const error = document.getElementById("question-error");
  error.hidden = true;
  const installer = document.querySelector("input[name='installer']:checked");
  const hub = document.querySelector("input[name='hub']:checked");
  const eda = document.querySelector("input[name='eda']:checked");
  if (!installer || !hub || !eda) {
    error.hidden = false;
    error.textContent = "Answer the installer, hub, and Event-Driven Ansible questions.";
    return null;
  }
  if (state.readError && state.readError.includes("rejected")) {
    error.hidden = false;
    error.textContent = state.readError;
    return null;
  }
  let rhelMajor = document.getElementById("rhel").value === ""
    ? null
    : Number(document.getElementById("rhel").value);
  if (installer.value === "operator") rhelMajor = null;
  if (installer.value === "rpm" && rhelMajor === null) {
    error.hidden = false;
    error.textContent = "RPM sources need a RHEL major version.";
    return null;
  }
  return {
    controller_version: state.ping.version,
    api_style: state.apiStyle,
    control_plane_nodes: state.controlPlaneNodes,
    execution_nodes: state.executionNodes,
    installer: installer.value,
    rhel_major: rhelMajor,
    hub: hub.value === "yes",
    eda: eda.value === "yes",
    lab_org: state.labOrg,
    lab_project: state.labProject,
    job_template_count: state.jobTemplateCount,
    execution_environment_count: state.eeCount,
    auth: state.auth,
  };
}

function statusClass(status) {
  if (status === "supported") return "badge badge--supported";
  if (status === "supported_with_steps") return "badge badge--steps";
  return "badge badge--unsupported";
}

function statusLabel(status) {
  if (status === "supported") return "Supported";
  if (status === "supported_with_steps") return "Extra steps";
  return "Unsupported";
}

function docLinks(docs) {
  if (!docs || !docs.length) return "";
  return "<ul class=\"docs\">" + docs.map((item) => (
    "<li><a href=\"" + esc(item.url) + "\" target=\"_blank\" rel=\"noopener noreferrer\">" +
    esc(item.title) + "</a></li>"
  )).join("") + "</ul>";
}

function renderTargets() {
  const advice = state.advice;
  const eda = advice.eda
    ? "<p class=\"callout\">" + esc(advice.eda.summary) + "</p>"
    : "";
  const cards = advice.targets.map((item) => {
    const label = item.status === "unsupported" ? "Review" : "Walk through";
    const recommended = item.recommended ? "<span class=\"badge\">Recommended</span>" : "";
    return (
      "<article class=\"card" + (item.recommended ? " card--recommended" : "") + "\">" +
        "<div class=\"card__head\"><h3>" + esc(item.title) + "</h3>" +
        "<span class=\"" + statusClass(item.status) + "\">" + statusLabel(item.status) + "</span></div>" +
        "<p>" + esc(item.summary) + "</p>" +
        "<p class=\"hint\">" + esc(item.why) + "</p>" +
        "<div class=\"card__actions\">" + recommended +
        "<button type=\"button\" class=\"secondary\" data-target-id=\"" + esc(item.id) + "\">" +
        label + "</button></div></article>"
    );
  }).join("");
  const empty = advice.targets.length
    ? "<div class=\"cards\">" + cards + "</div>"
    : "<p>This connection is outside the AAP 2.4 lab, so there is no target list yet.</p>";
  const blocked = state.precheck && state.precheck.status === "blocked"
    ? "<p class=\"callout\">Pre-check is blocked for " + esc(state.precheck.target.title) +
      ". Fix those items before the upgrade.</p>"
    : "";
  document.getElementById("targets").innerHTML =
    blocked +
    "<p class=\"lead\">" + esc(advice.source.message) + "</p>" + eda + empty;
}

function renderWalkthrough() {
  const advice = state.advice;
  const item = advice.targets.find((target) => target.id === state.selectedId);
  const root = document.getElementById("walkthrough");
  if (!item) {
    root.innerHTML = "<p>Choose a target first.</p>";
    return;
  }
  const steps = item.steps.length
    ? "<ol class=\"steps\">" + item.steps.map((step) => "<li>" + esc(step) + "</li>").join("") + "</ol>"
    : "<p>This target has no supported procedure in the wizard. Use the linked upgrade documentation for the current rule.</p>";
  const eda = advice.eda ? "<p class=\"callout\">" + esc(advice.eda.summary) + "</p>" : "";
  const notes = "<ul class=\"notes\">" + advice.lab_notes.map((note) => "<li>" + esc(note) + "</li>").join("") + "</ul>";
  root.innerHTML =
    "<div class=\"card__head\"><h3>" + esc(item.title) + "</h3>" +
    "<span class=\"" + statusClass(item.status) + "\">" + statusLabel(item.status) + "</span></div>" +
    "<p>" + esc(item.why) + "</p>" +
    steps +
    eda +
    "<h3>Lab notes</h3>" +
    notes +
    docLinks(item.docs) +
    "<button type=\"button\" class=\"primary\" id=\"to-validate\">Continue to validation</button>";
  document.getElementById("to-validate").addEventListener("click", () => showStep(6));
}

function checkItem(label, detail, met) {
  const stateName = met === true ? "met" : met === false ? "miss" : "unknown";
  return "<li data-state=\"" + stateName + "\"><span>" + esc(label) + "</span><strong>" + esc(detail) + "</strong></li>";
}

function syncState(status) {
  if (status === "successful") return true;
  if (status === "failed" || status === "error" || status === "canceled") return false;
  return null;
}

function renderValidation() {
  const version = state.ping ? state.ping.version : "";
  const api = state.apiStyle === "gateway" ? "/api/controller/v2/" : "/api/v2/";
  const notes = state.advice
    ? "<ul class=\"notes\">" + state.advice.lab_notes.map((note) => "<li>" + esc(note) + "</li>").join("") + "</ul>"
    : "";
  document.getElementById("validate").innerHTML =
    "<p class=\"hint\">Connected to " + esc(state.origin) + " via " + esc(api) + "</p>" +
    "<ul class=\"check\">" +
      checkItem("Controller version", version || "Unknown", version ? true : null) +
      checkItem(LAB + " organization", tri(state.labOrg, "Present", "Missing"), state.labOrg) +
      checkItem(LAB + " project", tri(state.labProject, "Present", "Missing"), state.labProject) +
      checkItem(
        "Project sync",
        state.projectStatus || "No status",
        state.labProject === true ? syncState(state.projectStatus) : state.labProject === false ? false : null
      ) +
      checkItem(
        "Job templates",
        state.jobTemplateCount == null ? "Not readable" : String(state.jobTemplateCount),
        state.jobTemplateCount == null ? null : state.jobTemplateCount > 0
      ) +
      checkItem(
        "Execution environments",
        state.eeCount == null ? "Not readable" : String(state.eeCount),
        state.eeCount == null ? null : state.eeCount > 0
      ) +
    "</ul>" +
    notes;
}

let refreshing = false;

async function refreshValidation() {
  if (refreshing) return;
  refreshing = true;
  setBusy(true);
  document.getElementById("validate").textContent = "Checking the controller…";
  try {
    const ok = await discover({ keepAdvice: true });
    if (!ok) return;
    renderValidation();
    showStepButtons();
  } catch (err) {
    setBanner("Could not re-read the controller.", "error");
  } finally {
    refreshing = false;
    setBusy(false);
  }
}

function showStepButtons() {
  document.querySelectorAll("[data-goto]").forEach((button) => {
    const number = Number(button.getAttribute("data-goto"));
    button.disabled = !unlocked(number);
    if (number === state.step) button.setAttribute("aria-current", "step");
    else button.removeAttribute("aria-current");
  });
}

function applyTheme(theme) {
  if (theme === "dark" || theme === "light") {
    document.documentElement.setAttribute("data-theme", theme);
  } else {
    document.documentElement.removeAttribute("data-theme");
  }
  const dark = document.documentElement.getAttribute("data-theme") === "dark" ||
    (!document.documentElement.hasAttribute("data-theme") &&
      window.matchMedia("(prefers-color-scheme: dark)").matches);
  document.getElementById("theme-toggle").textContent = dark ? "Light mode" : "Dark mode";
}

function initTheme() {
  applyTheme(localStorage.getItem("theme"));
  document.getElementById("theme-toggle").addEventListener("click", () => {
    const current = document.documentElement.getAttribute("data-theme");
    const prefersDark = window.matchMedia("(prefers-color-scheme: dark)").matches;
    const isDark = current === "dark" || (current !== "light" && prefersDark);
    const next = isDark ? "light" : "dark";
    localStorage.setItem("theme", next);
    applyTheme(next);
  });
}

document.getElementById("connect-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  setBanner("");
  if (!captureAuth(event.target)) return;
  setBusy(true);
  try {
    const response = await fetch("/connect", {
      method: "POST",
      headers: { "Content-Type": "application/json", Accept: "application/json" },
      body: JSON.stringify({
        url: event.target.url.value.trim(),
        verify_tls: event.target.verify_tls.checked,
      }),
    });
    const body = await response.json();
    if (!response.ok) {
      setBanner(body.error || "Could not use that controller URL.", "error");
      return;
    }
    state.origin = body.origin;
    const found = await discover();
    if (found) showStep(2);
  } catch (err) {
    setBanner("The local wizard server did not answer.", "error");
  } finally {
    setBusy(false);
  }
});

function optionalNumber(id) {
  const raw = document.getElementById(id).value.trim();
  if (!raw) return null;
  const number = Number(raw);
  return Number.isFinite(number) ? number : null;
}

function readHostForm() {
  const name = document.getElementById("host-name").value.trim();
  if (!name) return { error: "Enter a host name." };
  const host = {
    name: name,
    role: document.getElementById("host-role").value,
  };
  const rhel = document.getElementById("host-rhel").value.trim();
  if (rhel) host.rhel = rhel;
  const cpu = optionalNumber("host-cpu");
  const memory = optionalNumber("host-memory");
  const disk = optionalNumber("host-disk");
  if (cpu !== null) host.cpu = cpu;
  if (memory !== null) host.memory_gb = memory;
  if (disk !== null) host.disk_gb = disk;
  const noexecRaw = document.getElementById("host-noexec").value.trim();
  if (noexecRaw) {
    host.noexec = noexecRaw.toLowerCase() === "none"
      ? []
      : noexecRaw.split(",").map((item) => item.trim()).filter(Boolean);
  }
  const portsRaw = document.getElementById("host-ports").value.trim();
  if (portsRaw) {
    if (portsRaw.toLowerCase() === "none") {
      host.open_ports = [];
    } else {
      const ports = portsRaw.split(",").map((item) => Number(item.trim()));
      if (ports.some((port) => !Number.isInteger(port) || port < 1 || port > 65535)) {
        return { error: "Open ports must be numbers separated by commas." };
      }
      host.open_ports = ports;
    }
  }
  const localhost = document.getElementById("host-localhost").value;
  if (localhost) host.localhost_hostname = localhost === "yes";
  const registered = document.getElementById("host-registered").value;
  if (registered) host.registered = registered === "yes";
  const venv = document.getElementById("host-venv").value;
  if (venv) host.custom_venvs = venv === "yes";
  const schema = document.getElementById("host-schema").value;
  if (schema) host.schema_ok = schema === "yes";
  return { host: host };
}

function renderHostList() {
  const root = document.getElementById("host-list");
  if (!state.hosts.length) {
    root.innerHTML = "<p class=\"hint\">No hosts added yet. The controller version is still checked.</p>";
    return;
  }
  root.innerHTML = "<ul class=\"check\">" + state.hosts.map((host, index) => (
    "<li><span>" + esc(host.name) + " · " + esc(host.role) +
    (host.rhel ? " · RHEL " + esc(host.rhel) : "") + "</span>" +
    "<button type=\"button\" class=\"secondary\" data-remove-host=\"" + index + "\">Remove</button></li>"
  )).join("") + "</ul>";
}

function precheckLabel(status) {
  if (status === "ready") return "Ready";
  if (status === "blocked") return "Blocked";
  if (status === "unknown") return "Not measured";
  return "Incomplete";
}

function precheckClass(status) {
  if (status === "ready") return "badge badge--supported";
  if (status === "blocked") return "badge badge--unsupported";
  return "badge badge--steps";
}

function renderPrecheck() {
  const result = state.precheck;
  const root = document.getElementById("precheck-results");
  if (!result) {
    root.innerHTML = "";
    return;
  }
  const checks = result.checks.map((item) => {
    const stateName = item.status === "ready" ? "met" : item.status === "blocked" ? "miss" : "unknown";
    return "<li data-state=\"" + stateName + "\"><span><strong>" + esc(item.title) +
      "</strong><br>" + esc(item.detail) + " Required: " + esc(item.required) +
      "</span><strong>" + esc(precheckLabel(item.status)) + "</strong></li>";
  }).join("");
  const ports = "<table><thead><tr><th>Port</th><th>Service</th><th>Source</th><th>Destination</th><th>Use</th></tr></thead><tbody>" +
    result.ports.map((item) => (
      "<tr><td>" + esc(String(item.port)) + "/" + esc(item.protocol) + "</td><td>" + esc(item.service) +
      "</td><td>" + esc(item.source) + "</td><td>" + esc(item.destination) +
      "</td><td>" + (item.required ? "Required" : "Confirm") +
      (item.applies === "always" ? "" : " when " + esc(item.applies)) + "</td></tr>"
    )).join("") + "</tbody></table>";
  root.innerHTML =
    "<div class=\"card__head\"><h3>" + esc(result.target.title) + "</h3>" +
    "<span class=\"" + precheckClass(result.status) + "\">" + precheckLabel(result.status) + "</span></div>" +
    "<p>" + esc(result.summary) + "</p>" +
    "<ul class=\"check\">" + checks + "</ul>" +
    "<h3>Firewall ports for " + esc(result.target.version) + "</h3>" +
    ports +
    docLinks(result.docs);
}

let precheckRunning = false;

async function runPrecheck() {
  if (precheckRunning || !state.facts) return;
  precheckRunning = true;
  setBusy(true);
  const error = document.getElementById("precheck-error");
  error.hidden = true;
  try {
    const response = await fetch("/precheck", {
      method: "POST",
      headers: { "Content-Type": "application/json", Accept: "application/json" },
      body: JSON.stringify({
        target: document.getElementById("precheck-target").value,
        controller_version: state.ping.version,
        hub: state.facts.hub,
        eda: state.facts.eda,
        execution_nodes: state.facts.execution_nodes,
        hosts: state.hosts,
      }),
    });
    const body = await response.json();
    if (!response.ok) {
      setBanner(body.error || "Could not score this pre-check.", "error");
      return;
    }
    state.precheck = body;
    renderPrecheck();
  } catch (err) {
    setBanner("The local wizard server did not answer.", "error");
  } finally {
    precheckRunning = false;
    setBusy(false);
  }
}

async function showTargets() {
  if (!state.facts) return;
  setBusy(true);
  try {
    const response = await fetch("/advise", {
      method: "POST",
      headers: { "Content-Type": "application/json", Accept: "application/json" },
      body: JSON.stringify(state.facts),
    });
    const body = await response.json();
    if (!response.ok) {
      setBanner(body.error || "Could not score this environment.", "error");
      return;
    }
    state.advice = body;
    state.selectedId = body.recommended_id;
    renderTargets();
    if (state.selectedId) renderWalkthrough();
    showStep(4);
  } catch (err) {
    setBanner("The local wizard server did not answer.", "error");
  } finally {
    setBusy(false);
  }
}

document.getElementById("questions").addEventListener("submit", (event) => {
  event.preventDefault();
  const facts = collectFacts();
  if (!facts) return;
  state.facts = facts;
  const target = document.getElementById("precheck-target");
  if (facts.control_plane_nodes > 1) target.value = "rpm-2.6-enterprise";
  else if (facts.installer === "rpm") target.value = "rpm-2.6-growth";
  showStep(3);
});

document.getElementById("precheck-form").addEventListener("submit", (event) => {
  event.preventDefault();
  runPrecheck();
});

document.getElementById("add-host").addEventListener("click", () => {
  const error = document.getElementById("precheck-error");
  const read = readHostForm();
  if (read.error) {
    error.hidden = false;
    error.textContent = read.error;
    return;
  }
  error.hidden = true;
  state.hosts = state.hosts.filter((item) => item.name !== read.host.name).concat([read.host]);
  renderHostList();
});

document.getElementById("host-list").addEventListener("click", (event) => {
  const button = event.target.closest("[data-remove-host]");
  if (!button) return;
  state.hosts.splice(Number(button.getAttribute("data-remove-host")), 1);
  renderHostList();
});

document.getElementById("continue-targets").addEventListener("click", () => showTargets());

document.querySelectorAll("input[name='auth_mode']").forEach((input) => {
  input.addEventListener("change", syncAuthFields);
});
document.querySelectorAll("input[name='installer']").forEach((input) => {
  input.addEventListener("change", syncRhelField);
});
document.querySelectorAll("[data-goto]").forEach((button) => {
  button.addEventListener("click", () => showStep(Number(button.getAttribute("data-goto"))));
});
document.getElementById("targets").addEventListener("click", (event) => {
  const button = event.target.closest("[data-target-id]");
  if (!button) return;
  state.selectedId = button.getAttribute("data-target-id");
  renderWalkthrough();
  showStep(5);
});
document.getElementById("recheck").addEventListener("click", () => refreshValidation());

initTheme();
syncAuthFields();
renderHostList();
showStep(1);
