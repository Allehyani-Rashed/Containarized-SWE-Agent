from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen

from sqlmodel import Session, select

from .models import AuditLog, IntegrationCredential, Project
from .schemas import GitLabPATStatus
from .secrets import SecretError, get_secret_manager

GITLAB_PAT_KIND = "gitlab_pat"
CHATGPT_SESSION_KIND = "chatgpt_session"
VERIFICATION_STATUS_VERIFIED = "verified"
VERIFICATION_STATUS_ERROR = "error"


class ChatGPTSessionError(RuntimeError):
    """Raised when a ChatGPT session bundle is invalid or expired."""


class GitLabPATVerificationError(RuntimeError):
    """Raised when PAT verification cannot proceed due to configuration issues."""


@dataclass
class ChatGPTSessionMaterial:
    raw: str
    expires_at: Optional[datetime]
    token_preview: Optional[str]


def _ensure_credential(session: Session) -> IntegrationCredential:
    credential = session.exec(
        select(IntegrationCredential).where(IntegrationCredential.kind == GITLAB_PAT_KIND)
    ).first()
    if credential is None:
        credential = IntegrationCredential(kind=GITLAB_PAT_KIND)
        session.add(credential)
        session.flush()
    return credential


def get_gitlab_pat_status(session: Session) -> GitLabPATStatus:
    pat_credential = _get_credential(session, GITLAB_PAT_KIND)
    session_credential = _get_credential(session, CHATGPT_SESSION_KIND)
    pat_configured = bool(pat_credential and pat_credential.token_encrypted)
    session_configured = bool(session_credential and session_credential.token_encrypted)

    active_credential = "none"
    if pat_configured:
        active_credential = "api_token"
    elif session_configured:
        active_credential = "session"

    return GitLabPATStatus(
        configured=pat_configured,
        updated_at=pat_credential.updated_at if pat_credential else None,
        updated_by=pat_credential.updated_by if pat_credential else None,
        session_configured=session_configured,
        session_updated_at=session_credential.updated_at if session_credential else None,
        session_updated_by=session_credential.updated_by if session_credential else None,
        active_credential=active_credential,
        verification_status=pat_credential.verification_status if pat_credential else None,
        verification_checked_at=pat_credential.verification_checked_at if pat_credential else None,
        verification_error=pat_credential.verification_error if pat_credential else None,
        verification_host=pat_credential.verification_host if pat_credential else None,
    )


def get_gitlab_pat_token(session: Session) -> Optional[str]:
    credential = _get_credential(session, GITLAB_PAT_KIND)
    if credential is None or not credential.token_encrypted:
        return None
    manager = get_secret_manager()
    return manager.decrypt(credential.token_encrypted)


def set_gitlab_pat_token(session: Session, token: str, updated_by: Optional[str]) -> IntegrationCredential:
    credential = _ensure_credential(session)
    manager = get_secret_manager()
    credential.token_encrypted = manager.encrypt(token)
    credential.updated_at = datetime.now(timezone.utc)
    credential.updated_by = _normalize_actor(updated_by)
    credential.verification_status = None
    credential.verification_checked_at = None
    credential.verification_error = None
    credential.verification_host = None
    session.add(credential)
    _record_audit(session, "gitlab_pat.stored", credential.updated_by, details=None)
    return credential


def clear_gitlab_pat_token(session: Session, updated_by: Optional[str]) -> IntegrationCredential:
    credential = _ensure_credential(session)
    credential.token_encrypted = None
    credential.updated_at = datetime.now(timezone.utc)
    credential.updated_by = _normalize_actor(updated_by)
    credential.verification_status = None
    credential.verification_checked_at = None
    credential.verification_error = None
    credential.verification_host = None
    session.add(credential)
    _record_audit(session, "gitlab_pat.cleared", credential.updated_by, details=None)
    return credential


def _get_credential(session: Session, kind: str) -> IntegrationCredential | None:
    return session.exec(select(IntegrationCredential).where(IntegrationCredential.kind == kind)).first()


def _ensure_session_credential(session: Session) -> IntegrationCredential:
    credential = _get_credential(session, CHATGPT_SESSION_KIND)
    if credential is None:
        credential = IntegrationCredential(kind=CHATGPT_SESSION_KIND)
        session.add(credential)
        session.flush()
    return credential


def _parse_session_bundle(raw_bundle: str) -> ChatGPTSessionMaterial:
    try:
        payload = json.loads(raw_bundle)
    except json.JSONDecodeError as exc:
        raise ChatGPTSessionError("Session bundle must be valid JSON") from exc

    if not isinstance(payload, dict):
        raise ChatGPTSessionError("Session bundle must decode to an object")

    candidate_dicts = []

    session_node = payload.get("session")
    if isinstance(session_node, dict):
        candidate_dicts.append(session_node)

    tokens_node = payload.get("tokens")
    if isinstance(tokens_node, dict):
        candidate_dicts.append(tokens_node)

    candidate_dicts.append(payload)

    token_value = None
    for candidate in candidate_dicts:
        for key in ("session_token", "sessionToken", "access_token", "accessToken"):
            value = candidate.get(key)
            if isinstance(value, str) and value.strip():
                token_value = value.strip()
                break
        if token_value:
            break

    if not token_value:
        raise ChatGPTSessionError(
            "Session bundle missing a session/access token; expected keys: session_token, sessionToken, access_token, or accessToken",
        )

    expires_at = None
    for candidate in candidate_dicts:
        for key in ("expires_at", "expiresAt", "expiry", "expires", "access_token_expires_at"):
            raw_expiry = candidate.get(key)
            if not raw_expiry:
                continue
            if isinstance(raw_expiry, (int, float)):
                expires_at = datetime.fromtimestamp(float(raw_expiry), tz=timezone.utc)
                break
            if isinstance(raw_expiry, str):
                normalized = raw_expiry.strip()
                if not normalized:
                    continue
                if normalized.endswith("Z"):
                    normalized = normalized[:-1] + "+00:00"
                try:
                    expires_at = datetime.fromisoformat(normalized)
                    if expires_at.tzinfo is None:
                        expires_at = expires_at.replace(tzinfo=timezone.utc)
                    break
                except ValueError:
                    continue
        if expires_at is not None:
            break

    token_preview = token_value[:6] + "…" if len(token_value) > 6 else token_value
    return ChatGPTSessionMaterial(raw=raw_bundle, expires_at=expires_at, token_preview=token_preview)


def set_chatgpt_session_bundle(session: Session, bundle: str, updated_by: Optional[str]) -> IntegrationCredential:
    material = _parse_session_bundle(bundle)
    if material.expires_at is not None and material.expires_at <= datetime.now(timezone.utc):
        expires_str = material.expires_at.isoformat()
        raise ChatGPTSessionError(f"Session bundle expired at {expires_str}; log in again and retry")

    credential = _ensure_session_credential(session)
    manager = get_secret_manager()
    credential.token_encrypted = manager.encrypt(material.raw)
    credential.updated_at = datetime.now(timezone.utc)
    credential.updated_by = _normalize_actor(updated_by)
    session.add(credential)
    _record_audit(session, "chatgpt_session.rotated", credential.updated_by, details=None)
    return credential


def clear_chatgpt_session_bundle(session: Session, updated_by: Optional[str]) -> IntegrationCredential:
    credential = _ensure_session_credential(session)
    credential.token_encrypted = None
    credential.updated_at = datetime.now(timezone.utc)
    credential.updated_by = _normalize_actor(updated_by)
    session.add(credential)
    _record_audit(session, "chatgpt_session.cleared", credential.updated_by, details=None)
    return credential


def get_chatgpt_session_bundle(session: Session) -> Optional[ChatGPTSessionMaterial]:
    credential = _get_credential(session, CHATGPT_SESSION_KIND)
    if credential is None or not credential.token_encrypted:
        return None
    manager = get_secret_manager()
    try:
        decrypted = manager.decrypt(credential.token_encrypted)
    except Exception as exc:  # noqa: BLE001 - normalize downstream failure
        raise ChatGPTSessionError("Unable to decrypt stored ChatGPT session bundle") from exc

    try:
        return _parse_session_bundle(decrypted)
    except ChatGPTSessionError as exc:
        raise ChatGPTSessionError(str(exc)) from exc


def verify_gitlab_pat(
    session: Session,
    actor: Optional[str],
    requested_host: Optional[str],
) -> GitLabPATStatus:
    normalized_actor = _normalize_actor(actor)
    try:
        token = get_gitlab_pat_token(session)
    except SecretError as exc:
        credential = _ensure_credential(session)
        # Stored ciphertext cannot be decrypted with the active key; clear and flag it.
        credential.token_encrypted = None
        credential.updated_at = datetime.now(timezone.utc)
        credential.updated_by = normalized_actor
        credential.verification_status = VERIFICATION_STATUS_ERROR
        credential.verification_checked_at = datetime.now(timezone.utc)
        credential.verification_error = "Stored GitLab PAT could not be decrypted; re-enter the token"
        credential.verification_host = None
        session.add(credential)
        details = json.dumps({"status": "decrypt_failed"})
        _record_audit(session, "gitlab_pat.decrypt_failed", normalized_actor, details)
        session.commit()
        raise GitLabPATVerificationError(
            "Stored GitLab PAT could not be decrypted. Clear the credential and add a new token.",
        ) from exc

    if not token:
        raise GitLabPATVerificationError("GitLab PAT is not configured")

    host = _resolve_gitlab_host(session, requested_host)
    success, error_message = _probe_gitlab_pat(host, token)

    credential = _ensure_credential(session)
    credential.verification_checked_at = datetime.now(timezone.utc)
    credential.verification_host = host
    if success:
        credential.verification_status = VERIFICATION_STATUS_VERIFIED
        credential.verification_error = None
        details = json.dumps({"host": host, "status": "verified"})
        _record_audit(session, "gitlab_pat.verified", normalized_actor, details)
    else:
        credential.verification_status = VERIFICATION_STATUS_ERROR
        credential.verification_error = error_message
        details = json.dumps({"host": host, "status": "error", "error": error_message})
        _record_audit(session, "gitlab_pat.verify_failed", normalized_actor, details)

    session.add(credential)
    session.commit()

    return get_gitlab_pat_status(session)


def _resolve_gitlab_host(session: Session, requested_host: Optional[str]) -> str:
    candidate = requested_host.strip() if requested_host else ""
    if candidate:
        return _normalize_gitlab_host(candidate)

    fallback = session.exec(select(Project.gitlab_host).where(Project.gitlab_host.is_not(None))).first()
    if fallback:
        try:
            return _normalize_gitlab_host(fallback)
        except GitLabPATVerificationError:
            # Ignore stored invalid values and continue to default host.
            pass
    return "https://gitlab.com"


def _normalize_gitlab_host(raw_host: str) -> str:
    value = raw_host.strip()
    if not value:
        raise GitLabPATVerificationError("GitLab host must not be empty")

    candidate = value if "://" in value else f"https://{value}"
    parsed = urlparse(candidate)
    if not parsed.scheme or not parsed.netloc:
        raise GitLabPATVerificationError("GitLab host must be a valid http(s) URL")
    if parsed.scheme not in {"http", "https"}:
        raise GitLabPATVerificationError("GitLab host must use http or https")

    path = parsed.path.rstrip("/") if parsed.path else ""
    normalized = f"{parsed.scheme}://{parsed.netloc}"
    if path:
        normalized = f"{normalized}{path}"
    return normalized.rstrip("/")


def _probe_gitlab_pat(host: str, token: str) -> tuple[bool, Optional[str]]:
    url = f"{host.rstrip('/')}/api/v4/user"
    request = Request(url, method="GET")
    request.add_header("PRIVATE-TOKEN", token)
    request.add_header("Accept", "application/json")
    request.add_header("User-Agent", "codex-local-agent/verification")

    try:
        with urlopen(request, timeout=5) as response:
            status_code = response.getcode()
            if 200 <= status_code < 300:
                return True, None
            return False, _safe_error_message(f"GitLab responded with status {status_code}")
    except HTTPError as exc:  # pragma: no cover - covered via URLError in tests
        reason = exc.reason or "HTTP error"
        return False, _safe_error_message(f"GitLab responded with status {exc.code}: {reason}")
    except URLError as exc:
        reason = getattr(exc, "reason", exc)
        return False, _safe_error_message(f"Network error: {reason}")
    except Exception as exc:  # noqa: BLE001 - surface unexpected runtime issues
        return False, _safe_error_message(f"Unexpected error: {exc}")


def _safe_error_message(message: str, max_length: int = 240) -> str:
    clean = " ".join(str(message).split())
    if len(clean) <= max_length:
        return clean
    return f"{clean[: max_length - 1]}…"


def _record_audit(session: Session, action: str, actor: Optional[str], details: Optional[str]) -> None:
    event = AuditLog(action=action, actor=actor, details=details)
    session.add(event)


def _normalize_actor(actor: Optional[str]) -> Optional[str]:
    if actor is None:
        return None
    actor = actor.strip()
    return actor or None
