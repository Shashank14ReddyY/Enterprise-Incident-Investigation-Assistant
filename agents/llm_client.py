"""
llm_client.py
Single Anthropic API wrapper used by every agent.
Phase 3: now wraps every call with retry, timeout, and structured logging.
"""

from __future__ import annotations
import os
import logging
from typing import Optional

import anthropic
from dotenv import load_dotenv

from reliability.retry_handler import with_retry
from reliability.timeout_handler import run_with_timeout
from reliability.structured_logger import StructuredLogger

load_dotenv()
logger = logging.getLogger(__name__)
_slog = StructuredLogger("LLM Client")

MODEL = "claude-sonnet-4-6"
MAX_TOKENS = 2048
LLM_TIMEOUT_SECONDS = 90   # hard wall-clock limit per API call

_client: Optional[anthropic.Anthropic] = None


def _get_client() -> anthropic.Anthropic:
    global _client
    if _client is None:
        api_key = os.getenv("ANTHROPIC_API_KEY")
        if not api_key:
            raise ValueError("ANTHROPIC_API_KEY not set. Add it to your .env file.")
        _client = anthropic.Anthropic(api_key=api_key)
    return _client


def _raw_ask(system_prompt: str, user_prompt: str, max_tokens: int, model: str) -> str:
    """Bare API call — no retry or timeout here (applied by ask())."""
    client = _get_client()
    response = client.messages.create(
        model=model,
        max_tokens=max_tokens,
        system=system_prompt,
        messages=[{"role": "user", "content": user_prompt}],
    )
    return response.content[0].text


@with_retry(max_attempts=3, wait_min=2, wait_max=30)
def ask(
    system_prompt: str,
    user_prompt: str,
    max_tokens: int = MAX_TOKENS,
    model: str = MODEL,
) -> str:
    """
    Send a single system+user turn to Claude and return the text response.
    Automatically retried on transient failures (rate limits, network errors).
    Hard timeout of LLM_TIMEOUT_SECONDS enforced per attempt.

    Args:
        system_prompt:  Role/persona and task instructions for this agent.
        user_prompt:    The actual content/data for this turn.
        max_tokens:     Upper bound on response length.
        model:          Claude model string.

    Returns:
        The assistant's text reply as a plain string.
    """
    prompt_chars = len(system_prompt) + len(user_prompt)
    _slog.llm_call(model, prompt_chars)
    logger.debug("LLM call | model=%s | %d chars", model, prompt_chars)

    text = run_with_timeout(
        _raw_ask,
        system_prompt,
        user_prompt,
        max_tokens,
        model,
        timeout=LLM_TIMEOUT_SECONDS,
    )

    logger.debug("LLM response | %d chars", len(text))
    return text
