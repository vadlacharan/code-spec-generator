# Harness: dumb file helper. No scoring, no ranking.
# It only lists the tree and reads files the LLM asked for.

import os
from pathlib import Path

# Folders / extensions we never send to the LLM.
SKIP_DIRS = {"node_modules", ".git", "dist", "build", "__pycache__", ".venv", "venv", ".next"}
SKIP_EXTS = {".png", ".jpg", ".jpeg", ".gif", ".ico", ".pdf", ".zip", ".exe", ".dll", ".so", ".pyc"}

MAX_FILES_IN_TREE = 1000
PER_FILE_CHAR_CAP = 12000   # head 8k + tail 4k
TOTAL_CHAR_CAP = 100000     # v1 fixed budget


def is_text_file(path: Path) -> bool:
    if path.suffix.lower() in SKIP_EXTS:
        return False
    return True


def list_tree(root: Path) -> list[str]:
    """Walk root alphabetically, return relative file paths."""
    out: list[str] = []
    for dirpath, dirnames, filenames in os.walk(root):
        # skip trash dirs in place so walk does not descend into them
        dirnames[:] = sorted(d for d in dirnames if d not in SKIP_DIRS)
        for name in sorted(filenames):
            full = Path(dirpath) / name
            if not is_text_file(full):
                continue
            rel = str(full.relative_to(root))
            out.append(rel)
            if len(out) >= MAX_FILES_IN_TREE:
                return out
    return out


def read_one_file(root: Path, rel: str) -> str:
    """Read one file with 12k cap (head 8k + tail 4k)."""
    full = (root / rel).resolve()
    # zip-slip guard: file must stay inside session dir
    if not str(full).startswith(str(root.resolve())):
        return "<blocked: outside session dir>"
    try:
        text = full.read_text(encoding="utf-8", errors="ignore")
    except Exception:
        return "<unreadable>"
    if len(text) <= PER_FILE_CHAR_CAP:
        return text
    head = text[:8000]
    tail = text[-4000:]
    return head + "\n\n...<truncated>...\n\n" + tail


def read_picked(root: Path, picked: list[str]) -> str:
    """Read every LLM-picked file, pack until TOTAL_CHAR_CAP. Simple FIFO."""
    chunks: list[str] = []
    used = 0
    for rel in picked:
        content = read_one_file(root, rel)
        block = f"\n\n=== {rel} ===\n{content}\n"
        if used + len(block) > TOTAL_CHAR_CAP:
            break  # v1: stop here, no overflow handling
        chunks.append(block)
        used += len(block)
    return "".join(chunks)
