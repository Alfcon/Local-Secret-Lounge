from __future__ import annotations

import fnmatch
import logging
import os
import tempfile
import webbrowser
from pathlib import Path
from typing import Callable

import requests

from core.paths import get_models_dir
from core.settings_manager import SettingsManager

ProgressCallback = Callable[[int, int, str], None]

logger = logging.getLogger(__name__)


class HFDownloader:
    """Hugging Face GGUF downloader with progress callbacks for the desktop UI."""

    def __init__(self, settings_manager: SettingsManager) -> None:
        self.settings_manager = settings_manager

    def open_repo_in_browser(self, repo_id: str | None = None) -> None:
        if repo_id:
            webbrowser.open(f"https://huggingface.co/{repo_id.strip()}")
        else:
            webbrowser.open("https://huggingface.co/")

    def download_single_file(
        self,
        repo_id: str,
        filename: str,
        local_dir: str | None = None,
        token: str | None = None,
        progress_callback: ProgressCallback | None = None,
    ) -> str:
        self._ensure_online()
        self._ensure_repo_id(repo_id)
        self._ensure_gguf_name(filename)
        return self._download_resolved_file(
            repo_id=repo_id,
            filename=filename.strip(),
            local_dir=local_dir,
            token=token,
            progress_callback=progress_callback,
        )

    def download_matching_file(
        self,
        repo_id: str,
        pattern: str,
        local_dir: str | None = None,
        token: str | None = None,
        progress_callback: ProgressCallback | None = None,
    ) -> str:
        self._ensure_online()
        self._ensure_repo_id(repo_id)
        if not pattern.strip():
            raise ValueError('Enter a filename or wildcard pattern.')

        filename = self._resolve_matching_filename(repo_id=repo_id, pattern=pattern, token=token)
        return self._download_resolved_file(
            repo_id=repo_id,
            filename=filename,
            local_dir=local_dir,
            token=token,
            progress_callback=progress_callback,
        )

    def _resolve_matching_filename(self, repo_id: str, pattern: str, token: str | None = None) -> str:
        try:
            from huggingface_hub import HfApi
        except ImportError as exc:
            raise RuntimeError('huggingface_hub is not installed. Run: pip install huggingface_hub') from exc

        try:
            api = HfApi(token=token or None)
            repo_files = api.list_repo_files(repo_id=repo_id.strip(), repo_type='model')
        except Exception as exc:
            raise RuntimeError(self._friendly_error_message(exc)) from exc

        matches = sorted(
            file_name
            for file_name in repo_files
            if fnmatch.fnmatch(file_name, pattern.strip()) and file_name.lower().endswith('.gguf')
        )
        if not matches:
            raise FileNotFoundError('No .gguf files matched that pattern in the selected repo.')
        if len(matches) > 1:
            sample = '\n'.join(matches[:10])
            raise ValueError(
                'Multiple .gguf files matched. Use a more specific filename or pattern.\n\n'
                f'Matches:\n{sample}'
            )
        return matches[0]

    def _download_resolved_file(
        self,
        *,
        repo_id: str,
        filename: str,
        local_dir: str | None,
        token: str | None,
        progress_callback: ProgressCallback | None,
    ) -> str:
        try:
            from huggingface_hub import hf_hub_url
        except ImportError as exc:
            raise RuntimeError('huggingface_hub is not installed. Run: pip install huggingface_hub') from exc

        destination_root = Path(local_dir).expanduser().resolve() if local_dir else get_models_dir().resolve()
        destination_root.mkdir(parents=True, exist_ok=True)
        destination_path = destination_root / filename
        destination_path.parent.mkdir(parents=True, exist_ok=True)
        temp_handle = None

        headers = {}
        if token:
            headers['Authorization'] = f'Bearer {token.strip()}'

        url = hf_hub_url(repo_id=repo_id.strip(), filename=filename, repo_type='model')
        if progress_callback is not None:
            progress_callback(0, 0, 'Preparing download...')

        try:
            with requests.get(url, headers=headers, stream=True, timeout=60) as response:
                if response.status_code >= 400:
                    self._raise_http_error(response, repo_id, filename, token)

                total_bytes = int(response.headers.get('Content-Length') or 0)
                downloaded = 0
                temp_handle = tempfile.NamedTemporaryFile(delete=False, dir=str(destination_path.parent), suffix='.part')
                try:
                    for chunk in response.iter_content(chunk_size=1024 * 1024):
                        if not chunk:
                            continue
                        temp_handle.write(chunk)
                        downloaded += len(chunk)
                        if progress_callback is not None:
                            progress_callback(downloaded, total_bytes, f'Downloading {os.path.basename(filename)}...')
                finally:
                    temp_handle.close()

            os.replace(temp_handle.name, destination_path)
            if progress_callback is not None:
                final_total = total_bytes or int(destination_path.stat().st_size)
                progress_callback(final_total, final_total, 'Download complete.')
            return str(destination_path.resolve())
        except requests.Timeout as exc:
            raise RuntimeError('The download timed out while contacting Hugging Face. Try again.') from exc
        except requests.ConnectionError as exc:
            raise RuntimeError('Could not connect to Hugging Face. Check your internet connection and try again.') from exc
        except requests.RequestException as exc:
            raise RuntimeError(self._friendly_error_message(exc)) from exc
        except OSError as exc:
            raise RuntimeError(f'Could not write the downloaded model file: {exc}') from exc
        finally:
            if temp_handle is not None:
                try:
                    temp_name = temp_handle.name
                except Exception as exc:
                    logger.debug('Could not inspect temporary download file handle: %s', exc)
                    temp_name = None
                if temp_name and os.path.exists(temp_name):
                    try:
                        os.remove(temp_name)
                    except OSError:
                        pass

    def _raise_http_error(self, response: requests.Response, repo_id: str, filename: str, token: str | None) -> None:
        status_code = response.status_code
        if status_code == 401:
            raise RuntimeError('Authentication is required for this model or file. Add a valid Hugging Face access token.')
        if status_code == 403:
            if token:
                raise RuntimeError('Access to this model or file is forbidden. It may be gated or your token may not have access.')
            raise RuntimeError('This model appears to be gated or restricted. Add an access token with permission to download it.')
        if status_code == 404:
            raise RuntimeError(
                f"The repo or file was not found on Hugging Face. Check the repo id and filename.\n\nRepo: {repo_id}\nFile: {filename}"
            )
        raise RuntimeError(f'Hugging Face returned HTTP {status_code}: {response.reason}')

    def _ensure_online(self) -> None:
        if self.settings_manager.is_offline_mode():
            raise RuntimeError('Offline mode is enabled. Disable it before downloading from Hugging Face.')

    @staticmethod
    def _ensure_repo_id(repo_id: str) -> None:
        if not repo_id or '/' not in repo_id.strip():
            raise ValueError("Enter a valid Hugging Face repo id such as 'org/model-name'.")

    @staticmethod
    def _ensure_gguf_name(filename: str) -> None:
        if not filename.strip().lower().endswith('.gguf'):
            raise ValueError('Only direct .gguf downloads are supported in version 1.')

    @staticmethod
    def _friendly_error_message(exc: Exception) -> str:
        message = str(exc).strip() or exc.__class__.__name__
        lower = message.lower()
        if '401' in lower or 'unauthorized' in lower:
            return 'Authentication is required for this download. Add a valid Hugging Face access token.'
        if '403' in lower or 'forbidden' in lower or 'gated' in lower:
            return 'Access to this model is restricted or gated. Make sure your token has permission.'
        if '404' in lower or 'not found' in lower:
            return 'The requested Hugging Face repo or file was not found. Check the repo id and filename.'
        if 'connection' in lower or 'network' in lower:
            return 'Network error while contacting Hugging Face. Check your connection and try again.'
        return message
