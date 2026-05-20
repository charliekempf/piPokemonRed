const screen = document.querySelector("#screen");
const statusEl = document.querySelector("#status");
const statDigitsEl = document.querySelector("#stat-digits");
const statProgressEl = document.querySelector("#stat-progress span");
const statLocationEl = document.querySelector("#stat-location");
const statSpeedEl = document.querySelector("#stat-speed");
const statActualSpeedEl = document.querySelector("#stat-actual-speed");
const statDigitRateEl = document.querySelector("#stat-digit-rate");
const screenShellEl = document.querySelector(".screen-shell");
const seekLabelEl = document.querySelector("#seek-label");
const seekProgressBarEl = document.querySelector("#seek-progress-bar");
const romMissingPanelEl = document.querySelector("#rom-missing-panel");
const romUploadEl = document.querySelector("#rom-upload");
const romUploadButtonEl = document.querySelector("#rom-upload-button");
const romUploadStatusEl = document.querySelector("#rom-upload-status");
const speedEl = document.querySelector("#speed");
const pauseEl = document.querySelector("#pause");
const muteEl = document.querySelector("#mute");
const rewindEl = document.querySelector("#rewind");
const rewindButton = document.querySelector("#rewind-button");
const fastForwardButton = document.querySelector("#fast-forward-button");
const jumpDigitsEl = document.querySelector("#jump-digits");
const jumpButton = document.querySelector("#jump-button");
const warpStateEl = document.querySelector("#warp-state");
const warpLimitEl = document.querySelector("#warp-limit");
const warpStateButton = document.querySelector("#warp-state-button");
const simulateCheckpointIntervalEl = document.querySelector("#simulate-checkpoint-interval");
const simulateTargetDigitsEl = document.querySelector("#simulate-target-digits");
const simulateButton = document.querySelector("#simulate-button");
const stopSimulateButton = document.querySelector("#stop-simulate-button");
const simulateStatusEl = document.querySelector("#simulate-status");
const simulateStateEl = document.querySelector("#simulate-state");
const simulateProgressEl = document.querySelector("#simulate-progress");
const simulateRateEl = document.querySelector("#simulate-rate");
const simulateEtaEl = document.querySelector("#simulate-eta");
const runSelectEl = document.querySelector("#run-select");
const checkpointsEl = document.querySelector("#checkpoints");
const loadCheckpointButton = document.querySelector("#load-checkpoint-button");
const timelineEl = document.querySelector("#timeline");
const partyEl = document.querySelector("#party");
const bagEl = document.querySelector("#bag");
const playerPanelEl = document.querySelector("#player-panel");
const badgesToggleEl = document.querySelector("#badges-toggle");
const badgesCountEl = document.querySelector("#badges-count");
const playerInfoEl = document.querySelector("#player-info");
const badgesEl = document.querySelector("#badges");
const inputsEl = document.querySelector("#inputs");
const configDigitsPerInputEl = document.querySelector("#config-digits-per-input");
const configGameTitleEl = document.querySelector("#config-game-title");
const configGameVersionEl = document.querySelector("#config-game-version");
const configGameRegionEl = document.querySelector("#config-game-region");
const configSpreadChartEl = document.querySelector("#config-spread-chart");
const configRangesEl = document.querySelector("#config-ranges");

const FRAME_WIDTH = 160;
const FRAME_HEIGHT = 144;
const FRAME_BYTES = FRAME_WIDTH * FRAME_HEIGHT * 4;
const GAMEBOY_FPS = 4194304 / 70224;
const INPUT_ROW_HEIGHT = 38;
const INPUT_ROW_GAP = 6;
const INPUT_CANVAS_PADDING = 0;
const STATE_REFRESH_MS = 150;
const INPUT_REFRESH_MS = 33;

let frameFetchInFlight = false;
let inputFetchInFlight = false;
let controlsInitialized = false;
let backendBusy = false;
let romMissing = false;
let romUploadInFlight = false;
let selectedCheckpointDigits = null;
let runListSignature = "";
let checkpointListSignature = "";
let partyRenderSignature = "";
let bagRenderSignature = "";
let inputRenderSignature = "";
let configRenderSignature = "";
let lastInputFetchAt = 0;
let lastPartyMembers = [];
let badgesExpanded = false;
const expandedPartySlots = new Set();
const BUTTON_COLORS = {
  a: "#6f89af",
  b: "#c97b68",
  start: "#fff4b8",
  select: "#aeb4c0",
  up: "#7fb083",
  down: "#587d6a",
  left: "#b98fc9",
  right: "#d9a85f",
};

function speedSliderIsUnlimited() {
  return Number(speedEl.value) >= Number(speedEl.max);
}

function speedFromSlider() {
  if (speedSliderIsUnlimited()) {
    return 1000;
  }
  const speed = Math.max(0.1, Math.min(1000, 10 ** Number(speedEl.value)));
  return speed < 1 ? Number(speed.toFixed(1)) : Math.round(speed);
}

function snapSpeedSliderToValue(speed) {
  if (speedSliderIsUnlimited()) {
    return;
  }
  speedEl.value = String(Math.log10(Math.max(0.1, Math.min(1000, Number(speed)))));
}

function speedLabelFromSlider() {
  return speedSliderIsUnlimited() ? "Unlimited" : speedLabel(speedFromSlider());
}

function speedLabel(value) {
  const speed = Math.max(0.1, Number(value) || 1);
  return `${speed < 1 ? speed.toFixed(1) : Math.round(speed)}x`;
}

function actualSpeedLabel(value) {
  const speed = Math.max(0, Number(value) || 0);
  const precision = speed > 0 && speed < 10 ? 1 : 0;
  return `Actual ${speed.toFixed(precision)}x`;
}

function digitRateLabel(actualSpeed, digitsPerInput, framesPerInput) {
  const safeFramesPerInput = Math.max(1, Number(framesPerInput) || 1);
  const rate = Math.max(0, Number(actualSpeed) || 0) * GAMEBOY_FPS * Math.max(1, Number(digitsPerInput) || 1) / safeFramesPerInput;
  return digitRateValueLabel(rate);
}

function digitRateValueLabel(value) {
  const rate = Math.max(0, Number(value) || 0);
  if (rate >= 1000) {
    return `${fmt(Math.round(rate))} digits/s`;
  }
  return `${rate.toFixed(rate > 0 && rate < 10 ? 1 : 0)} digits/s`;
}

function renderSeekOverlay(state) {
  const seek = state.seek || {};
  const active = Boolean(seek.active) || backendBusy;
  const progress = Number.isFinite(Number(seek.progress)) ? Math.max(0, Math.min(100, Number(seek.progress))) : 0;
  screenShellEl.classList.toggle("is-seeking", active);
  seekLabelEl.textContent = seek.label || state.status || "Seeking";
  seekProgressBarEl.style.width = `${progress}%`;
}

function create2dRenderer(canvas) {
  const context = canvas.getContext("2d");
  const imageData = context.createImageData(FRAME_WIDTH, FRAME_HEIGHT);
  context.imageSmoothingEnabled = false;

  return {
    mode: "Canvas 2D",
    draw(bytes) {
      imageData.data.set(bytes);
      context.putImageData(imageData, 0, 0);
    },
  };
}

function compileShader(gl, type, source) {
  const shader = gl.createShader(type);
  gl.shaderSource(shader, source);
  gl.compileShader(shader);
  if (!gl.getShaderParameter(shader, gl.COMPILE_STATUS)) {
    throw new Error(gl.getShaderInfoLog(shader) || "Could not compile shader.");
  }
  return shader;
}

function createWebglRenderer(canvas) {
  const gl = canvas.getContext("webgl", {
    alpha: false,
    antialias: false,
    depth: false,
    preserveDrawingBuffer: true,
  });
  if (!gl) {
    return null;
  }

  const vertexShader = compileShader(
    gl,
    gl.VERTEX_SHADER,
    `
      attribute vec2 position;
      attribute vec2 texCoord;
      varying vec2 vTexCoord;
      void main() {
        gl_Position = vec4(position, 0.0, 1.0);
        vTexCoord = texCoord;
      }
    `,
  );
  const fragmentShader = compileShader(
    gl,
    gl.FRAGMENT_SHADER,
    `
      precision mediump float;
      uniform sampler2D frame;
      varying vec2 vTexCoord;
      void main() {
        gl_FragColor = texture2D(frame, vTexCoord);
      }
    `,
  );
  const program = gl.createProgram();
  gl.attachShader(program, vertexShader);
  gl.attachShader(program, fragmentShader);
  gl.linkProgram(program);
  if (!gl.getProgramParameter(program, gl.LINK_STATUS)) {
    throw new Error(gl.getProgramInfoLog(program) || "Could not link WebGL program.");
  }

  const vertexData = new Float32Array([
    -1, -1, 0, 1,
    1, -1, 1, 1,
    -1, 1, 0, 0,
    1, 1, 1, 0,
  ]);
  const buffer = gl.createBuffer();
  gl.bindBuffer(gl.ARRAY_BUFFER, buffer);
  gl.bufferData(gl.ARRAY_BUFFER, vertexData, gl.STATIC_DRAW);
  gl.useProgram(program);

  const position = gl.getAttribLocation(program, "position");
  const texCoord = gl.getAttribLocation(program, "texCoord");
  gl.enableVertexAttribArray(position);
  gl.vertexAttribPointer(position, 2, gl.FLOAT, false, 16, 0);
  gl.enableVertexAttribArray(texCoord);
  gl.vertexAttribPointer(texCoord, 2, gl.FLOAT, false, 16, 8);

  const texture = gl.createTexture();
  gl.bindTexture(gl.TEXTURE_2D, texture);
  gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MIN_FILTER, gl.NEAREST);
  gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MAG_FILTER, gl.NEAREST);
  gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_S, gl.CLAMP_TO_EDGE);
  gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_T, gl.CLAMP_TO_EDGE);
  gl.pixelStorei(gl.UNPACK_ALIGNMENT, 1);
  gl.viewport(0, 0, FRAME_WIDTH, FRAME_HEIGHT);

  return {
    mode: "WebGL",
    draw(bytes) {
      gl.bindTexture(gl.TEXTURE_2D, texture);
      gl.texImage2D(
        gl.TEXTURE_2D,
        0,
        gl.RGBA,
        FRAME_WIDTH,
        FRAME_HEIGHT,
        0,
        gl.RGBA,
        gl.UNSIGNED_BYTE,
        bytes,
      );
      gl.drawArrays(gl.TRIANGLE_STRIP, 0, 4);
    },
  };
}

function createRenderer(canvas) {
  try {
    return createWebglRenderer(canvas) || create2dRenderer(canvas);
  } catch (error) {
    console.warn("Falling back to Canvas 2D renderer.", error);
    return create2dRenderer(canvas);
  }
}

const renderer = createRenderer(screen);

async function post(path, body = {}) {
  const response = await fetch(path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  return response.json().catch(() => ({}));
}

romUploadButtonEl.addEventListener("click", () => {
  romUploadEl.click();
});

romUploadEl.addEventListener("change", async () => {
  const file = romUploadEl.files && romUploadEl.files[0];
  if (!file) {
    return;
  }
  romUploadInFlight = true;
  romUploadButtonEl.disabled = true;
  romUploadStatusEl.textContent = `Loading ${file.name}`;
  try {
    const formData = new FormData();
    formData.append("rom", file, file.name);
    const response = await fetch("/api/upload-rom", { method: "POST", body: formData });
    const result = await response.json();
    if (!result.ok) {
      throw new Error(result.error || "Upload failed");
    }
    controlsInitialized = false;
    romUploadStatusEl.textContent = "ROM loaded";
  } catch (error) {
    romUploadStatusEl.textContent = error.message || "ROM upload failed";
    romUploadButtonEl.disabled = false;
  } finally {
    romUploadInFlight = false;
    romUploadEl.value = "";
  }
});

speedEl.addEventListener("input", () => {
  const speed = speedFromSlider();
  snapSpeedSliderToValue(speed);
  statSpeedEl.textContent = `Set ${speedLabel(speed)}`;
  post("/api/speed", { speed });
  post("/api/limiter", { enabled: !speedSliderIsUnlimited() });
});

muteEl.addEventListener("click", () => {
  if (muteEl.dataset.audioUnavailable === "true") {
    speedEl.value = "0";
    statSpeedEl.textContent = "Set 1x";
    post("/api/speed", { speed: 1 });
    post("/api/limiter", { enabled: true });
    post("/api/volume", { volume: 100 });
    return;
  }
  const muted = muteEl.dataset.muted === "true";
  post("/api/volume", { volume: muted ? 100 : 0 });
});

runSelectEl.addEventListener("change", async () => {
  const runName = runSelectEl.value;
  runSelectEl.disabled = true;
  const result = await post("/api/select-run", { run_name: runName });
  if (!result.ok) {
    runSelectEl.title = result.error || "Could not load run config";
  }
  controlsInitialized = false;
  selectedCheckpointDigits = null;
  checkpointListSignature = "";
  partyRenderSignature = "";
  bagRenderSignature = "";
  inputRenderSignature = "";
  configRenderSignature = "";
  runSelectEl.disabled = false;
  refresh();
});

pauseEl.addEventListener("click", () => {
  post("/api/pause");
});

rewindButton.addEventListener("click", () => {
  post("/api/rewind", { digits: Number(rewindEl.value) });
});

fastForwardButton.addEventListener("click", () => {
  post("/api/fast-forward", { digits: Number(rewindEl.value) });
});

jumpButton.addEventListener("click", () => {
  const digits = Math.max(0, Number(String(jumpDigitsEl.value).replaceAll(",", "")) || 0);
  post("/api/jump", { digits });
});

warpStateButton.addEventListener("click", async () => {
  speedEl.value = "0";
  statSpeedEl.textContent = "Set 1x";
  await post("/api/speed", { speed: 1 });
  await post("/api/limiter", { enabled: true });
  post("/api/warp-state", { state: warpStateEl.value, limit_digits: Number(warpLimitEl.value) });
});

simulateButton.addEventListener("click", () => {
  const targetDigits = Math.max(0, Number(String(simulateTargetDigitsEl.value).replaceAll(",", "")) || 0);
  post("/api/simulate", {
    target_digits: targetDigits,
    checkpoint_interval_digits: Number(simulateCheckpointIntervalEl.value),
  });
});

stopSimulateButton.addEventListener("click", () => {
  stopSimulateButton.disabled = true;
  setSimulatorStats({ state: "Stopping" });
  post("/api/stop-simulate");
});

badgesToggleEl.addEventListener("click", () => {
  badgesExpanded = !badgesExpanded;
  playerPanelEl.classList.toggle("is-collapsed", !badgesExpanded);
  badgesToggleEl.setAttribute("aria-expanded", String(badgesExpanded));
});

loadCheckpointButton.addEventListener("click", () => {
  if (selectedCheckpointDigits === null) {
    return;
  }
  post("/api/jump", { digits: selectedCheckpointDigits });
});

function fmt(value) {
  return Number(value).toLocaleString();
}

function fmtRate(value) {
  const rate = Number(value);
  if (!Number.isFinite(rate)) {
    return "-";
  }
  return `${fmt(Math.round(rate))} digits/s`;
}

function fmtDuration(seconds) {
  const totalSeconds = Math.max(0, Math.round(Number(seconds) || 0));
  const hours = Math.floor(totalSeconds / 3600);
  const minutes = Math.floor((totalSeconds % 3600) / 60);
  const secs = totalSeconds % 60;
  if (hours > 0) {
    return `${hours}h ${String(minutes).padStart(2, "0")}m`;
  }
  if (minutes > 0) {
    return `${minutes}m ${String(secs).padStart(2, "0")}s`;
  }
  return `${secs}s`;
}

function renderInputs(items, state = {}) {
  const width = Math.max(220, Math.floor(inputsEl.getBoundingClientRect().width || inputsEl.clientWidth || 220));
  const height = items.length
    ? Math.max(1, (items.length * INPUT_ROW_HEIGHT) + ((items.length - 1) * INPUT_ROW_GAP) + (INPUT_CANVAS_PADDING * 2))
    : 72;
  const signature = JSON.stringify({ items, width, height, pixelRatio: window.devicePixelRatio || 1 });
  if (signature === inputRenderSignature) {
    return;
  }
  inputRenderSignature = signature;

  const pixelRatio = Math.max(1, window.devicePixelRatio || 1);
  if (inputsEl.width !== Math.round(width * pixelRatio) || inputsEl.height !== Math.round(height * pixelRatio)) {
    inputsEl.width = Math.round(width * pixelRatio);
    inputsEl.height = Math.round(height * pixelRatio);
    inputsEl.style.height = `${height}px`;
  }

  const context = inputsEl.getContext("2d");
  context.setTransform(pixelRatio, 0, 0, pixelRatio, 0, 0);
  context.clearRect(0, 0, width, height);
  context.textBaseline = "middle";
  inputsEl.title = items.length ? "Canvas-rendered input list" : "Out of digits. Download more.";
  inputsEl.setAttribute("aria-label", items.length ? inputsAccessibilityLabel(items) : "Out of digits. Download more.");

  if (!items.length) {
    roundRect(context, 0.5, 0.5, width - 1, height - 1, 6);
    context.fillStyle = "#46383b";
    context.fill();
    context.strokeStyle = "#7b5c63";
    context.stroke();
    context.font = "700 13px Segoe UI, system-ui, sans-serif";
    context.fillStyle = "#fff4b8";
    context.fillText("Out of digits", 10, 26);
    context.font = "12px Segoe UI, system-ui, sans-serif";
    context.fillStyle = "#d8c8c0";
    context.fillText("Download more", 10, 48);
    return;
  }

  items.forEach((item, index) => {
    const role = item.role || "future";
    const y = INPUT_CANVAS_PADDING + (index * (INPUT_ROW_HEIGHT + INPUT_ROW_GAP));
    drawInputRow(context, item, role, 0.5, y + 0.5, width - 1, INPUT_ROW_HEIGHT);
  });
}

function renderConfigInfo(config = {}) {
  const signature = JSON.stringify(config);
  if (signature === configRenderSignature) {
    return;
  }
  configRenderSignature = signature;

  const mapping = Array.isArray(config.mapping) ? config.mapping : [];
  const digitsPerInput = Number(config.digits_per_input) || 0;
  const game = config.game || {};
  configDigitsPerInputEl.textContent = digitsPerInput ? String(digitsPerInput) : "-";
  configGameTitleEl.textContent = game.title || "-";
  configGameVersionEl.textContent = game.version || "-";
  configGameRegionEl.textContent = game.region || "-";

  if (!mapping.length) {
    const empty = document.createElement("li");
    empty.className = "config-empty";
    empty.textContent = "No config data";
    configRangesEl.replaceChildren(empty);
    drawConfigPie([]);
    return;
  }

  configRangesEl.replaceChildren(
    ...mapping.map((entry) => {
      const button = String(entry.button || "").toLowerCase();
      const row = document.createElement("li");
      const swatch = document.createElement("span");
      const range = document.createElement("span");
      const share = document.createElement("strong");
      row.className = "config-range";
      swatch.className = "config-swatch";
      swatch.style.background = BUTTON_COLORS[button] || "#6f89af";
      range.textContent = `${String(entry.min).padStart(digitsPerInput || 2, "0")}-${String(entry.max).padStart(digitsPerInput || 2, "0")} -> ${button.toUpperCase()}`;
      share.textContent = `${Number(entry.percent || 0).toFixed(Number(entry.percent || 0) < 10 ? 1 : 0)}%`;
      row.append(swatch, range, share);
      return row;
    }),
  );
  drawConfigPie(mapping);
}

function drawConfigPie(mapping) {
  const canvas = configSpreadChartEl;
  const context = canvas.getContext("2d");
  const width = canvas.width;
  const height = canvas.height;
  context.clearRect(0, 0, width, height);
  if (!mapping.length) {
    return;
  }

  const total = mapping.reduce((sum, entry) => sum + Number(entry.count || 0), 0) || 1;
  const centerX = 74;
  const centerY = 75;
  const radius = 54;
  let start = -Math.PI / 2;
  for (const entry of mapping) {
    const end = start + ((Number(entry.count || 0) / total) * Math.PI * 2);
    context.beginPath();
    context.moveTo(centerX, centerY);
    context.arc(centerX, centerY, radius, start, end);
    context.closePath();
    context.fillStyle = BUTTON_COLORS[String(entry.button || "").toLowerCase()] || "#6f89af";
    context.fill();
    start = end;
  }

  context.beginPath();
  context.arc(centerX, centerY, radius, 0, Math.PI * 2);
  context.strokeStyle = "#454b58";
  context.lineWidth = 2;
  context.stroke();
}

function drawInputRow(context, item, role, x, y, width, height) {
  const isCurrent = role === "current";
  const isPast = role === "past";
  roundRect(context, x, y, width, height, 6);
  context.fillStyle = isCurrent ? "#3b4a61" : isPast ? "#292c34" : "#30333c";
  context.fill();
  context.strokeStyle = isCurrent ? "#6f89af" : isPast ? "#3a3f4a" : "#454b58";
  context.stroke();

  context.save();
  context.globalAlpha = isPast ? 0.48 : 1;
  context.font = "13px Consolas, 'Cascadia Mono', monospace";
  context.fillStyle = "#b8c0d0";
  context.fillText(`${fmt(item.digit_index)}  ${item.pair}`, x + 8, y + (height / 2));
  context.font = "700 13px Consolas, 'Cascadia Mono', monospace";
  context.fillStyle = "#fff4b8";
  const button = String(item.button || "").toUpperCase();
  const buttonWidth = context.measureText(button).width;
  context.fillText(button, x + width - 8 - buttonWidth, y + (height / 2));
  context.restore();
}

function roundRect(context, x, y, width, height, radius) {
  const safeRadius = Math.min(radius, width / 2, height / 2);
  context.beginPath();
  context.moveTo(x + safeRadius, y);
  context.lineTo(x + width - safeRadius, y);
  context.quadraticCurveTo(x + width, y, x + width, y + safeRadius);
  context.lineTo(x + width, y + height - safeRadius);
  context.quadraticCurveTo(x + width, y + height, x + width - safeRadius, y + height);
  context.lineTo(x + safeRadius, y + height);
  context.quadraticCurveTo(x, y + height, x, y + height - safeRadius);
  context.lineTo(x, y + safeRadius);
  context.quadraticCurveTo(x, y, x + safeRadius, y);
  context.closePath();
}

function inputsAccessibilityLabel(items) {
  return items
    .map((item) => `${item.role || "future"} ${fmt(item.digit_index)} ${item.pair} ${String(item.button || "").toUpperCase()}`)
    .join(", ");
}

function renderParty(members) {
  lastPartyMembers = members;
  const validSlots = new Set(members.map((member) => Number(member.slot)));
  for (const slot of expandedPartySlots) {
    if (!validSlots.has(slot)) {
      expandedPartySlots.delete(slot);
    }
  }
  const signature = JSON.stringify({
    members,
    expanded: [...expandedPartySlots].sort((a, b) => a - b),
  });
  if (signature === partyRenderSignature) {
    return;
  }
  partyRenderSignature = signature;

  if (!members.length) {
    const row = document.createElement("li");
    row.className = "party-empty";
    row.textContent = "No party data";
    partyEl.replaceChildren(row);
    return;
  }

  partyEl.replaceChildren(
    ...members.map((member) => {
      const row = document.createElement("li");
      const header = document.createElement("button");
      const badge = document.createElement("span");
      const body = document.createElement("div");
      const top = document.createElement("div");
      const name = document.createElement("strong");
      const speciesName = document.createElement("span");
      const level = document.createElement("span");
      const lower = document.createElement("div");
      const hpWrap = document.createElement("span");
      const hpBar = document.createElement("span");
      const hpText = document.createElement("span");
      const status = document.createElement("span");
      const moves = document.createElement("ol");
      const hp = Math.max(0, Number(member.hp));
      const maxHp = Math.max(0, Number(member.max_hp));
      const hpPercent = maxHp > 0 ? Math.min(100, (hp / maxHp) * 100) : 0;
      const hpState = hpPercent <= 20 ? "red" : hpPercent <= 50 ? "yellow" : "green";
      const isExpanded = expandedPartySlots.has(Number(member.slot));

      row.className = "party-member";
      row.classList.toggle("is-expanded", isExpanded);
      header.className = "party-toggle";
      badge.className = "party-badge";
      body.className = "party-body";
      top.className = "party-top";
      speciesName.className = "party-species";
      lower.className = "party-lower";
      hpWrap.className = "hp-wrap";
      hpBar.className = "hp-bar";
      hpText.className = "hp-text";
      status.className = "party-status";
      moves.className = "party-moves";
      hpBar.dataset.hpState = hpState;

      header.type = "button";
      header.setAttribute("aria-expanded", String(isExpanded));
      header.addEventListener("click", () => {
        const slot = Number(member.slot);
        if (expandedPartySlots.has(slot)) {
          expandedPartySlots.delete(slot);
        } else {
          expandedPartySlots.add(slot);
        }
        partyRenderSignature = "";
        renderParty(lastPartyMembers);
      });
      badge.textContent = String(member.slot);
      name.textContent = member.name || `MON ${member.species}`;
      speciesName.textContent = member.species_name || `Species ${member.species}`;
      level.textContent = `Lv ${member.level || "-"}`;
      hpBar.style.width = `${hpPercent}%`;
      hpText.textContent = maxHp > 0 ? `${fmt(hp)} / ${fmt(maxHp)}` : "- / -";
      status.textContent = member.status || "OK";
      status.dataset.status = String(member.status || "OK").toLowerCase();

      hpWrap.append(hpBar);
      top.append(name, level);
      lower.append(hpWrap, hpText, status);
      body.append(top, speciesName, lower);
      header.append(badge, body);
      moves.replaceChildren(
        ...(member.moves || []).map((move) => {
          const moveRow = document.createElement("li");
          const moveName = document.createElement("span");
          const pp = document.createElement("span");
          moveName.textContent = move.name || `Move ${move.id}`;
          pp.textContent = `PP ${fmt(move.pp)} / ${fmt(move.max_pp)}`;
          moveRow.append(moveName, pp);
          return moveRow;
        }),
      );
      if (!moves.children.length) {
        const emptyMove = document.createElement("li");
        emptyMove.className = "empty";
        emptyMove.textContent = "No moves";
        moves.append(emptyMove);
      }
      row.append(header, moves);
      return row;
    }),
  );
}

function renderBag(items) {
  const signature = JSON.stringify(items);
  if (signature === bagRenderSignature) {
    return;
  }
  bagRenderSignature = signature;

  if (!items.length) {
    const row = document.createElement("li");
    row.className = "bag-empty";
    row.textContent = "No items";
    bagEl.replaceChildren(row);
    return;
  }

  bagEl.replaceChildren(
    ...items.map((item) => {
      const row = document.createElement("li");
      const name = document.createElement("span");
      const quantity = document.createElement("strong");
      row.className = "bag-item";
      row.title = `Item $${Number(item.id).toString(16).toUpperCase().padStart(2, "0")}`;
      name.textContent = item.name || `Item $${Number(item.id).toString(16).toUpperCase().padStart(2, "0")}`;
      quantity.textContent = `x${fmt(item.quantity || 0)}`;
      row.append(name, quantity);
      return row;
    }),
  );
}

function renderBadges(badges) {
  const earnedCount = badges.filter((badge) => Boolean(badge.earned)).length;
  const totalCount = badges.length || 8;
  badgesCountEl.textContent = `${earnedCount} / ${totalCount}`;

  if (!badges.length) {
    const row = document.createElement("li");
    row.className = "badge-empty";
    row.textContent = "No badge data";
    badgesEl.replaceChildren(row);
    return;
  }

  badgesEl.replaceChildren(
    ...badges.map((badge) => {
      const row = document.createElement("li");
      const mark = document.createElement("span");
      const name = document.createElement("span");
      const state = document.createElement("span");
      row.className = "badge-item";
      row.classList.toggle("is-earned", Boolean(badge.earned));
      mark.className = "badge-mark";
      name.className = "badge-name";
      state.className = "badge-state";
      mark.textContent = String(badge.name || "?").slice(0, 1).toUpperCase();
      name.textContent = badge.name || `Badge ${badge.slot}`;
      state.textContent = badge.earned ? "Earned" : "Locked";
      row.append(mark, name, state);
      return row;
    }),
  );
}

function renderPlayerInfo(info = {}) {
  const time = info.time || {};
  const hours = Number(time.hours) || 0;
  const minutes = Number(time.minutes) || 0;
  const seconds = Number(time.seconds) || 0;
  const totalSeconds = Number.isFinite(Number(time.total_seconds))
    ? Number(time.total_seconds)
    : (hours * 3600) + (minutes * 60) + seconds;
  const days = totalSeconds / 86400;
  const dayLabel = days >= 10 ? days.toFixed(1) : days.toFixed(2);
  const rows = [
    ["Money", `$${fmt(info.money || 0)}`],
    ["Pokedex", `${fmt(info.pokedex_seen || 0)} seen / ${fmt(info.pokedex_caught || 0)} caught`],
    ["Time", `${fmt(hours)}:${String(minutes).padStart(2, "0")}:${String(seconds).padStart(2, "0")} [${dayLabel} days]`],
  ];
  playerInfoEl.replaceChildren(
    ...rows.flatMap(([label, value]) => {
      const term = document.createElement("dt");
      const detail = document.createElement("dd");
      term.textContent = label;
      detail.textContent = value;
      return [term, detail];
    }),
  );
}

function setSimulatorStats({ state = "Ready", progress = "-", rate = "-", eta = "-", title = "" } = {}) {
  simulateStateEl.textContent = state;
  simulateProgressEl.textContent = progress;
  simulateRateEl.textContent = rate;
  simulateEtaEl.textContent = eta;
  simulateStatusEl.textContent = [state, progress, rate, eta].filter((value) => value && value !== "-").join(", ") || "Ready";
  simulateStatusEl.title = title;
}

function renderRuns(runs = [], activeRun = "") {
  const signature = JSON.stringify({ runs, activeRun });
  if (signature === runListSignature) {
    return;
  }
  runListSignature = signature;

  if (!runs.length) {
    const option = document.createElement("option");
    option.value = "";
    option.textContent = "No checkpoint runs";
    runSelectEl.replaceChildren(option);
    runSelectEl.disabled = true;
    return;
  }

  runSelectEl.replaceChildren(
    ...runs.map((run) => {
      const option = document.createElement("option");
      option.value = run.name;
      option.textContent = `${run.label} - ${fmt(run.highest_digits)} digits`;
      option.title = `${run.checkpoint_count} checkpoints`;
      option.selected = run.name === activeRun;
      option.disabled = run.config_available === false;
      return option;
    }),
  );
  runSelectEl.disabled = backendBusy;
  runSelectEl.title = "Choose a checkpoint folder and its stored input_config.json";
}

function renderCheckpoints(checkpoints, currentDigits) {
  if (!checkpoints.length) {
    const row = document.createElement("li");
    row.className = "checkpoint-empty";
    row.textContent = "No checkpoints";
    checkpointsEl.replaceChildren(row);
    selectedCheckpointDigits = null;
    checkpointListSignature = "";
    loadCheckpointButton.disabled = true;
    return;
  }

  const checkpointItems = checkpoints.map(checkpointInfo);
  const nextSignature = checkpointItems
    .map((checkpoint) => `${checkpoint.digits}:${checkpoint.filename}`)
    .join("|");
  if (
    selectedCheckpointDigits === null
    || !checkpointItems.some((checkpoint) => checkpoint.digits === selectedCheckpointDigits)
  ) {
    selectedCheckpointDigits = checkpointItems.some((checkpoint) => checkpoint.digits === Number(currentDigits))
      ? Number(currentDigits)
      : checkpointItems[checkpointItems.length - 1].digits;
  }
  loadCheckpointButton.disabled = backendBusy || selectedCheckpointDigits === null;

  if (nextSignature === checkpointListSignature && checkpointsEl.children.length === checkpointItems.length) {
    for (const row of checkpointsEl.children) {
      const digits = Number(row.dataset.digits);
      row.classList.toggle("is-current", digits === Number(currentDigits));
      row.classList.toggle("is-selected", digits === selectedCheckpointDigits);
    }
    return;
  }

  const scrollTop = checkpointsEl.scrollTop;
  checkpointsEl.replaceChildren(
    ...checkpointItems.map((checkpoint) => {
      const row = document.createElement("li");
      row.textContent = checkpoint.filename;
      row.title = checkpoint.filename;
      row.tabIndex = 0;
      row.dataset.digits = String(checkpoint.digits);
      row.classList.toggle("is-current", checkpoint.digits === Number(currentDigits));
      row.classList.toggle("is-selected", checkpoint.digits === selectedCheckpointDigits);
      row.addEventListener("click", () => {
        selectedCheckpointDigits = checkpoint.digits;
        renderCheckpoints(checkpoints, currentDigits);
      });
      row.addEventListener("keydown", (event) => {
        if (event.key !== "Enter" && event.key !== " ") {
          return;
        }
        event.preventDefault();
        selectedCheckpointDigits = checkpoint.digits;
        renderCheckpoints(checkpoints, currentDigits);
      });
      return row;
    }),
  );
  checkpointListSignature = nextSignature;
  checkpointsEl.scrollTop = scrollTop;
}

function checkpointInfo(checkpoint) {
  const digits = typeof checkpoint === "object" ? Number(checkpoint.digits) : Number(checkpoint);
  const filename = typeof checkpoint === "object"
    ? checkpoint.filename
    : `checkpoint_${digits}_digits.state`;
  return { digits, filename };
}

function renderTimeline(checkpoints, currentDigits, maxDigits) {
  if (!checkpoints.length) {
    const empty = document.createElement("div");
    empty.className = "timeline-empty";
    empty.textContent = "No checkpoints";
    timelineEl.replaceChildren(empty);
    return;
  }

  const checkpointItems = checkpoints.map(checkpointInfo);
  const highestCheckpointDigits = Math.max(...checkpointItems.map((checkpoint) => checkpoint.digits));
  const timelineMax = Math.max(
    Number(maxDigits) || 0,
    highestCheckpointDigits,
    1,
  );
  const track = document.createElement("div");
  const fill = document.createElement("span");
  const cursor = document.createElement("span");

  track.className = "timeline-track";
  fill.className = "timeline-fill";
  cursor.className = "timeline-cursor";

  fill.style.width = `${Math.min(100, (highestCheckpointDigits / timelineMax) * 100)}%`;
  cursor.style.left = `${Math.min(100, (Number(currentDigits) / timelineMax) * 100)}%`;
  track.title = `Checkpoint coverage: ${fmt(highestCheckpointDigits)} digits charted. Click to jump to the nearest checkpoint.`;
  track.addEventListener("click", (event) => {
    if (backendBusy || !checkpointItems.length) {
      return;
    }
    const rect = track.getBoundingClientRect();
    const ratio = Math.max(0, Math.min(1, (event.clientX - rect.left) / rect.width));
    const targetDigits = ratio * timelineMax;
    const nearest = checkpointItems.reduce((best, checkpoint) => {
      return Math.abs(checkpoint.digits - targetDigits) < Math.abs(best.digits - targetDigits) ? checkpoint : best;
    }, checkpointItems[0]);
    post("/api/jump", { digits: nearest.digits });
  });

  track.append(fill, cursor);
  timelineEl.replaceChildren(track);
}

function setInitialControls(state) {
  if (controlsInitialized) {
    return;
  }
  speedEl.value = state.speed_limiter_enabled === "off"
    ? speedEl.max
    : Math.log10(Math.max(0.1, Math.min(1000, Number(state.speed))));
  simulateTargetDigitsEl.value = String(Math.max(0, Number(state.max_digits) || 0));
  controlsInitialized = true;
}

function setStateClass(status) {
  const normalized = String(status).toLowerCase().replace(/[^a-z]+/g, "-");
  statusEl.dataset.state = normalized || "unknown";
  pauseEl.dataset.state = normalized || "unknown";
  const isPlaying = normalized === "running"
    || normalized === "pause-pending"
    || normalized.startsWith("fast-forwarding")
    || normalized.startsWith("rewinding")
    || normalized.startsWith("simulating")
    || normalized.startsWith("jumping")
    || normalized.startsWith("finding-next");
  pauseEl.textContent = isPlaying ? "⏸" : "▶";
  pauseEl.setAttribute("aria-label", isPlaying ? "Pause" : "Play");
  pauseEl.title = isPlaying ? "Pause" : "Play";
}

function renderStats(state) {
  romMissing = Boolean(state.rom_missing);
  const progress = state.max_digits > 0
    ? Math.min(100, (Number(state.digits_consumed) / Number(state.max_digits)) * 100)
    : 0;
  setStateClass(state.status);
  backendBusy = String(state.status).startsWith("fast forwarding")
    || String(state.status).startsWith("rewinding")
    || String(state.status).startsWith("simulating")
    || String(state.status).startsWith("jumping")
    || String(state.status).startsWith("finding next");
  screenShellEl.classList.toggle("is-rom-missing", romMissing);
  renderSeekOverlay(state);
  romUploadButtonEl.disabled = !romMissing || romUploadInFlight;
  if (romMissing && !romUploadInFlight) {
    romUploadStatusEl.textContent = "Pokemon Red ROM required";
  }
  statDigitsEl.textContent = `${fmt(state.digits_consumed)} / ${fmt(state.max_digits)}`;
  statLocationEl.textContent = state.location || "-";
  statLocationEl.title = state.map_id == null ? "" : `Map $${Number(state.map_id).toString(16).toUpperCase().padStart(2, "0")}`;
  statProgressEl.style.width = `${progress}%`;
  statSpeedEl.textContent = state.speed_limiter_enabled === "off" ? "Set Unlimited" : `Set ${speedLabel(state.speed)}`;
  statActualSpeedEl.textContent = actualSpeedLabel(state.actual_speed_x);
  statDigitRateEl.textContent = Number.isFinite(Number(state.actual_digits_per_second))
    ? digitRateValueLabel(state.actual_digits_per_second)
    : digitRateLabel(state.actual_speed_x, state.digits_per_input, state.frames_per_input);
  const audioUnavailable = state.speed_limiter_enabled === "off";
  const muted = audioUnavailable || Number(state.sound_volume ?? 100) <= 0;
  muteEl.dataset.audioUnavailable = audioUnavailable ? "true" : "false";
  muteEl.dataset.muted = muted ? "true" : "false";
  muteEl.textContent = muted ? "🔇" : "🔊";
  muteEl.setAttribute("aria-label", audioUnavailable ? "Enable limited speed for audio" : muted ? "Unmute audio" : "Mute audio");
  muteEl.title = audioUnavailable ? "Audio off at Unlimited speed. Click for 1x audio." : muted ? "Unmute" : "Mute";

  jumpButton.disabled = backendBusy;
  warpStateButton.disabled = backendBusy;
  simulateButton.disabled = backendBusy;
  stopSimulateButton.disabled = true;
  runSelectEl.disabled = backendBusy || !(state.runs || []).length;
  if (romMissing) {
    jumpButton.disabled = true;
    warpStateButton.disabled = true;
    simulateButton.disabled = true;
  }
  if (state.chart_simulation && state.chart_simulation.running) {
    const chart = state.chart_simulation;
    stopSimulateButton.disabled = false;
    setSimulatorStats({
      state: "Charting",
      progress: `${fmt(chart.digits_consumed || 0)} / ${fmt(chart.target_digits)}`,
      rate: Number(chart.digits_per_second) > 0 ? fmtRate(chart.digits_per_second) : "warming up",
      eta: Number(chart.digits_per_second) > 0 ? fmtDuration(chart.eta_seconds) : "-",
      title: chart.last_state || "Running in a separate headless process from review jumps",
    });
  } else if (String(state.status).startsWith("simulating")) {
    setSimulatorStats({ state: state.status });
  } else if (state.last_simulation && (Number(state.last_simulation.digits) > 0 || Number(state.last_simulation.skipped_digits) > 0)) {
    const simulatedDigits = Number(state.last_simulation.digits) || 0;
    const skippedDigits = Number(state.last_simulation.skipped_digits) || 0;
    let progressText = "-";
    if (simulatedDigits > 0) {
      progressText = `${fmt(simulatedDigits)} digits`;
    }
    if (skippedDigits > 0) {
      progressText = progressText === "-" ? `skipped ${fmt(skippedDigits)}` : `${progressText}, skipped ${fmt(skippedDigits)}`;
    }
    setSimulatorStats({
      state: "Complete",
      progress: progressText,
      rate: simulatedDigits > 0 ? fmtRate(state.last_simulation.digits_per_second) : "-",
      eta: "-",
      title: state.last_simulation.last_state || "",
    });
  } else {
    setSimulatorStats();
  }
}

async function refresh() {
  try {
    const response = await fetch("/api/state", { cache: "no-store" });
    const state = await response.json();
    setInitialControls(state);
    renderStats(state);
    renderRuns(state.runs || [], state.active_run || "");
    renderConfigInfo(state.config || {});
    renderCheckpoints(state.checkpoints || [], state.digits_consumed);
    renderTimeline(state.checkpoints || [], state.digits_consumed, state.max_digits);
    renderParty(state.party || []);
    renderBag(state.bag || []);
    renderPlayerInfo(state.player_info || {});
    renderBadges(state.badges || []);
  } catch (error) {
    setStateClass("disconnected");
    statDigitsEl.textContent = "-";
    statLocationEl.textContent = "-";
    statLocationEl.title = "";
    statProgressEl.style.width = "0";
    screenShellEl.classList.remove("is-seeking");
    seekLabelEl.textContent = "Seeking";
    seekProgressBarEl.style.width = "0%";
    statSpeedEl.textContent = "-";
    statActualSpeedEl.textContent = "-";
    statDigitRateEl.textContent = "-";
    muteEl.dataset.muted = "false";
    muteEl.dataset.audioUnavailable = "false";
    muteEl.textContent = "🔊";
    muteEl.setAttribute("aria-label", "Mute audio");
    muteEl.title = "Mute";
    renderRuns([], "");
    renderConfigInfo({});
    renderCheckpoints([], 0);
    renderTimeline([], 0, 0);
    renderParty([]);
    renderBag([]);
    renderPlayerInfo({});
    renderBadges([]);
    renderInputs([]);
  } finally {
    setTimeout(refresh, STATE_REFRESH_MS);
  }
}

async function refreshInputs() {
  const now = performance.now();
  if (!inputFetchInFlight && now - lastInputFetchAt >= INPUT_REFRESH_MS) {
    lastInputFetchAt = now;
    inputFetchInFlight = true;
    try {
      const response = await fetch("/api/inputs", { cache: "no-store" });
      const state = await response.json();
      renderInputs(state.inputs || [], state);
    } catch (error) {
      renderInputs([]);
    } finally {
      inputFetchInFlight = false;
    }
  }
  requestAnimationFrame(refreshInputs);
}

async function drawFrameLoop() {
  if (!romMissing && !backendBusy && !frameFetchInFlight) {
    frameFetchInFlight = true;
    try {
      const response = await fetch("/api/frame.rgba", { cache: "no-store" });
      const buffer = await response.arrayBuffer();
      if (buffer.byteLength === FRAME_BYTES) {
        renderer.draw(new Uint8Array(buffer));
      }
    } catch (error) {
      console.warn("Frame fetch failed.", error);
    } finally {
      frameFetchInFlight = false;
    }
  }
  requestAnimationFrame(drawFrameLoop);
}

refresh();
refreshInputs();
drawFrameLoop();
