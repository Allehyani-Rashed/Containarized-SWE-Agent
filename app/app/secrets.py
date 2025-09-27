from __future__ import annotations

import base64
import logging
import os
from typing import Optional

from cryptography.fernet import Fernet, InvalidToken

logger = logging.getLogger(__name__)

_DEFAULT_KEY_MATERIAL = b"codex-local-fernet-secret-key-32"
DEFAULT_SECRET_KEY = base64.urlsafe_b64encode(_DEFAULT_KEY_MATERIAL)
SECRET_ENV_VAR = "APP_SECRET_KEY"


class SecretError(RuntimeError):
    """Raised when encryption/decryption operations fail."""


def _normalize_key(raw_key: Optional[str]) -> bytes:
    if raw_key:
        candidate = raw_key.strip()
        try:
            # Fernet expects a urlsafe base64-encoded key; this validates the format.
            Fernet(candidate)
            return candidate.encode("utf-8")
        except (ValueError, TypeError):
            try:
                decoded = base64.urlsafe_b64decode(candidate)
            except Exception as exc:  # noqa: BLE001 - propagate validation failure
                raise SecretError(
                    "APP_SECRET_KEY must be a urlsafe base64 encoded 32 byte key",
                ) from exc
            if len(decoded) != 32:
                raise SecretError("APP_SECRET_KEY must decode to 32 bytes")
            return base64.urlsafe_b64encode(decoded)
    logger.warning("APP_SECRET_KEY not set; using built-in development key")
    return DEFAULT_SECRET_KEY


class SecretManager:
    def __init__(self) -> None:
        key = _normalize_key(os.getenv(SECRET_ENV_VAR))
        self._fernet = Fernet(key)

    def encrypt(self, plaintext: str) -> str:
        token = self._fernet.encrypt(plaintext.encode("utf-8"))
        return token.decode("utf-8")

    def decrypt(self, token: str) -> str:
        try:
            decrypted = self._fernet.decrypt(token.encode("utf-8"))
        except InvalidToken as exc:  # noqa: BLE001 - provide readable failure
            raise SecretError("Unable to decrypt stored secret") from exc
        return decrypted.decode("utf-8")


_SECRET_MANAGER: SecretManager | None = None


def get_secret_manager() -> SecretManager:
    global _SECRET_MANAGER
    if _SECRET_MANAGER is None:
        _SECRET_MANAGER = SecretManager()
    return _SECRET_MANAGER


def reset_secret_manager() -> None:
    global _SECRET_MANAGER
    _SECRET_MANAGER = None
