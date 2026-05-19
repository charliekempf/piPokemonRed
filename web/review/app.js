const screen = document.querySelector("#screen");
const statusEl = document.querySelector("#status");
const statDigitsEl = document.querySelector("#stat-digits");
const statProgressEl = document.querySelector("#stat-progress span");
const statSpeedEl = document.querySelector("#stat-speed");
const statLimiterEl = document.querySelector("#stat-limiter");
const statRendererEl = document.querySelector("#stat-renderer");
const screenShellEl = document.querySelector(".screen-shell");
const speedEl = document.querySelector("#speed");
const limiterEl = document.querySelector("#limiter");
const pauseEl = document.querySelector("#pause");
const rewindEl = document.querySelector("#rewind");
const rewindButton = document.querySelector("#rewind-button");
const fastForwardButton = document.querySelector("#fast-forward-button");
const jumpDigitsEl = document.querySelector("#jump-digits");
const jumpButton = document.querySelector("#jump-button");
const warpStateEl = document.querySelector("#warp-state");
const warpStateButton = document.querySelector("#warp-state-button");
const simulateEl = document.querySelector("#simulate-digits");
const simulateButton = document.querySelector("#simulate-button");
const simulateStatusEl = document.querySelector("#simulate-status");
const checkpointsEl = document.querySelector("#checkpoints");
const partyEl = document.querySelector("#party");
const inputsEl = document.querySelector("#inputs");

const FRAME_WIDTH = 160;
const FRAME_HEIGHT = 144;
const FRAME_BYTES = FRAME_WIDTH * FRAME_HEIGHT * 4;

let frameFetchInFlight = false;
let controlsInitialized = false;
let backendBusy = false;

function speedFromSlider() {
  return Math.max(1, Math.min(1000, Math.round(10 ** Number(speedEl.value))));
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

fastForwardButton.addEventListener("click", () => {
  post("/api/fast-forward", { digits: Number(rewindEl.value) });
});

jumpButton.addEventListener("click", () => {
  const digits = Math.max(0, Number(String(jumpDigitsEl.value).replaceAll(",", "")) || 0);
  post("/api/jump", { digits });
});

warpStateButton.addEventListener("click", () => {
  post("/api/warp-state", { state: warpStateEl.value });
});

simulateButton.addEventListener("click", () => {
  post("/api/simulate", { digits: Number(simulateEl.value) });
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
      const badge = document.createElement("span");
      const body = document.createElement("div");
      const top = document.createElement("div");
      const name = document.createElement("strong");
      const level = document.createElement("span");
      const lower = document.createElement("div");
      const hpWrap = document.createElement("span");
      const hpBar = document.createElement("span");
      const hpText = document.createElement("span");
      const status = document.createElement("span");
      const hp = Math.max(0, Number(member.hp));
      const maxHp = Math.max(0, Number(member.max_hp));
      const hpPercent = maxHp > 0 ? Math.min(100, (hp / maxHp) * 100) : 0;

      row.className = "party-member";
      badge.className = "party-badge";
      body.className = "party-body";
      top.className = "party-top";
      lower.className = "party-lower";
      hpWrap.className = "hp-wrap";
      hpBar.className = "hp-bar";
      hpText.className = "hp-text";
      status.className = "party-status";

      badge.textContent = String(member.slot);
      name.textContent = member.name || `MON ${member.species}`;
      level.textContent = `Lv ${member.level || "-"}`;
      hpBar.style.width = `${hpPercent}%`;
      hpText.textContent = maxHp > 0 ? `${fmt(hp)} / ${fmt(maxHp)}` : "- / -";
      status.textContent = member.status || "OK";
      status.dataset.status = String(member.status || "OK").toLowerCase();

      hpWrap.append(hpBar);
      top.append(name, level);
      lower.append(hpWrap, hpText, status);
      body.append(top, lower);
      row.append(badge, body);
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
    return;
  }

  checkpointsEl.replaceChildren(
    ...checkpoints.map((digits) => {
      const row = document.createElement("li");
      const button = document.createElement("button");
      button.type = "button";
      button.textContent = fmt(digits);
      button.dataset.digits = String(digits);
      button.className = Number(digits) === Number(currentDigits) ? "is-current" : "";
      button.disabled = backendBusy;
      button.addEventListener("click", () => {
        post("/api/jump", { digits: Number(button.dataset.digits) });
      });
      row.append(button);
      return row;
    }),
  );
}

function setInitialControls(state) {
  if (controlsInitialized) {
    return;
  }
  speedEl.value = Math.log10(Math.max(1, Math.min(1000, Number(state.speed))));
  limiterEl.checked = state.speed_limiter_enabled === "on";
  controlsInitialized = true;
}

function setStateClass(status) {
  const normalized = String(status).toLowerCase().replace(/[^a-z]+/g, "-");
  statusEl.dataset.state = normalized || "unknown";
  pauseEl.dataset.state = normalized || "unknown";
}

function displayState(status) {
  const value = String(status);
  if (value.startsWith("fast forwarding")) {
    return "Fast-forward";
  }
  if (value.startsWith("simulating")) {
    return "Simulating";
  }
  if (value.startsWith("jumping")) {
    return "Jumping";
  }
  if (value.startsWith("finding next")) {
    return value.replace("finding next ", "Finding ");
  }
  if (value.startsWith("rewound")) {
    return "Rewound";
  }
  return value.charAt(0).toUpperCase() + value.slice(1);
}

function renderStats(state) {
  const progress = state.max_digits > 0
    ? Math.min(100, (Number(state.digits_consumed) / Number(state.max_digits)) * 100)
    : 0;
  setStateClass(state.status);
  backendBusy = String(state.status).startsWith("fast forwarding")
    || String(state.status).startsWith("simulating")
    || String(state.status).startsWith("jumping")
    || String(state.status).startsWith("finding next");
  screenShellEl.classList.toggle("is-fast-forwarding", backendBusy);
  statDigitsEl.textContent = `${fmt(state.digits_consumed)} / ${fmt(state.max_digits)}`;
  statProgressEl.style.width = `${progress}%`;
  statSpeedEl.textContent = `${state.speed}x`;
  statLimiterEl.textContent = state.speed_limiter_enabled;
  statRendererEl.textContent = renderer.mode;

  jumpButton.disabled = backendBusy;
  warpStateButton.disabled = backendBusy;
  simulateButton.disabled = backendBusy;
  if (String(state.status).startsWith("simulating")) {
    simulateStatusEl.textContent = state.status;
  } else if (state.last_simulation && Number(state.last_simulation.digits) > 0) {
    simulateStatusEl.textContent = `${fmt(state.last_simulation.digits)} digits, ${fmtRate(state.last_simulation.digits_per_second)}`;
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
    renderParty(state.party || []);
    renderInputs(state.inputs || []);
  } catch (error) {
    setStateClass("disconnected");
    statDigitsEl.textContent = "-";
    statProgressEl.style.width = "0";
    statSpeedEl.textContent = "-";
    statLimiterEl.textContent = "-";
    statRendererEl.textContent = renderer.mode;
    renderCheckpoints([], 0);
    renderParty([]);
    renderInputs([]);
  } finally {
    setTimeout(refresh, 150);
  }
}

async function drawFrameLoop() {
  if (!backendBusy && !frameFetchInFlight) {
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
