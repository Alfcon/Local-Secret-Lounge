# GPU Hardware Advisor Widget Design
**Date:** 2026-04-24  
**Feature:** Intelligent generation setting recommendations based on detected GPU and active model

---

## Overview

Add a **Hardware Advisor Widget** to the Default Generation Settings section that:
1. Detects the user's GPU (Nvidia or AMD) and CPU/RAM specs
2. Queries the currently active model (with fallbacks to last used model)
3. Calculates and displays recommended values for Context Size, CPU Threads, and Max Tokens
4. Provides an interactive card showing hardware specs, model info, and recommendations

The widget runs hardware detection in a background thread to avoid blocking the UI, and gracefully degrades when GPU or model information is unavailable.

---

## Architecture

### Component Breakdown

#### 1. GPU Detector (`core/gpu_detector.py`) — NEW MODULE

**Responsibility:** Detect installed GPUs and return their specifications.

**Interface:**
```python
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
```

**Implementation:**
- Try Nvidia detection first via `nvidia-smi --query-gpu=name,memory.total,memory.free --format=csv,noheader,nounits`
  - Parse CSV output (name, total MB, free MB)
  - Set `gpu_brand = "nvidia"`
- If Nvidia fails, try AMD detection via `rocm-smi --json`
  - Parse JSON to extract GPU name, total VRAM, used VRAM
  - Set `gpu_brand = "amd"`
  - Fallback: if JSON parsing fails, try `rocm-smi` text output
- If both fail, return `None`
- All subprocess calls have 5-second timeout

**Error Handling:**
- Catch `subprocess.TimeoutExpired` → log and return `None`
- Catch `json.JSONDecodeError` (AMD) → fall back to text parsing
- Catch `FileNotFoundError` (command not found) → try next detector
- Never raise; always fail gracefully

---

#### 2. GPU Recommender (`core/gpu_recommender.py`) — NEW MODULE

**Responsibility:** Calculate recommended generation settings based on hardware + model specs.

**Interface:**
```python
def recommend(
    gpu_vram_mb: int | None,
    model_params_billions: float,
    model_quantization: str,
    cpu_cores: int,
    ram_gb: float,
) -> dict[str, int]:
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
```

**Recommendation Formulas:**

1. **Estimate model memory footprint** (based on quantization):
   ```
   - Q4_K_M (4-bit): ~0.5 GB per billion params
   - Q5_K_M (5-bit): ~0.65 GB per billion params
   - Q8_0 (8-bit): ~1.0 GB per billion params
   - FP16: ~2.0 GB per billion params
   
   model_mem_mb = estimate_model_memory(model_params, quantization)
   ```

2. **Context Size recommendation:**
   ```
   if gpu_vram_mb is not None:
       available_vram_mb = gpu_vram_mb - model_mem_mb
       context_size = min(
           16384,  # reasonable max
           max(256, int((available_vram_mb / 8) * 128))  # rough scaling
       )
   else:
       context_size = 4096  # safe default for CPU-only
   ```

3. **Threads recommendation:**
   ```
   threads = min(cpu_cores, 16)  # cap at 16, most models plateau
   threads = max(1, threads)
   ```

4. **Max Tokens recommendation:**
   ```
   if gpu_vram_mb is not None:
       available_vram_mb = gpu_vram_mb - model_mem_mb
       max_tokens = min(
           2048,  # reasonable max
           max(32, int(available_vram_mb / 2))
       )
   else:
       max_tokens = 384  # default for CPU-only
   ```

5. **Warnings:**
   - If `available_vram_mb < 500`: Add "⚠️ GPU VRAM is very low, generation may be slow"
   - If `cpu_cores < 4`: Add "⚠️ CPU cores are low, consider increasing threads carefully"
   - If `ram_gb < 8`: Add "⚠️ System RAM is limited, monitor memory usage"

**Error Handling:**
- Invalid quantization string → default to Q4_K_M assumptions
- Negative available VRAM → return conservative defaults (context=256, tokens=32)
- Missing GPU → use CPU-only defaults
- Never raise exceptions; always return safe values

---

#### 3. HardwareAdvisorWidget (`ui/widgets/hardware_advisor_widget.py`) — NEW/REFACTORED

**Responsibility:** Display hardware specs, model info, and recommendations in the UI.

Refactored from old `SystemInfoWidget` (which was removed). Now standalone, not tied to model selection.

**Features:**
- Background detection thread (non-blocking UI)
- Displays:
  - GPU section: Brand, name, VRAM (total / free)
  - CPU/RAM section: Core count, total RAM
  - Model section: Model name, parameter count, quantization
  - Recommendations section: Suggested values with color-coded confidence
  - Warnings section: If any recommendations flagged

- Interactive elements:
  - "Refresh Hardware" button to manually re-detect
  - "Apply Recommendations" button to populate settings with suggested values
  - Collapsible sections for compact display

- Auto-refresh triggers:
  - On widget creation
  - When ModelManager emits "default_model_changed" signal (if available)

**Data Flow:**
1. Widget init spawns background thread
2. `_DetectWorker` runs `gpu_detector.detect()` and queries ModelManager
3. On completion, emits signal with detected data
4. Widget receives signal, calls `gpu_recommender.recommend()`, renders results

---

### Data Flow Diagram

```
SettingsPage loads
  ↓
Creates HardwareAdvisorWidget(model_manager)
  ├─ [Background Thread] _DetectWorker starts
  │  ├─ gpu_detector.detect() → GPU specs
  │  ├─ model_manager.get_active_model() → Model specs (or None)
  │  ├─ psutil for CPU/RAM → Hardware specs
  │  └─ Emit detection_finished signal
  ├─ Widget shows "Detecting…" placeholder
  │
  └─ On detection_finished signal:
     ├─ gpu_recommender.recommend(all_specs) → Recommendations
     └─ Widget renders:
        ├─ GPU: "RTX 4090 | 24GB VRAM | Nvidia"
        ├─ CPU: "12 cores | 32GB RAM"
        ├─ Model: "Mistral-7B-Q4_K_M"
        ├─ Recommendations: Context=8192, Threads=12, Tokens=512
        └─ Warnings: (if any)

User can:
  - Click "Apply Recommendations" → Populate settings fields
  - Click "Refresh Hardware" → Re-detect
  - Manually edit settings below widget
```

---

## Integration Into Settings Page

**Location:** `ui/windows/settings_page.py`

**Changes:**
1. Remove the old `SystemInfoWidget` import and references (already done in previous cleanup)
2. Add new import: `from ui.widgets.hardware_advisor_widget import HardwareAdvisorWidget`
3. In `_build_ui()`, after the "Local LLM Server" section, add:
   ```python
   # ── Hardware Advisor ──────────────────────────────────────────
   advisor_widget = HardwareAdvisorWidget(model_manager=self.model_manager)
   layout.addWidget(advisor_widget)
   
   # ── Generation Defaults ──────────────────────────────────────
   gen_section = CollapsibleSection("Default Generation Settings")
   # ... existing code ...
   ```

4. Store reference if needed: `self.hardware_advisor = advisor_widget` (for testing/updates)

**Connection:** The widget is self-contained and doesn't require explicit updates from SettingsPage beyond initialization.

---

## Error Handling & Graceful Degradation

| Scenario | Behavior |
|----------|----------|
| No GPU detected | Show "GPU: Not detected", display CPU/RAM, use CPU-only defaults |
| ModelManager unavailable | Fall back to `settings_manager.get('last_model_id')` |
| Model info missing | Show "Model: Unknown", use generic 7B/Q4_K_M assumptions |
| GPU detection timeout | Show "GPU: Detection timed out", proceed with other data |
| AMD rocm-smi fails | Try text output, or return None |
| Subprocess errors | Log debug message, continue with other detectors |
| Invalid model quantization | Assume Q4_K_M for memory estimates |
| Negative available VRAM | Return conservative minimums (context=256, tokens=32) |

All failures are non-blocking; the widget always displays something useful.

---

## Testing Strategy

### Unit Tests: `tests/test_gpu_detector.py`
- Mock `subprocess.run()` for nvidia-smi and rocm-smi
- Test successful Nvidia detection and parsing
- Test successful AMD detection and JSON parsing
- Test fallback from Nvidia to AMD
- Test timeout handling (subprocess.TimeoutExpired)
- Test malformed output handling
- Test missing command handling (FileNotFoundError)

### Unit Tests: `tests/test_gpu_recommender.py`
- Test recommendation formulas with various GPU/model combinations
- Test with no GPU (CPU-only defaults)
- Test edge cases:
  - Very low VRAM (< 500 MB available)
  - Very low CPU cores (1-2 cores)
  - Missing model info (use defaults)
  - Invalid quantization string
- Verify recommendations stay within bounds
- Verify warnings are generated appropriately

### Integration Tests: `tests/test_hardware_advisor_widget.py`
- Widget initialization without crashing
- Background detection completes and renders
- Mock ModelManager and verify it's queried
- Verify "Apply Recommendations" button populates parent settings fields
- Verify "Refresh Hardware" button re-triggers detection
- Test widget behavior when ModelManager is unavailable

### Manual Testing
- Run on system with Nvidia GPU → verify detection and recommendations
- Run on system with AMD GPU (if available) → verify detection
- Run on system with no GPU → verify fallback behavior
- Verify recommendations change when active model changes
- Verify UI remains responsive during detection

---

## Dependencies

**New external dependencies:** None
- `rocm-smi` command (AMD GPU detection) assumed available on AMD systems; gracefully fails if not
- `nvidia-smi` (Nvidia detection) already assumed available, reuses existing pattern
- `psutil` already in project

**Internal dependencies:**
- `ModelManager` (passed in by SettingsPage)
- `SettingsManager` (for fallback `last_model_id`)
- `gpu_detector.py` (new)
- `gpu_recommender.py` (new)

---

## Future Extensions

- Store recommendation history (which GPU/model combos recommended what settings)
- Fine-tune recommendation formulas based on real-world performance data
- Support multi-GPU systems (detect all, use fastest)
- Add user-defined recommendation profiles ("performance" vs. "balanced" vs. "conservative")
- Integrate with chat engine to monitor actual performance vs. recommendations

---

## Success Criteria

✅ GPU detection works for both Nvidia and AMD  
✅ Recommendations display above "Context Size" setting  
✅ Widget shows hardware specs, model info, warnings  
✅ UI remains responsive (background thread)  
✅ Graceful fallbacks when GPU/model data is missing  
✅ "Apply Recommendations" button populates settings  
✅ Unit tests pass with >90% code coverage  
✅ No UI blocking or crashes on any system configuration
