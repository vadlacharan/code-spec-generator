// UI: 1 upload -> 2 configure -> 3 poll status every 10s -> 4 download.
// API key is transient: kept in React state only, sent per generate call.

import { useEffect, useRef, useState } from "react";

const API = "http://localhost:8000";

// Same for every OpenCode inference chat model (deepseek, kimi, glm, ...).
// Verified against https://opencode.ai/inference/v1/models
// (each model lists api.chat-completions.base_url = this).
const OPENCODE_BASE_URL = "https://opencode.ai/inference/openai/v1";

// Model IDs are the plain inference IDs (no "opencode-go/" prefix).
const OPENCODE_MODELS = [
  "deepseek-v4.1-flash-free",
  "deepseek-v4.1-flash",
];

export default function App() {
  const [sessionId, setSessionId] = useState("");
  const [tree, setTree] = useState([]);
  const [provider, setProvider] = useState("opencode");
  const [model, setModel] = useState(OPENCODE_MODELS[0]);
  const [apiKey, setApiKey] = useState("");
  const [jobId, setJobId] = useState("");
  const [status, setStatus] = useState("");
  const [stage, setStage] = useState("");
  const [elapsed, setElapsed] = useState(0);
  const [spec, setSpec] = useState("");
  const [error, setError] = useState("");
  const clock = useRef(null); // 1s elapsed timer, cleared on done/error

  async function uploadSource(e) {
    const f = e.target.files[0];
    if (!f) return;
    const fd = new FormData();
    fd.append("file", f);
    const r = await fetch(`${API}/api/upload`, { method: "POST", body: fd });
    const j = await r.json();
    setSessionId(j.session_id);
    setTree(j.tree || []);
  }

  async function uploadTemplate(e) {
    const f = e.target.files[0];
    if (!f || !sessionId) return;
    const fd = new FormData();
    fd.append("file", f);
    await fetch(`${API}/api/upload-template/${sessionId}`, { method: "POST", body: fd });
    alert("template saved");
  }

  async function startGenerate() {
    setError("");
    setSpec("");
    setStage("queued...");
    setElapsed(0);
    const t0 = Date.now();
    if (clock.current) clearInterval(clock.current);
    clock.current = setInterval(() => setElapsed(Math.floor((Date.now() - t0) / 1000)), 1000);
    const r = await fetch(`${API}/api/generate`, {
      method: "POST",
      headers: { "content-type": "application/json" },
      // baseUrl is embedded: same for all OpenCode chat models.
      body: JSON.stringify({ session_id: sessionId, provider, model, apiKey, baseUrl: provider === "opencode" ? OPENCODE_BASE_URL : "" }),
    });
    const j = await r.json();
    setJobId(j.job_id);
    setStatus("pending");
  }

  // Simple polling every 10 seconds.
  useEffect(() => {
    if (!jobId || status === "done" || status === "error") return;
    const t = setInterval(async () => {
      const r = await fetch(`${API}/api/status/${jobId}`);
      const j = await r.json();
      setStatus(j.status);
      if (j.stage) setStage(j.stage);
      if (j.status === "done") {
        setSpec(j.spec_md || "");
        clearInterval(t);
        clearInterval(clock.current);
      }
      if (j.status === "error") {
        setError(j.error || "unknown error");
        clearInterval(t);
        clearInterval(clock.current);
      }
    }, 10000);
    return () => clearInterval(t);
  }, [jobId, status]);

  return (
    <div className="wrap">
      <h2>ai-code-doc</h2>

      <h3>1. Upload source (.zip or single file, max 25MB)</h3>
      <input type="file" onChange={uploadSource} />
      {sessionId && <p>session: {sessionId} ({tree.length} files)</p>}
      <div className="tree">{tree.slice(0, 100).join("\n")}</div>

      <h3>2. Configure + optional DOCX template</h3>
      <div className="row">
        <select value={provider} onChange={(e) => setProvider(e.target.value)}>
          <option value="opencode">opencode</option>
          <option value="claude">claude-direct</option>
        </select>
        <select value={model} onChange={(e) => setModel(e.target.value)}>
          {OPENCODE_MODELS.map((m) => (
            <option key={m} value={m}>{m}</option>
          ))}
        </select>
      </div>
      <div className="row">
        <input type="password" placeholder="API key: oc_sk_... for opencode, sk-ant-... for claude (not stored)" value={apiKey} onChange={(e) => setApiKey(e.target.value)} style={{ flex: 1 }} />
      </div>
      <div className="row">
        <input type="file" accept=".docx" onChange={uploadTemplate} />
      </div>

      <div className="row">
        <button onClick={startGenerate} disabled={!sessionId || !apiKey}>Generate spec</button>
      </div>

      <h3>3. Status (polls every 10s): {status} {elapsed}s</h3>
      {status === "pending" && stage && <p>{stage}</p>}
      {error && <pre style={{ background: "#fdd", color: "#900" }}>{error}</pre>}
      {spec && <pre>{spec.slice(0, 20000)}</pre>}

      <h3>4. Download</h3>
      <div className="row">
        {spec && sessionId ? (
          ["md", "docx", "pdf"].map((f) => (
            <a key={f} href={`${API}/api/download/${sessionId}?format=${f}`}>
              <button>Download .{f}</button>
            </a>
          ))
        ) : (
          ["md", "docx", "pdf"].map((f) => (
            <button key={f} disabled>Download .{f}</button>
          ))
        )}
      </div>
    </div>
  );
}
