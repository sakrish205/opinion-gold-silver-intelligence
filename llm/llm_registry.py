"""
Configurable local LLM model registry.
Active model is selected via Settings page — not hardcoded.

Each entry must declare: license, size_gb, min_ram_gb, finance_reasoning.
Add finance-specific models as evaluated (e.g. FinGPT, Finance-Llama variants).
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class LLMModelSpec:
    key: str
    ollama_name: str
    display_name: str
    size_gb: float
    min_ram_gb: float
    vram_gb: float
    quantization: str
    structured_output: bool
    finance_reasoning: str      # 'low' | 'medium' | 'high'
    cpu_capable: bool
    license: str
    notes: str = ""


LLM_MODELS: dict[str, LLMModelSpec] = {
    "phi3-mini": LLMModelSpec(
        key="phi3-mini",
        ollama_name="phi3:mini",
        display_name="Phi-3 Mini (Microsoft)",
        size_gb=2.3,
        min_ram_gb=4,
        vram_gb=0,
        quantization="Q4",
        structured_output=True,
        finance_reasoning="medium",
        cpu_capable=True,
        license="MIT",
        notes="Good general reasoning; structured JSON output reliable.",
    ),
    "llama3.2-1b": LLMModelSpec(
        key="llama3.2-1b",
        ollama_name="llama3.2:1b",
        display_name="Llama 3.2 1B (Meta)",
        size_gb=1.3,
        min_ram_gb=3,
        vram_gb=0,
        quantization="Q4",
        structured_output=True,
        finance_reasoning="low",
        cpu_capable=True,
        license="Llama 3.2 Community License",
        notes="Smallest model; fast on CPU; weaker finance reasoning.",
    ),
    "llama3.2-3b": LLMModelSpec(
        key="llama3.2-3b",
        ollama_name="llama3.2:3b",
        display_name="Llama 3.2 3B (Meta)",
        size_gb=2.0,
        min_ram_gb=6,
        vram_gb=0,
        quantization="Q4",
        structured_output=True,
        finance_reasoning="medium",
        cpu_capable=True,
        license="Llama 3.2 Community License",
        notes="Better than 1B; still CPU-capable on 6 GB RAM.",
    ),
    # Add finance-specific models below after evaluation:
    # "fingpt-...": LLMModelSpec(..., finance_reasoning="high", ...)
}

DEFAULT_MODEL_KEY = "phi3-mini"


def get_model(key: str) -> LLMModelSpec | None:
    return LLM_MODELS.get(key)


def list_models() -> list[LLMModelSpec]:
    return list(LLM_MODELS.values())
