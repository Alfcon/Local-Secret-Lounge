from __future__ import annotations

import json
import logging
import socket
from typing import Any
from urllib import error, parse, request
from urllib.response import addinfourl

from core.settings_manager import SettingsManager

logger = logging.getLogger(__name__)


class OllamaError(RuntimeError):
    """Raised when the Ollama Local Server cannot be reached or returns an invalid response."""


class OllamaClient:
    def __init__(self, base_url: str, api_key: str | None = None, timeout_seconds: float | None = 0.0) -> None:
        normalized = (base_url or '').strip()
        if not normalized:
            normalized = 'http://127.0.0.1:11434/v1'
        normalized = normalized.rstrip('/')
        if normalized.endswith('/v1'):  # noqa: SIM113
            self.base_url = normalized
        else:
            self.base_url = f'{normalized}/v1'
        self.api_key = (api_key or '').strip()

        raw_timeout = 0.0 if timeout_seconds is None else float(timeout_seconds)
        self.timeout_seconds: float | None = raw_timeout if raw_timeout > 0 else None

    @classmethod
    def from_settings(cls, settings_manager: SettingsManager) -> 'OllamaClient':
        return cls(
            base_url=str(settings_manager.get('ollama_base_url', 'http://127.0.0.1:11434/v1')),
            api_key=str(settings_manager.get('ollama_api_key', '') or ''),
            timeout_seconds=float(settings_manager.get('ollama_timeout_seconds', 0.0) or 0.0),
        )

    def list_models(self) -> list[dict[str, Any]]:
        payload = self._request_json('GET', '/models')
        if isinstance(payload, dict):
            data = payload.get('data', [])
        elif isinstance(payload, list):
            data = payload
        else:
            raise OllamaError('Ollama returned an invalid response for /models.')
        if not isinstance(data, list):
            raise OllamaError('Ollama returned an invalid model list.')

        models: list[dict[str, Any]] = []
        for item in data:
            if isinstance(item, dict) and str(item.get('id', '')).strip():
                models.append(item)
        return models

    def resolve_model(self, preferred_model_id: str | None = None) -> dict[str, Any]:
        models = self.list_models()
        if not models:
            raise OllamaError(
                'No Ollama models are available. Start the Ollama Local Server and load a model first.'
            )

        preferred = str(preferred_model_id or '').strip()
        selected: dict[str, Any] | None = None
        if preferred:
            selected = next((model for model in models if str(model.get('id')) == preferred), None)
            if selected is None:
                available = ', '.join(str(model.get('id', '')) for model in models[:8])
                raise OllamaError(
                    f"Ollama model '{preferred}' was not found on the local server. "
                    f"Available models: {available or 'none'}"
                )
        else:
            selected = models[0]

        model_id = str(selected.get('id', '')).strip()
        return {
            'id': f'ollama::{model_id}',
            'name': f'Ollama — {model_id}',
            'provider': 'ollama',
            'source': 'ollama_server',
            'path': '',
            'status': 'available',
            'is_default': bool(self.base_url),
            'ollama_model_id': model_id,
            'ollama_base_url': self.base_url,
        }

    def chat_completion(
        self,
        *,
        model_id: str,
        messages: list[dict[str, str]],
        temperature: float,
        max_tokens: int,
        stop: list[str] | None = None,
    ) -> str:
        payload: dict[str, Any] = {
            'model': model_id,
            'messages': messages,
            'temperature': float(temperature),
            'max_tokens': int(max_tokens),
            'stream': False,
        }
        if stop:
            payload['stop'] = stop

        response_payload = self._request_json('POST', '/chat/completions', payload)
        if not isinstance(response_payload, dict):
            raise OllamaError('Ollama returned an invalid response for /chat/completions.')

        choices = response_payload.get('choices', [])
        if not isinstance(choices, list) or not choices:
            raise OllamaError('Ollama returned no completion choices.')

        first_choice = choices[0] if isinstance(choices[0], dict) else {}
        message = first_choice.get('message', {})
        if isinstance(message, dict):
            content = message.get('content')
            if isinstance(content, str) and content.strip():
                return content.strip()

        text = first_choice.get('text')
        if isinstance(text, str) and text.strip():
            return text.strip()

        raise OllamaError('Ollama returned an empty response.')

    def chat_completion_stream(
        self,
        *,
        model_id: str,
        messages: list[dict[str, str]],
        temperature: float,
        max_tokens: int,
        stop: list[str] | None = None,
    ):
        payload: dict[str, Any] = {
            'model': model_id,
            'messages': messages,
            'temperature': float(temperature),
            'max_tokens': int(max_tokens),
            'stream': True,
        }
        if stop:
            payload['stop'] = stop

        response = self._open_request('POST', '/chat/completions', payload)
        try:
            for raw_line in response:
                line = raw_line.decode('utf-8', errors='replace').strip()
                if not line or not line.startswith('data:'):
                    continue
                payload_text = line[5:].strip()
                if not payload_text or payload_text == '[DONE]':
                    continue
                try:
                    item = json.loads(payload_text)
                except json.JSONDecodeError:
                    continue
                if not isinstance(item, dict):
                    continue
                choices = item.get('choices', [])
                if not isinstance(choices, list) or not choices:
                    continue
                first_choice = choices[0] if isinstance(choices[0], dict) else {}
                delta = first_choice.get('delta', {})
                if not isinstance(delta, dict):
                    continue
                content = delta.get('content')
                if isinstance(content, str) and content:
                    yield content
                elif isinstance(content, list):
                    joined = []
                    for piece in content:
                        if isinstance(piece, dict):
                            joined.append(str(piece.get('text') or piece.get('content') or ''))
                        else:
                            joined.append(str(piece))
                    merged = ''.join(part for part in joined if part)
                    if merged:
                        yield merged
        finally:
            response.close()

    def _open_request(self, method: str, endpoint: str, payload: dict[str, Any] | None = None) -> addinfourl:
        url = parse.urljoin(f'{self.base_url}/', endpoint.lstrip('/'))
        data = None
        headers = {'Content-Type': 'application/json'}
        if self.api_key:
            headers['Authorization'] = f'Bearer {self.api_key}'
        if payload is not None:
            data = json.dumps(payload).encode('utf-8')

        req = request.Request(url, data=data, headers=headers, method=method.upper())
        if self.timeout_seconds is None:
            return request.urlopen(req)
        return request.urlopen(req, timeout=self.timeout_seconds)

    def _request_json(self, method: str, endpoint: str, payload: dict[str, Any] | None = None) -> Any:
        try:
            response = self._open_request(method, endpoint, payload)
            with response:
                charset = response.headers.get_content_charset('utf-8')
                return json.loads(response.read().decode(charset))
        except error.HTTPError as exc:
            detail = ''
            try:
                detail = exc.read().decode('utf-8', errors='replace').strip()
            except Exception as read_exc:
                logger.debug('Could not read Ollama HTTP error payload for %s: %s', endpoint, read_exc)
                detail = ''
            raise OllamaError(
                f'Ollama request failed with HTTP {exc.code} for {endpoint}: {detail or exc.reason}'
            ) from exc
        except socket.timeout as exc:
            raise OllamaError(
                'Ollama did not finish before the configured timeout. '
                'Raise ollama_timeout_seconds in settings.json, or set it to 0 to wait indefinitely.'
            ) from exc
        except error.URLError as exc:
            raise OllamaError(
                f'Could not connect to Ollama at {self.base_url}. '
                'Start the Ollama Local Server and confirm the URL in Settings.'
            ) from exc
        except json.JSONDecodeError as exc:
            raise OllamaError(f'Ollama returned invalid JSON for {endpoint}.') from exc
