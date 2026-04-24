# Local Secret Lounge (LSL)

**Local Secret Lounge (LSL)** is an Adult Chat program that runs on a Local LLM. It provides an immersive roleplay experience with customizable characters, featuring advanced memory retrieval, narrative scene tracking, persistent multi-user chats, and real-time streaming. It includes a PySide6 desktop interface for character discovery, management, and dynamic conversations.

**Important Note**: Local Secret Lounge does not run models directly within the application. You **must** install and use an external local LLM server such as **LM Studio** or **Ollama**.

## Overview

- **Adult Chat Program** powered by a Local LLM via LM Studio or Ollama.
- **Desktop PySide6** character-chat application.
- Supports LM Studio Local Server and Ollama through their OpenAI-compatible chat endpoints.
- Saves chats, character snapshots, character creation, and chat settings under `data/`.
- Example character is Julie Jones.
- Includes retrieval-augmented prompting, a SQLite-backed memory store, prompt asset loading, streaming output, and a persisted scene state machine.

## Architecture

- **`app.py`**: Creates application folders, configures logging to `run_app.log`, builds managers, and opens the main window.
- **`core/settings_manager.py`**: Loads and saves `data/settings.json`. Stores backend selection, model defaults, user name, LM Studio, and Ollama settings.
- **`core/model_manager.py`**: Registers imported models.
- **`core/lm_studio_client.py`**: Lists models and sends chat-completions requests to LM Studio. Supports streaming deltas from the OpenAI-compatible endpoint.
- **`core/ollama_client.py`**: Lists models and sends chat-completions requests to Ollama. Supports streaming deltas from the OpenAI-compatible endpoint.
- **`core/chat_backend.py`**: Resolves whether chat requests should use LM Studio or Ollama.
- **`core/character_manager.py`**: Loads discover characters and user characters. Normalizes cards and optional memory payloads.
- **`core/character_state.py`**: Applies heuristic relationship and emotion updates. Builds memory prompt lines.
- **`core/prompt_assets.py`**: Loads base prompt files from `prompts/` and character-specific prompt overrides when present.
- **`core/scene_state.py`**: Maintains a persisted scene/world state machine for phase, tension, location, hooks, and recent beats.
- **`core/memory_store.py`**: Stores character context and chat memories in SQLite. Ranks retrieval candidates with lexical overlap plus hashed-vector semantic similarity.
- **`core/chat_engine.py`**: Runs generation through LM Studio or Ollama. Streams partial output to the UI. Cleans model output before the UI receives it.
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
- LM Studio and Ollama requests fall back to prompt-size estimation since a tokenizer is unavailable in-process.
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

### Requirements Based on the Code
The core dependencies for this project are required for UI and background processing. These are defined in `requirements.txt`:
- `PySide6` (for the desktop interface)
- `psutil`

### Recommended Model
For the best experience with the local chat, we recommend using the following model:
- [Dirty-Muse-Writer-v01-Uncensored-Erotica-NSFW-Q4_K_M-GGUF](https://huggingface.co/TheDrunkenSnail/Dirty-Muse-Writer-v01-Uncensored-Erotica-NSFW-Q4_K_M-GGUF?not-for-all-audiences=true)

#### Ollama Pull Command for Recommended Model:
If using Ollama, you can download and run this HuggingFace model directly using the following command in your terminal:
```bash
ollama run hf.co/TheDrunkenSnail/Dirty-Muse-Writer-v01-Uncensored-Erotica-NSFW-Q4_K_M-GGUF
```
#### LM Studio Steps To Load The Recommended Model:
Open LM Studio
Go to Model search.
Search for: Dirty-Muse-Writer-v01-Uncensored-Erotica-NSFW-Q4_K_M-GGUF
Click Download 

### Windows (using Miniconda)

Miniconda is to be installed for Windows systems to easily manage dependencies and environments.

1. Download and install [Miniconda](https://docs.anaconda.com/miniconda/).
2. Open the Anaconda Prompt (Miniconda3) and run the following commands:

```cmd
git clone https://github.com/Alfcon/Local-Secret-Lounge.git
cd Local-Secret-Lounge
conda create -n lsl-env python=3.11
conda activate lsl-env
pip install --upgrade pip
pip install -r requirements.txt

python app.py
```

### Linux

```bash
git clone https://github.com/Alfcon/Local-Secret-Lounge.git
cd Local-Secret-Lounge
python3 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt

python app.py
```

### Run Tests
```bash
python -m unittest discover -s tests -v
```

## Setup a Local LLM Server

You must use an external application like LM Studio or Ollama to run the models.

### Ollama Setup
1. Download and install [Ollama](https://ollama.com/).
2. Pull the recommended model (or another model) by running the pull command in your terminal. For example:
   ```bash
   ollama run hf.co/TheDrunkenSnail/Dirty-Muse-Writer-v01-Uncensored-Erotica-NSFW-Q4_K_M-GGUF
   ```
3. In Local Secret Lounge, open **Settings**.
4. Set the chat backend preference to **Ollama**.
5. Test the connection.

### LM Studio Setup
1. Download and open [LM Studio](https://lmstudio.ai/).
2. Download your preferred model within LM Studio.
3. Start the Local Server from the Developer tab.
4. Click: + Load Model.
5. Select: Dirty-Muse-Writer-v01-Uncensored-Erotica-NSFW-Q4_K_M-GGUF.
6. In Local Secret Lounge, open **Settings**.
7. Enter the LM Studio base URL (usually `http://127.0.0.1:1234/v1`).
8. Set the chat backend preference to **LM Studio**.
9. Optionally set a preferred LM Studio model id, then test the connection.

## Notes
- The Discover Characters page is the active entry point for starting a new chat.
- Review `run_app.log` when a character pack, snapshot, or template fails to load.
- Long chats keep the full transcript on disk while generation uses a summarized older-history block plus a recent-message window.
- Scene continuity depends on both the rolling summary and the persisted scene state machine.
- Prefer updating the one main system message instead of appending new system-role messages mid-chat. Keep `system_rules.txt` and `output_format.txt` short enough that retrieval and recent history still fit into context.
