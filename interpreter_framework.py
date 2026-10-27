"""Framework adapter: one request/response turn, typed output, local validation."""
import asyncio
import json
import os
import time
from pydantic_ai import Agent, NativeOutput, PromptedOutput, capture_run_messages
from pydantic_ai.messages import ModelRequest, ModelResponse, SystemPromptPart, UserPromptPart, TextPart
from pydantic_ai.usage import UsageLimits
from action_model import Action
from config import Settings
from errors import ModelError
from interpreter_http import build_messages, no_duplicate_keys
from provider import FRAMEWORK_VERSION, open_model
from world import validate_action


def framework_messages(messages):
    """Preserve the same public context and four completed turns as HTTP."""
    result = []
    for message in messages:
        role, content = message["role"], message["content"]
        if role == "assistant":
            result.append(ModelResponse(parts=[TextPart(content)]))
        else:
            part = SystemPromptPart(content) if role == "system" else UserPromptPart(content)
            result.append(ModelRequest(parts=[part]))
    return result


async def run_typed(model, messages, schema, *, temperature=0.2, timeout=60, mode="json"):
    """Step 3: run one typed framework turn, then validate against schema.

    Use the imports above and the supplied framework_messages helper.
    Return (validated_action_dict, framework_result). Do not add repair retries.
    The surrounding adapter handles provider configuration and measurements.
    """
    raise NotImplementedError("Step 3: implement run_typed in interpreter_framework.py")


async def interpret_async(text, observation, schema, history, *, prompt="revised",
                          model=None, base_url=None, api_key=None, temperature=0.2, timeout=60.0):
    started = time.perf_counter()
    metrics = {"backend": "framework", "framework_version": FRAMEWORK_VERSION,
               "model": model or os.getenv("LLM_MODEL", "llama-3.3-70b-versatile"),
               "temperature": temperature, "attempts": 0, "elapsed_ms": 0,
               "raw_content": None, "first_response_contract_valid": None}
    try:
        settings = Settings.load(model=model, base_url=base_url, api_key=api_key,
                                 temperature=temperature, timeout=timeout)
        mode = os.getenv("LLM_RESPONSE_MODE", "json").lower()
        if mode not in {"plain", "json", "schema"}:
            raise ValueError("LLM_RESPONSE_MODE must be plain, json or schema.")
        messages = build_messages(text, observation, schema, history, prompt)
        async with open_model(settings, metrics, response_mode=mode) as llm:
            action, result = await run_typed(llm, messages, schema, temperature=temperature,
                                            timeout=timeout, mode=mode)
        # Retain the previous strict JSON contract, including duplicate-key checks.
        raw = metrics["raw_content"]
        if not isinstance(raw, str):
            raise ValueError("Expected a JSON text response.")
        checked = validate_action(json.loads(raw, object_pairs_hook=no_duplicate_keys), schema)
        if checked != action:
            raise ValueError("Typed output differs from the original JSON action.")
        metrics.update(first_response_contract_valid=True, request_count=result.usage.requests,
                       action=action)
    except NotImplementedError:
        raise
    except Exception as error:
        metrics["first_response_contract_valid"] = (False if metrics["raw_content"] is not None else None)
        metrics["elapsed_ms"] = round((time.perf_counter() - started) * 1000)
        if isinstance(error, ValueError) and metrics["attempts"] == 0:
            message = str(error)
        else:
            status = getattr(error, "status_code", None)
            message = f"Framework call failed ({type(error).__name__}" + (f", HTTP {status}" if status else "") + "). Check provider support, output and settings."
        raise ModelError(message, metrics) from error
    metrics["elapsed_ms"] = round((time.perf_counter() - started) * 1000)
    return action, metrics


def interpret_request(*args, **kwargs):
    return asyncio.run(interpret_async(*args, **kwargs))
