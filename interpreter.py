"""Stable game interface with selectable HTTP and framework backends."""
from errors import ModelError


def interpret_request(*args, backend="framework", **kwargs):
    if backend == "http":
        from interpreter_http import interpret_request as interpret
    elif backend == "framework":
        from interpreter_framework import interpret_request as interpret
    else:
        raise ValueError("Choose http or framework.")
    try:
        action, metrics = interpret(*args, **kwargs)
    except ModelError as error:
        error.metrics.setdefault("backend", backend)
        raise
    from provider import FRAMEWORK_VERSION
    return action, {**metrics, "backend": backend, "framework_version": FRAMEWORK_VERSION}
