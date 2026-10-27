"""Provider lifetime and measurements; no remote telemetry is configured."""
from contextlib import asynccontextmanager
from importlib.metadata import version
import httpx2
from openai import AsyncOpenAI
from pydantic_ai.models.openai import OpenAIChatModel
from pydantic_ai.providers.openai import OpenAIProvider
from pydantic_ai.profiles.openai import OpenAIModelProfile

HTTP_CLIENT = httpx2.AsyncClient

FRAMEWORK_VERSION = version("pydantic-ai-slim")


@asynccontextmanager
async def open_model(settings, metrics, *, response_mode="json"):
    async def count_request(request):
        metrics["attempts"] += 1

    async def read_response(response):
        # Only successful model replies are captured, never headers or credentials.
        if response.status_code == 200:
            await response.aread()
            try:
                payload = response.json()
                choices = payload.get("choices", [])
                if choices:
                    metrics["raw_content"] = choices[0].get("message", {}).get("content")
            except (ValueError, TypeError, AttributeError):
                pass

    async with HTTP_CLIENT(timeout=settings.timeout,
            event_hooks={"request": [count_request], "response": [read_response]}) as http:
        async with AsyncOpenAI(api_key=settings.api_key, base_url=settings.base_url,
                               max_retries=1, timeout=settings.timeout, http_client=http) as client:
            profile = OpenAIModelProfile(supports_json_object_output=response_mode == "json",
                                         supports_json_schema_output=True,
                                         supports_tools=True)
            yield OpenAIChatModel(settings.model, provider=OpenAIProvider(openai_client=client),
                                  profile=profile)
