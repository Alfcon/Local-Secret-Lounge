from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re
from typing import Any, Iterable, Iterator

from core.chat_backend import is_lm_studio_model, is_ollama_model
from core.lm_studio_client import LMStudioClient
from core.ollama_client import OllamaClient
from core.settings_manager import SettingsManager


@dataclass(slots=True)
class LoadedModelInfo:
    model_id: str
    model_path: str
    chat_format: str | None
    n_ctx: int
    n_threads: int
    n_gpu_layers: int


class ChatEngine:
    """Routes chat generation to a local GGUF model or the LM Studio Local Server."""

    def __init__(self, settings_manager: SettingsManager) -> None:
        self.settings_manager = settings_manager
        self._llm: Any | None = None
        self._loaded: LoadedModelInfo | None = None

    @property
    def loaded_info(self) -> LoadedModelInfo | None:
        return self._loaded

    def unload_model(self) -> None:
        self._llm = None
        self._loaded = None

    def is_loaded_for(
        self,
        model_entry: dict[str, Any],
        *,
        n_ctx: int,
        n_threads: int,
        n_gpu_layers: int,
    ) -> bool:
        if self._loaded is None:
            return False
        return (
            self._loaded.model_id == str(model_entry.get("id", ""))
            and self._loaded.model_path == str(Path(str(model_entry.get("path", ""))).expanduser().resolve())
            and self._loaded.chat_format == self._normalize_chat_format(model_entry.get("chat_format"))
            and self._loaded.n_ctx == int(n_ctx)
            and self._loaded.n_threads == int(n_threads)
            and self._loaded.n_gpu_layers == int(n_gpu_layers)
        )

    def ensure_model_loaded(
        self,
        model_entry: dict[str, Any],
        *,
        n_ctx: int | None = None,
        n_threads: int | None = None,
        n_gpu_layers: int = 0,
    ) -> LoadedModelInfo:
        model_id = str(model_entry.get("id", "")).strip()
        model_path = Path(str(model_entry.get("path", "")).strip()).expanduser().resolve()
        if not model_id:
            raise ValueError("The selected model entry is missing an id.")
        if not str(model_path):
            raise ValueError("The selected model entry is missing a path.")
        if not model_path.exists() or not model_path.is_file():
            raise FileNotFoundError(f"Model file not found: {model_path}")
        if model_path.suffix.lower() != ".gguf":
            raise ValueError(f"Only GGUF models are supported. Invalid file: {model_path.name}")

        effective_ctx = self._effective_context_size(n_ctx)
        effective_threads = self._effective_threads(n_threads)
        effective_gpu_layers = self._effective_gpu_layers(n_gpu_layers)
        chat_format = self._normalize_chat_format(model_entry.get("chat_format"))

        if self.is_loaded_for(
            model_entry,
            n_ctx=effective_ctx,
            n_threads=effective_threads,
            n_gpu_layers=effective_gpu_layers,
        ):
            assert self._loaded is not None
            return self._loaded

        try:
            from llama_cpp import Llama
        except ImportError as exc:
            raise RuntimeError(
                "llama-cpp-python is not installed. Activate your virtual environment and run: pip install llama-cpp-python"
            ) from exc

        kwargs: dict[str, Any] = {
            "model_path": str(model_path),
            "n_ctx": effective_ctx,
            "n_threads": effective_threads,
            "n_gpu_layers": effective_gpu_layers,
            "verbose": False,
        }
        if chat_format:
            kwargs["chat_format"] = chat_format

        self.unload_model()
        self._llm = Llama(**kwargs)
        self._loaded = LoadedModelInfo(
            model_id=model_id,
            model_path=str(model_path),
            chat_format=chat_format,
            n_ctx=effective_ctx,
            n_threads=effective_threads,
            n_gpu_layers=effective_gpu_layers,
        )
        return self._loaded

    def generate_reply(
        self,
        *,
        model_entry: dict[str, Any],
        messages: list[dict[str, str]],
        temperature: float = 0.8,
        max_tokens: int | None = None,
        n_ctx: int | None = None,
        n_threads: int | None = None,
        n_gpu_layers: int = 0,
        stop: Iterable[str] | None = None,
    ) -> str:
        collected = ''.join(
            self.generate_reply_stream(
                model_entry=model_entry,
                messages=messages,
                temperature=temperature,
                max_tokens=max_tokens,
                n_ctx=n_ctx,
                n_threads=n_threads,
                n_gpu_layers=n_gpu_layers,
                stop=stop,
            )
        )
        cleaned = self.clean_generated_text(collected)
        if not cleaned:
            if is_lm_studio_model(model_entry):
                provider = 'LM Studio'
            elif is_ollama_model(model_entry):
                provider = 'Ollama'
            else:
                provider = 'local'
            raise RuntimeError(f'The {provider} model returned an empty response.')
        return cleaned

    def generate_reply_stream(
        self,
        *,
        model_entry: dict[str, Any],
        messages: list[dict[str, str]],
        temperature: float = 0.8,
        max_tokens: int | None = None,
        n_ctx: int | None = None,
        n_threads: int | None = None,
        n_gpu_layers: int = 0,
        stop: Iterable[str] | None = None,
    ) -> Iterator[str]:
        normalized_messages = self._normalize_messages(messages)
        if not normalized_messages:
            raise ValueError("No valid messages were provided to the chat engine.")

        effective_temperature = self._effective_temperature(temperature)
        effective_max_tokens = self._effective_max_tokens(max_tokens)
        stop_sequences = [str(item) for item in (stop or []) if str(item).strip()]

        if is_lm_studio_model(model_entry):
            client = LMStudioClient(
                base_url=str(
                    model_entry.get('lm_studio_base_url')
                    or self.settings_manager.get('lm_studio_base_url', 'http://127.0.0.1:1234/v1')
                ),
                api_key=str(
                    model_entry.get('lm_studio_api_key')
                    or self.settings_manager.get('lm_studio_api_key', '')
                    or ''
                ),
                timeout_seconds=float(self.settings_manager.get('lm_studio_timeout_seconds', 0.0) or 0.0),
            )
            emitted = False
            for chunk in client.chat_completion_stream(
                model_id=str(model_entry.get('lm_studio_model_id') or model_entry.get('id') or '').replace('lmstudio::', ''),
                messages=normalized_messages,
                temperature=effective_temperature,
                max_tokens=effective_max_tokens,
                stop=stop_sequences,
            ):
                if chunk:
                    emitted = True
                    yield chunk
            if not emitted:
                reply = client.chat_completion(
                    model_id=str(model_entry.get('lm_studio_model_id') or model_entry.get('id') or '').replace('lmstudio::', ''),
                    messages=normalized_messages,
                    temperature=effective_temperature,
                    max_tokens=effective_max_tokens,
                    stop=stop_sequences,
                )
                if reply:
                    yield reply
            return

        if is_ollama_model(model_entry):
            client = OllamaClient(
                base_url=str(
                    model_entry.get('ollama_base_url')
                    or self.settings_manager.get('ollama_base_url', 'http://127.0.0.1:11434/v1')
                ),
                api_key=str(
                    model_entry.get('ollama_api_key')
                    or self.settings_manager.get('ollama_api_key', '')
                    or ''
                ),
                timeout_seconds=float(self.settings_manager.get('ollama_timeout_seconds', 0.0) or 0.0),
            )
            emitted = False
            for chunk in client.chat_completion_stream(
                model_id=str(model_entry.get('ollama_model_id') or model_entry.get('id') or '').replace('ollama::', ''),
                messages=normalized_messages,
                temperature=effective_temperature,
                max_tokens=effective_max_tokens,
                stop=stop_sequences,
            ):
                if chunk:
                    emitted = True
                    yield chunk
            if not emitted:
                reply = client.chat_completion(
                    model_id=str(model_entry.get('ollama_model_id') or model_entry.get('id') or '').replace('ollama::', ''),
                    messages=normalized_messages,
                    temperature=effective_temperature,
                    max_tokens=effective_max_tokens,
                    stop=stop_sequences,
                )
                if reply:
                    yield reply
            return

        loaded = self.ensure_model_loaded(
            model_entry,
            n_ctx=n_ctx,
            n_threads=n_threads,
            n_gpu_layers=n_gpu_layers,
        )
        assert self._llm is not None

        chat_kwargs: dict[str, Any] = {
            "messages": normalized_messages,
            "temperature": effective_temperature,
            "max_tokens": effective_max_tokens,
            "stream": True,
        }
        if stop_sequences:
            chat_kwargs["stop"] = stop_sequences

        try:
            emitted = False
            for chunk in self._llm.create_chat_completion(**chat_kwargs):
                piece = self._extract_chat_stream_delta(chunk)
                if piece:
                    emitted = True
                    yield piece
            if emitted:
                return
            raise RuntimeError('Local chat completion stream produced no output.')
        except Exception as chat_exc:
            prompt = self._messages_to_prompt(normalized_messages)
            completion_kwargs: dict[str, Any] = {
                "prompt": prompt,
                "temperature": effective_temperature,
                "max_tokens": effective_max_tokens,
                "stream": True,
            }
            if stop_sequences:
                completion_kwargs["stop"] = stop_sequences
            try:
                emitted = False
                for chunk in self._llm.create_completion(**completion_kwargs):
                    piece = self._extract_completion_stream_delta(chunk)
                    if piece:
                        emitted = True
                        yield piece
                if emitted:
                    return
                raise RuntimeError('Local completion stream produced no output.')
            except Exception as completion_exc:
                model_name = str(model_entry.get("name") or loaded.model_id)
                raise RuntimeError(
                    "Local generation failed for "
                    f"{model_name}. Chat completion error: {chat_exc}. "
                    f"Fallback completion error: {completion_exc}"
                ) from completion_exc

    def count_message_tokens(
        self,
        *,
        model_entry: dict[str, Any],
        messages: list[dict[str, str]],
        n_ctx: int | None = None,
        n_threads: int | None = None,
        n_gpu_layers: int = 0,
    ) -> int:
        normalized_messages = self._normalize_messages(messages)
        if not normalized_messages:
            return 0
        prompt = self._messages_to_prompt(normalized_messages)
        if not is_lm_studio_model(model_entry):
            try:
                self.ensure_model_loaded(
                    model_entry,
                    n_ctx=n_ctx,
                    n_threads=n_threads,
                    n_gpu_layers=n_gpu_layers,
                )
                assert self._llm is not None
                tokens = self._llm.tokenize(prompt.encode('utf-8'), add_bos=False, special=True)
                return len(tokens)
            except Exception:
                pass
        return self.estimate_message_tokens(messages=normalized_messages)

    def estimate_message_tokens(self, *, messages: list[dict[str, str]]) -> int:
        total = 0
        for message in self._normalize_messages(messages):
            total += 4 + self._estimate_text_tokens(message.get('role', '')) + self._estimate_text_tokens(message.get('content', ''))
        return total

    @staticmethod
    def clean_generated_text(text: str) -> str:
        cleaned = ChatEngine._clean_response_text(text)
        if not cleaned:
            return ''
        return cleaned

    def build_initial_messages(self, character: dict[str, Any]) -> list[dict[str, str]]:
        messages: list[dict[str, str]] = []
        system_prompt = str(character.get("system_prompt", "")).strip()
        greeting = str(character.get("greeting", "")).strip()
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        if greeting:
            messages.append({"role": "assistant", "content": greeting})
        return messages

    def get_model_status_text(self) -> str:
        if self._loaded is None:
            return "No model loaded"
        return (
            f"Loaded: {self._loaded.model_id} | ctx={self._loaded.n_ctx} | "
            f"threads={self._loaded.n_threads} | gpu_layers={self._loaded.n_gpu_layers}"
        )

    def _effective_context_size(self, value: int | None) -> int:
        ctx = int(value or self.settings_manager.get("default_context_size", 4096) or 4096)
        return max(256, ctx)

    def _effective_threads(self, value: int | None) -> int:
        threads = int(value or self.settings_manager.get("default_threads", 4) or 4)
        return max(1, threads)

    @staticmethod
    def _effective_gpu_layers(value: int | None) -> int:
        gpu_layers = int(value or 0)
        return max(0, gpu_layers)

    def _effective_max_tokens(self, value: int | None) -> int:
        max_tokens = int(value or self.settings_manager.get("default_max_tokens", 512) or 512)
        return max(1, max_tokens)

    @staticmethod
    def _effective_temperature(value: float | int | None) -> float:
        temperature = float(value if value is not None else 0.8)
        return max(0.0, temperature)

    @staticmethod
    def _normalize_chat_format(value: Any) -> str | None:
        if value is None:
            return None
        text = str(value).strip()
        return text or None

    @staticmethod
    def _normalize_messages(messages: list[dict[str, str]]) -> list[dict[str, str]]:
        normalized: list[dict[str, str]] = []
        for message in messages:
            if not isinstance(message, dict):
                continue
            role = str(message.get("role", "")).strip().lower()
            content = str(message.get("content", "")).strip()
            if role not in {"system", "user", "assistant"}:
                continue
            if not content:
                continue
            normalized.append({"role": role, "content": content})
        return normalized

    @staticmethod
    def _extract_chat_content(response: Any) -> str:
        if not isinstance(response, dict):
            raise TypeError("Expected dict response from create_chat_completion.")
        choices = response.get("choices")
        if not isinstance(choices, list) or not choices:
            raise ValueError("Chat completion returned no choices.")
        first_choice = choices[0]
        if not isinstance(first_choice, dict):
            raise TypeError("Chat completion choice was not a dict.")
        message = first_choice.get("message", {})
        if not isinstance(message, dict):
            raise TypeError("Chat completion message was not a dict.")
        content = message.get("content", "")
        if isinstance(content, list):
            joined = []
            for item in content:
                if isinstance(item, dict):
                    text_value = item.get("text") or item.get("content") or ""
                    joined.append(str(text_value))
                else:
                    joined.append(str(item))
            return "\n".join(part for part in joined if part).strip()
        return str(content).strip()

    @staticmethod
    def _extract_chat_stream_delta(response: Any) -> str:
        if not isinstance(response, dict):
            return ''
        choices = response.get('choices')
        if not isinstance(choices, list) or not choices:
            return ''
        first_choice = choices[0] if isinstance(choices[0], dict) else {}
        delta = first_choice.get('delta', {})
        if isinstance(delta, dict):
            content = delta.get('content', '')
            if isinstance(content, str):
                return content
            if isinstance(content, list):
                return ''.join(str(item.get('text') or item.get('content') or '') if isinstance(item, dict) else str(item) for item in content)
        text = first_choice.get('text', '')
        return str(text or '')

    @staticmethod
    def _extract_completion_text(response: Any) -> str:
        if not isinstance(response, dict):
            raise TypeError("Expected dict response from create_completion.")
        choices = response.get("choices")
        if not isinstance(choices, list) or not choices:
            raise ValueError("Completion returned no choices.")
        first_choice = choices[0]
        if not isinstance(first_choice, dict):
            raise TypeError("Completion choice was not a dict.")
        return str(first_choice.get("text", "")).strip()

    @staticmethod
    def _extract_completion_stream_delta(response: Any) -> str:
        if not isinstance(response, dict):
            return ''
        choices = response.get('choices')
        if not isinstance(choices, list) or not choices:
            return ''
        first_choice = choices[0] if isinstance(choices[0], dict) else {}
        return str(first_choice.get('text', '') or '')

    @staticmethod
    def _messages_to_prompt(messages: list[dict[str, str]]) -> str:
        parts: list[str] = []
        for message in messages:
            role = message["role"].upper()
            content = message["content"].strip()
            parts.append(f"{role}: {content}")
        parts.append("ASSISTANT:")
        return "\n\n".join(parts)

    @staticmethod
    def _estimate_text_tokens(text: str) -> int:
        cleaned = str(text or '').strip()
        if not cleaned:
            return 0
        word_estimate = len(re.findall(r'\S+', cleaned))
        char_estimate = max(1, len(cleaned) // 4)
        return max(word_estimate, char_estimate)

    @staticmethod
    def _strip_trailing_choice_prompt(text: str) -> str:
        cleaned = str(text or '').strip()
        if not cleaned:
            return cleaned

        prompt_pattern = re.compile(
            r'(?:\n\s*\n|^)(?P<line>(?:Do you want to|Would you like to|Do you wanna|Or maybe)\b[^\n!?]*'
            r'(?:\?|instead\?))\s*$',
            flags=re.IGNORECASE,
        )
        while True:
            match = prompt_pattern.search(cleaned)
            if match is None:
                break
            cleaned = cleaned[:match.start()].rstrip()
        return cleaned

    @staticmethod
    def _remove_standalone_artifact_lines(text: str) -> str:
        cleaned = str(text or '')
        cleaned = re.sub(r'(?m)^\s*[.]{1,3}\s*$', '', cleaned)
        cleaned = re.sub(r'(?m)^\s*[.…]{2,}\s*$', '', cleaned)
        cleaned = re.sub(r'(?m)^\s*[-•*]+\s*$', '', cleaned)
        while '\n\n\n' in cleaned:
            cleaned = cleaned.replace('\n\n\n', '\n\n')
        return cleaned.strip()

    @staticmethod
    def _clean_response_text(text: str) -> str:
        cleaned = str(text or "").replace("\r\n", "\n").replace("\xa0", " ")
        cleaned = re.sub(r"[ \t]+\n", "\n", cleaned)
        cleaned = cleaned.strip()
        cleaned = re.sub(r"(?:^|\n)\s*[-*_]{3,}\s*(?=\n|$)", "", cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r"(?:^|\n)\s*continue the scene\.?\s*$", "", cleaned, flags=re.IGNORECASE | re.MULTILINE)
        cleaned = re.sub(
            r"\n+\s*(?:to proceed\b|please tell\b|tell (?:maya|her|him|them)\b|how do you respond\b|what do you do next\b).*$",
            "",
            cleaned,
            flags=re.IGNORECASE | re.DOTALL,
        )
        cleaned = re.sub(r"(?:^|\n)\s*no system prompting\s*(?=\n|$)", "\n", cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r"(?:^|\n)\s*\[[0-9]{1,2}:[0-9]{2}\]\s*[^\n]+(?=\n|$)", "\n", cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r"(?<=\S)\s+[0-9]{1,2}\s*$", "", cleaned)
        cleaned = re.sub(r"\n\s*[0-9]{1,2}\s*$", "", cleaned)
        cleaned = ChatEngine._strip_trailing_choice_prompt(cleaned)
        cleaned = ChatEngine._remove_standalone_artifact_lines(cleaned)
        while "\n\n\n" in cleaned:
            cleaned = cleaned.replace("\n\n\n", "\n\n")
        return cleaned.strip()
