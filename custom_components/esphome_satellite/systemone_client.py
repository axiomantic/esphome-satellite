"""Async Client for System 1 Decision Model Daemon."""
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
    CLASSIFICATION_CRITERIA,
)

_LOGGER = logging.getLogger(__name__)

class SystemOneClientError(Exception):
    """Base exception for System 1 client communication failures."""

class SystemOneClient:
    """Async client communicating with the System 1 inference endpoint."""

    def __init__(
        self,
        hass: HomeAssistant,
        endpoint_url: str,
        auth_token: str | None = None,
        timeout_seconds: float = 2.5,
    ) -> None:
        self._hass = hass
        self._endpoint_url = endpoint_url
        self._auth_token = auth_token
        self._timeout = aiohttp.ClientTimeout(total=timeout_seconds)

    async def classify_addressing(
        self,
        text: str,
        question_text: str,
        min_confidence: float = 0.60,
        criteria: dict[str, str] | None = None,
    ) -> tuple[str, float, float]:
        """Classify whether the utterance is addressed or ambient conversation.
        
        Returns:
            tuple[choice, confidence, rtt_ms]
            choice: 'addressed' | 'ambient'
        """
        # Empty or purely whitespace text is never addressed
        stripped = text.strip()
        if not stripped:
            return (CHOICE_AMBIENT, 1.0, 0.0)

        effective_criteria = criteria if criteria is not None else CLASSIFICATION_CRITERIA

        payload: dict[str, Any] = {
            "state": stripped,
            "questions": {
                "address_intent": {
                    "type": "choice",
                    "instructions": question_text,
                    "criteria": effective_criteria,
                }
            },
            "min_confidence": 0.0,
        }

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
                        "System 1 endpoint returned HTTP %d in %.1fms: %s",
                        response.status,
                        rtt_ms,
                        body,
                    )
                    raise SystemOneClientError(f"HTTP {response.status}: {body}")

                data = await response.json()
                
                # Parse answers format supporting dict or list
                answers = data.get("answers", {})
                result: dict[str, Any] = {}
                if isinstance(answers, dict) and "address_intent" in answers:
                    result = answers["address_intent"]
                elif isinstance(answers, list) and len(answers) > 0:
                    result = answers[0]

                if result:
                    choice = result.get("choice", CHOICE_ADDRESSED)
                    # Support Laya answer_confidence, standard confidence, or probability lookup
                    probs = result.get("probabilities", {})
                    choice_prob = probs.get(choice, 0.0) if isinstance(probs, dict) else 0.0
                    conf = float(result.get("answer_confidence", choice_prob if choice_prob > 0.0 else result.get("confidence", 0.0)))
                    abstention = result.get("abstention", "passed")
                    if abstention == "abstained":
                        _LOGGER.info(
                            "System 1 model abstained on utterance '%s' (rtt=%.1fms); treating as addressed",
                            stripped,
                            rtt_ms,
                        )
                        return (CHOICE_ADDRESSED, 0.0, rtt_ms)
                    return (choice, conf, rtt_ms)

                _LOGGER.warning("Malformed System 1 response schema: %s", data)
                return (CHOICE_ADDRESSED, 0.50, rtt_ms)

        except (aiohttp.ClientError, TimeoutError) as err:
            rtt_ms = (time.perf_counter() - start_time) * 1000.0
            _LOGGER.warning("System 1 communication error in %.1fms: %s", rtt_ms, err)
            raise SystemOneClientError(str(err)) from err
