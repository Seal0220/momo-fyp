import type { AudioDevice, CameraInfo, ConfigField, ConfigUpdateResponse, StatusSnapshot } from "./types";

export async function fetchStatus(): Promise<StatusSnapshot> {
  const response = await fetch("/api/status");
  if (!response.ok) throw new Error("Failed to fetch status");
  return response.json();
}

export async function fetchConfig(): Promise<{ config: Record<string, unknown>; fields: ConfigField[] }> {
  const response = await fetch("/api/config");
  if (!response.ok) throw new Error("Failed to fetch config");
  return response.json();
}

export async function fetchCameras(): Promise<CameraInfo[]> {
  const response = await fetch("/api/cameras");
  if (!response.ok) throw new Error("Failed to fetch cameras");
  return response.json();
}

export async function fetchOllamaModels(): Promise<string[]> {
  const response = await fetch("/api/ollama/models");
  if (!response.ok) throw new Error("Failed to fetch models");
  const data = await response.json();
  return data.models;
}

export async function fetchAudioDevices(): Promise<AudioDevice[]> {
  const response = await fetch("/api/audio/devices");
  if (!response.ok) throw new Error("Failed to fetch audio devices");
  return response.json();
}

export async function uploadCameraFrame(blob: Blob) {
  const response = await fetch("/api/camera/frame", {
    method: "POST",
    headers: { "Content-Type": "image/jpeg" },
    body: blob,
  });
  if (!response.ok) throw new Error("Failed to upload frame");
  return response.json();
}

export async function updateConfig(payload: Record<string, unknown>): Promise<ConfigUpdateResponse> {
  const response = await fetch("/api/config", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  if (!response.ok) throw new Error("Failed to update config");
  return response.json();
}

export async function simulatePipeline() {
  const response = await fetch("/api/control/simulate-pipeline", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ sentence_index: 1, event_summary: "揮手" }),
  });
  if (!response.ok) throw new Error("Failed to simulate pipeline");
  return response.json();
}
