# ai-code-doc

Upload a `.zip` or single source file, get a downloadable design spec.

## Folders

- `backend/` — FastAPI + harness + LLM + docs. Memory only, no DB.
- `frontend/` — React (Vite). Key stays in UI state, polled every 10s.

## Run backend

```bash
cd backend
pip install -r requirements.txt
uvicorn main:app --port 8000
```

## Run frontend

```bash
cd frontend
npm install
npm run dev
```

## Flow

1. `POST /api/upload` — save zip/file to `/tmp/ai-code-doc/<session>`, list tree.
2. `POST /api/generate` — starts background job, returns `job_id`.
   - Call 1: tree -> LLM picks max 30 files (JSON array).
   - Harness reads those files (12k/file, 100k total).
   - Call 2: contents -> Markdown spec.
3. `GET /api/status/{job}` — frontend polls every 10s.
4. `GET /api/download/{session}?format=md|docx|pdf`.

Providers: `claude` uses Anthropic Messages API. `opencode` uses
`https://opencode.ai/inference/openai/v1/chat/completions` (same base URL for
all chat models — embedded in both frontend and backend). Default model is
`deepseek-v4.1-flash-free`; dropdown also offers `deepseek-v4.1-flash`,
`kimi-k3`, `glm-5.3`. API key is pasted in the UI per request
(`oc_sk_...` for opencode, `sk-ant-...` for claude-direct) and never stored.

Templates: optional `.docx` with `{{overview}} {{tech_stack}} ... {{full_spec}}`.
If none uploaded, a clean doc is built from Markdown.
