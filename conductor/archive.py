"""Session artifact export — self-contained archive of a completed session."""

from __future__ import annotations

import hashlib
import json
import shutil
from datetime import datetime, timezone
from pathlib import Path

from .constants import SESSIONS_DIR, SessionError


def export_session(session_id: str, output_dir: Path | None = None) -> Path:
    """Export a complete session archive as a self-contained directory.

    Copies the session directory (from sessions/{session_id}/), including
    session-log.yaml, spec.md, plan.md, status.md, adr.md, and any other
    artifacts. Generates a manifest.json with session_id, export_date,
    file list, and content hashes.

    Returns the output directory path.
    """
    source_dir = SESSIONS_DIR / session_id
    if not source_dir.exists():
        raise SessionError(f"Session directory not found: {source_dir}")

    if output_dir is None:
        output_dir = Path.cwd() / f"session-export-{session_id}"

    if output_dir.exists():
        raise SessionError(f"Output directory already exists: {output_dir}. Remove it first or choose another path.")

    # Copy session directory contents
    shutil.copytree(source_dir, output_dir)

    # Build manifest with content hashes
    files: list[dict[str, str]] = []
    for file_path in sorted(output_dir.rglob("*")):
        if file_path.is_file() and file_path.name != "manifest.json":
            rel = str(file_path.relative_to(output_dir))
            content_hash = hashlib.sha256(file_path.read_bytes()).hexdigest()
            files.append({
                "path": rel,
                "sha256": content_hash,
                "size_bytes": str(file_path.stat().st_size),
            })

    manifest = {
        "session_id": session_id,
        "export_date": datetime.now(timezone.utc).isoformat(),
        "source_dir": str(source_dir),
        "files": files,
        "file_count": len(files),
    }

    manifest_path = output_dir / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2))

    return output_dir
