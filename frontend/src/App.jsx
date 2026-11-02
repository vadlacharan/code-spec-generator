// UI: 1 upload -> 2 configure -> 3 poll status every 10s -> 4 download.
// API key is transient: kept in React state only, sent per generate call.

import { useEffect, useState } from "react";

const API = "http://localhost:8000";

export default function App() {
  const [sessionId, setSessionId] = useState("");
  const [tree, setTree] = useState([]);
  const [provider, setProvider] = useState("claude");
  const [model, setModel] = useState("");
  const [baseUrl, setBaseUrl] = useState("");
  const [apiKey, setApiKey] = useState("");
  const [jobId, setJobId] = useState("");
  const [status, setStatus] = useState("");
  const [spec, setSpec] = useState("");

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
    const r = await fetch(`${API}/api/generate`, {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ session_id: sessionId, provider, model, apiKey, baseUrl }),
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
      if (j.status === "done") {
        setSpec(j.spec_md || "");
        clearInterval(t);
      }
      if (j.status === "error") clearInterval(t);
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
          <option value="claude">claude</option>
          <option value="opencode">opencode</option>
        </select>
        <input placeholder="model (e.g. deepseek-chat)" value={model} onChange={(e) => setModel(e.target.value)} />
      </div>
      <div className="row">
        <input placeholder="baseUrl (opencode only)" value={baseUrl} onChange={(e) => setBaseUrl(e.target.value)} style={{ flex: 1 }} />
      </div>
      <div className="row">
        <input type="password" placeholder="API key (not stored)" value={apiKey} onChange={(e) => setApiKey(e.target.value)} style={{ flex: 1 }} />
      </div>
      <div className="row">
        <input type="file" accept=".docx" onChange={uploadTemplate} />
      </div>

      <div className="row">
        <button onClick={startGenerate} disabled={!sessionId || !apiKey}>Generate spec</button>
      </div>

      <h3>3. Status (polls every 10s): {status}</h3>
      {spec && <pre>{spec.slice(0, 20000)}</pre>}

      <h3>4. Download</h3>
      <div className="row">
        {["md", "docx", "pdf"].map((f) => (
          <a key={f} href={`${API}/api/download/${sessionId}?format=${f}`}>
            <button disabled={!spec}>Download .{f}</button>
          </a>
        ))}
      </div>
    </div>
  );
}
