import unittest
from unittest.mock import patch, MagicMock
import subprocess
import json

from core import gpu_detector

class TestGPUDetector(unittest.TestCase):

    @patch('core.gpu_detector.subprocess.run')
    def test_nvidia_detection_success(self, mock_run):
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "RTX 4090, 24576, 20000\n"
        mock_run.return_value = mock_result

        result = gpu_detector.detect()
        
        self.assertIsNotNone(result)
        self.assertEqual(result['gpu_name'], "RTX 4090")
        self.assertEqual(result['gpu_brand'], "nvidia")
        self.assertEqual(result['gpu_vram_total_mb'], 24576)
        self.assertEqual(result['gpu_vram_free_mb'], 20000)

    @patch('core.gpu_detector.subprocess.run')
    def test_amd_detection_success(self, mock_run):
        # First call (nvidia) fails
        mock_nvidia = MagicMock()
        mock_nvidia.returncode = 1
        
        # Second call (amd) succeeds
        mock_amd = MagicMock()
        mock_amd.returncode = 0
        mock_amd.stdout = json.dumps({
            "card0": {
                "Card series": "Radeon RX 7900 XTX",
                "VRAM Total Memory (B)": "25769803776",
                "VRAM Total Used Memory (B)": "1073741824"
            }
        })
        
        mock_run.side_effect = [mock_nvidia, mock_amd]

        result = gpu_detector.detect()
        
        self.assertIsNotNone(result)
        self.assertEqual(result['gpu_name'], "Radeon RX 7900 XTX")
        self.assertEqual(result['gpu_brand'], "amd")
        self.assertEqual(result['gpu_vram_total_mb'], 24576)  # 24GB
        self.assertEqual(result['gpu_vram_free_mb'], 23552)   # 24GB - 1GB

    @patch('core.gpu_detector.subprocess.run')
    def test_amd_fallback_text_parsing(self, mock_run):
        mock_nvidia = MagicMock()
        mock_nvidia.returncode = 1
        
        mock_amd = MagicMock()
        mock_amd.returncode = 0
        # Invalid JSON, triggering fallback
        mock_amd.stdout = '''
Card series: Radeon RX 6800
VRAM Total Memory (B): 17179869184
VRAM Total Used Memory (B): 2147483648
        '''
        
        mock_run.side_effect = [mock_nvidia, mock_amd]
        
        result = gpu_detector.detect()
        
        self.assertIsNotNone(result)
        self.assertEqual(result['gpu_name'], "Radeon RX 6800")
        self.assertEqual(result['gpu_brand'], "amd")
        self.assertEqual(result['gpu_vram_total_mb'], 16384)
        self.assertEqual(result['gpu_vram_free_mb'], 14336)

    @patch('core.gpu_detector.subprocess.run')
    def test_timeout_handling(self, mock_run):
        mock_run.side_effect = subprocess.TimeoutExpired(cmd='nvidia-smi', timeout=5)
        
        result = gpu_detector.detect()
        self.assertIsNone(result)

    @patch('core.gpu_detector.subprocess.run')
    def test_no_gpu_detected(self, mock_run):
        mock_fail = MagicMock()
        mock_fail.returncode = 1
        mock_run.side_effect = [mock_fail, mock_fail]
        
        result = gpu_detector.detect()
        self.assertIsNone(result)

    @patch('core.gpu_detector.subprocess.run')
    def test_command_not_found(self, mock_run):
        mock_run.side_effect = FileNotFoundError()
        
        result = gpu_detector.detect()
        self.assertIsNone(result)

if __name__ == '__main__':
    unittest.main()
