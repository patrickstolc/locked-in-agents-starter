"""Shared error type for an LLM request or unusable model response."""


class ModelError(RuntimeError):
    """Store the failure measurements so evaluation can count failed requests."""

    def __init__(self, message, metrics=None):
        super().__init__(message)
        self.metrics = {} if metrics is None else dict(metrics)
