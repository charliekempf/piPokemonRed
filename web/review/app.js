const screen = document.querySelector("#screen");
const statusEl = document.querySelector("#status");
const statStateEl = document.querySelector("#stat-state");
const statDigitsEl = document.querySelector("#stat-digits");
const statProgressEl = document.querySelector("#stat-progress span");
const statSpeedEl = document.querySelector("#stat-speed");
const statLimiterEl = document.querySelector("#stat-limiter");
const statRendererEl = document.querySelector("#stat-renderer");
const statInputsEl = document.querySelector("#stat-inputs");
const statLastEl = document.querySelector("#stat-last");
const statSnapshotsEl = document.querySelector("#stat-snapshots");
const screenShellEl = document.querySelector(".screen-shell");
const speedEl = document.querySelector("#speed");
const limiterEl = document.querySelector("#limiter");
const pauseEl = document.querySelector("#pause");
const rewindEl = document.querySelector("#rewind");
const rewindButton = document.querySelector("#rewind-button");
const fastForwardButton = document.querySelector("#fast-forward-button");
const upcomingEl = document.querySelector("#upcoming");

const FRAME_WIDTH = 160;
const FRAME_HEIGHT = 144;
const FRAME_BYTES = FRAME_WIDTH * FRAME_HEIGHT * 4;

let frameFetchInFlight = false;
let controlsInitialized = false;
let fastForwarding = false;

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

function fmt(value) {
  return Number(value).toLocaleString();
}

function renderUpcoming(items) {
  if (!items.length) {
    const row = document.createElement("li");
    const title = document.createElement("span");
    const detail = document.createElement("span");
    row.className = "empty";
    title.textContent = "Out of digits";
    detail.textContent = "Download more";
    row.append(title, detail);
    upcomingEl.replaceChildren(row);
    return;
  }

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
}

function displayState(status) {
  const value = String(status);
  if (value.startsWith("fast forwarding")) {
    return "Fast-forward";
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
  fastForwarding = String(state.status).startsWith("fast forwarding");
  screenShellEl.classList.toggle("is-fast-forwarding", fastForwarding);
  statStateEl.textContent = displayState(state.status);
  statStateEl.title = state.status;
  statDigitsEl.textContent = `${fmt(state.digits_consumed)} / ${fmt(state.max_digits)}`;
  statProgressEl.style.width = `${progress}%`;
  statSpeedEl.textContent = `${state.speed}x`;
  statLimiterEl.textContent = state.speed_limiter_enabled;
  statRendererEl.textContent = renderer.mode;
  statInputsEl.textContent = fmt(state.inputs_sent);
  statLastEl.textContent = String(state.last_button).toUpperCase();
  statSnapshotsEl.textContent = fmt(state.snapshots);
}

async function refresh() {
  try {
    const response = await fetch("/api/state", { cache: "no-store" });
    const state = await response.json();
    setInitialControls(state);
    renderStats(state);
    renderUpcoming(state.upcoming);
  } catch (error) {
    setStateClass("disconnected");
    statStateEl.textContent = "Disconnected";
    statDigitsEl.textContent = "-";
    statProgressEl.style.width = "0";
    statSpeedEl.textContent = "-";
    statLimiterEl.textContent = "-";
    statRendererEl.textContent = renderer.mode;
    statInputsEl.textContent = "-";
    statLastEl.textContent = "-";
    statSnapshotsEl.textContent = "-";
  } finally {
    setTimeout(refresh, 150);
  }
}

async function drawFrameLoop() {
  if (!fastForwarding && !frameFetchInFlight) {
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
