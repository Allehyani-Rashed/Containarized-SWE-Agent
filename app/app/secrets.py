from __future__ import annotations

from cryptography.fernet import Fernet, InvalidToken


class SecretError(RuntimeError):
    """Raised when encryption/decryption operations fail."""


# NOTE: Local-only personal builds rely on a shared static key so secrets
# remain decryptable across restarts without extra configuration.
# TODO(cloud-hardening): Replace this with an environment-sourced key before
# any shared or cloud deployment.
_STATIC_FERNET_KEY = "5uTQNPgdEuCG1Nhs3uFGPaROHyBcXPyF7K6dAz_IW00="


def _normalized_static_key() -> bytes:
    try:
        Fernet(_STATIC_FERNET_KEY)
    except (ValueError, TypeError) as exc:  # pragma: no cover - guarded constant
        raise SecretError("Configured static Fernet key is invalid") from exc
    return _STATIC_FERNET_KEY.encode("utf-8")


class SecretManager:
    def __init__(self) -> None:
        key = _normalized_static_key()
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
