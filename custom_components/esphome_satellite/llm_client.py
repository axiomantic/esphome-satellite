"""Async Client for OpenAI-Compatible Local LLM Gatekeeper."""
from __future__ import annotations

import logging
import socket
import time
from typing import Any
import aiohttp
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .const import (
    CHOICE_ADDRESSED,
    CHOICE_AMBIENT,
    make_llm_followup_prompt,
    make_llm_initial_prompt,
)
from .systemone_client import GatekeeperClientError

_LOGGER = logging.getLogger(__name__)


class GatekeeperLlmClientError(GatekeeperClientError):
    """Exception for LLM gatekeeper communication failures."""


class GatekeeperLlmClient:
    """Async client communicating with an OpenAI-compatible chat completion endpoint."""

    def __init__(
        self,
        hass: HomeAssistant,
        endpoint_url: str,
        auth_token: str | None = None,
        model: str = "",
        timeout_seconds: float = 2.5,
    ) -> None:
        self._hass = hass
        self._endpoint_url = self._normalize_endpoint(endpoint_url)
        self._auth_token = auth_token
        self._model = model.strip() if model else ""
        self._timeout_seconds = timeout_seconds
        self._timeout = aiohttp.ClientTimeout(total=timeout_seconds)

    @property
    def endpoint_url(self) -> str:
        """Normalized OpenAI chat completions endpoint URL."""
        return self._endpoint_url

    @property
    def token(self) -> str | None:
        """Bearer authentication token."""
        return self._auth_token

    @property
    def model(self) -> str:
        """Target model identifier."""
        return self._model

    @property
    def timeout(self) -> float:
        """Request timeout in seconds."""
        return self._timeout_seconds

    @staticmethod
    def _normalize_endpoint(url: str) -> str:
        """Ensure endpoint URL points to /chat/completions."""
        clean = url.rstrip("/")
        if clean.endswith("/chat/completions"):
            return clean
        if clean.endswith("/v1"):
            return f"{clean}/chat/completions"
        return f"{clean}/v1/chat/completions"

    async def classify_addressing(
        self,
        text: str,
        question_text: str = "",
        min_confidence: float = 0.60,
        criteria: dict[str, str] | None = None,
        target_wake_word: str | None = None,
        phonetic_variants: list[str] | None = None,
        is_followup: bool = False,
    ) -> tuple[str, float, float]:
        """Classify whether the utterance is addressed or ambient conversation.

        Returns:
            tuple[choice, confidence, rtt_ms]
            choice: 'addressed' | 'ambient'
        """
        stripped = text.strip()
        if not stripped:
            return (CHOICE_AMBIENT, 1.0, 0.0)

        target = target_wake_word or "assistant"
        variants = phonetic_variants or []

        if is_followup:
            prompt = make_llm_followup_prompt(target)
        else:
            prompt = make_llm_initial_prompt(target, variants)

        payload: dict[str, Any] = {
            "messages": [
                {"role": "system", "content": prompt},
                {"role": "user", "content": f'Transcript: "{stripped}"'},
            ],
            "temperature": 0.0,
            "max_tokens": 2,
        }
        if self._model:
            payload["model"] = self._model

        headers = {"Content-Type": "application/json"}
        if self._auth_token:
            headers["Authorization"] = f"Bearer {self._auth_token}"

        session = async_get_clientsession(self._hass, family=socket.AF_INET)
        start_time = time.perf_counter()

        try:
            async with session.post(
                self._endpoint_url,
                json=payload,
                headers=headers,
                timeout=self._timeout,
            ) as response:
                rtt_ms = (time.perf_counter() - start_time) * 1000.0

                if response.status != 200:
                    body = await response.text()
                    _LOGGER.warning(
                        "LLM Gatekeeper returned HTTP %d in %.1fms: %s",
                        response.status,
                        rtt_ms,
                        body,
                    )
                    raise GatekeeperLlmClientError(f"HTTP {response.status}: {body}")

                data = await response.json()
                choices = data.get("choices")
                if not choices or not isinstance(choices, list):
                    _LOGGER.warning("Malformed LLM response: missing choices: %s", data)
                    return (CHOICE_ADDRESSED, 0.50, rtt_ms)

                message = choices[0].get("message", {})
                content = message.get("content", "").strip()

                is_yes = content.upper().startswith("YES")
                choice = CHOICE_ADDRESSED if is_yes else CHOICE_AMBIENT
                conf = 1.0 if is_yes else 0.0
                return (choice, conf, rtt_ms)

        except (aiohttp.ClientError, TimeoutError) as err:
            rtt_ms = (time.perf_counter() - start_time) * 1000.0
            _LOGGER.warning("LLM Gatekeeper communication error in %.1fms: %s", rtt_ms, err)
            raise GatekeeperLlmClientError(str(err)) from err
