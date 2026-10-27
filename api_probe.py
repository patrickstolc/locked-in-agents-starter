"""A working, one-call API example. Run this before changing interpreter.py.

Only an OpenAI-compatible Chat Completions endpoint is assumed. JSON mode,
validation, conversation memory and retries are NOT implemented here.
"""
import json
import os
import time
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import Request, urlopen

base_url = os.getenv("LLM_BASE_URL", "https://api.groq.com/openai/v1")
model = os.getenv("LLM_MODEL", "llama-3.3-70b-versatile")
api_key = os.getenv("LLM_API_KEY", "")


def main():
    if not api_key:
        raise SystemExit("Set LLM_API_KEY in your environment first.")
    if urlsplit(base_url).scheme != "https":
        raise SystemExit("Use an HTTPS endpoint for a hosted API.")
    body = {
        "model": model,
        "messages": [{"role": "user", "content": "Reply with just the word READY."}],
        "max_tokens": 30,
    }
    request = Request(
        base_url.rstrip("/") + "/chat/completions",
        data=json.dumps(body).encode("utf-8"),
        headers={"Authorization": "Bearer " + api_key,
                 "Content-Type": "application/json"},
        method="POST",
    )
    started = time.perf_counter()
    try:
        with urlopen(request, timeout=30) as response:
            result = json.load(response)
        print("Model:", model)
        print("Reply:", result["choices"][0]["message"]["content"])
        print("Time:", round((time.perf_counter() - started) * 1000), "ms")
    except HTTPError as error:
        raise SystemExit(f"Provider returned HTTP {error.code}. Check your key, model or quota.")
    except (URLError, TimeoutError):
        raise SystemExit("The API could not be reached. Check your connection and endpoint.")
    except (KeyError, IndexError, ValueError, TypeError):
        raise SystemExit("The endpoint did not return the expected Chat Completions format.")


if __name__ == "__main__":
    main()
