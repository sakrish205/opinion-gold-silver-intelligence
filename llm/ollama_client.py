"""
Ollama local LLM client.
Gracefully returns a fallback string if Ollama is not running.

LLM responsibilities:
  ✓ News interpretation, event extraction, sentiment/direction classification,
    qualitative impact, confidence explanation, summarization, conflict detection.

LLM must NOT:
  ✗ Determine authoritative prices
  ✗ Determine actual outcomes
  ✗ Determine +3/-6 scores
  ✗ Override numerical forecast results
"""
from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone

import requests

from config import DB_PATH
from llm.llm_registry import DEFAULT_MODEL_KEY, LLM_MODELS, get_model

OLLAMA_BASE = "http://localhost:11434"
_TIMEOUT = 30  # seconds

_OFFLINE_MSG = "[LLM offline — start Ollama and pull a model to enable summaries]"


def _active_model_key() -> str:
    """Read active model from settings table (falls back to default)."""
    try:
        with sqlite3.connect(DB_PATH) as conn:
            row = conn.execute(
                "SELECT value FROM _settings WHERE key='llm_model_key' LIMIT 1"
            ).fetchone()
            if row and row[0] in LLM_MODELS:
                return row[0]
    except Exception:
        pass
    return DEFAULT_MODEL_KEY


def is_online() -> bool:
    try:
        resp = requests.get(f"{OLLAMA_BASE}/api/tags", timeout=3)
        return resp.status_code == 200
    except Exception:
        return False


def generate(prompt: str, model_key: str | None = None, json_mode: bool = False) -> str:
    """
    Send a prompt to the local Ollama model.
    Returns the response string, or _OFFLINE_MSG if Ollama is not running.
    """
    key = model_key or _active_model_key()
    spec = get_model(key)
    ollama_name = spec.ollama_name if spec else key

    payload: dict = {"model": ollama_name, "prompt": prompt, "stream": False}
    if json_mode:
        payload["format"] = "json"

    try:
        resp = requests.post(
            f"{OLLAMA_BASE}/api/generate", json=payload, timeout=_TIMEOUT
        )
        resp.raise_for_status()
        return resp.json().get("response", "").strip()
    except requests.exceptions.ConnectionError:
        return _OFFLINE_MSG
    except Exception as exc:
        return f"[LLM error: {exc}]"


def analyse_news(headlines: list[str], model_key: str | None = None) -> dict:
    """
    Run LLM news analysis pipeline. Returns structured dict.
    The LLM determines qualitative direction/impact — NOT numerical scores.
    """
    if not headlines:
        return {}
    joined = "\n".join(f"- {h}" for h in headlines[:20])
    prompt = f"""You are a gold and silver market analyst. Analyse these headlines:

{joined}

Respond ONLY with valid JSON matching this schema:
{{
  "event": "one-line summary of the key event",
  "direction": "UP or DOWN or NEUTRAL or UNCLEAR",
  "impact": "HIGH or MEDIUM or LOW",
  "confidence": 0.0,
  "explanation": "brief explanation",
  "asset": "XAU or XAG or BOTH or OTHER",
  "source_reliability": "HIGH or MEDIUM or LOW or UNKNOWN"
}}

Rules:
- direction is qualitative only; do not determine prices or scores
- confidence is 0.0 to 1.0
- asset refers to which metal is primarily affected"""

    raw = generate(prompt, model_key=model_key, json_mode=True)
    if raw.startswith("[LLM"):
        return {"error": raw, "direction": None, "impact": None, "confidence": None}
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return {"error": f"Invalid JSON from LLM: {raw[:200]}", "direction": None}
