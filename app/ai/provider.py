"""Provider abstraction and safe provider implementations for Stage 6."""
from __future__ import annotations

import json
import re
from abc import ABC, abstractmethod
from typing import Any

import httpx

from app.ai.context import OptimizationContext
from app.ai.schemas import (
    EvidenceItem,
    RecommendationDecision,
    RecommendationDraft,
    RecommendationRisk,
)


class LLMProviderError(RuntimeError):
    """Raised when the configured provider cannot produce a valid response."""


class LLMProvider(ABC):
    """Application-level interface for exactly one enabled runtime provider."""

    provider_name: str

    @abstractmethod
    def analyze_optimization(self, context: OptimizationContext) -> RecommendationDraft:
        """Return a structured recommendation from bounded context."""


class FakeLLMProvider(LLMProvider):
    """Offline provider used by tests and local UI development."""

    provider_name = "fake"

    def analyze_optimization(self, context: OptimizationContext) -> RecommendationDraft:
        candidate = context.candidate.get("decision")
        resource = context.resource
        alternative = context.savings.get("recommended_alternative") or {}
        target_type = alternative.get("target_type")

        if candidate != "candidate":
            return RecommendationDraft(
                decision=(
                    RecommendationDecision.needs_more_data
                    if candidate == "needs_more_data"
                    else RecommendationDecision.reject
                ),
                current_configuration={"instance_type": resource["instance_type"]},
                recommended_configuration={},
                reasoning=[context.candidate.get("reason", "Candidate check did not pass.")],
                evidence=[EvidenceItem(source="candidate_engine", statement="Deterministic candidate gate did not pass.")],
                concerns=["AI analysis cannot override the deterministic candidate gate."],
                required_validation=[],
                risk=RecommendationRisk.medium,
                confidence=0.99,
            )

        recommended = {"instance_type": target_type} if target_type else {}
        concerns = [] if target_type else ["No supported downsizing alternative is available."]
        return RecommendationDraft(
            decision=RecommendationDecision.recommend if target_type else RecommendationDecision.needs_more_data,
            current_configuration={"instance_type": resource["instance_type"]},
            recommended_configuration=recommended,
            reasoning=[
                "The deterministic candidate engine found sustained low utilization.",
                "The proposed target comes from the deterministic pricing catalog.",
            ],
            evidence=[
                EvidenceItem(source="candidate_engine", statement=context.candidate["reason"]),
                EvidenceItem(source="cloudwatch", statement="Metric summaries were supplied by the backend."),
            ],
            concerns=concerns,
            required_validation=["Validate memory and application performance before changing capacity."],
            risk=RecommendationRisk.medium,
            confidence=0.75,
        )


class OpenAICompatibleProvider(LLMProvider):
    """Minimal JSON provider adapter for an OpenAI-compatible endpoint.

    Only instantiate this adapter when one real provider is explicitly configured.
    The adapter never grants the provider AWS or shell access.
    """

    provider_name = "openai-compatible"

    def __init__(self, base_url: str, api_key: str, model: str, timeout: float = 30.0) -> None:
        if not base_url or not api_key or not model:
            raise ValueError("base_url, api_key, and model are required for a real LLM provider")
        self._url = base_url.rstrip("/") + "/chat/completions"
        self._headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
        self._model = model
        self._timeout = timeout

    def analyze_optimization(self, context: OptimizationContext) -> RecommendationDraft:
        payload = {
            "model": self._model,
            "temperature": 0,
            "response_format": {"type": "json_object"},
            "messages": [
                {
                    "role": "system",
                    "content": (
                        "Return only JSON matching the RecommendationDraft schema. "
                        "Never invent evidence, credentials, actions, or metrics."
                    ),
                },
                {"role": "user", "content": json.dumps(context.model_dump(mode="json"))},
            ],
        }
        try:
            response = httpx.post(self._url, headers=self._headers, json=payload, timeout=self._timeout)
            response.raise_for_status()
            body: dict[str, Any] = response.json()
            content = body["choices"][0]["message"]["content"]
            return RecommendationDraft.model_validate(json.loads(_extract_json(content)))
        except httpx.HTTPStatusError as exc:
            detail = "provider returned an HTTP error"
            try:
                error_body = exc.response.json()
                if isinstance(error_body, dict):
                    provider_error = error_body.get("error", {})
                    if isinstance(provider_error, dict):
                        detail = provider_error.get("message", detail)
                    elif isinstance(provider_error, str):
                        detail = provider_error
                elif isinstance(error_body, list) and error_body:
                    first_error = error_body[0]
                    if isinstance(first_error, dict):
                        provider_error = first_error.get("error", first_error)
                        if isinstance(provider_error, dict):
                            detail = provider_error.get("message", detail)
            except (ValueError, TypeError):
                pass
            raise LLMProviderError(
                f"LLM provider returned HTTP {exc.response.status_code}: {detail}"
            ) from exc
        except (httpx.HTTPError, KeyError, IndexError, TypeError, ValueError, json.JSONDecodeError) as exc:
            raise LLMProviderError("LLM provider response was unavailable or invalid") from exc


def _extract_json(content: str) -> str:
    """Accept strict JSON plus the common fenced-JSON model response."""
    cleaned = content.strip()
    fenced = re.fullmatch(r"```(?:json)?\s*(.*?)\s*```", cleaned, flags=re.DOTALL | re.IGNORECASE)
    if fenced:
        return fenced.group(1).strip()
    return cleaned

