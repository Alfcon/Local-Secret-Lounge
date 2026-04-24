def estimate_model_memory(model_params_billions: float, quantization: str) -> float:
    """Estimate model memory footprint in MB based on parameters and quantization."""
    quantization = quantization.upper()
    if "Q4" in quantization or "4-BIT" in quantization:
        multiplier = 0.5
    elif "Q5" in quantization or "5-BIT" in quantization:
        multiplier = 0.65
    elif "Q8" in quantization or "8-BIT" in quantization:
        multiplier = 1.0
    elif "FP16" in quantization or "16-BIT" in quantization:
        multiplier = 2.0
    else:
        # Default to Q4_K_M assumptions if unknown
        multiplier = 0.5
    
    return model_params_billions * multiplier * 1024

def recommend(
    gpu_vram_mb: int | None,
    model_params_billions: float,
    model_quantization: str,
    cpu_cores: int,
    ram_gb: float,
) -> dict[str, int | list[str]]:
    """
    Calculate recommended generation settings.
    
    Args:
        gpu_vram_mb: Total GPU VRAM in MB (or None if no GPU)
        model_params_billions: Model size (7.0 for 7B, etc.)
        model_quantization: Quantization type ("Q4_K_M", "FP16", etc.)
        cpu_cores: Physical CPU cores
        ram_gb: Total system RAM in GB
    
    Returns:
        {
            'context_size': int,       # recommended context window
            'threads': int,            # recommended CPU threads
            'max_tokens': int,         # recommended max generation
            'warnings': list[str],     # e.g., ["GPU VRAM is low"]
        }
    """
    warnings = []
    
    model_mem_mb = estimate_model_memory(model_params_billions, model_quantization)
    
    # Context Size & Max Tokens
    if gpu_vram_mb is not None:
        available_vram_mb = gpu_vram_mb - model_mem_mb
        
        if available_vram_mb <= 0:
            context_size = 256
            max_tokens = 32
            warnings.append("⚠️ Model memory exceeds available VRAM. Using minimum settings.")
        else:
            context_size = min(16384, max(256, int((available_vram_mb / 8) * 128)))
            max_tokens = min(2048, max(32, int(available_vram_mb / 2)))
            
        if available_vram_mb > 0 and available_vram_mb < 500:
            warnings.append("⚠️ GPU VRAM is very low, generation may be slow.")
    else:
        context_size = 4096
        max_tokens = 384
        
    # Threads
    threads = min(cpu_cores, 16)
    threads = max(1, threads)
    
    if cpu_cores < 4:
        warnings.append("⚠️ CPU cores are low, consider increasing threads carefully.")
        
    if ram_gb < 8.0:
        warnings.append("⚠️ System RAM is limited, monitor memory usage.")
        
    return {
        'context_size': int(context_size),
        'threads': int(threads),
        'max_tokens': int(max_tokens),
        'warnings': warnings,
    }
