from __future__ import annotations

import json
import os
import time

from leadpilot.application.ai_foundation import (
    AIAuthenticationError,
    AIConfigurationError,
    AIProviderConfiguration,
    AIProviderName,
    AIProviderUnavailableError,
    AITimeoutError,
    ProviderGenerationResult,
    StructuredGenerationRequest,
)


class GeminiAIProvider:
    """Lazy Gemini adapter; provider SDK objects never cross this boundary."""

    name = AIProviderName.GEMINI

    def generate_structured(
        self, request: StructuredGenerationRequest, config: AIProviderConfiguration
    ) -> ProviderGenerationResult:
        reference = config.credentials_reference or "GEMINI_API_KEY"
        api_key = os.getenv(reference, "").strip()
        if not api_key:
            raise AIConfigurationError(
                f"Gemini credential environment variable {reference} is not configured."
            )
        started = time.monotonic()
        try:
            from google import genai

            client = genai.Client(api_key=api_key)
            response = client.models.generate_content(
                model=request.model_name or config.model_name,
                contents=request.user_prompt,
                config={
                    "system_instruction": request.system_prompt,
                    "temperature": float(request.temperature or config.temperature),
                    "max_output_tokens": request.max_output_tokens
                    or config.max_output_tokens,
                    "response_mime_type": "application/json",
                    "response_json_schema": request.response_schema,
                },
            )
            usage = getattr(response, "usage_metadata", None)
            return ProviderGenerationResult(
                raw_output=response.text or json.dumps({}),
                input_tokens=getattr(usage, "prompt_token_count", None),
                output_tokens=getattr(usage, "candidates_token_count", None),
                total_tokens=getattr(usage, "total_token_count", None),
                finish_reason=str(getattr(response, "finish_reason", "")) or None,
                provider_request_id=getattr(response, "response_id", None),
                duration_ms=int((time.monotonic() - started) * 1000),
            )
        except TimeoutError as exc:
            raise AITimeoutError("Gemini request timed out.") from exc
        except AIConfigurationError:
            raise
        except Exception as exc:
            message = type(exc).__name__.lower()
            if "auth" in message or "permission" in message:
                raise AIAuthenticationError("Gemini authentication failed.") from exc
            raise AIProviderUnavailableError(
                "Gemini generation is temporarily unavailable."
            ) from exc
