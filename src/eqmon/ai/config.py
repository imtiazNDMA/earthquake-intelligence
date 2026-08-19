"""Model roster and inference tunables.

Routing lives here as configuration rather than as constants scattered through
call sites, so swapping a model is a single edit. Every value is env-overridable
because the roster is machine-specific: it depends on what is loaded in LM
Studio and how much VRAM the box has.

Measured on the reference machine (RTX 6000 Ada, 48 GB) 2026-08-13 — see
ai_implementation.md section 2 for the full probe results.
"""
from __future__ import annotations

import os

AI_ROUTES_ENABLED = os.getenv("EQMON_AI_ENABLED", "false").lower() in {
    "1", "true", "yes", "on",
}

# LM Studio's OpenAI-compatible server. The API key is required by the protocol
# but ignored by LM Studio; it is not a secret and does not belong in .env.
LMSTUDIO_BASE_URL = os.getenv("LMSTUDIO_BASE_URL", "http://localhost:1234/v1").rstrip("/")
LMSTUDIO_API_KEY = "lm-studio"

# --- Model roster ----------------------------------------------------------
# Primary. Measured 2.7-3.3 s, exact tool-call arguments, correct abstention.
MODEL_PRIMARY = os.getenv("EQMON_AI_MODEL", "google/gemma-4-26b-a4b")

# Independent architecture for cross-checking high-stakes output. Measured
# 2.9-9.5 s and equally exact on tool calls, so a disagreement is informative
# rather than just noise. Local inference is free at the margin, which is what
# makes routine cross-checking affordable at all.
MODEL_CROSSCHECK = os.getenv("EQMON_AI_MODEL_CROSSCHECK", "qwen/qwen3.5-9b")

# Small/fast, for routing and classification. Unbenchmarked as of this writing;
# Phase 0 confirms it or drops it.
MODEL_ROUTER = os.getenv("EQMON_AI_MODEL_ROUTER", "nvidia/nemotron-3-nano")

# Batch only. Measured 12-97 s: fine unattended overnight, never interactive.
MODEL_BATCH = os.getenv("EQMON_AI_MODEL_BATCH", "deepseek/deepseek-v4-flash")

# Dormant experimental embedding model. Deterministic place resolution uses
# coordinates and orthographic matching; retain only for reproducible comparison.
MODEL_EMBED = os.getenv("EQMON_AI_MODEL_EMBED", "text-embedding-nomic-embed-text-v1.5")

# --- Timeouts --------------------------------------------------------------
# Generous relative to the measured 3 s primary latency: a cold model load in LM
# Studio costs tens of seconds, and timing out during one turns a slow first
# request into a hard failure.
CHAT_TIMEOUT_S = float(os.getenv("EQMON_AI_TIMEOUT_S", "120"))
EMBED_TIMEOUT_S = float(os.getenv("EQMON_AI_EMBED_TIMEOUT_S", "60"))
EXPOSURE_TOOL_TIMEOUT_S = float(os.getenv("EQMON_AI_EXPOSURE_TIMEOUT_S", "180"))

# --- Circuit breaker -------------------------------------------------------
# AI is additive, never load-bearing. When LM Studio is down the breaker fails
# AI routes fast and leaves the rest of the platform untouched.
BREAKER_THRESHOLD = int(os.getenv("EQMON_AI_BREAKER_THRESHOLD", "5"))
BREAKER_RESET_S = float(os.getenv("EQMON_AI_BREAKER_RESET_S", "30"))

# --- Sampling --------------------------------------------------------------
# Deterministic by default. Note this does NOT guarantee reproducibility: the
# primary model is a mixture-of-experts and its routing varies run to run.
# Measured — free-text generation repeated identically 3/3, grammar-constrained
# generation did not. Assert reproducibility in evals; never assume it.
DEFAULT_TEMPERATURE = 0.0
DEFAULT_MAX_TOKENS = 1024
