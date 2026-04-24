import sys
import unittest
from unittest.mock import patch, MagicMock

from PySide6.QtWidgets import QApplication
from ui.widgets.hardware_advisor_widget import HardwareAdvisorWidget

# Ensure a QApplication exists before creating widgets
app = QApplication.instance()
if app is None:
    app = QApplication(sys.argv)

class TestHardwareAdvisorWidget(unittest.TestCase):

    def setUp(self):
        self.mock_model_manager = MagicMock()
        self.mock_settings_manager = MagicMock()
        self.mock_model_manager.settings_manager = self.mock_settings_manager
        
        self.mock_settings_manager.get.return_value = 'test_model_id'
        self.mock_model_manager.get_model.return_value = {
            'name': 'Test Model',
            'filename': 'test_model_7b_Q4_K_M.gguf'
        }

    @patch('ui.widgets.hardware_advisor_widget.detect_gpu')
    @patch('ui.widgets.hardware_advisor_widget.recommend')
    @patch('ui.widgets.hardware_advisor_widget.psutil')
    def test_widget_initialization(self, mock_psutil, mock_recommend, mock_detect_gpu):
        mock_detect_gpu.return_value = {
            'gpu_name': 'RTX 3080',
            'gpu_brand': 'nvidia',
            'gpu_vram_total_mb': 10240,
            'gpu_vram_free_mb': 8192
        }
        
        mock_psutil.cpu_count.return_value = 8
        mock_virtual_memory = MagicMock()
        mock_virtual_memory.total = 16 * (1024**3)
        mock_psutil.virtual_memory.return_value = mock_virtual_memory
        
        mock_recommend.return_value = {
            'context_size': 4096,
            'threads': 4,
            'max_tokens': 512,
            'warnings': []
        }

        widget = HardwareAdvisorWidget(model_manager=self.mock_model_manager)
        self.assertIsNotNone(widget)
        
        # Test basic UI elements exist
        self.assertTrue(hasattr(widget, 'refresh_btn'))
        self.assertTrue(hasattr(widget, 'apply_btn'))
        self.assertTrue(hasattr(widget, 'gpu_label'))

    @patch('ui.widgets.hardware_advisor_widget.detect_gpu')
    @patch('ui.widgets.hardware_advisor_widget.recommend')
    @patch('ui.widgets.hardware_advisor_widget.psutil')
    def test_detection_flow(self, mock_psutil, mock_recommend, mock_detect_gpu):
        # We can directly test the worker to avoid complex QThread timing issues in unittest
        from ui.widgets.hardware_advisor_widget import _DetectWorker
        
        mock_detect_gpu.return_value = {
            'gpu_name': 'RTX 3080',
            'gpu_brand': 'nvidia',
            'gpu_vram_total_mb': 10240,
            'gpu_vram_free_mb': 8192
        }
        
        mock_psutil.cpu_count.return_value = 8
        mock_virtual_memory = MagicMock()
        mock_virtual_memory.total = 16 * (1024**3)
        mock_psutil.virtual_memory.return_value = mock_virtual_memory

        worker = _DetectWorker(self.mock_model_manager)
        
        # Capture signal output
        emitted_data = None
        def catch_signal(data):
            nonlocal emitted_data
            emitted_data = data
            
        worker.finished_signal.connect(catch_signal)
        worker.run() # Call run directly synchronously
        
        self.assertIsNotNone(emitted_data)
        self.assertEqual(emitted_data['gpu_name'], 'RTX 3080')
        self.assertEqual(emitted_data['cpu_cores'], 8)
        self.assertEqual(emitted_data['ram_gb'], 16.0)
        self.assertEqual(emitted_data['model_name'], 'Test Model')
        self.assertEqual(emitted_data['model_params_billions'], 7.0)
        self.assertEqual(emitted_data['model_quantization'], 'Q4_K_M')

if __name__ == '__main__':
    unittest.main()
