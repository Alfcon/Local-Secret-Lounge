import logging
import psutil
from typing import Any

from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QFrame, QGridLayout
)

from core.gpu_detector import detect as detect_gpu
from core.gpu_recommender import recommend
from core.model_manager import ModelManager

logger = logging.getLogger(__name__)

class _DetectWorker(QThread):
    finished_signal = Signal(dict)

    def __init__(self, model_manager: ModelManager | None = None):
        super().__init__()
        self.model_manager = model_manager

    def run(self) -> None:
        data: dict[str, Any] = {}
        
        # 1. Detect GPU
        gpu_info = detect_gpu()
        if gpu_info:
            data.update(gpu_info)
            data['gpu_detected'] = True
        else:
            data['gpu_detected'] = False
            
        # 2. CPU / RAM
        data['cpu_cores'] = psutil.cpu_count(logical=False) or psutil.cpu_count(logical=True) or 4
        data['ram_gb'] = psutil.virtual_memory().total / (1024**3)
        
        # 3. Model
        model_name = "Unknown Model"
        model_params_billions = 7.0
        model_quantization = "Q4_K_M"
        
        if self.model_manager and hasattr(self.model_manager, 'settings_manager'):
            try:
                sm = self.model_manager.settings_manager
                model_id = sm.get('default_model_id') or sm.get('last_model_id')
                if model_id:
                    model = self.model_manager.get_model(str(model_id))
                    if model:
                        model_name = model.get('name', 'Unknown')
                        filename = str(model.get('filename', '')).upper()
                        
                        if '7B' in filename: model_params_billions = 7.0
                        elif '8B' in filename: model_params_billions = 8.0
                        elif '13B' in filename: model_params_billions = 13.0
                        elif '14B' in filename: model_params_billions = 14.0
                        elif '30B' in filename: model_params_billions = 30.0
                        elif '34B' in filename: model_params_billions = 34.0
                        elif '70B' in filename: model_params_billions = 70.0
                        
                        if 'Q4_' in filename: model_quantization = "Q4_K_M"
                        elif 'Q5_' in filename: model_quantization = "Q5_K_M"
                        elif 'Q8_' in filename: model_quantization = "Q8_0"
                        elif 'FP16' in filename: model_quantization = "FP16"
            except Exception as e:
                logger.debug("Error extracting model info: %s", e)
                
        data['model_name'] = model_name
        data['model_params_billions'] = model_params_billions
        data['model_quantization'] = model_quantization
        
        self.finished_signal.emit(data)


class HardwareAdvisorWidget(QFrame):
    """Widget to display hardware specs and recommended generation settings."""

    def __init__(self, model_manager: ModelManager | None = None, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.model_manager = model_manager
        self.setObjectName("hardwareAdvisorWidget")
        self.setStyleSheet("""
            #hardwareAdvisorWidget {
                background-color: #1e1e32;
                border: 1px solid #33334d;
                border-radius: 8px;
            }
            QLabel { color: #d0d0e0; }
            QLabel#headerLabel { font-weight: bold; color: #a49aff; }
            QLabel#warningLabel { color: #ffb86c; }
        """)
        
        self._worker: _DetectWorker | None = None
        self._recommendations: dict[str, int | list[str]] = {}
        
        self._build_ui()
        self._start_detection()
        
        if self.model_manager and hasattr(self.model_manager, 'add_default_changed_listener'):
            try:
                self.model_manager.add_default_changed_listener(self._on_model_changed)
            except Exception as e:
                logger.debug("Could not hook model_manager listener: %s", e)

    def _build_ui(self) -> None:
        self.main_layout = QVBoxLayout(self)
        self.main_layout.setContentsMargins(16, 16, 16, 16)
        self.main_layout.setSpacing(12)
        
        # Header
        header_layout = QHBoxLayout()
        title = QLabel("Hardware Advisor")
        title.setStyleSheet("font-size: 14px; font-weight: bold; color: #e6e6fa;")
        header_layout.addWidget(title)
        header_layout.addStretch()
        
        self.refresh_btn = QPushButton("↻ Refresh Hardware")
        self.refresh_btn.setFixedHeight(28)
        self.refresh_btn.clicked.connect(self._start_detection)
        header_layout.addWidget(self.refresh_btn)
        
        self.main_layout.addLayout(header_layout)
        
        # Content Grid
        self.grid = QGridLayout()
        self.grid.setHorizontalSpacing(24)
        self.grid.setVerticalSpacing(8)
        
        self.gpu_label = QLabel("Detecting...")
        self.cpu_label = QLabel("Detecting...")
        self.model_label = QLabel("Detecting...")
        self.rec_label = QLabel("Detecting...")
        
        lbl_gpu = QLabel("GPU:")
        lbl_gpu.setObjectName("headerLabel")
        self.grid.addWidget(lbl_gpu, 0, 0)
        self.grid.addWidget(self.gpu_label, 0, 1)
        
        lbl_cpu = QLabel("CPU/RAM:")
        lbl_cpu.setObjectName("headerLabel")
        self.grid.addWidget(lbl_cpu, 1, 0)
        self.grid.addWidget(self.cpu_label, 1, 1)
        
        lbl_model = QLabel("Active Model:")
        lbl_model.setObjectName("headerLabel")
        self.grid.addWidget(lbl_model, 2, 0)
        self.grid.addWidget(self.model_label, 2, 1)
        
        lbl_rec = QLabel("Recommendations:")
        lbl_rec.setObjectName("headerLabel")
        self.grid.addWidget(lbl_rec, 3, 0, Qt.AlignmentFlag.AlignTop)
        self.grid.addWidget(self.rec_label, 3, 1)
        
        self.main_layout.addLayout(self.grid)
        
        # Warnings
        self.warnings_label = QLabel("")
        self.warnings_label.setObjectName("warningLabel")
        self.warnings_label.setWordWrap(True)
        self.warnings_label.setVisible(False)
        self.main_layout.addWidget(self.warnings_label)
        
        # Apply button
        apply_layout = QHBoxLayout()
        apply_layout.addStretch()
        self.apply_btn = QPushButton("✓ Apply Recommendations")
        self.apply_btn.setFixedHeight(32)
        self.apply_btn.setEnabled(False)
        self.apply_btn.clicked.connect(self._apply_recommendations)
        apply_layout.addWidget(self.apply_btn)
        
        self.main_layout.addLayout(apply_layout)

    def _start_detection(self) -> None:
        self.refresh_btn.setEnabled(False)
        self.apply_btn.setEnabled(False)
        self.gpu_label.setText("Detecting...")
        self.cpu_label.setText("Detecting...")
        self.model_label.setText("Detecting...")
        self.rec_label.setText("Detecting...")
        self.warnings_label.setVisible(False)
        
        self._worker = _DetectWorker(self.model_manager)
        self._worker.finished_signal.connect(self._on_detection_finished)
        self._worker.start()

    def _on_detection_finished(self, data: dict[str, Any]) -> None:
        self.refresh_btn.setEnabled(True)
        
        # GPU
        gpu_detected = data.get('gpu_detected', False)
        if gpu_detected:
            brand = str(data.get('gpu_brand', '')).capitalize()
            name = data.get('gpu_name', 'Unknown')
            total = data.get('gpu_vram_total_mb', 0)
            self.gpu_label.setText(f"{name} | {total} MB VRAM | {brand}")
            gpu_vram = total
        else:
            self.gpu_label.setText("Not detected (Using CPU defaults)")
            gpu_vram = None
            
        # CPU / RAM
        cores = data.get('cpu_cores', 4)
        ram = data.get('ram_gb', 8.0)
        self.cpu_label.setText(f"{cores} cores | {ram:.1f} GB RAM")
        
        # Model
        model_name = data.get('model_name', 'Unknown')
        model_params = data.get('model_params_billions', 7.0)
        model_quant = data.get('model_quantization', 'Q4_K_M')
        self.model_label.setText(f"{model_name} (~{model_params}B, {model_quant})")
        
        # Recommend
        self._recommendations = recommend(
            gpu_vram_mb=gpu_vram,
            model_params_billions=model_params,
            model_quantization=model_quant,
            cpu_cores=cores,
            ram_gb=ram
        )
        
        ctx = self._recommendations.get('context_size', 4096)
        thr = self._recommendations.get('threads', 4)
        tok = self._recommendations.get('max_tokens', 384)
        
        self.rec_label.setText(f"Context: {ctx} | Threads: {thr} | Max Tokens: {tok}")
        
        warnings = self._recommendations.get('warnings', [])
        if warnings and isinstance(warnings, list):
            self.warnings_label.setText("\\n".join(warnings))
            self.warnings_label.setVisible(True)
        else:
            self.warnings_label.setVisible(False)
            
        self.apply_btn.setEnabled(True)

    def _on_model_changed(self, *args, **kwargs) -> None:
        self._start_detection()

    def _apply_recommendations(self) -> None:
        ctx = int(str(self._recommendations.get('context_size', 4096)))
        thr = int(str(self._recommendations.get('threads', 4)))
        tok = int(str(self._recommendations.get('max_tokens', 384)))
        
        parent = self.parentWidget()
        while parent:
            if hasattr(parent, 'ctx_spin') and hasattr(parent, 'threads_spin') and hasattr(parent, 'max_tokens_spin'):
                parent.ctx_spin.setValue(ctx)
                parent.threads_spin.setValue(thr)
                parent.max_tokens_spin.setValue(tok)
                break
            parent = parent.parentWidget()
