const frame = document.querySelector("#camera-frame");
const frameEmpty = document.querySelector("#frame-empty");
const badge = document.querySelector("#connection-badge");
const cameraDevice = document.querySelector("#camera-device");
const refreshCamerasButton = document.querySelector("#refresh-cameras-button");
const applyCameraButton = document.querySelector("#apply-camera-button");
const recenterButton = document.querySelector("#recenter-button");
const eventLog = document.querySelector("#event-log");
const runtimeConfigForm = document.querySelector("#runtime-config-form");
const runtimeConfigFields = document.querySelector("#runtime-config-fields");
const reloadConfigButton = document.querySelector("#reload-config-button");
const applyConfigButton = document.querySelector("#apply-config-button");
const configFeedback = document.querySelector("#config-feedback");

const fields = {
  cameraMode: document.querySelector("#camera-mode"),
  mode: document.querySelector("#mode-value"),
  fps: document.querySelector("#fps-value"),
  track: document.querySelector("#track-value"),
  bbox: document.querySelector("#bbox-value"),
  people: document.querySelector("#people-value"),
  center: document.querySelector("#center-value"),
  distance: document.querySelector("#distance-value"),
  position: document.querySelector("#position-value"),
  colors: document.querySelector("#colors-value"),
  leftServo: document.querySelector("#left-servo-value"),
  rightServo: document.querySelector("#right-servo-value"),
  trackingSource: document.querySelector("#tracking-source-value"),
  audioActive: document.querySelector("#audio-active-value"),
  audioPlaying: document.querySelector("#audio-playing-value"),
  audioLast: document.querySelector("#audio-last-value"),
  audioError: document.querySelector("#audio-error-value"),
  lightRegion: document.querySelector("#light-region-value"),
  lightLeft: document.querySelector("#light-left-value"),
  lightRight: document.querySelector("#light-right-value"),
  lightLeftLeds: document.querySelector("#light-left-leds-value"),
  lightRightLeds: document.querySelector("#light-right-leds-value"),
  serialState: document.querySelector("#serial-state-value"),
  serialPort: document.querySelector("#serial-port-value"),
  serialTx: document.querySelector("#serial-tx-value"),
  serialRx: document.querySelector("#serial-rx-value"),
  serialError: document.querySelector("#serial-error-value"),
  ram: document.querySelector("#ram-value"),
  gpu: document.querySelector("#gpu-value"),
  personRuntime: document.querySelector("#person-runtime-value"),
};

let hasLoadedCameras = false;
let hasPendingCameraSelection = false;
let frameSocket = null;
let frameWatchdogTimer = null;
let currentFrameUrl = null;
let isMjpegFallbackActive = false;
let statusSocket = null;
let statusReconnectTimer = null;
let configCatalog = [];
let configGroups = {};
let editableConfigKeys = new Set();
let configValues = {};

const audioStateOrder = ["no_one", "left", "center", "right", "full"];
const audioStateLabels = {
  no_one: "1-無人",
  left: "2-左",
  center: "3-中",
  right: "4-右",
  full: "5-全",
};
const lightRegionOrder = ["no_one", "left", "right", "full"];
const lightRegionLabels = {
  no_one: "1-無人",
  left: "2-左",
  right: "3-右",
  left_right: "2-左, 3-右",
  full: "4-全",
};
const lightSideStateLabels = {
  empty: "無人",
  present: "有人",
  super_close: "超近",
};

function text(value, fallback = "-") {
  if (value === null || value === undefined || value === "") {
    return fallback;
  }
  return String(value);
}

function fixed(value, digits = 2) {
  if (typeof value !== "number" || Number.isNaN(value)) {
    return "-";
  }
  return value.toFixed(digits);
}

function percent(value) {
  if (typeof value !== "number" || Number.isNaN(value)) {
    return "-";
  }
  return `${(value * 100).toFixed(1)}%`;
}

function orderedLabels(values, order, labels) {
  if (!Array.isArray(values) || !values.length) {
    return "-";
  }
  const unique = new Set(values.filter(Boolean));
  return order
    .filter((key) => unique.has(key))
    .concat([...unique].filter((key) => !order.includes(key)))
    .map((key) => labels[key] || key)
    .join(", ");
}

function updateZoneMap(mapId, activeStates, playingStates = []) {
  const root = document.querySelector(`#${mapId}`);
  if (!root) {
    return;
  }
  const active = new Set(activeStates || []);
  const playing = new Set(playingStates || []);
  for (const item of root.querySelectorAll("[data-zone]")) {
    const zone = item.dataset.zone;
    item.classList.toggle("active", active.has(zone));
    item.classList.toggle("playing", playing.has(zone));
  }
}

function normalizeAudioStates(audio) {
  if (Array.isArray(audio.active_states) && audio.active_states.length) {
    return audio.active_states;
  }
  if (typeof audio.current_state === "string" && audio.current_state) {
    return audio.current_state.split(",").map((item) => item.trim()).filter(Boolean);
  }
  return ["no_one"];
}

function lightSideLabel(side) {
  if (!side) {
    return "-";
  }
  const state = lightSideStateLabels[side.state] || text(side.state);
  const brightness = `${fixed(side.brightness_pct, 1)}%`;
  const cycle = side.solid ? "solid" : `${fixed(side.cycle_sec, 2)}s`;
  return `${state} / ${brightness} / ${cycle}`;
}

function clamp(value, min, max) {
  if (typeof value !== "number" || Number.isNaN(value)) {
    return min;
  }
  return Math.min(Math.max(value, min), max);
}

function lerp(start, end, amount) {
  return start + (end - start) * amount;
}

function ledColorForLevel(levelPct) {
  const level = clamp(levelPct, 0, 100) / 100;
  const off = [244, 247, 251];
  const on = [119, 194, 109];
  return `rgb(${off.map((channel, index) => Math.round(lerp(channel, on[index], level))).join(", ")})`;
}

function renderLedGrid(container, values, totalCount = 15) {
  if (!container) {
    return;
  }
  const levels = Array.isArray(values) ? values : [];
  const cells = [];
  for (let index = 0; index < totalCount; index += 1) {
    const level = clamp(Number(levels[index] || 0), 0, 100);
    const cell = document.createElement("span");
    cell.className = "led-cell";
    cell.classList.toggle("on", level > 0);
    cell.style.backgroundColor = ledColorForLevel(level);
    cell.style.boxShadow = level > 0 ? `0 0 ${Math.max(2, level / 9).toFixed(1)}px rgba(119, 194, 109, ${Math.max(0.15, level / 100).toFixed(2)})` : "";
    cell.textContent = String(index + 1);
    cell.title = `LED ${index + 1}: ${level.toFixed(1)}%`;
    cells.push(cell);
  }
  container.replaceChildren(...cells);
}

function runtimeLabel(runtime) {
  if (!runtime) {
    return "-";
  }
  const backend = runtime.backend || "unknown";
  const device = runtime.effective_device || runtime.requested_mode || "unknown";
  return `${backend} / ${device}`;
}

function gpuLabel(stats) {
  if (!stats || !stats.gpu_device) {
    return "-";
  }
  const name = stats.gpu_name || stats.gpu_device;
  const reserved = fixed(stats.gpu_memory_reserved_mb, 1);
  const allocated = fixed(stats.gpu_memory_allocated_mb, 1);
  if (typeof stats.gpu_memory_total_mb === "number") {
    return `${name}: ${reserved} / ${fixed(stats.gpu_memory_total_mb, 0)} MB reserved (${allocated} MB active)`;
  }
  if (typeof stats.gpu_memory_reserved_mb === "number") {
    return `${name}: ${reserved} MB reserved (${allocated} MB active)`;
  }
  return `${name}: memory unavailable`;
}

function cameraLabel(camera) {
  const deviceName = camera.device_name || "Camera";
  const deviceId = camera.device_id || "default";
  const modes = Array.isArray(camera.modes) ? camera.modes : [];
  const preferredMode = modes[0];
  if (!preferredMode) {
    return `${deviceName} (${deviceId})`;
  }
  return `${deviceName} (${deviceId}) - ${preferredMode.width}x${preferredMode.height}@${preferredMode.fps}`;
}

function ensureCameraOption(deviceId, label = null) {
  if (!deviceId) {
    return;
  }
  if (Array.from(cameraDevice.options).some((option) => option.value === deviceId)) {
    return;
  }
  const option = document.createElement("option");
  option.value = deviceId;
  option.textContent = label || `Current camera (${deviceId})`;
  cameraDevice.append(option);
}

function setCameraOptions(cameras, selectedDeviceId = "default") {
  const options = cameras.map((camera) => {
    const option = document.createElement("option");
    option.value = camera.device_id || "default";
    option.textContent = cameraLabel(camera);
    return option;
  });

  if (!options.length) {
    const fallback = document.createElement("option");
    fallback.value = "default";
    fallback.textContent = "Default camera";
    options.push(fallback);
  }

  cameraDevice.replaceChildren(...options);
  ensureCameraOption(selectedDeviceId);
  cameraDevice.value = selectedDeviceId || "default";
}

async function refreshCameraList(selectedDeviceId = cameraDevice.value || "default") {
  refreshCamerasButton.disabled = true;
  refreshCamerasButton.textContent = "Refreshing";
  try {
    const response = await fetch("/api/cameras", { cache: "no-store" });
    if (!response.ok) {
      throw new Error(`cameras ${response.status}`);
    }
    const cameras = await response.json();
    setCameraOptions(Array.isArray(cameras) ? cameras : [], selectedDeviceId);
    hasLoadedCameras = true;
  } catch (error) {
    ensureCameraOption(selectedDeviceId || "default", "Default camera");
    cameraDevice.value = selectedDeviceId || "default";
    setBadge("error", "camera scan failed");
  } finally {
    refreshCamerasButton.disabled = false;
    refreshCamerasButton.textContent = "Refresh";
  }
}

function setBadge(kind, label) {
  badge.className = `status-badge ${kind}`;
  badge.textContent = label;
}

function updateStatus(status) {
  const audience = status.audience || {};
  const servo = status.servo || {};
  const serial = status.serial_monitor || {};
  const stats = status.stats || {};
  const audio = status.position_audio || {};
  const light = status.light || {};
  const cameraDeviceId = status.camera_device_id || "default";
  const activeAudioStates = normalizeAudioStates(audio);
  const playingAudioStates = Array.isArray(audio.playing_states) ? audio.playing_states : [];

  fields.cameraMode.textContent = `${text(status.camera_device_id)} / ${text(status.camera_mode)}`;
  if (hasLoadedCameras && !hasPendingCameraSelection) {
    ensureCameraOption(cameraDeviceId);
    cameraDevice.value = cameraDeviceId;
  }
  fields.mode.textContent = text(status.mode, "IDLE");
  fields.fps.textContent = `${fixed(status.yolo_detect_fps, 1)} fps`;
  fields.track.textContent = `track ${text(audience.track_id)}`;
  fields.bbox.textContent = audience.person_bbox ? audience.person_bbox.join(", ") : "-";
  fields.people.textContent = typeof audience.person_count === "number" ? String(audience.person_count) : "-";
  fields.center.textContent = `${fixed(audience.center_x_norm, 3)}, ${fixed(audience.center_y_norm, 3)}`;
  fields.distance.textContent = `${text(audience.distance_class)} (${percent(audience.bbox_area_ratio)})`;
  fields.position.textContent = `${text(audience.position_state)} / ${text(audience.horizontal_class)}`;
  fields.colors.textContent = `${text(audience.top_color)} / ${text(audience.bottom_color)}`;
  fields.leftServo.textContent = `${fixed(servo.left_deg, 1)} deg`;
  fields.rightServo.textContent = `${fixed(servo.right_deg, 1)} deg`;
  fields.trackingSource.textContent = text(servo.tracking_source);
  fields.audioActive.textContent = orderedLabels(activeAudioStates, audioStateOrder, audioStateLabels);
  fields.audioPlaying.textContent = orderedLabels(playingAudioStates, audioStateOrder, audioStateLabels);
  fields.audioLast.textContent = audio.last_triggered_state
    ? `${audioStateLabels[audio.last_triggered_state] || audio.last_triggered_state} / ${text(audio.last_audio_file)}`
    : "-";
  fields.audioError.textContent = text(audio.last_error);
  updateZoneMap("audio-zone-map", activeAudioStates, playingAudioStates);
  fields.lightRegion.textContent = lightRegionLabels[light.region] || text(light.region);
  fields.lightLeft.textContent = lightSideLabel(light.left);
  fields.lightRight.textContent = lightSideLabel(light.right);
  const ledValues = Array.isArray(light.led_values_pct) ? light.led_values_pct : [];
  const sideLedCount = Math.max(15, Math.ceil(ledValues.length / 2));
  const leftLedValues = ledValues.slice(0, sideLedCount);
  const rightLedValues = ledValues.slice(sideLedCount, sideLedCount * 2);
  renderLedGrid(fields.lightLeftLeds, leftLedValues, sideLedCount);
  renderLedGrid(fields.lightRightLeds, rightLedValues, sideLedCount);
  const lightActiveZones = light.region === "left_right" ? ["left", "right"] : [light.region || "no_one"];
  updateZoneMap("light-zone-map", lightActiveZones);
  fields.serialState.textContent = status.serial_connected ? "connected" : "offline";
  fields.serialPort.textContent = text(serial.port);
  fields.serialTx.textContent = text(serial.last_tx);
  fields.serialRx.textContent = text(serial.last_rx);
  fields.serialError.textContent = text(serial.last_error);
  fields.ram.textContent = `${fixed(stats.memory_rss_mb, 1)} MB`;
  fields.gpu.textContent = gpuLabel(stats);
  fields.personRuntime.textContent = runtimeLabel(status.yolo_person_runtime);

  eventLog.replaceChildren(
    ...(status.event_log || []).slice(0, 6).map((entry) => {
      const item = document.createElement("li");
      item.textContent = entry;
      return item;
    }),
  );

  setBadge("ready", status.serial_connected ? "ready" : "monitoring");
}

async function refreshStatus() {
  try {
    const response = await fetch("/api/status", { cache: "no-store" });
    if (!response.ok) {
      throw new Error(`status ${response.status}`);
    }
    updateStatus(await response.json());
  } catch (error) {
    setBadge("error", "offline");
  }
}

function parseConfigValue(field, input) {
  if (field.type === "boolean") {
    return input.checked;
  }
  if (input.value === "" && field.value === null) {
    return null;
  }
  if (field.type === "int") {
    return Number.parseInt(input.value, 10);
  }
  if (field.type === "float") {
    return Number.parseFloat(input.value);
  }
  return input.value;
}

function createConfigControl(field) {
  if (field.enum && field.enum.length) {
    const select = document.createElement("select");
    select.name = field.key;
    for (const value of field.enum) {
      const option = document.createElement("option");
      option.value = value;
      option.textContent = configOptionLabel(field, value);
      select.append(option);
    }
    select.value = field.value ?? field.default ?? "";
    return select;
  }
  const input = document.createElement("input");
  input.name = field.key;
  if (field.type === "boolean") {
    input.type = "checkbox";
    input.checked = Boolean(field.value);
    return input;
  }
  input.type = field.type === "int" || field.type === "float" ? "number" : "text";
  if (field.type === "float") {
    input.step = "0.001";
  }
  if (field.type === "int") {
    input.step = "1";
  }
  input.value = field.value ?? "";
  return input;
}

const configOptionLabels = {
  "camera.source": {
    browser: "瀏覽器",
    backend: "後端攝影機",
  },
  "yolo.device_mode": {
    auto: "auto",
    cpu: "CPU",
    gpu: "GPU",
    mps: "MPS",
  },
};

function configOptionLabel(field, value) {
  return configOptionLabels[field.key]?.[value] || value;
}

function renderRuntimeConfig() {
  runtimeConfigFields.replaceChildren();
  const fieldsByGroup = new Map();
  for (const field of configCatalog) {
    if (!editableConfigKeys.has(field.key)) {
      continue;
    }
    const group = field.applies_to || "general";
    if (!fieldsByGroup.has(group)) {
      fieldsByGroup.set(group, []);
    }
    fieldsByGroup.get(group).push(field);
  }

  for (const [group, fields] of fieldsByGroup.entries()) {
    const groupEl = document.createElement("section");
    groupEl.className = "config-group";
    const title = document.createElement("h3");
    title.className = "config-group-title";
    title.textContent = configGroups[group] || group;
    groupEl.append(title);

    for (const field of fields) {
      const row = document.createElement("div");
      row.className = "config-field";
      const label = document.createElement("label");
      label.htmlFor = `config-${field.key}`;
      label.textContent = field.label;
      const control = createConfigControl(field);
      control.id = `config-${field.key}`;
      control.dataset.configKey = field.key;
      control.title = field.description;
      row.append(label, control);
      if (field.valid_range) {
        const hint = document.createElement("small");
        hint.textContent = field.valid_range;
        row.append(hint);
      }
      groupEl.append(row);
    }

    runtimeConfigFields.append(groupEl);
  }
}

async function loadRuntimeConfig() {
  configFeedback.textContent = "載入中";
  try {
    const response = await fetch("/api/config", { cache: "no-store" });
    if (!response.ok) {
      throw new Error(`config ${response.status}`);
    }
    const payload = await response.json();
    configCatalog = payload.fields || [];
    configGroups = payload.groups || {};
    editableConfigKeys = new Set(payload.editable_keys || []);
    configValues = Object.fromEntries(configCatalog.map((field) => [field.key, field.value]));
    renderRuntimeConfig();
    configFeedback.textContent = "就緒";
  } catch (error) {
    configFeedback.textContent = "無法取得設定";
  }
}

async function applyRuntimeConfig(event) {
  event.preventDefault();
  applyConfigButton.disabled = true;
  configFeedback.textContent = "套用中";
  const payload = {};
  for (const field of configCatalog) {
    if (!editableConfigKeys.has(field.key)) {
      continue;
    }
    const input = runtimeConfigForm.elements[field.key];
    if (!input) {
      continue;
    }
    const value = parseConfigValue(field, input);
    if (Number.isNaN(value)) {
      configFeedback.textContent = `${field.label} 格式不正確`;
      applyConfigButton.disabled = false;
      return;
    }
    if (value !== configValues[field.key]) {
      payload[field.key] = value;
    }
  }

  try {
    const result = await postJson("/api/config", payload);
    if (result.validation_errors && result.validation_errors.length) {
      configFeedback.textContent = result.validation_errors.join("; ");
      return;
    }
    configFeedback.textContent = result.effective_changes.length
      ? `已套用 ${result.effective_changes.length} 項變更`
      : "沒有變更";
    await loadRuntimeConfig();
    await refreshStatus();
  } catch (error) {
    configFeedback.textContent = "套用失敗";
  } finally {
    applyConfigButton.disabled = false;
  }
}

function statusSocketUrl() {
  const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
  return `${protocol}//${window.location.host}/api/status/ws`;
}

function scheduleStatusReconnect() {
  if (statusReconnectTimer !== null) {
    return;
  }
  statusReconnectTimer = window.setTimeout(() => {
    statusReconnectTimer = null;
    connectStatusStream();
  }, 1200);
}

function connectStatusStream() {
  if (statusReconnectTimer !== null) {
    window.clearTimeout(statusReconnectTimer);
    statusReconnectTimer = null;
  }
  const previousSocket = statusSocket;
  statusSocket = null;
  if (previousSocket && previousSocket.readyState <= WebSocket.OPEN) {
    previousSocket.close();
  }
  const socket = new WebSocket(statusSocketUrl());
  statusSocket = socket;

  socket.addEventListener("open", () => {
    if (socket !== statusSocket) {
      return;
    }
    setBadge("ready", "monitoring");
  });

  socket.addEventListener("message", (event) => {
    if (socket !== statusSocket) {
      return;
    }
    updateStatus(JSON.parse(event.data));
  });

  socket.addEventListener("close", () => {
    if (socket !== statusSocket) {
      return;
    }
    setBadge("error", "status reconnecting");
    scheduleStatusReconnect();
  });

  socket.addEventListener("error", () => {
    if (socket === statusSocket) {
      socket.close();
    }
  });
}

function cameraSocketUrl() {
  const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
  return `${protocol}//${window.location.host}/api/camera/ws`;
}

function clearFrameWatchdog() {
  if (frameWatchdogTimer !== null) {
    window.clearTimeout(frameWatchdogTimer);
    frameWatchdogTimer = null;
  }
}

function scheduleFrameWatchdog(socket) {
  clearFrameWatchdog();
  frameWatchdogTimer = window.setTimeout(() => {
    frameWatchdogTimer = null;
    if (socket === frameSocket) {
      useMjpegFrameStream("using mjpeg frame stream");
    }
  }, 2500);
}

function useMjpegFrameStream(message = "waiting for frame") {
  if (isMjpegFallbackActive) {
    return;
  }
  isMjpegFallbackActive = true;
  clearFrameWatchdog();
  const previousSocket = frameSocket;
  frameSocket = null;
  if (previousSocket && previousSocket.readyState <= WebSocket.OPEN) {
    previousSocket.close();
  }
  if (currentFrameUrl) {
    URL.revokeObjectURL(currentFrameUrl);
    currentFrameUrl = null;
  }
  frameEmpty.textContent = message;
  frameEmpty.classList.remove("hidden");
  frame.src = `/api/camera/stream.mjpg?t=${Date.now()}`;
}

function showFrameBlob(blob) {
  clearFrameWatchdog();
  isMjpegFallbackActive = false;
  const previousUrl = currentFrameUrl;
  currentFrameUrl = URL.createObjectURL(blob);
  frame.src = currentFrameUrl;
  frameEmpty.classList.add("hidden");
  if (previousUrl) {
    window.setTimeout(() => URL.revokeObjectURL(previousUrl), 1000);
  }
}

function connectFrameStream() {
  const previousSocket = frameSocket;
  frameSocket = null;
  isMjpegFallbackActive = false;
  clearFrameWatchdog();
  if (previousSocket && previousSocket.readyState <= WebSocket.OPEN) {
    previousSocket.close();
  }
  const socket = new WebSocket(cameraSocketUrl());
  frameSocket = socket;
  socket.binaryType = "blob";

  socket.addEventListener("open", () => {
    if (socket !== frameSocket) {
      return;
    }
    frameEmpty.textContent = "waiting for frame";
    scheduleFrameWatchdog(socket);
  });

  socket.addEventListener("message", (event) => {
    if (socket !== frameSocket) {
      return;
    }
    if (event.data instanceof Blob) {
      showFrameBlob(event.data);
    }
  });

  socket.addEventListener("close", () => {
    if (socket !== frameSocket) {
      return;
    }
    clearFrameWatchdog();
    useMjpegFrameStream("using mjpeg frame stream");
  });

  socket.addEventListener("error", () => {
    if (socket === frameSocket) {
      socket.close();
    }
  });
}

frame.addEventListener("load", () => {
  frameEmpty.classList.add("hidden");
});

frame.addEventListener("error", () => {
  frameEmpty.textContent = "waiting for frame";
  frameEmpty.classList.remove("hidden");
});

async function postJson(url, payload = {}) {
  const response = await fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  if (!response.ok) {
    throw new Error(`${url} ${response.status}`);
  }
  return response.json();
}

refreshCamerasButton.addEventListener("click", async () => {
  await refreshCameraList();
});

cameraDevice.addEventListener("change", () => {
  hasPendingCameraSelection = true;
});

applyCameraButton.addEventListener("click", async () => {
  applyCameraButton.disabled = true;
  try {
    await postJson("/api/config", {
      "camera.source": "backend",
      "camera.device_id": cameraDevice.value || "default",
    });
    hasPendingCameraSelection = false;
    await refreshStatus();
    connectFrameStream();
  } finally {
    applyCameraButton.disabled = false;
  }
});

recenterButton.addEventListener("click", async () => {
  recenterButton.disabled = true;
  try {
    await postJson("/api/control/recenter-servos");
    await refreshStatus();
  } finally {
    recenterButton.disabled = false;
  }
});

runtimeConfigForm.addEventListener("submit", applyRuntimeConfig);

reloadConfigButton.addEventListener("click", async () => {
  await loadRuntimeConfig();
});

refreshCameraList();
loadRuntimeConfig();
connectStatusStream();
connectFrameStream();
