"""Security utilities for secret masking and log redaction."""

import logging
from collections.abc import Mapping
from typing import Any


def mask_secret(value: str) -> str:
    """Mask a secret string to prevent accidental leakage in logs/UI.

    For strings with 8 or more characters, preserves first 2 and last 2 characters.
    For shorter or empty strings, masks completely.
    """
    if not value or len(value) < 8:
        return "******"
    return f"{value[:2]}********{value[-2:]}"


class RedactingFilter(logging.Filter):
    """Logging filter that scrubs known secrets and tokens from log records."""

    def __init__(self, secrets: list[str] | None = None) -> None:
        super().__init__()
        self.secrets: set[str] = {s.strip() for s in (secrets or []) if s and len(s.strip()) > 3}

    def add_secret(self, secret: str) -> None:
        """Add a secret string to the redaction set."""
        if secret and len(secret.strip()) > 3:
            self.secrets.add(secret.strip())

    def _redact_text(self, text: str) -> str:
        for secret in self.secrets:
            if secret in text:
                text = text.replace(secret, "[REDACTED]")
        return text

    def _redact_obj(self, obj: Any) -> Any:
        if isinstance(obj, str):
            return self._redact_text(obj)
        if isinstance(obj, Mapping):
            return {k: self._redact_obj(v) for k, v in obj.items()}
        if isinstance(obj, (list, tuple)):
            redacted = [self._redact_obj(item) for item in obj]
            return tuple(redacted) if isinstance(obj, tuple) else redacted
        return obj

    def filter(self, record: logging.LogRecord) -> bool:
        if isinstance(record.msg, str):
            record.msg = self._redact_text(record.msg)
        if record.args:
            if isinstance(record.args, tuple):
                record.args = tuple(self._redact_obj(a) for a in record.args)
            elif isinstance(record.args, dict):
                record.args = {k: self._redact_obj(v) for k, v in record.args.items()}
        return True
