# Local Secret Lounge

**LSL (Local Secret Lounge)** is an AI chat app for immersive roleplay with customizable characters, powered by local GGUF or LM Studio models. It features advanced memory retrieval, narrative scene tracking, persistent multi-user chats, and real-time streaming, plus a PySide6 desktop interface for character discovery, management, and dynamic conversations.

## Overview

- **Desktop PySide6** character-chat application.
- Supports local GGUF models through `llama-cpp-python`.
- Supports LM Studio Local Server through the OpenAI-compatible chat endpoint.
- Saves chats, character snapshots, and chat settings under `data/`.
- Includes retrieval-augmented prompting, a SQLite-backed memory store, prompt asset loading, streaming output, and a persisted scene state machine.

## Architecture

- **`app.py`**: Creates application folders, configures logging to `run_app.log`, builds managers, and opens the main window.
- **`core/settings_manager.py`**: Loads and saves `data/settings.json`. Stores backend selection, model defaults, user name, and LM Studio settings.
- **`core/model_manager.py`**: Registers local GGUF models and imported models.
- **`core/lm_studio_client.py`**: Lists models and sends chat-completions requests to LM Studio. Supports streaming deltas from the OpenAI-compatible endpoint.
- **`core/chat_backend.py`**: Resolves whether chat requests should use a local GGUF model or LM Studio.
- **`core/character_manager.py`**: Loads discover characters and user characters. Normalizes cards and optional memory payloads.
- **`core/character_state.py`**: Applies heuristic relationship and emotion updates. Builds memory prompt lines.
- **`core/prompt_assets.py`**: Loads base prompt files from `prompts/` and character-specific prompt overrides when present.
- **`core/scene_state.py`**: Maintains a persisted scene/world state machine for phase, tension, location, hooks, and recent beats.
- **`core/memory_store.py`**: Stores character context and chat memories in SQLite. Ranks retrieval candidates with lexical overlap plus hashed-vector semantic similarity.
- **`core/chat_engine.py`**: Runs generation through `llama-cpp-python` or LM Studio. Streams partial output to the UI. Uses tokenizer-backed token counting for local GGUF models and a fallback estimate when a tokenizer is unavailable. Cleans model output before the UI receives it.
- **`core/chat_storage.py`**: Saves chats to `data/chats/<chat_id>/chat.json`. Snapshots character assets into each chat folder. Persists rolling summaries and scene state.
- **`ui/main_window.py`**: Hosts Discover Characters, My Character Library, My Chats, and Settings.
- **`ui/windows/chat_window.py`**: Builds the runtime system prompt, loads prompt assets, tracks participants and scene state. Maintains a rolling continuity summary for older turns, trims request context, retrieves relevant memory entries, and streams replies into the transcript.

## Runtime Prompt Flow

1. **Load** the selected character card and optional memory state.
2. **Load prompt assets** from `prompts/system_rules.txt`, `prompts/output_format.txt`, `prompts/scene_template.txt`, and any matching `character_rules_<slug>.txt` file.
3. **Render `scene_template.txt`** using rolling scene summary, participant memory state, recent exchange window, and the latest user message.
4. **Merge prompt assets** to build one main system message from:
   - Character system prompt
   - Bundled prompt assets
   - Current scene state machine snapshot
   - Participant canon and mutable memory lines
   - Retrieval results from the SQLite memory store
   - Rolling continuity summary for older turns
5. **Keep one refreshed system message** instead of appending new system messages during the chat. Send only this refreshed system message plus a recent token-budgeted message window to the model.
6. **Stream assistant output** into the UI, then persist the finalized cleaned reply.
7. **Save** the full transcript, rolling summary, scene state, and participant snapshots to disk.

## Retrieval and Memory Behavior

- Character context, lore, system prompts, and memory prompt lines are indexed into `data/memory_store.sqlite3`.
- User and assistant turns are indexed as searchable episodic memories.
- Retrieval is scoped to the current chat and active participants.
- Ranking uses a hybrid score:
  - Hashed-vector semantic similarity
  - Token overlap
  - Slight recency bias
- Retrieved lines are inserted into the system prompt as supporting context before generation.

## Context Management

- Older turns are folded into a **rolling summary** that is injected into the refreshed system prompt.
- Recent turns are selected against a token budget before each request.
- Local GGUF requests use model-tokenizer counts when available.
- LM Studio requests fall back to prompt-size estimation when no tokenizer is available in-process.
- Full transcripts are preserved on disk.

## Directory Structure

### Prompt Asset Files
- `prompts/system_rules.txt`
- `prompts/output_format.txt`
- `prompts/scene_template.txt`
- `prompts/character_rules_<slug>.txt`

### Chat and Character Data
- Settings: `data/settings.json`
- Model registry: `data/models/models.json`
- Discover characters: `data/discover_characters/`
- User characters: `data/characters/`
- Saved chats: `data/chats/<chat_id>/`
- Memory store database: `data/memory_store.sqlite3`
- Story-generated character template: `data/template.json`

## Installation and Execution

```bash
cd ~/LocalSecretLounge
python3 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
sudo apt install build-essential cmake libopenblas-dev
CMAKE_ARGS="-DGGML_BLAS=ON -DGGML_BLAS_VENDOR=OpenBLAS" pip install llama-cpp-python
python app.py
```

### Run Tests
```bash
python -m unittest discover -s tests -v
```

## LM Studio Local Server Setup

1. Open LM Studio.
2. Start the Local Server from the Developer tab.
3. In Local Secret Lounge, open **Settings**.
4. Enter the LM Studio base URL (usually `http://127.0.0.1:1234/v1`).
5. Set the chat backend preference to LM Studio.
6. Optionally set a preferred LM Studio model id, then test the connection.

## Notes
- The Discover Characters page is the active entry point for starting a new chat.
- Review `run_app.log` when a character pack, snapshot, or template fails to load.
- Long chats keep the full transcript on disk while generation uses a summarized older-history block plus a recent-message window.
- Scene continuity depends on both the rolling summary and the persisted scene state machine.
- Prefer updating the one main system message instead of appending new system-role messages mid-chat. Keep `system_rules.txt` and `output_format.txt` short enough that retrieval and recent history still fit into context.
