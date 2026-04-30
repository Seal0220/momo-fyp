const frame = document.querySelector("#camera-frame");
const frameEmpty = document.querySelector("#frame-empty");
const badge = document.querySelector("#connection-badge");
const cameraDevice = document.querySelector("#camera-device");
const refreshCamerasButton = document.querySelector("#refresh-cameras-button");
const applyCameraButton = document.querySelector("#apply-camera-button");
const recenterButton = document.querySelector("#recenter-button");
const eventLog = document.querySelector("#event-log");

const fields = {
  cameraMode: document.querySelector("#camera-mode"),
  mode: document.querySelector("#mode-value"),
  fps: document.querySelector("#fps-value"),
  track: document.querySelector("#track-value"),
  bbox: document.querySelector("#bbox-value"),
  center: document.querySelector("#center-value"),
  distance: document.querySelector("#distance-value"),
  position: document.querySelector("#position-value"),
  colors: document.querySelector("#colors-value"),
  leftServo: document.querySelector("#left-servo-value"),
  rightServo: document.querySelector("#right-servo-value"),
  trackingSource: document.querySelector("#tracking-source-value"),
  serialState: document.querySelector("#serial-state-value"),
  serialPort: document.querySelector("#serial-port-value"),
  serialTx: document.querySelector("#serial-tx-value"),
  serialRx: document.querySelector("#serial-rx-value"),
  serialError: document.querySelector("#serial-error-value"),
  ram: document.querySelector("#ram-value"),
  gpu: document.querySelector("#gpu-value"),
  personRuntime: document.querySelector("#person-runtime-value"),
};

let lastFrameOk = false;
let hasLoadedCameras = false;
let hasPendingCameraSelection = false;

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

function runtimeLabel(runtime) {
  if (!runtime) {
    return "-";
  }
  const backend = runtime.backend || "unknown";
  const device = runtime.effective_device || runtime.requested_mode || "unknown";
  return `${backend} / ${device}`;
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
  const cameraDeviceId = status.camera_device_id || "default";

  fields.cameraMode.textContent = `${text(status.camera_device_id)} / ${text(status.camera_mode)}`;
  if (hasLoadedCameras && !hasPendingCameraSelection) {
    ensureCameraOption(cameraDeviceId);
    cameraDevice.value = cameraDeviceId;
  }
  fields.mode.textContent = text(status.mode, "IDLE");
  fields.fps.textContent = `${fixed(status.yolo_detect_fps, 1)} fps`;
  fields.track.textContent = `track ${text(audience.track_id)}`;
  fields.bbox.textContent = audience.person_bbox ? audience.person_bbox.join(", ") : "-";
  fields.center.textContent = `${fixed(audience.center_x_norm, 3)}, ${fixed(audience.center_y_norm, 3)}`;
  fields.distance.textContent = `${text(audience.distance_class)} (${percent(audience.bbox_area_ratio)})`;
  fields.position.textContent = `${text(audience.position_state)} / ${text(audience.horizontal_class)}`;
  fields.colors.textContent = `${text(audience.top_color)} / ${text(audience.bottom_color)}`;
  fields.leftServo.textContent = `${fixed(servo.left_deg, 1)} deg`;
  fields.rightServo.textContent = `${fixed(servo.right_deg, 1)} deg`;
  fields.trackingSource.textContent = text(servo.tracking_source);
  fields.serialState.textContent = status.serial_connected ? "connected" : "offline";
  fields.serialPort.textContent = text(serial.port);
  fields.serialTx.textContent = text(serial.last_tx);
  fields.serialRx.textContent = text(serial.last_rx);
  fields.serialError.textContent = text(serial.last_error);
  fields.ram.textContent = `${fixed(stats.memory_rss_mb, 1)} MB`;
  fields.gpu.textContent = stats.gpu_memory_mb === null ? "-" : `${fixed(stats.gpu_memory_mb, 1)} MB`;
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

function refreshFrame() {
  frame.src = `/api/camera/frame.jpg?t=${Date.now()}`;
}

frame.addEventListener("load", () => {
  lastFrameOk = true;
  frameEmpty.classList.add("hidden");
});

frame.addEventListener("error", () => {
  lastFrameOk = false;
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
      camera_source: "backend",
      camera_device_id: cameraDevice.value || "default",
    });
    hasPendingCameraSelection = false;
    await refreshStatus();
    refreshFrame();
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

refreshCameraList();
refreshStatus();
refreshFrame();
setInterval(refreshStatus, 500);
setInterval(() => {
  if (lastFrameOk || !document.hidden) {
    refreshFrame();
  }
}, 250);
