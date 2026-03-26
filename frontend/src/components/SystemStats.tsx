import type { StatusSnapshot } from "../lib/types";

export function SystemStats({ status }: { status: StatusSnapshot }) {
  return (
    <section className="panel">
      <div className="panel-header">
        <h3>System Stats</h3>
      </div>
      <div className="stats-grid">
        <div><strong>RSS</strong><span>{status.stats.memory_rss_mb} MB</span></div>
        <div><strong>VMS</strong><span>{status.stats.memory_vms_mb} MB</span></div>
        <div><strong>Temp Files</strong><span>{status.stats.temp_file_count}</span></div>
        <div><strong>Temp Size</strong><span>{status.stats.temp_file_size_mb} MB</span></div>
        <div><strong>TTS Loaded</strong><span>{String(status.tts_loaded)}</span></div>
        <div><strong>Serial</strong><span>{String(status.serial_connected)}</span></div>
        <div><strong>Ollama</strong><span>{String(status.ollama_connected)}</span></div>
        <div><strong>Pipeline</strong><span>{status.pipeline.stage}</span></div>
      </div>
    </section>
  );
}
