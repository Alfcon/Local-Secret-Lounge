Prompt assets reference

The live application now auto-loads these files when they exist:
- prompts/system_rules.txt
- prompts/output_format.txt
- prompts/scene_template.txt
- prompts/character_rules_<slug>.txt

Current runtime prompt flow
1. Load the selected character card and optional memory state
2. Load bundled prompt assets from prompts/
3. Render scene_template.txt using:
   - rolling scene summary
   - participant memory state
   - recent exchange window
   - latest user message
4. Merge those prompt assets with:
   - character system prompt
   - scene state machine lines
   - participant canon lines
   - mutable memory lines
   - retrieved context from the SQLite memory store
5. Refresh one main system message instead of inserting extra system messages later in the chat
6. Send only that refreshed system message plus a recent token-budgeted message window to the model

Character-specific prompt files
- The loader checks for character_rules_<slug>.txt using the character slug, id, or normalized name
- Example shipped files:
  - prompts/character_rules_maya.txt
  - prompts/character_rules_sophia.txt

Retrieval-augmented prompt additions
- Character lore, system prompts, memory prompt lines, and prior chat turns are indexed into data/memory_store.sqlite3
- Before each generation request, relevant entries are ranked and inserted as supporting context
- Retrieval is scoped to the active chat and its participants

Scene state
- The runtime prompt includes a scene-state section with:
  - phase
  - tension
  - location
  - active participants
  - recent beats
  - world-state notes
  - unresolved hooks

If you change the prompt pipeline later
- Keep this file aligned with ui/windows/chat_window.py
- Keep system_rules.txt and output_format.txt short enough that retrieval and recent history still fit into context
- Prefer updating the one main system message instead of appending new system-role messages mid-chat
