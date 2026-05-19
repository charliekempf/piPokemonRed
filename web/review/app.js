const screen = document.querySelector("#screen");
const statusEl = document.querySelector("#status");
const statDigitsEl = document.querySelector("#stat-digits");
const statProgressEl = document.querySelector("#stat-progress span");
const statLocationEl = document.querySelector("#stat-location");
const statSpeedEl = document.querySelector("#stat-speed");
const statActualSpeedEl = document.querySelector("#stat-actual-speed");
const statVolumeEl = document.querySelector("#stat-volume");
const screenShellEl = document.querySelector(".screen-shell");
const seekLabelEl = document.querySelector("#seek-label");
const seekProgressBarEl = document.querySelector("#seek-progress-bar");
const romMissingPanelEl = document.querySelector("#rom-missing-panel");
const romUploadEl = document.querySelector("#rom-upload");
const romUploadButtonEl = document.querySelector("#rom-upload-button");
const romUploadStatusEl = document.querySelector("#rom-upload-status");
const speedEl = document.querySelector("#speed");
const volumeEl = document.querySelector("#volume");
const pauseEl = document.querySelector("#pause");
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
const simulateStatusEl = document.querySelector("#simulate-status");
const checkpointsEl = document.querySelector("#checkpoints");
const loadCheckpointButton = document.querySelector("#load-checkpoint-button");
const timelineEl = document.querySelector("#timeline");
const partyEl = document.querySelector("#party");
const badgesPanelEl = document.querySelector("#badges-panel");
const badgesToggleEl = document.querySelector("#badges-toggle");
const badgesCountEl = document.querySelector("#badges-count");
const badgesEl = document.querySelector("#badges");
const inputsEl = document.querySelector("#inputs");

const FRAME_WIDTH = 160;
const FRAME_HEIGHT = 144;
const FRAME_BYTES = FRAME_WIDTH * FRAME_HEIGHT * 4;

let frameFetchInFlight = false;
let controlsInitialized = false;
let backendBusy = false;
let romMissing = false;
let romUploadInFlight = false;
let selectedCheckpointDigits = null;
let checkpointListSignature = "";
let partyRenderSignature = "";
let lastPartyMembers = [];
let badgesExpanded = false;
const expandedPartySlots = new Set();

function speedSliderIsUnlimited() {
  return Number(speedEl.value) >= Number(speedEl.max);
}

function speedFromSlider() {
  return speedSliderIsUnlimited() ? 1000 : Math.max(1, Math.min(1000, Math.round(10 ** Number(speedEl.value))));
}

function speedLabelFromSlider() {
  return speedSliderIsUnlimited() ? "Unlimited" : `${speedFromSlider()}x`;
}

function actualSpeedLabel(value) {
  const speed = Math.max(0, Number(value) || 0);
  const precision = speed > 0 && speed < 10 ? 1 : 0;
  return `Actual ${speed.toFixed(precision)}x`;
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
  await fetch(path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
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
  statSpeedEl.textContent = `Set ${speedLabelFromSlider()}`;
  post("/api/speed", { speed: speedFromSlider() });
  post("/api/limiter", { enabled: !speedSliderIsUnlimited() });
});

volumeEl.addEventListener("input", () => {
  const volume = Math.max(0, Math.min(100, Math.round(Number(volumeEl.value))));
  statVolumeEl.textContent = `${volume}%`;
  post("/api/volume", { volume });
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

badgesToggleEl.addEventListener("click", () => {
  badgesExpanded = !badgesExpanded;
  badgesPanelEl.classList.toggle("is-collapsed", !badgesExpanded);
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
  return `${fmt(Math.round(rate))}/s`;
}

function renderInputs(items) {
  if (!items.length) {
    const row = document.createElement("li");
    const title = document.createElement("span");
    const detail = document.createElement("span");
    row.className = "empty";
    title.textContent = "Out of digits";
    detail.textContent = "Download more";
    row.append(title, detail);
    inputsEl.replaceChildren(row);
    return;
  }

  inputsEl.replaceChildren(
    ...items.map((item) => {
      const row = document.createElement("li");
      const pair = document.createElement("span");
      const button = document.createElement("span");
      row.className = item.role || "future";
      pair.className = "pair";
      button.className = "button";
      pair.textContent = `${fmt(item.digit_index)}  ${item.pair}`;
      button.textContent = item.button.toUpperCase();
      row.append(pair, button);
      return row;
    }),
  );
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
    : `checkpoint_${String(digits).padStart(8, "0")}_digits.state`;
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
  const timelineMax = Math.max(
    Number(maxDigits) || 0,
    ...checkpointItems.map((checkpoint) => checkpoint.digits),
  );
  const track = document.createElement("div");
  const fill = document.createElement("span");
  const cursor = document.createElement("span");
  const markers = document.createElement("ol");

  track.className = "timeline-track";
  fill.className = "timeline-fill";
  cursor.className = "timeline-cursor";
  markers.className = "timeline-markers";

  fill.style.width = `${Math.min(100, (Number(currentDigits) / timelineMax) * 100)}%`;
  cursor.style.left = `${Math.min(100, (Number(currentDigits) / timelineMax) * 100)}%`;

  markers.replaceChildren(
    ...checkpointItems.map((checkpoint) => {
      const item = document.createElement("li");
      const marker = document.createElement("button");
      const position = timelineMax > 0 ? Math.min(100, (checkpoint.digits / timelineMax) * 100) : 0;
      const isCurrent = Number(checkpoint.digits) === Number(currentDigits);

      item.style.left = `${position}%`;
      marker.type = "button";
      marker.className = isCurrent ? "is-current" : "";
      marker.dataset.digits = String(checkpoint.digits);
      marker.title = `${checkpoint.filename} (${fmt(checkpoint.digits)} digits)`;
      marker.setAttribute("aria-label", `Jump to ${checkpoint.filename}`);
      marker.disabled = backendBusy;
      marker.addEventListener("click", () => {
        post("/api/jump", { digits: checkpoint.digits });
      });
      item.append(marker);
      return item;
    }),
  );

  track.append(fill, cursor, markers);
  timelineEl.replaceChildren(track);
}

function setInitialControls(state) {
  if (controlsInitialized) {
    return;
  }
  speedEl.value = state.speed_limiter_enabled === "off"
    ? speedEl.max
    : Math.log10(Math.max(1, Math.min(1000, Number(state.speed))));
  volumeEl.value = String(Math.max(0, Math.min(100, Number(state.sound_volume ?? 100))));
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
  statSpeedEl.textContent = state.speed_limiter_enabled === "off" ? "Set Unlimited" : `Set ${state.speed}x`;
  statActualSpeedEl.textContent = actualSpeedLabel(state.actual_speed_x);
  statVolumeEl.textContent = `${Math.max(0, Math.min(100, Number(state.sound_volume ?? 100)))}%`;

  jumpButton.disabled = backendBusy;
  warpStateButton.disabled = backendBusy;
  simulateButton.disabled = backendBusy;
  if (romMissing) {
    jumpButton.disabled = true;
    warpStateButton.disabled = true;
    simulateButton.disabled = true;
  }
  if (state.chart_simulation && state.chart_simulation.running) {
    simulateStatusEl.textContent = `charting to ${fmt(state.chart_simulation.target_digits)} digits`;
    simulateStatusEl.title = "Running in a separate headless process from review jumps";
  } else if (String(state.status).startsWith("simulating")) {
    simulateStatusEl.textContent = state.status;
    simulateStatusEl.title = "";
  } else if (state.last_simulation && (Number(state.last_simulation.digits) > 0 || Number(state.last_simulation.skipped_digits) > 0)) {
    const simulatedDigits = Number(state.last_simulation.digits) || 0;
    const skippedDigits = Number(state.last_simulation.skipped_digits) || 0;
    const parts = [];
    if (simulatedDigits > 0) {
      parts.push(`${fmt(simulatedDigits)} digits`);
      parts.push(fmtRate(state.last_simulation.digits_per_second));
    }
    if (skippedDigits > 0) {
      parts.push(`skipped ${fmt(skippedDigits)}`);
    }
    simulateStatusEl.textContent = parts.join(", ");
    simulateStatusEl.title = state.last_simulation.last_state || "";
  } else {
    simulateStatusEl.textContent = "Ready";
    simulateStatusEl.title = "";
  }
}

async function refresh() {
  try {
    const response = await fetch("/api/state", { cache: "no-store" });
    const state = await response.json();
    setInitialControls(state);
    renderStats(state);
    renderCheckpoints(state.checkpoints || [], state.digits_consumed);
    renderTimeline(state.checkpoints || [], state.digits_consumed, state.max_digits);
    renderParty(state.party || []);
    renderBadges(state.badges || []);
    renderInputs(state.inputs || []);
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
    statVolumeEl.textContent = "-";
    renderCheckpoints([], 0);
    renderTimeline([], 0, 0);
    renderParty([]);
    renderBadges([]);
    renderInputs([]);
  } finally {
    setTimeout(refresh, 150);
  }
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
drawFrameLoop();
