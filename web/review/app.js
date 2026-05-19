const screen = document.querySelector("#screen");
const statusEl = document.querySelector("#status");
const speedEl = document.querySelector("#speed");
const limiterEl = document.querySelector("#limiter");
const pauseEl = document.querySelector("#pause");
const rewindEl = document.querySelector("#rewind");
const rewindButton = document.querySelector("#rewind-button");
const upcomingEl = document.querySelector("#upcoming");

let lastFrameVersion = -1;

function speedFromSlider() {
  return Math.max(1, Math.min(1000, Math.round(10 ** Number(speedEl.value))));
}

async function post(path, body = {}) {
  await fetch(path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
}

speedEl.addEventListener("input", () => {
  post("/api/speed", { speed: speedFromSlider() });
});

limiterEl.addEventListener("change", () => {
  post("/api/limiter", { enabled: limiterEl.checked });
});

pauseEl.addEventListener("click", () => {
  post("/api/pause");
});

rewindButton.addEventListener("click", () => {
  post("/api/rewind", { digits: Number(rewindEl.value) });
});

function fmt(value) {
  return Number(value).toLocaleString();
}

function renderUpcoming(items) {
  upcomingEl.replaceChildren(
    ...items.map((item) => {
      const row = document.createElement("li");
      const pair = document.createElement("span");
      const button = document.createElement("span");
      pair.className = "pair";
      button.className = "button";
      pair.textContent = `${fmt(item.digit_index)}  ${item.pair}`;
      button.textContent = item.button.toUpperCase();
      row.append(pair, button);
      return row;
    }),
  );
}

async function refresh() {
  try {
    const response = await fetch("/api/state", { cache: "no-store" });
    const state = await response.json();
    statusEl.textContent = `${state.status} | ${fmt(state.digits_consumed)}/${fmt(state.max_digits)} digits | ${state.speed}x (${state.speed_limiter_enabled}) | inputs sent: ${fmt(state.inputs_sent)} | last: ${state.last_button} | snapshots: ${state.snapshots}`;
    renderUpcoming(state.upcoming);
    if (state.frame_version !== lastFrameVersion) {
      lastFrameVersion = state.frame_version;
      screen.src = `/api/frame.png?v=${state.frame_version}`;
    }
  } catch (error) {
    statusEl.textContent = `Disconnected: ${error}`;
  } finally {
    setTimeout(refresh, 150);
  }
}

refresh();
