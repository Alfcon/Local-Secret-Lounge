from __future__ import annotations

import json
import shutil
from datetime import datetime
from pathlib import Path
from typing import Any

from core.model_validator import ModelValidator
from core.paths import get_models_dir, get_models_registry_file
from core.settings_manager import SettingsManager


DEFAULT_MODEL_PERFORMANCE: dict[str, int] = {
    'context_size': 4096,
    'threads': 4,
    'max_tokens': 384,
}


class ModelManager:
    """Registry manager for local GGUF models with validation and safer removal."""

    def __init__(self, settings_manager: SettingsManager) -> None:
        self.settings_manager = settings_manager
        self.registry_file = get_models_registry_file()
        self.models_dir = get_models_dir()
        self._models: list[dict[str, Any]] = []
        # Callbacks invoked (with model_id) whenever the default model changes,
        # either via set_default_model() or via import_local_model(set_default=True).
        # UI layers can subscribe to auto-refresh backend status etc.
        self._default_changed_callbacks: list = []
        self.reload_registry()

    def add_default_changed_listener(self, callback) -> None:
        """Register a zero-or-one-argument callable to be invoked whenever the
        default model changes. The callback receives the new default model id
        (str) or None if no default is set. Exceptions inside callbacks are
        swallowed so one broken listener cannot break model-management flow.
        """
        if callable(callback) and callback not in self._default_changed_callbacks:
            self._default_changed_callbacks.append(callback)

    def remove_default_changed_listener(self, callback) -> None:
        try:
            self._default_changed_callbacks.remove(callback)
        except ValueError:
            pass

    def _notify_default_changed(self, model_id: str | None) -> None:
        for cb in list(self._default_changed_callbacks):
            try:
                cb(model_id)
            except TypeError:
                # Callback that takes no args
                try:
                    cb()
                except Exception:
                    pass
            except Exception:
                # Never let a listener break the model flow
                pass


    def reload_registry(self) -> list[dict[str, Any]]:
        self._models = self.load_registry()
        self.validate_all_models()
        return self._models

    def load_registry(self) -> list[dict[str, Any]]:
        if not self.registry_file.exists():
            return []
        try:
            data = json.loads(self.registry_file.read_text(encoding="utf-8"))
            models = data if isinstance(data, list) else []
        except json.JSONDecodeError:
            return []

        normalized: list[dict[str, Any]] = []
        for model in models:
            if not isinstance(model, dict):
                continue
            entry = dict(model)
            entry['chat_format'] = self._infer_chat_format(
                explicit_value=entry.get('chat_format'),
                display_name=entry.get('name'),
                filename=entry.get('filename'),
                file_path=entry.get('path'),
            )
            entry['performance'] = self._normalize_performance_settings(entry.get('performance'))
            normalized.append(entry)
        return normalized

    def save_registry(self) -> None:
        self.registry_file.parent.mkdir(parents=True, exist_ok=True)
        self.registry_file.write_text(json.dumps(self._models, indent=2), encoding="utf-8")

    def list_models(self) -> list[dict[str, Any]]:
        return list(self._models)

    def get_model(self, model_id: str) -> dict[str, Any] | None:
        return next((model for model in self._models if model["id"] == model_id), None)

    def get_model_performance_settings(self, model_id: str | None) -> dict[str, int]:
        model = self.get_model(str(model_id)) if model_id else None
        if model is None:
            return self._default_performance_settings()
        return self._normalize_performance_settings(model.get('performance'))

    def update_model_performance_settings(
        self,
        model_id: str,
        *,
        context_size: int,
        threads: int,
        max_tokens: int,
    ) -> dict[str, Any]:
        model = self.get_model(model_id)
        if model is None:
            raise ValueError('Model not found.')

        model['performance'] = self._normalize_performance_settings(
            {
                'context_size': context_size,
                'threads': threads,
                'max_tokens': max_tokens,
            }
        )
        self.save_registry()
        return model

    def get_model_by_path(self, file_path: str | Path) -> dict[str, Any] | None:
        resolved = str(Path(file_path).expanduser().resolve())
        return next((model for model in self._models if model.get("path") == resolved), None)

    def get_model_by_sha256(self, sha256: str) -> dict[str, Any] | None:
        for model in self._models:
            if model.get("sha256") == sha256:
                return model
        return None

    def generate_model_id(self, display_name: str) -> str:
        slug = "".join(ch.lower() if ch.isalnum() else "_" for ch in display_name).strip("_")
        slug = "_".join(part for part in slug.split("_") if part)
        base_slug = slug or "model"
        candidate = base_slug
        counter = 2
        existing_ids = {model["id"] for model in self._models}
        while candidate in existing_ids:
            candidate = f"{base_slug}_{counter}"
            counter += 1
        return candidate

    def import_local_model(
        self,
        source_path: str,
        display_name: str,
        copy_to_managed_storage: bool,
        chat_format: str | None = None,
        set_default: bool = False,
    ) -> dict[str, Any]:
        source = Path(source_path).expanduser().resolve()
        if not display_name.strip():
            raise ValueError("Enter a display name for the model.")

        validation = ModelValidator.validate_model_file(source)
        if validation["status"] != "available":
            raise ValueError(validation["error"] or "The selected model file is invalid.")

        source_sha256 = ModelValidator.compute_sha256(source)
        duplicate = self._find_duplicate(source, source_sha256)
        if duplicate is not None:
            raise ValueError(
                f"This model is already registered as '{duplicate['name']}'.\n\nPath: {duplicate['path']}"
            )

        final_path = source
        managed_storage = False
        if copy_to_managed_storage:
            destination = self._unique_destination(self.models_dir / source.name, source)
            shutil.copy2(source, destination)
            final_path = destination.resolve()
            managed_storage = True

        return self._register_model(
            final_path=final_path,
            display_name=display_name,
            source="local_import",
            repo_id=None,
            filename=final_path.name,
            chat_format=chat_format,
            set_default=set_default,
            sha256=source_sha256,
            managed_storage=managed_storage,
        )

    def _register_model(
        self,
        final_path: Path,
        display_name: str,
        source: str,
        repo_id: str | None,
        filename: str,
        chat_format: str | None,
        set_default: bool,
        sha256: str | None,
        managed_storage: bool,
    ) -> dict[str, Any]:
        validation = ModelValidator.validate_model_file(final_path)
        model_entry = {
            "id": self.generate_model_id(display_name),
            "name": display_name,
            "path": str(final_path.resolve()),
            "source": source,
            "repo_id": repo_id,
            "filename": filename,
            "format": "gguf",
            "size_bytes": validation.get("size_bytes", 0),
            "chat_format": self._infer_chat_format(
                explicit_value=chat_format,
                display_name=display_name,
                filename=filename,
                file_path=final_path,
            ),
            "is_default": False,
            "status": validation.get("status", "invalid"),
            "validation_error": validation.get("error"),
            "sha256": sha256,
            "managed_storage": managed_storage,
            "added_at": datetime.now().replace(microsecond=0).isoformat(),
            "performance": self._default_performance_settings(),
        }
        self._models.append(model_entry)
        if set_default:
            self.set_default_model(model_entry["id"])
        else:
            self.save_registry()
        return model_entry

    def _find_duplicate(self, file_path: Path, sha256: str | None) -> dict[str, Any] | None:
        duplicate = self.get_model_by_path(file_path)
        if duplicate is not None:
            return duplicate

        if not sha256:
            return None

        for model in self._models:
            existing_hash = model.get("sha256")
            if existing_hash and existing_hash == sha256:
                return model

            size_bytes = int(model.get("size_bytes") or 0)
            if not existing_hash and size_bytes > 0 and size_bytes == int(file_path.stat().st_size):
                existing_path = Path(model.get("path", ""))
                if existing_path.exists() and existing_path != file_path:
                    try:
                        computed = ModelValidator.compute_sha256(existing_path)
                    except OSError:
                        continue
                    model["sha256"] = computed
                    if computed == sha256:
                        self.save_registry()
                        return model
        return None

    def _unique_destination(self, destination: Path, source: Path) -> Path:
        candidate = destination
        if candidate.exists() and candidate.resolve() != source.resolve():
            stem = destination.stem
            suffix = destination.suffix
            counter = 2
            while candidate.exists():
                candidate = destination.with_name(f"{stem}_{counter}{suffix}")
                counter += 1
        return candidate

    def is_managed_model_path(self, file_path: str | Path) -> bool:
        try:
            Path(file_path).expanduser().resolve().relative_to(self.models_dir.resolve())
            return True
        except ValueError:
            return False

    def remove_model(
        self,
        model_id: str,
        delete_file: bool = False,
        allow_external_delete: bool = False,
    ) -> dict[str, Any]:
        model = self.get_model(model_id)
        if model is None:
            raise ValueError("Model not found.")

        deleted_file = False
        model_path = Path(model["path"])
        if delete_file and model_path.exists():
            is_managed = self.is_managed_model_path(model_path)
            if not is_managed and not allow_external_delete:
                raise PermissionError(
                    "Refusing to delete a file outside Local Secret Lounge's managed models folder without explicit confirmation."
                )
            model_path.unlink()
            deleted_file = True

        self._models = [entry for entry in self._models if entry["id"] != model_id]
        if self.settings_manager.get("default_model_id") == model_id:
            self.settings_manager.set("default_model_id", None)
        self.save_registry()
        return {"removed": True, "deleted_file": deleted_file}

    def set_default_model(self, model_id: str) -> None:
        found = False
        for model in self._models:
            is_default = model["id"] == model_id
            model["is_default"] = is_default
            if is_default:
                found = True
        if found:
            self.settings_manager.set("default_model_id", model_id)
            self.save_registry()
            self._notify_default_changed(model_id)

    @staticmethod
    def _infer_chat_format(
        *,
        explicit_value: Any,
        display_name: Any = None,
        filename: Any = None,
        file_path: Any = None,
    ) -> str | None:
        explicit_text = str(explicit_value or '').strip()
        if explicit_text:
            return explicit_text

        combined = ' '.join(
            str(part or '').strip().lower()
            for part in (display_name, filename, file_path)
            if str(part or '').strip()
        )
        if 'gemma' in combined:
            return 'gemma'
        return None

    def _default_performance_settings(self) -> dict[str, int]:
        return {
            'context_size': max(512, int(self.settings_manager.get('default_context_size', DEFAULT_MODEL_PERFORMANCE['context_size']) or DEFAULT_MODEL_PERFORMANCE['context_size'])),
            'threads': max(1, int(self.settings_manager.get('default_threads', DEFAULT_MODEL_PERFORMANCE['threads']) or DEFAULT_MODEL_PERFORMANCE['threads'])),
            'max_tokens': max(64, int(self.settings_manager.get('default_max_tokens', DEFAULT_MODEL_PERFORMANCE['max_tokens']) or DEFAULT_MODEL_PERFORMANCE['max_tokens'])),
        }

    def _normalize_performance_settings(self, value: Any) -> dict[str, int]:
        base = self._default_performance_settings()
        if not isinstance(value, dict):
            return base
        return {
            'context_size': max(512, int(value.get('context_size', base['context_size']) or base['context_size'])),
            'threads': max(1, int(value.get('threads', base['threads']) or base['threads'])),
            'max_tokens': max(64, int(value.get('max_tokens', base['max_tokens']) or base['max_tokens'])),
        }

    def _relocate_model_path(self, model: dict[str, Any]) -> bool:
        """Repair a stale absolute path from another OS or drive letter.

        If the stored path does not exist but the model's filename is present
        inside the app-local models directory, the path is updated in-place
        and True is returned so the caller can persist the corrected registry.

        This makes models.json fully portable: a registry written on Windows
        (e.g. E:\\LocalSecretLounge\\data\\models\\model.gguf) is transparently repaired
        when the app is run from a USB drive on Linux or macOS.
        """
        stored = Path(model.get("path", ""))
        if stored.exists():
            return False  # path is fine as-is

        filename = model.get("filename") or stored.name
        if not filename:
            return False

        candidate = self.models_dir / filename
        if candidate.exists():
            model["path"] = str(candidate.resolve())
            return True

        return False

    def validate_all_models(self) -> list[dict[str, Any]]:
        changed = False
        default_model_id = self.settings_manager.get("default_model_id")
        for model in self._models:
            # FIX: Repair Windows/absolute paths that no longer exist on this OS.
            # If the filename is found in the local models dir, update path and
            # save the corrected registry so subsequent launches are instant.
            if self._relocate_model_path(model):
                changed = True
            validation = ModelValidator.validate_model_file(model.get("path", ""))
            if model.get("status") != validation.get("status"):
                changed = True
            if model.get("size_bytes") != validation.get("size_bytes", 0):
                changed = True
            if model.get("validation_error") != validation.get("error"):
                changed = True
            normalized_chat_format = self._infer_chat_format(
                explicit_value=model.get('chat_format'),
                display_name=model.get('name'),
                filename=model.get('filename'),
                file_path=model.get('path'),
            )
            if model.get('chat_format') != normalized_chat_format:
                changed = True
            normalized_performance = self._normalize_performance_settings(model.get('performance'))
            if model.get('performance') != normalized_performance:
                changed = True
            model["status"] = validation.get("status", "invalid")
            model["size_bytes"] = validation.get("size_bytes", 0)
            model["validation_error"] = validation.get("error")
            model["managed_storage"] = self.is_managed_model_path(model.get("path", ""))
            model["is_default"] = model["id"] == default_model_id
            model['chat_format'] = normalized_chat_format
            model['performance'] = normalized_performance
        if changed:
            self.save_registry()
        return self._models
