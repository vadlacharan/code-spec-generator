# Backend entry: upload -> generate (background job) -> poll status -> download.
# Memory only: sessions + jobs dicts, temp dirs under /tmp. No DB.

import asyncio
import json
import shutil
import tempfile
import time
import uuid
import zipfile
from pathlib import Path

from fastapi import FastAPI, File, UploadFile, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel

from harness import list_tree, read_picked
from llm import call_llm
from docs import markdown_to_docx, markdown_to_pdf

MAX_UPLOAD_BYTES = 25 * 1024 * 1024  # 25MB
SESSION_TTL_SECS = 60 * 60  # 1 hour

app = FastAPI(title="ai-code-doc")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # local demo, no auth
    allow_methods=["*"],
    allow_headers=["*"],
)

# session_id -> {dir, tree, template_path, spec_md, picked, created}
sessions: dict = {}
# job_id -> {status, session_id, picked, spec_md, error}
jobs: dict = {}


class GenerateBody(BaseModel):
    session_id: str
    provider: str = "claude"  # claude | opencode
    model: str = ""
    apiKey: str = ""
    baseUrl: str = ""  # only for opencode gateways


def _get_session(session_id: str) -> dict:
    s = sessions.get(session_id)
    if not s:
        raise HTTPException(404, "session not found or expired")
    return s


def _safe_extract_zip(zip_path: Path, dest: Path):
    with zipfile.ZipFile(zip_path) as z:
        for m in z.namelist():
            target = (dest / m).resolve()
            if not str(target).startswith(str(dest.resolve())):
                raise HTTPException(400, "unsafe zip path")
        z.extractall(dest)


@app.get("/api/health")
@app.get("/health")
def health():
    return {"ok": True}


@app.get("/")
def root():
    return {"ok": True, "service": "ai-code-doc"}


@app.post("/api/upload")
async def upload(file: UploadFile = File(...)):
    data = await file.read()
    if len(data) > MAX_UPLOAD_BYTES:
        raise HTTPException(413, "file over 25MB")
    session_id = uuid.uuid4().hex[:12]
    root = Path(tempfile.gettempdir()) / "ai-code-doc" / session_id
    root.mkdir(parents=True, exist_ok=True)
    name = (file.filename or "").lower()
    if name.endswith(".zip"):
        tmp = root / "_upload.zip"
        tmp.write_bytes(data)
        _safe_extract_zip(tmp, root)
        tmp.unlink(missing_ok=True)
    else:
        (root / (file.filename or "single_file.txt")).write_bytes(data)
    tree = list_tree(root)
    sessions[session_id] = {
        "dir": root, "tree": tree, "template_path": None,
        "spec_md": "", "picked": [], "created": time.time(),
    }
    return {"session_id": session_id, "tree": tree}


@app.post("/api/upload-template/{session_id}")
async def upload_template(session_id: str, file: UploadFile = File(...)):
    s = _get_session(session_id)
    data = await file.read()
    if len(data) > MAX_UPLOAD_BYTES:
        raise HTTPException(413, "template over 25MB")
    p = Path(s["dir"]) / "_template.docx"
    p.write_bytes(data)
    s["template_path"] = p
    return {"ok": True}


PICK_SYSTEM = "You pick source files for a design-spec. Reply ONLY with a JSON array of paths, max 30, most important first."
SPEC_SYSTEM = (
    "You write design specifications from source code. "
    "Reply in Markdown with these sections: ## Overview, ## Tech Stack, ## Architecture, "
    "## API Endpoints, ## Data Models, ## File Structure, ## Setup, ## Limitations."
)


async def _run_job(job_id: str, body: GenerateBody):
    """Background worker: tree -> LLM picks files -> read files -> LLM writes spec."""
    jobs[job_id]["stage"] = "picking files (LLM call 1/2)..."
    try:
        s = _get_session(body.session_id)
        tree = s["tree"]
        # Call 1: let LLM decide which files to read.
        pick_raw = await call_llm(
            body.provider, body.apiKey, body.model,
            PICK_SYSTEM, "File tree:\n" + "\n".join(tree[:1000]),
            body.baseUrl,
        )
        try:
            start = pick_raw.find("[")
            end = pick_raw.rfind("]") + 1
            picked = json.loads(pick_raw[start:end])
            picked = [p for p in picked if p in tree][:30]
        except Exception:
            picked = tree[:20]  # fallback: first 20 files
        jobs[job_id]["stage"] = f"reading {len(picked)} files..."
        jobs[job_id]["picked"] = picked
        # Harness reads whatever the LLM asked for.
        packed = read_picked(Path(s["dir"]), picked)
        jobs[job_id]["stage"] = f"writing spec (LLM call 2/2, {len(packed)} chars)..."
        # Call 2: write the spec.
        spec_md = await call_llm(
            body.provider, body.apiKey, body.model,
            SPEC_SYSTEM, f"Project files:\n{packed}",
            body.baseUrl,
        )
        s["spec_md"] = spec_md
        s["picked"] = picked
        jobs[job_id] = {"status": "done", "session_id": body.session_id,
                        "picked": picked, "spec_md": spec_md}
    except Exception as e:
        jobs[job_id] = {"status": "error", "session_id": body.session_id, "error": str(e)}


@app.post("/api/generate")
async def generate(body: GenerateBody):
    _get_session(body.session_id)
    if not body.apiKey:
        raise HTTPException(400, "apiKey required (paste in UI, never stored)")
    job_id = uuid.uuid4().hex[:12]
    jobs[job_id] = {"status": "pending", "session_id": body.session_id,
                    "stage": "queued...", "started": time.time()}
    asyncio.create_task(_run_job(job_id, body))
    return {"job_id": job_id}


@app.get("/api/status/{job_id}")
def status(job_id: str):
    j = jobs.get(job_id)
    if not j:
        raise HTTPException(404, "job not found")
    if j["status"] == "done":
        # trim spec in poll response so 10s polling stays light
        return {"status": "done", "picked": j["picked"], "spec_md": j["spec_md"][:20000]}
    return j


@app.get("/api/download/{session_id}")
def download(session_id: str, format: str = "md"):
    s = _get_session(session_id)
    if not s["spec_md"]:
        raise HTTPException(400, "no spec yet, generate first")
    outdir = Path(s["dir"])
    if format == "md":
        p = outdir / "spec.md"
        p.write_text(s["spec_md"])
        return FileResponse(p, filename="spec.md")
    if format == "docx":
        p = outdir / "spec.docx"
        markdown_to_docx(s["spec_md"], s["template_path"], p)
        return FileResponse(p, filename="spec.docx")
    if format == "pdf":
        p = outdir / "spec.pdf"
        markdown_to_pdf(s["spec_md"], p)
        return FileResponse(p, filename="spec.pdf")
    raise HTTPException(400, "format must be md|docx|pdf")


@app.delete("/api/session/{session_id}")
def delete_session(session_id: str):
    s = sessions.pop(session_id, None)
    if s:
        shutil.rmtree(s["dir"], ignore_errors=True)
    return {"ok": True}
