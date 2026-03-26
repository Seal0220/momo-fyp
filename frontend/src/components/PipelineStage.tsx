import type { PipelineStage as Stage } from "../lib/types";

const STAGES: Stage[] = ["LLM", "TTS", "PLAYBACK"];

export function PipelineStage({ active, elapsedMs }: { active: Stage; elapsedMs: number }) {
  return (
    <section className="panel">
      <div className="panel-header">
        <h3>Pipeline</h3>
        <span>{elapsedMs} ms</span>
      </div>
      <div className="pipeline">
        {STAGES.map((stage) => (
          <div key={stage} className={`pipeline-node ${active === stage ? "active" : ""}`}>
            <span>{stage}</span>
          </div>
        ))}
      </div>
    </section>
  );
}

