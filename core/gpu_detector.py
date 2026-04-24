import json
import logging
import subprocess
from typing import Any

logger = logging.getLogger(__name__)

def detect() -> dict[str, Any] | None:
    """
    Detect GPU and return specs.
    
    Returns:
        {
            'gpu_name': str,           # e.g., "RTX 4090"
            'gpu_brand': str,          # "nvidia" or "amd"
            'gpu_vram_total_mb': int,
            'gpu_vram_free_mb': int,
        }
        OR None if no GPU detected
    """
    # Try Nvidia
    try:
        result = subprocess.run(
            ['nvidia-smi', '--query-gpu=name,memory.total,memory.free', '--format=csv,noheader,nounits'],
            capture_output=True,
            text=True,
            timeout=5
        )
        if result.returncode == 0 and result.stdout.strip():
            lines = result.stdout.strip().split('\n')
            parts = [p.strip() for p in lines[0].split(',')]
            if len(parts) >= 3:
                return {
                    'gpu_name': parts[0],
                    'gpu_brand': 'nvidia',
                    'gpu_vram_total_mb': int(parts[1]),
                    'gpu_vram_free_mb': int(parts[2]),
                }
    except (subprocess.TimeoutExpired, FileNotFoundError, ValueError) as e:
        logger.debug("Nvidia GPU detection failed: %s", e)

    # Try AMD
    try:
        result = subprocess.run(
            ['rocm-smi', '--showproductname', '--showmeminfo', 'vram', '--json'],
            capture_output=True,
            text=True,
            timeout=5
        )
        if result.returncode == 0 and result.stdout.strip():
            try:
                data = json.loads(result.stdout)
                for key, val in data.items():
                    if key.startswith('card'):
                        gpu_name = val.get('Card series', val.get('Card Series', 'AMD GPU'))
                        vram_total = int(val.get('VRAM Total Memory (B)', 0)) // (1024 * 1024)
                        vram_used = int(val.get('VRAM Total Used Memory (B)', 0)) // (1024 * 1024)
                        return {
                            'gpu_name': gpu_name,
                            'gpu_brand': 'amd',
                            'gpu_vram_total_mb': vram_total,
                            'gpu_vram_free_mb': max(0, vram_total - vram_used),
                        }
            except json.JSONDecodeError as e:
                logger.debug("AMD JSON parsing failed: %s", e)
                # Fallback text parsing
                gpu_name = "AMD GPU"
                vram_total = 0
                vram_used = 0
                for line in result.stdout.split('\n'):
                    if 'Card series:' in line or 'Card Series:' in line:
                        gpu_name = line.split(':', 1)[1].strip()
                    elif 'VRAM Total Memory (B):' in line:
                        vram_total = int(line.split(':', 1)[1].strip()) // (1024 * 1024)
                    elif 'VRAM Total Used Memory (B):' in line:
                        vram_used = int(line.split(':', 1)[1].strip()) // (1024 * 1024)
                if vram_total > 0:
                    return {
                        'gpu_name': gpu_name,
                        'gpu_brand': 'amd',
                        'gpu_vram_total_mb': vram_total,
                        'gpu_vram_free_mb': max(0, vram_total - vram_used),
                    }
    except (subprocess.TimeoutExpired, FileNotFoundError, ValueError) as e:
        logger.debug("AMD GPU detection failed: %s", e)

    return None
