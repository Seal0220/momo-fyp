import type { StatusSnapshot } from "../lib/types";

export function PromptPanel({ status }: { status: StatusSnapshot }) {
  return (
    <section className="panel">
      <div className="panel-header">
        <h3>Prompt / Output</h3>
      </div>
      <div className="prompt-stack">
        <label className="field">
          <span>System Prompt</span>
          <textarea readOnly rows={6} value={status.current_prompt_system ?? ""} />
        </label>
        <label className="field">
          <span>User Prompt</span>
          <textarea readOnly rows={10} value={status.current_prompt_user ?? ""} />
        </label>
        <label className="field">
          <span>LLM Output</span>
          <textarea readOnly rows={3} value={status.last_llm_output ?? ""} />
        </label>
        <label className="field">
          <span>Last Spoken Text</span>
          <textarea readOnly rows={3} value={status.last_spoken_text ?? ""} />
        </label>
      </div>
    </section>
  );
}
