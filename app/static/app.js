const $ = (selector) => document.querySelector(selector);
const money = new Intl.NumberFormat("en-US", { style: "currency", currency: "USD" });
let snapshot = null;

function escapeHtml(value) {
  return String(value).replace(/[&<>"']/g, (character) => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#039;",
  })[character]);
}

async function api(path, options = {}) {
  const response = await fetch(path, {
    credentials: "same-origin",
    headers: { "Content-Type": "application/json", ...(options.headers || {}) },
    ...options,
  });
  if (response.status === 401) {
    showLogin();
    throw new Error("Sign in required");
  }
  const body = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(body.detail || `Request failed (${response.status})`);
  return body;
}

function showLogin() {
  $("#app").classList.add("hidden");
  $("#login").classList.remove("hidden");
}

function showApp() {
  $("#login").classList.add("hidden");
  $("#app").classList.remove("hidden");
}

function notice(message, isError = false) {
  const element = $("#notice");
  element.textContent = message;
  element.classList.toggle("error", isError);
  element.classList.remove("hidden");
  clearTimeout(notice.timer);
  notice.timer = setTimeout(() => element.classList.add("hidden"), 7000);
}

function dateText(value) {
  if (!value) return "—";
  return new Date(value).toLocaleString([], { dateStyle: "short", timeStyle: "short" });
}

function renderChart(points) {
  const canvas = $("#equity-chart");
  const ratio = window.devicePixelRatio || 1;
  const width = canvas.clientWidth;
  const height = 240;
  canvas.width = width * ratio;
  canvas.height = height * ratio;
  const context = canvas.getContext("2d");
  context.scale(ratio, ratio);
  context.clearRect(0, 0, width, height);
  if (points.length < 2) {
    context.fillStyle = "#829ab1";
    context.font = "13px system-ui";
    context.textAlign = "center";
    context.fillText("Performance appears after the first trading cycles.", width / 2, height / 2);
    return;
  }
  const values = points.map((point) => point.virtual_equity);
  const minimum = Math.min(...values);
  const maximum = Math.max(...values);
  const range = Math.max(maximum - minimum, 1);
  const padding = { left: 48, right: 12, top: 18, bottom: 28 };
  const x = (index) => padding.left + index * ((width - padding.left - padding.right) / (points.length - 1));
  const y = (value) => padding.top + (maximum - value) * ((height - padding.top - padding.bottom) / range);
  context.strokeStyle = "#d9e2ec";
  context.lineWidth = 1;
  for (let index = 0; index < 4; index += 1) {
    const rowY = padding.top + index * ((height - padding.top - padding.bottom) / 3);
    context.beginPath(); context.moveTo(padding.left, rowY); context.lineTo(width - padding.right, rowY); context.stroke();
  }
  context.strokeStyle = "#175cd3";
  context.lineWidth = 2.5;
  context.beginPath();
  points.forEach((point, index) => index ? context.lineTo(x(index), y(point.virtual_equity)) : context.moveTo(x(index), y(point.virtual_equity)));
  context.stroke();
  context.fillStyle = "#627d98";
  context.font = "11px system-ui";
  context.textAlign = "right";
  context.fillText(money.format(maximum), padding.left - 7, padding.top + 4);
  context.fillText(money.format(minimum), padding.left - 7, height - padding.bottom + 4);
}

function render(data) {
  snapshot = data;
  showApp();
  const state = data.state;
  const settings = data.settings;
  let title = "Paper bot running";
  let subtitle = `Checks ${settings.watchlist.length} symbols every ${settings.evaluation_minutes} minutes during regular hours.`;
  if (state.emergency_stop) { title = "Emergency stop engaged"; subtitle = state.halt_reason || "Manual confirmation is required to resume."; }
  else if (state.paused) { title = "Paper bot paused"; subtitle = state.last_error || "No automated orders will be submitted."; }
  if (!data.credentials_configured) { title = "Setup required"; subtitle = "Add Alpaca paper credentials to your local .env file."; }
  $("#bot-title").textContent = title;
  $("#bot-subtitle").textContent = subtitle;
  $("#start").textContent = state.emergency_stop ? "Resume bot" : "Start bot";
  $("#start").disabled = !data.credentials_configured || (!state.paused && !state.emergency_stop);
  $("#pause").disabled = state.paused;
  $("#run-now").disabled = state.paused;

  const account = data.account;
  $("#equity").textContent = account ? money.format(account.equity) : "—";
  $("#cash").textContent = account ? money.format(account.cash) : "—";
  $("#position-count").textContent = data.positions.length;
  $("#slots").textContent = `of ${settings.max_positions} allowed`;
  $("#market").textContent = data.market ? (data.market.is_open ? "Open" : "Closed") : "—";
  $("#market").className = data.market?.is_open ? "positive" : "";
  $("#market-next").textContent = data.market ? `${data.market.is_open ? "Closes" : "Opens"} ${dateText(data.market.is_open ? data.market.next_close : data.market.next_open)}` : "Regular hours only";

  $("#daily-limit").textContent = `${(settings.max_daily_loss_pct * 100).toFixed(1)}%`;
  $("#drawdown-limit").textContent = `${(settings.max_drawdown_pct * 100).toFixed(1)}%`;
  $("#trade-risk").textContent = `${(settings.risk_per_trade_pct * 100).toFixed(1)}%`;
  $("#position-limit").textContent = `${(settings.max_position_pct * 100).toFixed(0)}%`;
  $("#history-range").textContent = data.equity_history.length ? `${data.equity_history.length} observations` : "No data yet";
  renderChart(data.equity_history);

  $("#positions").innerHTML = data.positions.length ? data.positions.map((position) => `<tr>
    <td>${escapeHtml(position.symbol)}</td><td>${position.qty.toFixed(4)}</td><td>${money.format(position.avg_entry_price)}</td>
    <td>${money.format(position.current_price)}</td><td>${money.format(position.market_value)}</td>
    <td class="${position.unrealized_pl >= 0 ? "positive" : "negative"}">${money.format(position.unrealized_pl)} (${(position.unrealized_plpc * 100).toFixed(2)}%)</td>
  </tr>`).join("") : '<tr><td colspan="6" class="empty">No open positions</td></tr>';

  $("#signals").innerHTML = data.signals.length ? data.signals.slice(0, 16).map((signal) => `<div class="feed-item">
    <div class="feed-top"><strong>${escapeHtml(signal.symbol)}</strong><span class="tag ${signal.action.toLowerCase()}">${escapeHtml(signal.action)} · ${signal.score.toFixed(0)}</span></div>
    <p>${escapeHtml(signal.explanation)}</p><p>${dateText(signal.created_at)} · ${money.format(signal.price)}</p>
  </div>`).join("") : '<p class="empty">Signals will appear after the first market cycle.</p>';

  $("#events").innerHTML = data.events.length ? data.events.slice(0, 20).map((event) => `<div class="feed-item">
    <div class="feed-top"><strong>${escapeHtml(event.symbol || event.event_type.replaceAll("_", " "))}</strong><span class="tag ${event.event_type === "ERROR" || event.event_type.includes("HALT") ? "error" : ""}">${escapeHtml(event.event_type.replaceAll("_", " "))}</span></div>
    <p>${escapeHtml(event.message)}</p><p>${dateText(event.created_at)}</p>
  </div>`).join("") : '<p class="empty">No events yet.</p>';

  if (data.connection_error) notice(data.connection_error, true);
}

async function refresh() {
  try { render(await api("/api/dashboard")); }
  catch (error) { if (error.message !== "Sign in required") notice(error.message, true); }
}

async function action(path, success, body) {
  try {
    const options = { method: "POST" };
    if (body !== undefined) options.body = JSON.stringify(body);
    await api(path, options);
    notice(success);
    await refresh();
  } catch (error) { notice(error.message, true); }
}

$("#login-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  $("#login-error").textContent = "";
  try {
    await api("/api/login", { method: "POST", body: JSON.stringify({ password: $("#password").value }) });
    $("#password").value = "";
    await refresh();
  } catch (error) { $("#login-error").textContent = error.message; }
});
$("#logout").addEventListener("click", async () => { await api("/api/logout", { method: "POST" }); showLogin(); });
$("#refresh").addEventListener("click", refresh);
$("#test").addEventListener("click", () => action("/api/control/test", "Paper connection succeeded."));
$("#pause").addEventListener("click", () => action("/api/control/pause", "Bot paused. Existing positions were not changed."));
$("#run-now").addEventListener("click", () => action("/api/control/run-now", "Market cycle completed."));
$("#emergency").addEventListener("click", () => {
  if (confirm("Stop automated trading and cancel every open order? Existing positions will remain open.")) action("/api/control/emergency-stop", "Emergency stop engaged.");
});
$("#start").addEventListener("click", () => {
  if (snapshot?.state.emergency_stop) {
    const phrase = prompt('Type "RESUME PAPER TRADING" to clear the emergency stop.');
    if (phrase) action("/api/control/resume", "Paper bot resumed.", { confirmation: phrase });
  } else action("/api/control/start", "Paper bot started.");
});

function populateSettings() {
  const form = $("#settings-form");
  const settings = snapshot.settings;
  Object.entries(settings).forEach(([key, value]) => {
    const input = form.elements.namedItem(key);
    if (!input) return;
    if (key === "watchlist") input.value = value.join(", ");
    else if (key.endsWith("_pct")) input.value = value * 100;
    else input.value = value;
  });
}
$("#open-settings").addEventListener("click", () => { populateSettings(); $("#settings-dialog").showModal(); });
$("#close-settings").addEventListener("click", () => $("#settings-dialog").close());
$("#cancel-settings").addEventListener("click", () => $("#settings-dialog").close());
$("#settings-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const data = Object.fromEntries(new FormData(event.target));
  const payload = {};
  Object.entries(data).forEach(([key, value]) => {
    if (key === "watchlist") payload[key] = value.split(",").map((item) => item.trim()).filter(Boolean);
    else payload[key] = Number(value);
  });
  ["max_position_pct", "risk_per_trade_pct", "max_daily_loss_pct", "max_drawdown_pct"].forEach((key) => payload[key] /= 100);
  try {
    await api("/api/settings", { method: "PUT", body: JSON.stringify(payload) });
    $("#settings-dialog").close(); notice("Settings saved."); await refresh();
  } catch (error) { notice(error.message, true); }
});

$("#backtest").addEventListener("click", async () => {
  const button = $("#backtest"); button.disabled = true; button.textContent = "Running…";
  try {
    const result = await api("/api/backtest", { method: "POST" });
    const container = $("#backtest-results");
    container.innerHTML = `<div><span>Ending equity</span><strong>${money.format(result.ending_equity)}</strong></div>
      <div><span>Total return</span><strong class="${result.return_pct >= 0 ? "positive" : "negative"}">${result.return_pct.toFixed(2)}%</strong></div>
      <div><span>Maximum drawdown</span><strong>${result.max_drawdown_pct.toFixed(2)}%</strong></div>
      <div><span>Win rate</span><strong>${result.win_rate_pct.toFixed(1)}%</strong></div>`;
    container.classList.remove("hidden"); notice("Backtest completed. Historical results do not predict future performance.");
  } catch (error) { notice(error.message, true); }
  finally { button.disabled = false; button.textContent = "Run 6-month backtest"; }
});

$("#report").addEventListener("click", () => {
  window.location.assign("/api/reports/monthly.csv");
});

window.addEventListener("resize", () => snapshot && renderChart(snapshot.equity_history));
refresh();
setInterval(refresh, 30000);

