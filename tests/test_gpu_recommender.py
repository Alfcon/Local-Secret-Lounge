import unittest
from core import gpu_recommender

class TestGPURecommender(unittest.TestCase):

    def test_estimate_model_memory(self):
        # Test default
        self.assertEqual(gpu_recommender.estimate_model_memory(7.0, "unknown"), 7.0 * 0.5 * 1024)
        
        # Test various quantizations
        self.assertEqual(gpu_recommender.estimate_model_memory(8.0, "Q4_K_M"), 8.0 * 0.5 * 1024)
        self.assertEqual(gpu_recommender.estimate_model_memory(13.0, "Q5_K_M"), 13.0 * 0.65 * 1024)
        self.assertEqual(gpu_recommender.estimate_model_memory(7.0, "Q8_0"), 7.0 * 1.0 * 1024)
        self.assertEqual(gpu_recommender.estimate_model_memory(70.0, "FP16"), 70.0 * 2.0 * 1024)

    def test_recommend_with_gpu(self):
        # 24GB VRAM, 7B Q4 model, 16 cores, 32GB RAM
        result = gpu_recommender.recommend(
            gpu_vram_mb=24576,
            model_params_billions=7.0,
            model_quantization="Q4_K_M",
            cpu_cores=16,
            ram_gb=32.0
        )
        
        self.assertEqual(result['context_size'], 16384) # Should hit max context
        self.assertEqual(result['threads'], 16) # Should hit max threads (or 16)
        self.assertEqual(result['max_tokens'], 2048) # Should hit max tokens
        self.assertEqual(len(result['warnings']), 0)

    def test_recommend_low_vram(self):
        # 4GB VRAM, 7B Q4 model (~3.5GB), 4 cores, 16GB RAM
        # Available VRAM = 4096 - 3584 = 512 MB
        result = gpu_recommender.recommend(
            gpu_vram_mb=4096,
            model_params_billions=7.0,
            model_quantization="Q4_K_M",
            cpu_cores=4,
            ram_gb=16.0
        )
        
        self.assertLess(result['context_size'], 16384)
        self.assertLess(result['max_tokens'], 2048)
        self.assertEqual(result['threads'], 4)
        self.assertEqual(len(result['warnings']), 0) # exactly 512 MB available

    def test_recommend_very_low_vram(self):
        # 4GB VRAM, 7.5B Q5 model (~5GB), 4 cores, 8GB RAM
        # Negative available VRAM
        result = gpu_recommender.recommend(
            gpu_vram_mb=4096,
            model_params_billions=7.5,
            model_quantization="Q5_K_M",
            cpu_cores=4,
            ram_gb=8.0
        )
        
        self.assertEqual(result['context_size'], 256)
        self.assertEqual(result['max_tokens'], 32)
        self.assertTrue(any("Model memory exceeds available VRAM" in w for w in result['warnings']))

    def test_recommend_no_gpu(self):
        result = gpu_recommender.recommend(
            gpu_vram_mb=None,
            model_params_billions=7.0,
            model_quantization="Q4_K_M",
            cpu_cores=8,
            ram_gb=16.0
        )
        
        self.assertEqual(result['context_size'], 4096)
        self.assertEqual(result['max_tokens'], 384)
        self.assertEqual(result['threads'], 8)

    def test_recommend_low_cpu_and_ram(self):
        result = gpu_recommender.recommend(
            gpu_vram_mb=8192,
            model_params_billions=7.0,
            model_quantization="Q4_K_M",
            cpu_cores=2,
            ram_gb=4.0
        )
        
        self.assertEqual(result['threads'], 2)
        self.assertTrue(any("CPU cores are low" in w for w in result['warnings']))
        self.assertTrue(any("System RAM is limited" in w for w in result['warnings']))

if __name__ == '__main__':
    unittest.main()
