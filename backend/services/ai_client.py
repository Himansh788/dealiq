"""
Groq AI Client
==============
Central Groq client used by all services.
Usage: from services.ai_client import AsyncAnthropicCompat as AsyncGroq
"""
import os
from groq import AsyncGroq as _AsyncGroq

MODEL_COMPLEX = "llama-3.3-70b-versatile"
MODEL_FAST = "llama-3.1-8b-instant"


class AsyncAnthropicCompat(_AsyncGroq):
    """Thin wrapper around AsyncGroq; kept for import compatibility across all services."""

    def __init__(self, api_key: str = None):
        super().__init__(
            api_key=api_key or os.getenv("GROQ_API_KEY"),
            timeout=60.0,
        )
