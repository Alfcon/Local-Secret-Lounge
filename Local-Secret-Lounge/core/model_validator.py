from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any


class ModelValidator:
    """Utility helpers for GGUF file validation and fingerprints."""

    MAGIC = b"GGUF"

    @classmethod
    def validate_model_file(cls, path: str | Path) -> dict[str, Any]:
        file_path = Path(path).expanduser().resolve()
        result: dict[str, Any] = {
            "path": str(file_path),
            "exists": file_path.exists(),
            "is_file": False,
            "format": file_path.suffix.lower().lstrip('.') or None,
            "size_bytes": 0,
            "status": "missing",
            "error": None,
        }

        if not file_path.exists():
            result["error"] = f"Model file not found: {file_path}"
            return result

        if not file_path.is_file():
            result["status"] = "invalid"
            result["error"] = "Selected path is not a file."
            return result

        result["is_file"] = True
        try:
            result["size_bytes"] = file_path.stat().st_size
        except OSError as exc:
            result["status"] = "invalid"
            result["error"] = f"Could not read file size: {exc}"
            return result

        if file_path.suffix.lower() != ".gguf":
            result["status"] = "invalid"
            result["error"] = "Only .gguf files are supported in version 1."
            return result

        if result["size_bytes"] <= 0:
            result["status"] = "invalid"
            result["error"] = "The file is empty."
            return result

        try:
            with file_path.open('rb') as handle:
                magic = handle.read(4)
        except OSError as exc:
            result["status"] = "invalid"
            result["error"] = f"Could not open file: {exc}"
            return result

        if magic != cls.MAGIC:
            result["status"] = "invalid"
            result["error"] = "This file does not appear to be a valid GGUF model."
            return result

        result["status"] = "available"
        return result

    @staticmethod
    def compute_sha256(path: str | Path, chunk_size: int = 1024 * 1024) -> str:
        file_path = Path(path).expanduser().resolve()
        digest = hashlib.sha256()
        with file_path.open('rb') as handle:
            while True:
                chunk = handle.read(chunk_size)
                if not chunk:
                    break
                digest.update(chunk)
        return digest.hexdigest()
