from __future__ import annotations

import json
import logging
from typing import Any, Iterator
from urllib import error, request

from core.settings_manager import SettingsManager

logger = logging.getLogger(__name__)

CLAUDE_API_URL = "https://api.anthropic.com/v1/messages"
CLAUDE_DEFAULT_MODEL = "claude-sonnet-4-20250514"
ANTHROPIC_VERSION = "2023-06-01"


class ClaudeAPIError(RuntimeError):
    """Raised when the Claude API cannot be reached or returns an error."""


class ClaudeClient:
    def __init__(self, api_key: str, model_id: str | None = None, timeout_seconds: float = 120.0) -> None:
        self.api_key = (api_key or "").strip()
        self.model_id = (model_id or "").strip() or CLAUDE_DEFAULT_MODEL
        self.timeout_seconds = timeout_seconds if timeout_seconds > 0 else 120.0

    @classmethod
    def from_settings(cls, settings_manager: SettingsManager) -> "ClaudeClient":
        return cls(
            api_key=str(settings_manager.get("claude_api_key", "") or ""),
            model_id=str(settings_manager.get("claude_model_id", "") or ""),
            timeout_seconds=float(settings_manager.get("claude_timeout_seconds", 120.0) or 120.0),
        )

    def test_connection(self) -> str:
        """Test the API key is valid. Returns model id on success, raises ClaudeAPIError on failure."""
        if not self.api_key:
            raise ClaudeAPIError("No Claude API key is configured. Enter your key in Settings.")
        payload = {
            "model": self.model_id,
            "max_tokens": 16,
            "messages": [{"role": "user", "content": "Hi"}],
        }
        try:
            resp = self._post(payload)
            return str(resp.get("model", self.model_id))
        except ClaudeAPIError:
            raise
        except Exception as exc:
            raise ClaudeAPIError(f"Claude API test failed: {exc}") from exc

    def chat_completion(
        self,
        messages: list[dict[str, str]],
        temperature: float = 0.8,
        max_tokens: int = 512,
        stop: list[str] | None = None,
        system: str | None = None,
    ) -> str:
        """Non-streaming chat completion. Returns the assistant text."""
        if not self.api_key:
            raise ClaudeAPIError("No Claude API key is configured. Enter your key in Settings.")

        # Anthropic API separates system from messages
        api_messages, api_system = self._split_system(messages, system)

        payload: dict[str, Any] = {
            "model": self.model_id,
            "max_tokens": max(1, max_tokens),
            "temperature": max(0.0, float(temperature)),
            "messages": api_messages,
        }
        if api_system:
            payload["system"] = api_system
        if stop:
            payload["stop_sequences"] = [s for s in stop if s.strip()]

        try:
            resp = self._post(payload)
        except ClaudeAPIError:
            raise
        except Exception as exc:
            raise ClaudeAPIError(f"Claude API request failed: {exc}") from exc

        return self._extract_text(resp)

    def chat_completion_stream(
        self,
        messages: list[dict[str, str]],
        temperature: float = 0.8,
        max_tokens: int = 512,
        stop: list[str] | None = None,
        system: str | None = None,
    ) -> Iterator[str]:
        """Streaming chat completion. Yields text chunks."""
        if not self.api_key:
            raise ClaudeAPIError("No Claude API key is configured. Enter your key in Settings.")

        api_messages, api_system = self._split_system(messages, system)

        payload: dict[str, Any] = {
            "model": self.model_id,
            "max_tokens": max(1, max_tokens),
            "temperature": max(0.0, float(temperature)),
            "messages": api_messages,
            "stream": True,
        }
        if api_system:
            payload["system"] = api_system
        if stop:
            payload["stop_sequences"] = [s for s in stop if s.strip()]

        body = json.dumps(payload).encode("utf-8")
        req = request.Request(
            CLAUDE_API_URL,
            data=body,
            headers=self._headers(),
            method="POST",
        )

        try:
            with request.urlopen(req, timeout=self.timeout_seconds) as resp:
                for raw_line in resp:
                    line = raw_line.decode("utf-8").rstrip("\n\r")
                    if not line.startswith("data:"):
                        continue
                    data_str = line[5:].strip()
                    if data_str == "[DONE]":
                        break
                    try:
                        event = json.loads(data_str)
                    except json.JSONDecodeError:
                        continue
                    chunk = self._extract_stream_delta(event)
                    if chunk:
                        yield chunk
        except error.HTTPError as exc:
            body_text = ""
            try:
                body_text = exc.read().decode("utf-8", errors="replace")
            except Exception:
                pass
            raise ClaudeAPIError(
                f"Claude API returned HTTP {exc.code}: {body_text or exc.reason}"
            ) from exc
        except error.URLError as exc:
            raise ClaudeAPIError(f"Claude API network error: {exc.reason}") from exc
        except Exception as exc:
            raise ClaudeAPIError(f"Claude API streaming error: {exc}") from exc

    # ── private helpers ──────────────────────────────────────────────────────

    def _headers(self) -> dict[str, str]:
        return {
            "x-api-key": self.api_key,
            "anthropic-version": ANTHROPIC_VERSION,
            "content-type": "application/json",
        }

    def _post(self, payload: dict[str, Any]) -> dict[str, Any]:
        body = json.dumps(payload).encode("utf-8")
        req = request.Request(
            CLAUDE_API_URL,
            data=body,
            headers=self._headers(),
            method="POST",
        )
        try:
            with request.urlopen(req, timeout=self.timeout_seconds) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except error.HTTPError as exc:
            body_text = ""
            try:
                body_text = exc.read().decode("utf-8", errors="replace")
            except Exception:
                pass
            raise ClaudeAPIError(
                f"Claude API returned HTTP {exc.code}: {body_text or exc.reason}"
            ) from exc
        except error.URLError as exc:
            raise ClaudeAPIError(f"Claude API network error: {exc.reason}") from exc

    @staticmethod
    def _split_system(
        messages: list[dict[str, str]], override_system: str | None
    ) -> tuple[list[dict[str, str]], str]:
        """Split system messages from the list; Anthropic requires them separately."""
        system_parts: list[str] = []
        api_messages: list[dict[str, str]] = []
        for msg in messages:
            role = str(msg.get("role", "")).strip().lower()
            content = str(msg.get("content", "")).strip()
            if not content:
                continue
            if role == "system":
                system_parts.append(content)
            elif role in ("user", "assistant"):
                api_messages.append({"role": role, "content": content})

        system_text = override_system or "\n\n".join(system_parts)
        # Anthropic requires messages to alternate user/assistant and start with user.
        # Ensure first message is always from user.
        if api_messages and api_messages[0]["role"] == "assistant":
            api_messages.insert(0, {"role": "user", "content": "(begin)"})
        # Ensure no two consecutive same-role messages (merge them).
        merged: list[dict[str, str]] = []
        for msg in api_messages:
            if merged and merged[-1]["role"] == msg["role"]:
                merged[-1] = {"role": msg["role"], "content": merged[-1]["content"] + "\n" + msg["content"]}
            else:
                merged.append(msg)
        if not merged:
            merged = [{"role": "user", "content": "(begin)"}]
        # Ensure last message is from user (Anthropic requirement for turn-based)
        # Actually for multi-turn we just send what we have; API handles it.
        return merged, system_text

    @staticmethod
    def _extract_text(resp: dict[str, Any]) -> str:
        content = resp.get("content", [])
        if not isinstance(content, list):
            return ""
        parts = []
        for block in content:
            if isinstance(block, dict) and block.get("type") == "text":
                parts.append(str(block.get("text", "")))
        return "\n".join(parts).strip()

    @staticmethod
    def _extract_stream_delta(event: dict[str, Any]) -> str:
        event_type = event.get("type", "")
        if event_type == "content_block_delta":
            delta = event.get("delta", {})
            if isinstance(delta, dict) and delta.get("type") == "text_delta":
                return str(delta.get("text", ""))
        return ""
