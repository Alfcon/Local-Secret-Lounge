from __future__ import annotations

import os
import platform
import subprocess
from typing import Any

from PySide6.QtCore import QObject, QThread, Qt, Signal
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
)

try:
    import psutil as _psutil

    _PSUTIL_OK = True
except ImportError:
    _PSUTIL_OK = False


# ---------------------------------------------------------------------------
# Background worker — runs system detection off the UI thread
# ---------------------------------------------------------------------------

class _DetectWorker(QObject):
    """Detects CPU / RAM / GPU info in a background thread."""

    finished: Signal = Signal(dict)

    def run(self) -> None:  # called by QThread.started
        info: dict[str, Any] = {
            "cpu_name": platform.processor() or platform.machine() or "Unknown",
            "cpu_cores": os.cpu_count() or 1,
            "ram_total_gb": 0.0,
            "ram_avail_gb": 0.0,
            "gpu_name": None,
            "gpu_vram_total_mb": 0,
            "gpu_vram_free_mb": 0,
        }

        if _PSUTIL_OK:
            vm = _psutil.virtual_memory()
            info["ram_total_gb"] = vm.total / (1024 ** 3)
            info["ram_avail_gb"] = vm.available / (1024 ** 3)

        try:
            result = subprocess.run(
                [
                    "nvidia-smi",
                    "--query-gpu=name,memory.total,memory.free",
                    "--format=csv,noheader,nounits",
                ],
                capture_output=True,
                text=True,
                timeout=5,
            )
            if result.returncode == 0 and result.stdout.strip():
                # nvidia-smi returns one line per GPU; use the first
                first_line = result.stdout.strip().splitlines()[0]
                parts = [p.strip() for p in first_line.split(",")]
                if len(parts) >= 3:
                    info["gpu_name"] = parts[0]
                    info["gpu_vram_total_mb"] = int(parts[1])
                    info["gpu_vram_free_mb"] = int(parts[2])
        except Exception:
            pass  # no nvidia-smi or not an NVIDIA system

        self.finished.emit(info)


# ---------------------------------------------------------------------------
# Main widget
# ---------------------------------------------------------------------------

class SystemInfoWidget(QFrame):
    """
    Small card placed above the Local GGUF Models section.
    Shows live CPU / RAM / GPU stats and calculates recommended performance
    settings for whichever GGUF model the user has selected.
    """

    def __init__(self, model_manager, parent=None) -> None:
        super().__init__(parent)
        self.model_manager = model_manager
        self.setObjectName("sectionCard")

        # Cached hardware values (populated after detection)
        self._cpu_name: str = "Detecting…"
        self._cpu_cores: int = os.cpu_count() or 1
        self._ram_total_gb: float = 0.0
        self._ram_avail_gb: float = 0.0
        self._gpu_name: str | None = None
        self._gpu_vram_total_mb: int = 0
        self._gpu_vram_free_mb: int = 0

        self._selected_model_id: str | None = None

        # Thread references — kept alive until finished
        self._thread: QThread | None = None
        self._worker: _DetectWorker | None = None

        self._build_ui()
        self._run_detection()

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(16, 14, 16, 14)
        root.setSpacing(10)

        # Header row -------------------------------------------------------
        hdr = QHBoxLayout()
        lbl = QLabel("System & Model Advisor")
        lbl.setObjectName("sectionTitle")
        hdr.addWidget(lbl)
        hdr.addStretch()
        self._refresh_btn = QPushButton("Refresh")
        self._refresh_btn.setFixedWidth(84)
        self._refresh_btn.setToolTip("Re-read CPU, RAM and GPU information")
        self._refresh_btn.clicked.connect(self._run_detection)
        hdr.addWidget(self._refresh_btn)
        root.addLayout(hdr)

        subtitle = QLabel(
            "Live hardware snapshot and starting-point settings for the selected model."
        )
        subtitle.setStyleSheet("color: #8f98c2; font-size: 12px;")
        root.addWidget(subtitle)

        # Hardware stats ---------------------------------------------------
        hw_row = QHBoxLayout()
        hw_row.setSpacing(28)
        self._cpu_val = self._make_stat(hw_row, "CPU")
        self._ram_val = self._make_stat(hw_row, "System RAM")
        self._gpu_val = self._make_stat(hw_row, "GPU / VRAM")
        hw_row.addStretch()
        root.addLayout(hw_row)

        # Divider ----------------------------------------------------------
        div = QFrame()
        div.setFrameShape(QFrame.Shape.HLine)
        div.setStyleSheet("background:#2d3147; max-height:1px; border:none;")
        root.addWidget(div)

        # Recommendations --------------------------------------------------
        rec_hdr = QLabel("Recommended Settings for Selected Model")
        rec_hdr.setStyleSheet(
            "color:#c4bedf; font-size:13px; font-weight:600;"
        )
        root.addWidget(rec_hdr)

        rec_row = QHBoxLayout()
        rec_row.setSpacing(28)
        self._rec_ctx     = self._make_rec(rec_row, "Context Size")
        self._rec_threads = self._make_rec(rec_row, "Threads")
        self._rec_tokens  = self._make_rec(rec_row, "Max Tokens")
        self._rec_gpu_lyr = self._make_rec(rec_row, "GPU Layers\n(llama.cpp)")
        rec_row.addStretch()
        root.addLayout(rec_row)

        self._note_lbl = QLabel(
            "Select a model in the list below to see tailored recommendations."
        )
        self._note_lbl.setStyleSheet("color:#8f98c2; font-size:12px;")
        self._note_lbl.setWordWrap(True)
        root.addWidget(self._note_lbl)

    # ------------------------------------------------------------------
    # Widget factory helpers
    # ------------------------------------------------------------------

    def _make_stat(self, parent: QHBoxLayout, caption: str) -> QLabel:
        """Returns the value QLabel; adds a captioned vertical block to parent."""
        col = QVBoxLayout()
        col.setSpacing(2)
        cap = QLabel(caption)
        cap.setStyleSheet("color:#8f98c2; font-size:11px; font-weight:600;")
        val = QLabel("Detecting…")
        val.setStyleSheet("color:#f3ecff; font-size:12px;")
        val.setWordWrap(True)
        val.setMaximumWidth(230)
        col.addWidget(cap)
        col.addWidget(val)
        parent.addLayout(col)
        return val

    def _make_rec(self, parent: QHBoxLayout, caption: str) -> QLabel:
        """Returns the value QLabel; adds a centred recommendation block to parent."""
        col = QVBoxLayout()
        col.setSpacing(2)
        cap = QLabel(caption)
        cap.setStyleSheet("color:#8f98c2; font-size:11px; font-weight:600;")
        cap.setAlignment(Qt.AlignmentFlag.AlignCenter)
        val = QLabel("—")
        val.setStyleSheet(
            "color:#ead6ff; font-size:18px; font-weight:700;"
        )
        val.setAlignment(Qt.AlignmentFlag.AlignCenter)
        col.addWidget(cap)
        col.addWidget(val)
        parent.addLayout(col)
        return val

    # ------------------------------------------------------------------
    # Background detection
    # ------------------------------------------------------------------

    def _run_detection(self) -> None:
        """Kick off a background thread to read hardware info."""
        # Disable refresh while running
        self._refresh_btn.setEnabled(False)
        self._cpu_val.setText("Detecting…")
        self._ram_val.setText("Detecting…")
        self._gpu_val.setText("Detecting…")

        # Clean up any previous thread
        if self._thread is not None and self._thread.isRunning():
            self._thread.quit()
            self._thread.wait(2000)

        self._thread = QThread(self)
        self._worker = _DetectWorker()
        self._worker.moveToThread(self._thread)

        self._thread.started.connect(self._worker.run)
        self._worker.finished.connect(self._on_detection_done)
        self._worker.finished.connect(self._thread.quit)

        self._thread.start()

    def _on_detection_done(self, info: dict) -> None:
        """Called on the UI thread once detection finishes."""
        self._cpu_name           = str(info.get("cpu_name", "Unknown"))
        self._cpu_cores          = int(info.get("cpu_cores", 1))
        self._ram_total_gb       = float(info.get("ram_total_gb", 0))
        self._ram_avail_gb       = float(info.get("ram_avail_gb", 0))
        self._gpu_name           = info.get("gpu_name")
        self._gpu_vram_total_mb  = int(info.get("gpu_vram_total_mb", 0))
        self._gpu_vram_free_mb   = int(info.get("gpu_vram_free_mb", 0))

        # CPU display
        cpu_disp = self._cpu_name
        if len(cpu_disp) > 42:
            cpu_disp = cpu_disp[:40] + "…"
        self._cpu_val.setText(f"{cpu_disp}\n{self._cpu_cores} logical cores")

        # RAM display
        if self._ram_total_gb > 0:
            self._ram_val.setText(
                f"{self._ram_total_gb:.1f} GB total\n"
                f"{self._ram_avail_gb:.1f} GB free"
            )
        else:
            self._ram_val.setText("Install psutil\nfor RAM data")

        # GPU display
        if self._gpu_name:
            vram_total = self._gpu_vram_total_mb / 1024
            vram_free  = self._gpu_vram_free_mb  / 1024
            self._gpu_val.setText(
                f"{self._gpu_name}\n"
                f"{vram_total:.1f} GB total · {vram_free:.1f} GB free"
            )
        else:
            self._gpu_val.setText(
                "No NVIDIA GPU detected\nCPU inference only"
            )

        self._refresh_btn.setEnabled(True)
        self._update_recommendations()

    # ------------------------------------------------------------------
    # Public API — called from settings_page when selection changes
    # ------------------------------------------------------------------

    def update_for_model(self, model_id: str | None) -> None:
        """Update recommendations for the given model id (may be None)."""
        self._selected_model_id = model_id
        self._update_recommendations()

    # ------------------------------------------------------------------
    # Recommendation logic
    # ------------------------------------------------------------------

    def _update_recommendations(self) -> None:
        model_id = self._selected_model_id
        if not model_id:
            self._reset_rec_labels()
            self._note_lbl.setText(
                "Select a model in the list below to see tailored recommendations."
            )
            return

        model = self.model_manager.get_model(model_id)
        if model is None:
            self._reset_rec_labels()
            return

        size_bytes = int(model.get("size_bytes", 0) or 0)
        size_gb = size_bytes / (1024 ** 3)

        rec = self._compute(size_gb)
        model_name = str(model.get("name", "Selected model"))

        self._rec_ctx.setText(str(rec["context_size"]))
        self._rec_ctx.setStyleSheet(
            "color:#ead6ff; font-size:18px; font-weight:700;"
        )

        self._rec_threads.setText(str(rec["threads"]))
        self._rec_threads.setStyleSheet(
            "color:#ead6ff; font-size:18px; font-weight:700;"
        )

        self._rec_tokens.setText(str(rec["max_tokens"]))
        self._rec_tokens.setStyleSheet(
            "color:#ead6ff; font-size:18px; font-weight:700;"
        )

        gpu_lyr    = rec["gpu_layers"]
        total_lyr  = rec["total_layers"]

        if gpu_lyr == 0:
            gpu_text  = "CPU only\n(0)"
            gpu_colour = "#9fa7d1"
        elif gpu_lyr >= total_lyr:
            gpu_text  = f"All layers\n({gpu_lyr})"
            gpu_colour = "#7bde9a"  # green — full GPU
        else:
            gpu_text  = f"{gpu_lyr} / {total_lyr}"
            gpu_colour = "#f0c060"  # amber — split

        self._rec_gpu_lyr.setText(gpu_text)
        self._rec_gpu_lyr.setStyleSheet(
            f"color:{gpu_colour}; font-size:15px; font-weight:700;"
        )

        # Build explanatory note
        size_label = f"{size_gb:.1f} GB" if size_gb > 0 else "unknown size"
        notes: list[str] = [f"Model: {model_name} ({size_label})."]

        if gpu_lyr == 0:
            notes.append(
                "No NVIDIA GPU found — all layers run on CPU. "
                "Generation will be slower."
            )
        elif gpu_lyr >= total_lyr:
            notes.append("Model fits fully in GPU VRAM — best speed.")
        else:
            notes.append(
                f"{gpu_lyr} of {total_lyr} layers offloaded to GPU; "
                "remainder runs on CPU (split mode)."
            )

        notes.append(
            "These are starting-point values. "
            "Reduce context size if you see token-limit errors."
        )
        self._note_lbl.setText("  ".join(notes))

    def _reset_rec_labels(self) -> None:
        style = "color:#ead6ff; font-size:18px; font-weight:700;"
        for lbl in (
            self._rec_ctx,
            self._rec_threads,
            self._rec_tokens,
            self._rec_gpu_lyr,
        ):
            lbl.setText("—")
            lbl.setStyleSheet(style)

    def _estimate_layers(self, size_gb: float) -> int:
        """Estimate transformer layer count from model file size."""
        if size_gb < 2:    return 26   # ~1-2 B
        elif size_gb < 5:  return 32   # 3 B
        elif size_gb < 10: return 32   # 7 B Q4–Q8
        elif size_gb < 15: return 40   # 13 B
        elif size_gb < 25: return 48   # 20–30 B
        else:              return 60   # 30 B +

    def _compute(self, size_gb: float) -> dict:
        """Return recommended settings dict for a model of the given size."""
        total_layers = self._estimate_layers(size_gb)
        vram_gb = self._gpu_vram_total_mb / 1024 if self._gpu_vram_total_mb else 0.0
        ram_gb  = self._ram_total_gb or 8.0  # safe fallback

        # GPU layers — keep 12 % VRAM as headroom for KV cache
        if vram_gb > 0 and size_gb > 0:
            usable = vram_gb * 0.88
            if size_gb <= usable:
                gpu_layers = total_layers
            else:
                gpu_layers = max(0, int(total_layers * (usable / size_gb)))
        else:
            gpu_layers = 0

        # Context size — driven by system RAM
        if ram_gb >= 48:   ctx = 16384
        elif ram_gb >= 32: ctx = 8192
        elif ram_gb >= 16: ctx = 4096
        else:              ctx = 2048

        # Clamp context for low-RAM CPU-only setups to prevent overflow
        if gpu_layers == 0 and ram_gb < 16:
            ctx = min(ctx, 2048)

        # Threads — leave 2 logical cores free for OS / other tasks
        threads = max(4, min(self._cpu_cores - 2, 16))

        # Max tokens
        if gpu_layers >= total_layers:
            max_tokens = 2048
        elif gpu_layers > 0:
            max_tokens = 1024
        else:
            max_tokens = 512

        return {
            "context_size": ctx,
            "threads": threads,
            "max_tokens": max_tokens,
            "gpu_layers": gpu_layers,
            "total_layers": total_layers,
        }
