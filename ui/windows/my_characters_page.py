from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QListWidget, QListWidgetItem, QFrame, QSplitter,
    QTextEdit, QFileDialog, QMessageBox, QLineEdit, QFormLayout,
    QScrollArea, QSizePolicy, QDialog, QDialogButtonBox,
    QSpinBox, QDoubleSpinBox, QTabWidget, QGridLayout,
)
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QFont

from core.character_manager import CharacterManager
from core.chat_storage import ChatStorage
from ui.widgets.avatar_label import AvatarLabel
from ui.widgets.character_image import CharacterImage

logger = logging.getLogger(__name__)


class EditMemoryDialog(QDialog):
    """Dialog for viewing and editing a user-created character's memory.json."""

    def __init__(
        self,
        character: dict[str, Any],
        character_manager: CharacterManager,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._character = character
        self._character_manager = character_manager
        self._char_id = str(character.get("id", character.get("name", ""))).strip()
        self.setWindowTitle(f"Edit Memory — {character.get('name', '')}")
        self.setMinimumSize(720, 640)
        self.setModal(True)
        self._memory: dict[str, Any] = {}
        self._build_ui()
        self._load()

    # ── UI construction ────────────────────────────────────────────────

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setSpacing(10)
        root.setContentsMargins(20, 20, 20, 20)

        header = QLabel(f"🧠  Memory Editor — <b>{self._character.get('name', '')}</b>")
        header.setStyleSheet("font-size: 14px; color: #c8c8e0; margin-bottom: 4px;")
        root.addWidget(header)

        hint = QLabel(
            "Edit the character's remembered knowledge, relationship scores, emotional state, "
            "memories and scene flags. Changes are written directly to <code>memory.json</code>."
        )
        hint.setWordWrap(True)
        hint.setStyleSheet("font-size: 11px; color: #8888a8; margin-bottom: 6px;")
        root.addWidget(hint)

        self.tabs = QTabWidget()
        self.tabs.setStyleSheet(
            "QTabWidget::pane { border: 1px solid #3a3a5a; border-radius: 4px; }"
            "QTabBar::tab { background: #1a1a3a; color: #a0a0c0; padding: 6px 14px; }"
            "QTabBar::tab:selected { background: #0f3460; color: #ffffff; }"
        )
        root.addWidget(self.tabs, stretch=1)

        self._build_relationship_tab()
        self._build_emotional_tab()
        self._build_memories_tab()
        self._build_knowledge_tab()
        self._build_flags_tab()

        # Buttons
        btns = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel
        )
        btns.accepted.connect(self._on_save)
        btns.rejected.connect(self.reject)
        root.addWidget(btns)

        self.error_label = QLabel("")
        self.error_label.setStyleSheet("color: #ff6578; font-size: 12px; font-weight: bold;")
        root.addWidget(self.error_label)

    def _scroll_tab(self) -> tuple[QScrollArea, QFormLayout]:
        """Return a (scroll_area, form_layout) pair for a scrollable tab."""
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        inner = QWidget()
        form = QFormLayout(inner)
        form.setSpacing(10)
        form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)
        scroll.setWidget(inner)
        return scroll, form

    def _section_label(self, form: QFormLayout, text: str) -> None:
        lbl = QLabel(text)
        lbl.setStyleSheet("font-weight: bold; margin-top: 8px; color: #a8a8c8;")
        form.addRow(lbl)

    def _field_hint(self, form: QFormLayout, text: str) -> None:
        """Add a small italic hint line below the previous field."""
        lbl = QLabel(text)
        lbl.setWordWrap(True)
        lbl.setStyleSheet("font-size: 10px; color: #6060a0; font-style: italic; margin-bottom: 2px;")
        form.addRow(lbl)

    # -- Relationship tab --------------------------------------------------
    def _build_relationship_tab(self) -> None:
        scroll, form = self._scroll_tab()

        self._section_label(form, "— Relationship with User —")

        intro = QLabel(
            "These values describe how this character feels about the <i>user</i> right now. "
            "They are read by the AI each session to shape tone, willingness, and behaviour. "
            "All numeric scores range from <b>−100 to +100</b> unless noted."
        )
        intro.setWordWrap(True)
        intro.setStyleSheet("font-size: 11px; color: #8888aa; margin-bottom: 4px;")
        form.addRow(intro)

        self.rel_status_edit = QLineEdit()
        self.rel_status_edit.setPlaceholderText("e.g. Neutral, Curious, Warm, Hostile, Infatuated…")
        self.rel_status_edit.setToolTip(
            "A short human-readable label summarising the overall relationship mood.\n"
            "Shown in the character panel and used as a quick narrative reference.\n"
            "Examples: Neutral · Curious · Warm · Distrustful · Hostile · Devoted"
        )
        form.addRow("Status Label", self.rel_status_edit)
        self._field_hint(form, "Free-text label — no strict format. Keep it short (1–3 words).")

        # Relationship score spinboxes with individual tooltips
        rel_int_fields = [
            ("trust",       "Trust",       "Willingness to believe and confide in the user.\n0 = total stranger, 100 = unconditional trust, −100 = deep distrust."),
            ("affection",   "Affection",   "Warmth and fondness felt toward the user.\n0 = indifferent, 100 = deeply caring, −100 = strong dislike."),
            ("respect",     "Respect",     "Regard for the user's competence or character.\n0 = no opinion, 100 = deep admiration, −100 = contempt."),
            ("fear",        "Fear",        "How threatened or intimidated the character feels.\n0 = no fear, 100 = terrified. Rarely goes negative."),
            ("resentment",  "Resentment",  "Lingering bitterness or grievance toward the user.\n0 = none, 100 = deeply resentful. Usually 0–100."),
            ("dependency",  "Dependency",  "How much the character relies on or needs the user.\n0 = fully independent, 100 = heavily dependent."),
            ("openness",    "Openness",    "Willingness to share personal thoughts and feelings.\n0 = closed off, 100 = completely open."),
            ("attraction",  "Attraction",  "Romantic or physical interest in the user.\n0 = none, 100 = strong attraction. Usually 0–100."),
        ]
        self._rel_spinboxes: dict[str, QSpinBox] = {}
        for key, label, tooltip in rel_int_fields:
            sb = QSpinBox()
            sb.setRange(-100, 100)
            sb.setFixedWidth(90)
            sb.setToolTip(tooltip)
            row_w = QWidget()
            row_l = QHBoxLayout(row_w)
            row_l.setContentsMargins(0, 0, 0, 0)
            row_l.addWidget(sb)
            range_lbl = QLabel("  −100 → +100")
            range_lbl.setStyleSheet("font-size: 10px; color: #6060a0;")
            row_l.addWidget(range_lbl)
            row_l.addStretch()
            form.addRow(label, row_w)
            self._rel_spinboxes[key] = sb

        self.rel_reason_edit = QLineEdit()
        self.rel_reason_edit.setToolTip(
            "A brief note explaining why the relationship score last changed.\n"
            "Example: 'User helped character escape a difficult situation.'\n"
            "Used for narrative continuity — does not affect AI scoring directly."
        )
        form.addRow("Last Change Reason", self.rel_reason_edit)
        self._field_hint(form, "Optional. Briefly describe what caused the last relationship shift.")

        self.rel_interp_edit = QTextEdit()
        self.rel_interp_edit.setMinimumHeight(55)
        self.rel_interp_edit.setToolTip(
            "A short narrative summary of how the character currently views the user.\n"
            "Injected into the prompt to give the AI contextual flavour.\n"
            "Example: 'Sees the user as an unreliable but intriguing outsider.'"
        )
        form.addRow("Interpretation", self.rel_interp_edit)
        self._field_hint(form, "1–2 sentences describing how the character perceives the user right now.")

        self._section_label(form, "— Relationships with Other Characters —")
        self.other_rels_edit = QTextEdit()
        self.other_rels_edit.setMinimumHeight(80)
        self.other_rels_edit.setPlaceholderText("Alice: childhood friends, deeply trusted\nBob: professional rival, low trust")
        self.other_rels_edit.setToolTip(
            "Inter-character relationships used when multiple characters are in the same scene.\n"
            "Format each line as:  CharacterName: description\n"
            "Example:\n  Sophia Smith: close friend, high trust\n  Marcus: distrusted colleague"
        )
        form.addRow("Other Chars", self.other_rels_edit)
        self._field_hint(form, "Format: CharacterName: description — one entry per line.")

        self.tabs.addTab(scroll, "Relationship")

    # -- Emotional tab -----------------------------------------------------
    def _build_emotional_tab(self) -> None:
        scroll, form = self._scroll_tab()

        self._section_label(form, "— Emotional Baseline —")

        intro = QLabel(
            "The character's default emotional state at the <i>start</i> of a session. "
            "These values drift during chat and are reset here to establish a baseline. "
            "All scores are <b>0 – 100</b>. Higher = more of that emotion."
        )
        intro.setWordWrap(True)
        intro.setStyleSheet("font-size: 11px; color: #8888aa; margin-bottom: 4px;")
        form.addRow(intro)

        emotional_fields = [
            ("confidence", "Confidence",
             "How self-assured and capable the character feels.\n"
             "0 = deeply insecure / paralysed by self-doubt\n"
             "50 = balanced, context-dependent confidence\n"
             "100 = unshakeable self-belief (may tip into arrogance)"),
            ("anxiety",    "Anxiety",
             "Background level of worry, tension, or unease.\n"
             "0 = completely calm / unbothered\n"
             "50 = moderately watchful or stressed\n"
             "100 = overwhelmed, panicked, or hyper-vigilant"),
            ("hope",       "Hope",
             "Optimism about the future and ongoing interactions.\n"
             "0 = deeply pessimistic / resigned\n"
             "50 = cautiously neutral\n"
             "100 = genuinely hopeful and forward-looking"),
            ("guilt",      "Guilt",
             "Weight of past actions or moral failures.\n"
             "0 = clear conscience\n"
             "50 = carrying some regret\n"
             "100 = consumed by guilt / may behave self-destructively"),
            ("anger",      "Anger",
             "Underlying frustration or readiness to react with hostility.\n"
             "0 = no aggression, very even-tempered\n"
             "50 = visibly irritable under pressure\n"
             "100 = barely controlled rage"),
            ("loneliness", "Loneliness",
             "Feeling of isolation or longing for connection.\n"
             "0 = content with solitude, socially fulfilled\n"
             "50 = quietly wishes for more connection\n"
             "100 = deeply isolated, craves any social contact"),
        ]
        self._emotion_spinboxes: dict[str, QSpinBox] = {}
        for key, label, tooltip in emotional_fields:
            sb = QSpinBox()
            sb.setRange(0, 100)
            sb.setFixedWidth(90)
            sb.setToolTip(tooltip)
            row_w = QWidget()
            row_l = QHBoxLayout(row_w)
            row_l.setContentsMargins(0, 0, 0, 0)
            row_l.addWidget(sb)
            range_lbl = QLabel("  0 → 100")
            range_lbl.setStyleSheet("font-size: 10px; color: #6060a0;")
            row_l.addWidget(range_lbl)
            row_l.addStretch()
            form.addRow(label, row_w)
            self._emotion_spinboxes[key] = sb

        self._field_hint(form, "💡 Tip: Hover over any field label for a detailed description.")
        self.tabs.addTab(scroll, "Emotional")

    # -- Memories tab ------------------------------------------------------
    def _build_memories_tab(self) -> None:
        scroll, form = self._scroll_tab()

        intro = QLabel(
            "Memories are injected into the prompt to give the character a sense of history. "
            "Keep entries concise — one clear sentence per line works best. "
            "The AI uses these to stay consistent across conversations."
        )
        intro.setWordWrap(True)
        intro.setStyleSheet("font-size: 11px; color: #8888aa; margin-bottom: 4px;")
        form.addRow(intro)

        self._section_label(form, "— Stable Memories —")
        self._field_hint(
            form,
            "Permanent, core facts that define who this character is. "
            "These never change through conversation — things like backstory, "
            "defining relationships, or pivotal life events."
        )
        self.stable_memories_edit = QTextEdit()
        self.stable_memories_edit.setMinimumHeight(110)
        self.stable_memories_edit.setPlaceholderText(
            "Grew up in a small coastal town and never left until age 22.\n"
            "Has a complicated relationship with her estranged brother.\n"
            "Was once betrayed by someone she trusted deeply."
        )
        self.stable_memories_edit.setToolTip(
            "Permanent background facts injected at the start of every session.\n"
            "Use for: backstory, defining events, core relationships.\n"
            "One memory per line. Keep each line under ~120 characters for best results."
        )
        form.addRow("Stable", self.stable_memories_edit)

        self._section_label(form, "— Episodic Memories —")
        self._field_hint(
            form,
            "Recent or context-specific experiences from past chats. "
            "These can fade or be replaced as new events occur. "
            "Reference specific interactions, decisions, or moments."
        )
        self.episodic_memories_edit = QTextEdit()
        self.episodic_memories_edit.setMinimumHeight(110)
        self.episodic_memories_edit.setPlaceholderText(
            "User ordered a whisky sour and seemed nervous on their first visit.\n"
            "Helped the user find a lost item last Tuesday — felt appreciated.\n"
            "User mentioned they recently broke up with someone."
        )
        self.episodic_memories_edit.setToolTip(
            "Recent events and interactions from previous sessions.\n"
            "Use for: things the user said or did, shared experiences, emotional moments.\n"
            "One memory per line. Older / less important ones can be removed over time."
        )
        form.addRow("Episodic", self.episodic_memories_edit)

        self._section_label(form, "— Open Threads —")
        self._field_hint(
            form,
            "Unresolved topics, promises, or plot hooks the character is actively thinking about. "
            "The AI uses these to naturally bring up unfinished business during conversation."
        )
        self.open_threads_edit = QTextEdit()
        self.open_threads_edit.setMinimumHeight(80)
        self.open_threads_edit.setPlaceholderText(
            "Wondering if the user will return after their argument last session.\n"
            "Promised to find out information about the old warehouse — hasn't yet.\n"
            "Curious about the user's real reason for visiting the lounge."
        )
        self.open_threads_edit.setToolTip(
            "Pending questions, promises, or story threads the character hasn't resolved.\n"
            "The AI will weave these naturally into dialogue when appropriate.\n"
            "Remove a thread once it has been resolved in conversation."
        )
        form.addRow("Threads", self.open_threads_edit)

        self.tabs.addTab(scroll, "Memories")

    # -- Knowledge tab -----------------------------------------------------
    def _build_knowledge_tab(self) -> None:
        scroll, form = self._scroll_tab()

        intro = QLabel(
            "These fields shape what the character <i>knows</i>, <i>suspects</i>, and <i>hides</i>. "
            "The AI uses them to control what the character will volunteer, question, or conceal "
            "during conversation. One entry per line."
        )
        intro.setWordWrap(True)
        intro.setStyleSheet("font-size: 11px; color: #8888aa; margin-bottom: 4px;")
        form.addRow(intro)

        knowledge_fields = [
            (
                "suspicions_edit",
                "Suspicions",
                "Things the character suspects may be true but hasn't confirmed.\n"
                "The AI will let these colour the character's questions and reactions "
                "without stating them outright.\n\n"
                "Examples:\n"
                "  The user may be hiding their real identity.\n"
                "  Someone in the lounge is passing information to rivals.",
                "The user might not be who they claim to be.\n"
                "Something odd is going on with the new bartender.",
            ),
            (
                "unknowns_edit",
                "Unknowns",
                "Facts the character genuinely does not know and may be curious about.\n"
                "The AI uses these to make the character ask natural questions "
                "and avoid accidentally 'knowing' things they shouldn't.\n\n"
                "Examples:\n"
                "  Does not know the user's real occupation.\n"
                "  Unaware of what happened to her old friend Marcus.",
                "Does not know why the user keeps coming back.\n"
                "Hasn't found out what happened at the warehouse fire.",
            ),
            (
                "secrets_held_edit",
                "Secrets Held",
                "Things the character knows but actively keeps hidden from the user.\n"
                "The AI will reference these internally to shape evasive or careful "
                "behaviour, but will not reveal them unless dramatically appropriate.\n\n"
                "Examples:\n"
                "  Is working as an informant for a local crime boss.\n"
                "  Knows the real reason the bar owner disappeared.",
                "Has a fake identity and false backstory.\n"
                "Knows the real culprit but was told never to speak of it.",
            ),
        ]

        for attr, label, tooltip, placeholder in knowledge_fields:
            self._section_label(form, f"— {label} —")
            te = QTextEdit()
            te.setMinimumHeight(80)
            te.setPlaceholderText(placeholder + "\n(one entry per line)")
            te.setToolTip(tooltip)
            form.addRow(label, te)
            setattr(self, attr, te)

        self.tabs.addTab(scroll, "Knowledge")

    # -- Flags tab ---------------------------------------------------------
    def _build_flags_tab(self) -> None:
        scroll, form = self._scroll_tab()

        self._section_label(form, "— Scene Flags —")

        intro = QLabel(
            "Boolean switches that change how the character behaves in the current scene. "
            "These are checked by the AI at the start of each session to set the stage."
        )
        intro.setWordWrap(True)
        intro.setStyleSheet("font-size: 11px; color: #8888aa; margin-bottom: 4px;")
        form.addRow(intro)

        from PySide6.QtWidgets import QCheckBox
        flag_fields = [
            (
                "available_for_interaction",
                "Available for Interaction",
                "✅ ON  — Character is present and willing to engage with the user.\n"
                "❌ OFF — Character is absent, busy, or refusing contact.\n\n"
                "When OFF, the AI will describe the character as unavailable rather than "
                "roleplaying a full conversation. Default: ON.",
            ),
            (
                "injured",
                "Injured",
                "✅ ON  — Character is currently hurt or recovering from an injury.\n"
                "❌ OFF — Character is in normal physical condition.\n\n"
                "When ON, the AI will reflect physical limitations in dialogue and "
                "behaviour (slower movement, guarded posture, pain references). Default: OFF.",
            ),
            (
                "hostile_mode",
                "Hostile Mode",
                "✅ ON  — Character starts the session in an aggressive or antagonistic state.\n"
                "❌ OFF — Character's disposition follows normal relationship scores.\n\n"
                "Overrides relationship scores for tone. Useful after a major conflict "
                "or betrayal where the character should be combative from the first line. Default: OFF.",
            ),
            (
                "romance_locked",
                "Romance Locked",
                "✅ ON  — Romantic progression is blocked; the character will deflect or "
                "refuse romantic advances regardless of attraction score.\n"
                "❌ OFF — Romance can develop naturally based on attraction and trust scores.\n\n"
                "Use to hard-lock the relationship at a platonic level, or while a conflict "
                "is unresolved. Does not affect friendship or warmth. Default: OFF.",
            ),
        ]
        self._flag_checkboxes: dict[str, "QCheckBox"] = {}
        for key, label, tooltip in flag_fields:
            cb = QCheckBox()
            cb.setToolTip(tooltip)
            form.addRow(label, cb)
            # Inline description beneath the checkbox
            desc_text = tooltip.split("\n\n")[-1]  # grab the last paragraph
            self._field_hint(form, desc_text)
            self._flag_checkboxes[key] = cb

        self.tabs.addTab(scroll, "Scene Flags")

    # ── Data load / save ──────────────────────────────────────────────

    def _load(self) -> None:
        try:
            self._memory = self._character_manager.load_memory(self._char_id)
        except Exception as exc:
            logger.warning("Could not load memory for %s: %s", self._char_id, exc)
            self._memory = {}

        m = self._memory

        # Relationship with user
        rel = m.get("relationship_with_user", {})
        if not isinstance(rel, dict):
            rel = {}
        self.rel_status_edit.setText(str(rel.get("status_label", "Neutral")))
        for key, sb in self._rel_spinboxes.items():
            sb.setValue(int(rel.get(key, 0)))
        self.rel_reason_edit.setText(str(rel.get("last_change_reason", "")))
        self.rel_interp_edit.setPlainText(str(rel.get("interpretation", "")))

        # Other character relationships (list of dicts or strings)
        other_rels = m.get("relationships_with_characters", [])
        lines: list[str] = []
        for entry in other_rels if isinstance(other_rels, list) else []:
            if isinstance(entry, dict):
                name = entry.get("name", entry.get("character", ""))
                rel_text = entry.get("relationship", entry.get("description", ""))
                lines.append(f"{name}: {rel_text}" if name else str(entry))
            else:
                lines.append(str(entry))
        self.other_rels_edit.setPlainText("\n".join(lines))

        # Emotional baseline
        emo = m.get("emotional_baseline", {})
        if not isinstance(emo, dict):
            emo = {}
        for key, sb in self._emotion_spinboxes.items():
            sb.setValue(int(emo.get(key, 50 if key in ("confidence", "anxiety", "hope", "loneliness") else 0)))

        # Memories
        memories = m.get("memories", {})
        if not isinstance(memories, dict):
            memories = {}
        self.stable_memories_edit.setPlainText(
            "\n".join(str(x) for x in memories.get("stable", []))
        )
        self.episodic_memories_edit.setPlainText(
            "\n".join(str(x) for x in memories.get("episodic", []))
        )

        # Open threads
        threads = m.get("open_threads", [])
        self.open_threads_edit.setPlainText("\n".join(str(x) for x in threads))

        # Knowledge
        knowledge = m.get("knowledge", {})
        if not isinstance(knowledge, dict):
            knowledge = {}
        self.suspicions_edit.setPlainText("\n".join(str(x) for x in knowledge.get("suspicions", [])))
        self.unknowns_edit.setPlainText("\n".join(str(x) for x in knowledge.get("unknowns", [])))
        self.secrets_held_edit.setPlainText("\n".join(str(x) for x in knowledge.get("secrets_held", [])))

        # Scene flags
        flags = m.get("scene_flags", {})
        if not isinstance(flags, dict):
            flags = {}
        defaults = {
            "available_for_interaction": True,
            "injured": False,
            "hostile_mode": False,
            "romance_locked": False,
        }
        for key, cb in self._flag_checkboxes.items():
            cb.setChecked(bool(flags.get(key, defaults.get(key, False))))

    def _on_save(self) -> None:
        def _split_lines(text: str) -> list[str]:
            return [t.strip() for t in text.splitlines() if t.strip()]

        # Rebuild the memory dict, preserving any unknown top-level keys
        updated = dict(self._memory)

        updated["relationship_with_user"] = {
            "status_label": self.rel_status_edit.text().strip() or "Neutral",
            "last_change_reason": self.rel_reason_edit.text().strip(),
            "interpretation": self.rel_interp_edit.toPlainText().strip(),
            **{key: sb.value() for key, sb in self._rel_spinboxes.items()},
        }

        # Parse "Name: description" lines back into list-of-dicts
        other_rel_lines = _split_lines(self.other_rels_edit.toPlainText())
        other_rels_out: list[Any] = []
        for line in other_rel_lines:
            if ":" in line:
                name_part, _, rel_part = line.partition(":")
                other_rels_out.append({"name": name_part.strip(), "relationship": rel_part.strip()})
            else:
                other_rels_out.append(line)
        updated["relationships_with_characters"] = other_rels_out

        updated["emotional_baseline"] = {
            key: sb.value() for key, sb in self._emotion_spinboxes.items()
        }

        updated["memories"] = {
            "stable": _split_lines(self.stable_memories_edit.toPlainText()),
            "episodic": _split_lines(self.episodic_memories_edit.toPlainText()),
        }

        updated["open_threads"] = _split_lines(self.open_threads_edit.toPlainText())

        updated["knowledge"] = {
            "suspicions": _split_lines(self.suspicions_edit.toPlainText()),
            "unknowns": _split_lines(self.unknowns_edit.toPlainText()),
            "secrets_held": _split_lines(self.secrets_held_edit.toPlainText()),
        }

        updated["scene_flags"] = {
            key: cb.isChecked() for key, cb in self._flag_checkboxes.items()
        }

        try:
            self._character_manager.save_memory(self._char_id, updated)
            self.accept()
        except Exception as exc:
            self.error_label.setText(str(exc))


class EditCharacterDialog(QDialog):
    """Full edit dialog for a user-created character."""

    def __init__(
        self,
        character: dict[str, Any],
        character_manager: CharacterManager,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._character = dict(character)
        self.character_manager = character_manager
        self.setWindowTitle(f"Edit Character — {character.get('name', '')}")
        self.setMinimumSize(680, 700)
        self.setModal(True)
        self._build_ui()
        self._populate()

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setSpacing(12)
        root.setContentsMargins(24, 24, 24, 24)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        inner = QWidget()
        form = QFormLayout(inner)
        form.setSpacing(10)
        form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)
        scroll.setWidget(inner)

        def add_section(title: str):
            lbl = QLabel(title)
            lbl.setStyleSheet("font-weight: bold; margin-top: 10px; color: #a8a8c8;")
            form.addRow(lbl)

        add_section("--- Basic ---")
        self.name_edit = QLineEdit()
        form.addRow("Name *", self.name_edit)

        self.title_edit = QLineEdit()
        form.addRow("Title / Role", self.title_edit)

        self.story_role_edit = QLineEdit()
        form.addRow("Story Role", self.story_role_edit)

        self.description_edit = QTextEdit()
        self.description_edit.setMinimumHeight(60)
        form.addRow("Description", self.description_edit)

        self.system_prompt_edit = QTextEdit()
        self.system_prompt_edit.setMinimumHeight(80)
        form.addRow("System Prompt", self.system_prompt_edit)

        self.greeting_edit = QTextEdit()
        self.greeting_edit.setMinimumHeight(60)
        form.addRow("Greeting", self.greeting_edit)

        self.scenario_edit = QTextEdit()
        self.scenario_edit.setMinimumHeight(60)
        form.addRow("Starting Scenario", self.scenario_edit)

        self.example_dialogue_edit = QTextEdit()
        self.example_dialogue_edit.setMinimumHeight(60)
        form.addRow("Example Dialogue", self.example_dialogue_edit)

        self.world_lore_edit = QTextEdit()
        self.world_lore_edit.setMinimumHeight(60)
        form.addRow("World Lore Notes", self.world_lore_edit)

        add_section("--- Identity ---")
        self.age_edit = QLineEdit()
        form.addRow("Age", self.age_edit)

        self.age_band_edit = QLineEdit()
        form.addRow("Age Band", self.age_band_edit)

        self.public_summary_edit = QTextEdit()
        self.public_summary_edit.setMinimumHeight(60)
        form.addRow("Public Summary", self.public_summary_edit)

        self.private_truths_edit = QTextEdit()
        self.private_truths_edit.setMinimumHeight(60)
        self.private_truths_edit.setPlaceholderText("One per line")
        form.addRow("Private Truths", self.private_truths_edit)

        self.core_traits_edit = QLineEdit()
        self.core_traits_edit.setPlaceholderText("Comma-separated")
        form.addRow("Core Traits", self.core_traits_edit)

        self.values_edit = QLineEdit()
        self.values_edit.setPlaceholderText("Comma-separated")
        form.addRow("Values", self.values_edit)

        self.fears_edit = QLineEdit()
        self.fears_edit.setPlaceholderText("Comma-separated")
        form.addRow("Fears", self.fears_edit)

        self.goals_short_edit = QTextEdit()
        self.goals_short_edit.setMinimumHeight(50)
        self.goals_short_edit.setPlaceholderText("One per line")
        form.addRow("Goals (Short Term)", self.goals_short_edit)

        self.goals_mid_edit = QTextEdit()
        self.goals_mid_edit.setMinimumHeight(50)
        self.goals_mid_edit.setPlaceholderText("One per line")
        form.addRow("Goals (Mid Term)", self.goals_mid_edit)

        self.goals_long_edit = QTextEdit()
        self.goals_long_edit.setMinimumHeight(50)
        self.goals_long_edit.setPlaceholderText("One per line")
        form.addRow("Goals (Long Term)", self.goals_long_edit)

        self.boundaries_hard_edit = QTextEdit()
        self.boundaries_hard_edit.setMinimumHeight(50)
        self.boundaries_hard_edit.setPlaceholderText("One per line")
        form.addRow("Boundaries (Hard)", self.boundaries_hard_edit)

        self.boundaries_soft_edit = QTextEdit()
        self.boundaries_soft_edit.setMinimumHeight(50)
        self.boundaries_soft_edit.setPlaceholderText("One per line")
        form.addRow("Boundaries (Soft)", self.boundaries_soft_edit)

        add_section("--- Voice ---")
        self.voice_tone_edit = QLineEdit()
        form.addRow("Tone", self.voice_tone_edit)

        self.voice_cadence_edit = QLineEdit()
        form.addRow("Cadence", self.voice_cadence_edit)

        self.voice_favored_edit = QTextEdit()
        self.voice_favored_edit.setMinimumHeight(50)
        self.voice_favored_edit.setPlaceholderText("One per line")
        form.addRow("Favored Patterns", self.voice_favored_edit)

        self.voice_avoid_edit = QTextEdit()
        self.voice_avoid_edit.setMinimumHeight(50)
        self.voice_avoid_edit.setPlaceholderText("One per line")
        form.addRow("Avoid Patterns", self.voice_avoid_edit)

        add_section("--- Knowledge ---")
        self.known_facts_edit = QTextEdit()
        self.known_facts_edit.setMinimumHeight(60)
        self.known_facts_edit.setPlaceholderText("One per line")
        form.addRow("Known Facts", self.known_facts_edit)

        add_section("--- Meta ---")
        self.tags_edit = QLineEdit()
        self.tags_edit.setPlaceholderText("Comma-separated tags")
        form.addRow("Tags", self.tags_edit)

        avatar_row = QHBoxLayout()
        self.avatar_path_edit = QLineEdit()
        self.avatar_path_edit.setPlaceholderText("Path to avatar image (optional)")
        avatar_row.addWidget(self.avatar_path_edit)
        browse_btn = QPushButton("Browse…")
        browse_btn.setStyleSheet("font-size: 11px;")
        browse_btn.clicked.connect(self._browse_avatar)
        avatar_row.addWidget(browse_btn)
        form.addRow("Avatar Image", avatar_row)

        self.folder_edit = QLineEdit()
        form.addRow("Folder", self.folder_edit)

        root.addWidget(scroll)

        btns = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel
        )
        btns.accepted.connect(self._on_save)
        btns.rejected.connect(self.reject)
        root.addWidget(btns)

        self.error_label = QLabel("")
        self.error_label.setStyleSheet("color: #ff6578; font-size: 12px; font-weight: bold;")
        root.addWidget(self.error_label)

    def _populate(self) -> None:
        c = self._character
        self.name_edit.setText(str(c.get("name", "")))
        self.title_edit.setText(str(c.get("title", "") or c.get("role", "")))
        self.story_role_edit.setText(str(c.get("story_role", "")))
        self.description_edit.setPlainText(str(c.get("description", "") or ""))
        self.system_prompt_edit.setPlainText(str(c.get("system_prompt", "") or ""))
        self.greeting_edit.setPlainText(str(c.get("greeting", "") or ""))
        self.scenario_edit.setPlainText(str(c.get("starting_scenario", "") or ""))
        self.example_dialogue_edit.setPlainText(str(c.get("example_dialogue", "") or ""))
        self.world_lore_edit.setPlainText(
            str(c.get("world_lore_notes", "") or c.get("world_lore", "") or "")
        )

        identity = c.get("identity", {})
        if not isinstance(identity, dict): identity = {}
        self.age_edit.setText(str(identity.get("age", "")))
        self.age_band_edit.setText(str(identity.get("age_band", "")))
        self.public_summary_edit.setPlainText(str(identity.get("public_summary", "")))
        self.private_truths_edit.setPlainText("\n".join(str(x) for x in identity.get("private_truths", [])))
        self.core_traits_edit.setText(", ".join(str(x) for x in identity.get("core_traits", [])))
        self.values_edit.setText(", ".join(str(x) for x in identity.get("values", [])))
        self.fears_edit.setText(", ".join(str(x) for x in identity.get("fears", [])))
        
        goals = identity.get("goals", {})
        if not isinstance(goals, dict): goals = {}
        self.goals_short_edit.setPlainText("\n".join(str(x) for x in goals.get("short_term", [])))
        self.goals_mid_edit.setPlainText("\n".join(str(x) for x in goals.get("mid_term", [])))
        self.goals_long_edit.setPlainText("\n".join(str(x) for x in goals.get("long_term", [])))

        boundaries = identity.get("boundaries", {})
        if not isinstance(boundaries, dict): boundaries = {}
        self.boundaries_hard_edit.setPlainText("\n".join(str(x) for x in boundaries.get("hard", [])))
        self.boundaries_soft_edit.setPlainText("\n".join(str(x) for x in boundaries.get("soft", [])))

        voice = c.get("voice", {})
        if not isinstance(voice, dict): voice = {}
        self.voice_tone_edit.setText(str(voice.get("tone", "")))
        self.voice_cadence_edit.setText(str(voice.get("cadence", "")))
        self.voice_favored_edit.setPlainText("\n".join(str(x) for x in voice.get("favored_patterns", [])))
        self.voice_avoid_edit.setPlainText("\n".join(str(x) for x in voice.get("avoid_patterns", [])))

        knowledge = c.get("knowledge", {})
        if not isinstance(knowledge, dict): knowledge = {}
        self.known_facts_edit.setPlainText("\n".join(str(x) for x in knowledge.get("known_facts", [])))

        tags = c.get("tags", [])
        self.tags_edit.setText(", ".join(str(t) for t in tags))
        self.avatar_path_edit.setText(str(c.get("avatar_path", "") or ""))
        self.folder_edit.setText(str(c.get("folder", "General")))

    def _browse_avatar(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Select Avatar Image",
            str(Path.home()),
            "Images (*.png *.jpg *.jpeg *.webp *.bmp)",
        )
        if path:
            self.avatar_path_edit.setText(path)

    def _on_save(self) -> None:
        name = self.name_edit.text().strip()
        if not name:
            self.error_label.setText("Character name is required.")
            self.name_edit.setFocus()
            return

        def _split_comma(text: str) -> list[str]:
            return [t.strip() for t in text.split(",") if t.strip()]

        def _split_lines(text: str) -> list[str]:
            return [t.strip() for t in text.split("\n") if t.strip()]

        tags = _split_comma(self.tags_edit.text())

        try:
            age_val = int(self.age_edit.text().strip())
        except ValueError:
            age_val = 0

        updated = dict(self._character)
        updated.update({
            "name": name,
            "title": self.title_edit.text().strip(),
            "role": self.title_edit.text().strip(),
            "story_role": self.story_role_edit.text().strip(),
            "description": self.description_edit.toPlainText().strip(),
            "system_prompt": self.system_prompt_edit.toPlainText().strip(),
            "greeting": self.greeting_edit.toPlainText().strip(),
            "starting_scenario": self.scenario_edit.toPlainText().strip(),
            "example_dialogue": self.example_dialogue_edit.toPlainText().strip(),
            "world_lore_notes": self.world_lore_edit.toPlainText().strip(),
            "identity": {
                "age": age_val,
                "age_band": self.age_band_edit.text().strip(),
                "public_summary": self.public_summary_edit.toPlainText().strip(),
                "private_truths": _split_lines(self.private_truths_edit.toPlainText()),
                "core_traits": _split_comma(self.core_traits_edit.text()),
                "values": _split_comma(self.values_edit.text()),
                "fears": _split_comma(self.fears_edit.text()),
                "goals": {
                    "short_term": _split_lines(self.goals_short_edit.toPlainText()),
                    "mid_term": _split_lines(self.goals_mid_edit.toPlainText()),
                    "long_term": _split_lines(self.goals_long_edit.toPlainText()),
                },
                "boundaries": {
                    "hard": _split_lines(self.boundaries_hard_edit.toPlainText()),
                    "soft": _split_lines(self.boundaries_soft_edit.toPlainText()),
                }
            },
            "voice": {
                "tone": self.voice_tone_edit.text().strip(),
                "cadence": self.voice_cadence_edit.text().strip(),
                "favored_patterns": _split_lines(self.voice_favored_edit.toPlainText()),
                "avoid_patterns": _split_lines(self.voice_avoid_edit.toPlainText()),
            },
            "knowledge": {
                "known_facts": _split_lines(self.known_facts_edit.toPlainText()),
            },
            "tags": tags,
            "avatar_path": self.avatar_path_edit.text().strip(),
            "folder": self.folder_edit.text().strip() or "General",
        })

        try:
            self.character_manager.save_character(
                updated,
                copy_avatar_to_managed_storage=bool(self.avatar_path_edit.text().strip()),
            )
            self.accept()
        except Exception as exc:
            self.error_label.setText(str(exc))
class EditMemoryDialog(QDialog):
    """Dialog for viewing and editing a user-created character's memory.json."""

    def __init__(
        self,
        character: dict[str, Any],
        character_manager: CharacterManager,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._character = character
        self.character_manager = character_manager
        slug = str(character.get("id", "")).strip() or str(character.get("name", "")).strip().lower().replace(" ", "_")
        self._memory_path: Path = character_manager._character_memory_file(slug)
        self._memory: dict[str, Any] = {}
        self.setWindowTitle(f"Edit Memory — {character.get('name', '')}")
        self.setMinimumSize(720, 780)
        self.setModal(True)
        self._load_memory()
        self._build_ui()
        self._populate()

    # ── I/O ──────────────────────────────────────────────────────────────

    def _load_memory(self) -> None:
        if self._memory_path.is_file():
            try:
                with self._memory_path.open(encoding="utf-8") as fh:
                    self._memory = json.load(fh)
            except Exception as exc:
                logger.warning("Could not load memory file %s: %s", self._memory_path, exc)
                self._memory = {}
        else:
            self._memory = {}

    def _save_memory(self) -> None:
        self._memory_path.parent.mkdir(parents=True, exist_ok=True)
        with self._memory_path.open("w", encoding="utf-8") as fh:
            json.dump(self._memory, fh, indent=2, ensure_ascii=False)

    # ── UI ───────────────────────────────────────────────────────────────

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setSpacing(12)
        root.setContentsMargins(24, 24, 24, 24)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        inner = QWidget()
        self._form = QFormLayout(inner)
        self._form.setSpacing(10)
        self._form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)
        scroll.setWidget(inner)

        def section(title: str) -> None:
            lbl = QLabel(title)
            lbl.setStyleSheet("font-weight: bold; margin-top: 10px; color: #a8a8c8;")
            self._form.addRow(lbl)

        # ── Relationship with User ────────────────────────────────────────
        section("── Relationship with User ──")

        self.rel_status_edit = QLineEdit()
        self.rel_status_edit.setPlaceholderText("e.g. Neutral, Curious, Warm, Hostile…")
        self._form.addRow("Status Label", self.rel_status_edit)

        self._rel_sliders: dict[str, QLineEdit] = {}
        for field in ("trust", "affection", "respect", "fear", "resentment", "dependency", "openness", "attraction"):
            w = QLineEdit()
            w.setPlaceholderText("0 – 100")
            w.setMaximumWidth(80)
            self._rel_sliders[field] = w
            self._form.addRow(field.capitalize(), w)

        self.rel_reason_edit = QLineEdit()
        self._form.addRow("Last Change Reason", self.rel_reason_edit)

        self.rel_interp_edit = QTextEdit()
        self.rel_interp_edit.setMinimumHeight(50)
        self._form.addRow("Interpretation", self.rel_interp_edit)

        # ── Emotional Baseline ────────────────────────────────────────────
        section("── Emotional Baseline ──")

        self._emotion_edits: dict[str, QLineEdit] = {}
        for field in ("confidence", "anxiety", "hope", "guilt", "anger", "loneliness"):
            w = QLineEdit()
            w.setPlaceholderText("0 – 100")
            w.setMaximumWidth(80)
            self._emotion_edits[field] = w
            self._form.addRow(field.capitalize(), w)

        # ── Stable Memories ───────────────────────────────────────────────
        section("── Stable Memories (one per line: importance|summary) ──")

        self.stable_edit = QTextEdit()
        self.stable_edit.setMinimumHeight(90)
        self.stable_edit.setPlaceholderText("90|Known for her kind and encouraging nature.\n71|Uses her confidence to push through obstacles.")
        self._form.addRow("Stable Memories", self.stable_edit)

        # ── Episodic Memories ─────────────────────────────────────────────
        section("── Episodic Memories (one per line: importance|summary) ──")

        self.episodic_edit = QTextEdit()
        self.episodic_edit.setMinimumHeight(90)
        self.episodic_edit.setPlaceholderText("83|Sophia helped Maya study for exams.\n63|Maya was shy during a group presentation.")
        self._form.addRow("Episodic Memories", self.episodic_edit)

        # ── Open Threads ──────────────────────────────────────────────────
        section("── Open Threads (one per line: priority|summary) ──")

        self.threads_edit = QTextEdit()
        self.threads_edit.setMinimumHeight(70)
        self.threads_edit.setPlaceholderText("80|Open to new adventures with Sophia.\n67|Needs help with writing projects.")
        self._form.addRow("Open Threads", self.threads_edit)

        # ── Knowledge ─────────────────────────────────────────────────────
        section("── Knowledge ──")

        self.suspicions_edit = QTextEdit()
        self.suspicions_edit.setMinimumHeight(50)
        self.suspicions_edit.setPlaceholderText("One per line")
        self._form.addRow("Suspicions", self.suspicions_edit)

        self.unknowns_edit = QTextEdit()
        self.unknowns_edit.setMinimumHeight(50)
        self.unknowns_edit.setPlaceholderText("One per line")
        self._form.addRow("Unknowns", self.unknowns_edit)

        self.secrets_edit = QTextEdit()
        self.secrets_edit.setMinimumHeight(50)
        self.secrets_edit.setPlaceholderText("One per line")
        self._form.addRow("Secrets Held", self.secrets_edit)

        # ── Scene Flags ───────────────────────────────────────────────────
        section("── Scene Flags ──")

        self._flag_edits: dict[str, QLineEdit] = {}
        for flag in ("available_for_interaction", "injured", "hostile_mode", "romance_locked"):
            w = QLineEdit()
            w.setPlaceholderText("true / false")
            w.setMaximumWidth(80)
            self._flag_edits[flag] = w
            self._form.addRow(flag.replace("_", " ").title(), w)

        root.addWidget(scroll)

        # Error label + buttons
        self.error_label = QLabel("")
        self.error_label.setStyleSheet("color: #ff6578; font-size: 12px; font-weight: bold;")
        root.addWidget(self.error_label)

        btn_row = QHBoxLayout()
        reset_btn = QPushButton("↺  Reset to Blank")
        reset_btn.setObjectName("secondary_btn")
        reset_btn.clicked.connect(self._on_reset)
        btn_row.addWidget(reset_btn)
        btn_row.addStretch()

        btns = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel
        )
        btns.accepted.connect(self._on_save)
        btns.rejected.connect(self.reject)
        btn_row.addWidget(btns)
        root.addLayout(btn_row)

    # ── Population helpers ────────────────────────────────────────────────

    @staticmethod
    def _int_field(val: Any) -> str:
        try:
            return str(int(val))
        except (TypeError, ValueError):
            return "0"

    @staticmethod
    def _bool_field(val: Any) -> str:
        if isinstance(val, bool):
            return "true" if val else "false"
        return str(val).lower()

    @staticmethod
    def _items_to_text(items: list[dict], score_key: str, summary_key: str = "summary") -> str:
        lines = []
        for item in items:
            score = item.get(score_key, 0)
            text = str(item.get(summary_key, "")).strip()
            if text:
                lines.append(f"{score}|{text}")
        return "\n".join(lines)

    def _populate(self) -> None:
        m = self._memory

        rel = m.get("relationship_with_user", {})
        if not isinstance(rel, dict):
            rel = {}
        self.rel_status_edit.setText(str(rel.get("status_label", "")))
        for field, widget in self._rel_sliders.items():
            widget.setText(self._int_field(rel.get(field, 0)))
        self.rel_reason_edit.setText(str(rel.get("last_change_reason", "")))
        self.rel_interp_edit.setPlainText(str(rel.get("interpretation", "")))

        emo = m.get("emotional_baseline", {})
        if not isinstance(emo, dict):
            emo = {}
        for field, widget in self._emotion_edits.items():
            widget.setText(self._int_field(emo.get(field, 0)))

        memories = m.get("memories", {})
        if not isinstance(memories, dict):
            memories = {}
        self.stable_edit.setPlainText(self._items_to_text(memories.get("stable", []), "importance"))
        self.episodic_edit.setPlainText(self._items_to_text(memories.get("episodic", []), "importance"))

        threads = m.get("open_threads", [])
        self.threads_edit.setPlainText(self._items_to_text(threads, "priority"))

        knowledge = m.get("knowledge", {})
        if not isinstance(knowledge, dict):
            knowledge = {}
        self.suspicions_edit.setPlainText("\n".join(str(x) for x in knowledge.get("suspicions", [])))
        self.unknowns_edit.setPlainText("\n".join(str(x) for x in knowledge.get("unknowns", [])))
        self.secrets_edit.setPlainText("\n".join(str(x) for x in knowledge.get("secrets_held", [])))

        flags = m.get("scene_flags", {})
        if not isinstance(flags, dict):
            flags = {}
        for flag, widget in self._flag_edits.items():
            widget.setText(self._bool_field(flags.get(flag, False)))

    # ── Save ──────────────────────────────────────────────────────────────

    @staticmethod
    def _parse_int(text: str, default: int = 0) -> int:
        try:
            return max(0, min(100, int(text.strip())))
        except (ValueError, AttributeError):
            return default

    @staticmethod
    def _parse_bool(text: str) -> bool:
        return str(text).strip().lower() in ("true", "yes", "1")

    @staticmethod
    def _parse_scored_lines(text: str, score_key: str, id_prefix: str) -> list[dict]:
        result = []
        for idx, line in enumerate(text.strip().splitlines(), start=1):
            line = line.strip()
            if not line:
                continue
            if "|" in line:
                score_str, _, summary = line.partition("|")
                try:
                    score = int(score_str.strip())
                except ValueError:
                    score = 50
            else:
                score = 50
                summary = line
            summary = summary.strip()
            if summary:
                result.append({
                    "id": f"{id_prefix}_{idx:03d}",
                    score_key: score,
                    "summary": summary,
                })
        return result

    @staticmethod
    def _parse_lines(text: str) -> list[str]:
        return [line.strip() for line in text.strip().splitlines() if line.strip()]

    def _on_save(self) -> None:
        try:
            # Keep existing keys we don't edit (character_ref, relationships_with_characters…)
            updated = dict(self._memory)

            updated["relationship_with_user"] = {
                "status_label": self.rel_status_edit.text().strip(),
                **{field: self._parse_int(widget.text()) for field, widget in self._rel_sliders.items()},
                "last_change_reason": self.rel_reason_edit.text().strip(),
                "interpretation": self.rel_interp_edit.toPlainText().strip(),
            }

            updated["emotional_baseline"] = {
                field: self._parse_int(widget.text())
                for field, widget in self._emotion_edits.items()
            }

            stable = self._parse_scored_lines(self.stable_edit.toPlainText(), "importance", "stable")
            episodic_raw = self._parse_scored_lines(self.episodic_edit.toPlainText(), "importance", "epi")
            # Preserve extra keys on existing episodic entries
            existing_episodic = {
                e.get("summary", ""): e
                for e in self._memory.get("memories", {}).get("episodic", [])
                if isinstance(e, dict)
            }
            episodic: list[dict] = []
            for entry in episodic_raw:
                existing = existing_episodic.get(entry["summary"], {})
                merged = {**existing, **entry}
                episodic.append(merged)

            updated["memories"] = {"stable": stable, "episodic": episodic}

            updated["open_threads"] = self._parse_scored_lines(
                self.threads_edit.toPlainText(), "priority", "thread"
            )

            updated["knowledge"] = {
                "suspicions": self._parse_lines(self.suspicions_edit.toPlainText()),
                "unknowns": self._parse_lines(self.unknowns_edit.toPlainText()),
                "secrets_held": self._parse_lines(self.secrets_edit.toPlainText()),
            }

            updated["scene_flags"] = {
                flag: self._parse_bool(widget.text())
                for flag, widget in self._flag_edits.items()
            }

            self._memory = updated
            self._save_memory()
            self.accept()
        except Exception as exc:
            self.error_label.setText(f"Save failed: {exc}")
            logger.exception("Memory save error")

    def _on_reset(self) -> None:
        reply = QMessageBox.question(
            self,
            "Reset Memory",
            "Reset all memory values to blank defaults? This will overwrite current values in the editor (you still need to Save).",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel,
        )
        if reply == QMessageBox.StandardButton.Yes:
            # Clear all relation sliders and emotions to 0
            self.rel_status_edit.setText("Neutral")
            for w in self._rel_sliders.values():
                w.setText("0")
            self.rel_reason_edit.clear()
            self.rel_interp_edit.clear()
            for w in self._emotion_edits.values():
                w.setText("0")
            self.stable_edit.clear()
            self.episodic_edit.clear()
            self.threads_edit.clear()
            self.suspicions_edit.clear()
            self.unknowns_edit.clear()
            self.secrets_edit.clear()
            for flag, w in self._flag_edits.items():
                w.setText("true" if flag == "available_for_interaction" else "false")


class CharacterDetailPanel(QWidget):
    """Right-hand panel showing full character details."""

    chat_requested = Signal(dict)
    edit_requested = Signal(dict)
    edit_memory_requested = Signal(dict)
    delete_requested = Signal(str)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._character: dict[str, Any] | None = None
        self._build_ui()


    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setSpacing(16)
        layout.setContentsMargins(20, 20, 20, 20)

        self.empty_label = QLabel("Select a character to view details.")
        self.empty_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.empty_label.setStyleSheet("color: #c8c8e0; font-size: 14px;")
        layout.addWidget(self.empty_label)

        self.detail_widget = QWidget()
        detail_layout = QHBoxLayout(self.detail_widget)
        detail_layout.setSpacing(16)
        detail_layout.setContentsMargins(0, 0, 0, 0)

        # Left column: Character image (33%)
        left_col = QVBoxLayout()
        left_col.setSpacing(0)
        left_col.setContentsMargins(0, 0, 0, 0)
        self.avatar = CharacterImage(minimum_size=(192, 600))
        self.avatar.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        left_col.addWidget(self.avatar, alignment=Qt.AlignmentFlag.AlignTop)
        left_col.addStretch()

        # Right column: Character details (67%)
        right_col = QVBoxLayout()
        right_col.setSpacing(12)
        right_col.setContentsMargins(0, 0, 0, 0)

        self.name_label = QLabel("")
        font = QFont()
        font.setBold(True)
        font.setPointSize(16)
        self.name_label.setFont(font)
        right_col.addWidget(self.name_label)

        self.title_label = QLabel("")
        self.title_label.setStyleSheet("color: #d8d8f0; font-size: 12px; font-weight: bold;")
        right_col.addWidget(self.title_label)

        self.story_role_label = QLabel("")
        self.story_role_label.setStyleSheet("color: #d8d8f0; font-size: 12px; font-weight: bold;")
        self.story_role_label.setWordWrap(True)
        right_col.addWidget(self.story_role_label)

        self.source_label = QLabel("")
        self.source_label.setStyleSheet("color: #a8a8c8; font-size: 11px;")
        right_col.addWidget(self.source_label)

        self.desc_heading = QLabel("Description")
        self.desc_heading.setObjectName("section_label")
        right_col.addWidget(self.desc_heading)

        self.desc_label = QLabel("")
        self.desc_label.setWordWrap(True)
        self.desc_label.setStyleSheet("color: #f0f0ff; font-size: 12px; line-height: 1.5;")
        right_col.addWidget(self.desc_label)

        self.prompt_heading = QLabel("System Prompt")
        self.prompt_heading.setObjectName("section_label")
        right_col.addWidget(self.prompt_heading)

        self.prompt_preview = QTextEdit()
        self.prompt_preview.setReadOnly(True)
        self.prompt_preview.setMinimumHeight(80)
        self.prompt_preview.setStyleSheet(
            "background-color: #12122a; color: #e0e0f8; "
            "border: 1px solid #3a3a5a; border-radius: 6px; font-size: 11px;"
        )
        right_col.addWidget(self.prompt_preview)

        self.tags_row = QHBoxLayout()
        self.tags_row.setSpacing(6)
        right_col.addLayout(self.tags_row)

        right_col.addStretch()

        btn_row = QHBoxLayout()
        btn_row.setSpacing(10)

        self.chat_btn = QPushButton("💬  Start Chat")
        self.chat_btn.setFixedHeight(36)
        self.chat_btn.clicked.connect(self._on_chat)
        btn_row.addWidget(self.chat_btn)

        self.edit_btn = QPushButton("✏  Edit")
        self.edit_btn.setObjectName("secondary_btn")
        self.edit_btn.setFixedHeight(36)
        self.edit_btn.clicked.connect(self._on_edit)
        btn_row.addWidget(self.edit_btn)

        self.edit_memory_btn = QPushButton("🧠  Edit Memory")
        self.edit_memory_btn.setObjectName("secondary_btn")
        self.edit_memory_btn.setFixedHeight(36)
        self.edit_memory_btn.clicked.connect(self._on_edit_memory)
        btn_row.addWidget(self.edit_memory_btn)

        self.delete_btn = QPushButton("🗑  Delete")
        self.delete_btn.setObjectName("danger_btn")
        self.delete_btn.setFixedHeight(36)
        self.delete_btn.clicked.connect(self._on_delete)
        btn_row.addWidget(self.delete_btn)

        right_col.addLayout(btn_row)

        # Add columns to main detail layout
        detail_layout.addLayout(left_col, 1)
        detail_layout.addLayout(right_col, 2)

        layout.addWidget(self.detail_widget)
        self.detail_widget.hide()

    def set_character(self, character: dict[str, Any] | None) -> None:
        self._character = character
        if character is None:
            self.empty_label.show()
            self.detail_widget.hide()
            return

        self.empty_label.hide()
        self.detail_widget.show()

        name_color = str(character.get("name_color", "") or "#ffffff")
        self.avatar.set_character(
            character.get("name", "?"),
            character.get("avatar_path", ""),
            name_color,
        )
        name = character.get("name", "Unknown")
        self.name_label.setText(f"Name: {name}")
        self.name_label.setStyleSheet(f"color: {name_color}; font-size: 16px; font-weight: bold;")

        title = str(character.get("title", "") or character.get("role", "") or "").strip()
        if title:
            self.title_label.setText(f"Title / Role: {title}")
            self.title_label.show()
        else:
            self.title_label.hide()

        story_role = str(character.get("story_role", "")).strip()
        if story_role:
            self.story_role_label.setText(f"Story Role: {story_role}")
            self.story_role_label.show()
        else:
            self.story_role_label.hide()

        source = str(character.get("source", "user"))
        self.source_label.setText(f"Source: {source}")

        desc = str(character.get("description", "") or "").strip()
        self.desc_label.setText(desc)
        if desc:
            self.desc_heading.show()
            self.desc_label.show()
        else:
            self.desc_heading.hide()
            self.desc_label.hide()

        sys_prompt = str(character.get("system_prompt", "") or "").strip()
        self.prompt_preview.setPlainText(sys_prompt)
        if sys_prompt:
            self.prompt_heading.show()
            self.prompt_preview.show()
        else:
            self.prompt_heading.hide()
            self.prompt_preview.hide()

        while self.tags_row.count():
            item = self.tags_row.takeAt(0)
            if item and item.widget():
                item.widget().deleteLater()

        for tag in character.get("tags", [])[:6]:
            tag_lbl = QLabel(str(tag))
            tag_lbl.setStyleSheet(
                "background-color: #1a4a8a; color: #e0f0ff; "
                "border-radius: 8px; padding: 2px 8px; font-size: 10px; font-weight: bold;"
            )
            self.tags_row.addWidget(tag_lbl)
        self.tags_row.addStretch()

        is_discover = str(character.get("source", "")) == "discover"
        self.edit_btn.setEnabled(not is_discover)
        self.edit_memory_btn.setEnabled(not is_discover)
        self.delete_btn.setEnabled(not is_discover)

    def _on_chat(self) -> None:
        if self._character:
            self.chat_requested.emit(self._character)

    def _on_edit(self) -> None:
        if self._character:
            self.edit_requested.emit(self._character)

    def _on_edit_memory(self) -> None:
        if self._character:
            self.edit_memory_requested.emit(self._character)

    def _on_delete(self) -> None:
        if self._character:
            name = self._character.get("name", "this character")
            reply = QMessageBox.question(
                self,
                "Delete Character",
                f"Are you sure you want to delete '{name}'? This cannot be undone.",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel,
            )
            if reply == QMessageBox.StandardButton.Yes:
                self.delete_requested.emit(str(self._character.get("id", "")))


class MyCharactersPage(QWidget):
    """My Character Library page — list + detail panel."""

    chat_requested = Signal(dict)

    def __init__(self, character_manager: CharacterManager, parent: QWidget | None = None, settings_manager=None) -> None:
        super().__init__(parent)
        self.character_manager = character_manager
        self.chat_storage = ChatStorage()
        self._characters: list[dict[str, Any]] = []
        self.settings_manager = settings_manager
        self._splitter = None
        self._build_ui()
        self.refresh()


    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setSpacing(0)
        layout.setContentsMargins(0, 0, 0, 0)

        top_bar = QFrame()
        top_bar.setStyleSheet("background-color: #16213e; border-bottom: 1px solid #2a2a4a;")
        top_bar.setFixedHeight(60)
        top_layout = QHBoxLayout(top_bar)
        top_layout.setContentsMargins(20, 8, 20, 8)

        heading = QLabel("My Character Library")
        heading.setObjectName("heading")
        top_layout.addWidget(heading)
        top_layout.addStretch()

        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("Search…")
        self.search_input.setMinimumWidth(150)
        self.search_input.setMaximumWidth(280)
        self.search_input.setFixedHeight(32)
        self.search_input.textChanged.connect(self._apply_filter)
        top_layout.addWidget(self.search_input)

        refresh_btn = QPushButton("↻ Refresh")
        refresh_btn.setObjectName("secondary_btn")
        refresh_btn.setFixedHeight(32)
        refresh_btn.clicked.connect(self.refresh)
        top_layout.addWidget(refresh_btn)

        create_btn = QPushButton("＋ Create Character")
        create_btn.setFixedHeight(32)
        create_btn.clicked.connect(self._on_create_character)
        top_layout.addWidget(create_btn)

        layout.addWidget(top_bar)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.setStyleSheet("QSplitter::handle { background-color: #2a2a4a; }")
        self._splitter = splitter

        left_panel = QWidget()
        left_panel.setStyleSheet("background-color: #16213e;")
        left_panel.setMinimumWidth(180)
        left_panel.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Expanding)
        left_layout = QVBoxLayout(left_panel)
        left_layout.setSpacing(0)
        left_layout.setContentsMargins(0, 0, 0, 0)

        self.char_list = QListWidget()
        self.char_list.setFrameShape(QFrame.Shape.NoFrame)
        self.char_list.setStyleSheet(
            "QListWidget { background-color: #16213e; border: none; color: #ffffff; }"
            "QListWidget::item { padding: 10px 14px; border-bottom: 1px solid #3a3a5a; color: #ffffff; }"
            "QListWidget::item:selected { background-color: #0f3460; color: #ffffff; }"
        )
        self.char_list.currentRowChanged.connect(self._on_selection_changed)
        left_layout.addWidget(self.char_list)

        splitter.addWidget(left_panel)

        self.detail_panel = CharacterDetailPanel()
        self.detail_panel.chat_requested.connect(self.chat_requested.emit)
        self.detail_panel.edit_requested.connect(self._on_edit_character)
        self.detail_panel.edit_memory_requested.connect(self._on_edit_character_memory)
        self.detail_panel.delete_requested.connect(self._on_delete_character)
        splitter.addWidget(self.detail_panel)

        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 3)

        # Restore splitter ratio from settings if available
        sizes = None
        if self.settings_manager:
            ratio = self.settings_manager.get("my_characters_splitter_ratio", None)
            if isinstance(ratio, (list, tuple)) and len(ratio) == 2:
                sizes = ratio
        if sizes:
            splitter.setSizes(sizes)
        else:
            splitter.setSizes([280, 780])

        splitter.splitterMoved.connect(self._on_splitter_moved)

        layout.addWidget(splitter)

    def _on_splitter_moved(self, pos, index):
        if self.settings_manager and self._splitter:
            sizes = self._splitter.sizes()
            self.settings_manager.set("my_characters_splitter_ratio", sizes)

    def _on_create_character(self) -> None:
        empty_character = {
            "name": "",
            "role": "",
            "story_role": "",
            "system_prompt": "",
            "starting_scenario": "",
            "greeting": "",
            "identity": {
                "age_band": "",
                "public_summary": "",
                "private_truths": [],
                "core_traits": [],
                "values": [],
                "fears": [],
                "goals": {
                    "short_term": [],
                    "mid_term": [],
                    "long_term": []
                },
                "boundaries": {
                    "hard": [],
                    "soft": []
                },
                "age": 0
            },
            "voice": {
                "tone": "",
                "cadence": "",
                "favored_patterns": [],
                "avoid_patterns": []
            },
            "knowledge": {
                "known_facts": []
            },
            "tags": [],
            "folder": "General"
        }
        dialog = EditCharacterDialog(empty_character, self.character_manager, parent=self)
        dialog.setWindowTitle("Create Character")
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self.refresh()
            # Select the newly created character
            for i in range(self.char_list.count()):
                item = self.char_list.item(i)
                if item:
                    c = item.data(Qt.ItemDataRole.UserRole)
                    if str(c.get("name", "")) == dialog.name_edit.text().strip():
                        self.char_list.setCurrentRow(i)
                        break

    def refresh(self) -> None:
        try:
            all_chars = self.character_manager.list_all_characters()
        except Exception as exc:
            logger.error("Failed to load characters: %s", exc)
            all_chars = []

        # Determine which built-in (discover) character names have an active chat
        builtin_with_chats: set[str] = set()
        try:
            chats = self.chat_storage.list_chats()
            for chat in chats:
                char_name = str(chat.get("character_name", "")).strip().lower()
                if char_name:
                    builtin_with_chats.add(char_name)
        except Exception as exc:
            logger.warning("Could not read chat list for filtering: %s", exc)

        # Keep all user-created characters; keep built-in only if they have a chat
        self._characters = [
            c for c in all_chars
            if str(c.get("source", "")) != "discover"
            or str(c.get("name", "")).strip().lower() in builtin_with_chats
        ]

        self._apply_filter(self.search_input.text())

    def _apply_filter(self, query: str) -> None:
        q = query.strip().lower()
        if q:
            filtered = [
                c for c in self._characters
                if q in str(c.get("name", "")).lower()
                or any(q in str(t).lower() for t in c.get("tags", []))
            ]
        else:
            filtered = list(self._characters)
        self._populate_list(filtered)

    def _populate_list(self, characters: list[dict[str, Any]]) -> None:
        self.char_list.clear()
        self._filtered = characters
        for char in characters:
            name = str(char.get("name", "Unknown"))
            source = str(char.get("source", ""))
            label = f"{'★ ' if char.get('is_favorite') else ''}{name}"
            if source == "discover":
                label += "  [built-in]"
            item = QListWidgetItem(label)
            item.setData(Qt.ItemDataRole.UserRole, char)
            self.char_list.addItem(item)
        self.detail_panel.set_character(None)

    def _on_selection_changed(self, row: int) -> None:
        if row < 0:
            self.detail_panel.set_character(None)
            return
        item = self.char_list.item(row)
        if item:
            char = item.data(Qt.ItemDataRole.UserRole)
            self.detail_panel.set_character(char)

    def _on_edit_character(self, character: dict[str, Any]) -> None:
        dialog = EditCharacterDialog(character, self.character_manager, parent=self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self.refresh()
            # Re-select the edited character
            edited_name = character.get("name", "")
            for i in range(self.char_list.count()):
                item = self.char_list.item(i)
                if item:
                    c = item.data(Qt.ItemDataRole.UserRole)
                    if str(c.get("name", "")) == edited_name:
                        self.char_list.setCurrentRow(i)
                        break

    def _on_edit_character_memory(self, character: dict[str, Any]) -> None:
        slug = str(character.get("id", "")).strip() or str(character.get("name", "")).strip().lower().replace(" ", "_")
        memory_path = self.character_manager._character_memory_file(slug)
        if not memory_path.is_file():
            # Ensure a blank memory file is created before opening the editor
            try:
                self.character_manager._ensure_memory(slug)
            except Exception as exc:
                QMessageBox.warning(self, "Memory Error", f"Could not create memory file:\n{exc}")
                return
        dialog = EditMemoryDialog(character, self.character_manager, parent=self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            # Re-select the character so the panel refreshes without losing selection
            current_name = character.get("name", "")
            self.refresh()
            for i in range(self.char_list.count()):
                item = self.char_list.item(i)
                if item:
                    c = item.data(Qt.ItemDataRole.UserRole)
                    if str(c.get("name", "")) == current_name:
                        self.char_list.setCurrentRow(i)
                        break

    def _on_delete_character(self, character_id: str) -> None:
        try:
            self.character_manager.delete_character(character_id)
            self.refresh()
        except Exception as exc:
            QMessageBox.warning(self, "Delete Failed", str(exc))
