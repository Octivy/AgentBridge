from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import secrets
import threading
import time
import uuid
from dataclasses import dataclass
from typing import Any, Dict, Optional


CONTROL_ARGUMENT_KEYS = {
    "confirmed_by_local_user",
    "permission_request_id",
    "permission_token",
    "preview_hash",
    "task_id",
    "trace_id",
}


class PermissionTicketError(ValueError):
    """Raised when a write authorization ticket is missing, invalid, or stale."""


@dataclass(frozen=True)
class PermissionGrant:
    permission_request_id: str
    permission_token: str
    preview_hash: str
    expires_at: int


class PermissionTicketService:
    """Issues short-lived, tamper-evident and one-time write capabilities."""

    def __init__(self, secret: Optional[str] = None, ttl_seconds: int = 600) -> None:
        configured_secret = secret if secret is not None else os.getenv("CADMCP_PERMISSION_SECRET", "")
        self._secret = configured_secret.encode("utf-8") if configured_secret else secrets.token_bytes(32)
        self._ttl_seconds = max(30, int(ttl_seconds))
        self._consumed_nonces: Dict[str, int] = {}
        self._lock = threading.Lock()

    @staticmethod
    def preview_hash(tool_name: str, arguments: Dict[str, Any]) -> str:
        canonical = {
            "tool_name": str(tool_name or "").strip().lower(),
            "arguments": _business_arguments(arguments),
        }
        encoded = json.dumps(canonical, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)
        return hashlib.sha256(encoded.encode("utf-8")).hexdigest()

    def issue(self, tool_name: str, arguments: Dict[str, Any], now: Optional[int] = None) -> PermissionGrant:
        issued_at = int(time.time() if now is None else now)
        request_id = "perm_" + uuid.uuid4().hex
        nonce = uuid.uuid4().hex
        preview_hash = self.preview_hash(tool_name, arguments)
        payload = {
            "v": 1,
            "permission_request_id": request_id,
            "tool_name": str(tool_name or "").strip().lower(),
            "preview_hash": preview_hash,
            "iat": issued_at,
            "exp": issued_at + self._ttl_seconds,
            "nonce": nonce,
        }
        encoded_payload = _base64url_encode(
            json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
        )
        signature = _base64url_encode(hmac.new(self._secret, encoded_payload.encode("ascii"), hashlib.sha256).digest())
        return PermissionGrant(
            permission_request_id=request_id,
            permission_token=encoded_payload + "." + signature,
            preview_hash=preview_hash,
            expires_at=payload["exp"],
        )

    def consume(
        self,
        tool_name: str,
        arguments: Dict[str, Any],
        permission_token: str,
        *,
        expected_preview_hash: str = "",
        now: Optional[int] = None,
    ) -> Dict[str, Any]:
        token = str(permission_token or "").strip()
        if not token or "." not in token:
            raise PermissionTicketError("A valid permission_token from the dry-run preview is required.")

        encoded_payload, supplied_signature = token.rsplit(".", 1)
        expected_signature = _base64url_encode(
            hmac.new(self._secret, encoded_payload.encode("ascii"), hashlib.sha256).digest()
        )
        if not hmac.compare_digest(supplied_signature, expected_signature):
            raise PermissionTicketError("The permission ticket signature is invalid.")

        try:
            payload = json.loads(_base64url_decode(encoded_payload).decode("utf-8"))
        except (ValueError, UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise PermissionTicketError("The permission ticket payload is invalid.") from exc

        current_time = int(time.time() if now is None else now)
        if int(payload.get("exp") or 0) < current_time:
            raise PermissionTicketError("The permission ticket has expired; generate a new preview.")

        normalized_tool = str(tool_name or "").strip().lower()
        if payload.get("tool_name") != normalized_tool:
            raise PermissionTicketError("The permission ticket was issued for a different tool.")

        actual_hash = self.preview_hash(tool_name, arguments)
        token_hash = str(payload.get("preview_hash") or "")
        if not token_hash or not hmac.compare_digest(token_hash, actual_hash):
            raise PermissionTicketError("Tool arguments changed after preview; generate a new preview.")
        if expected_preview_hash and not hmac.compare_digest(str(expected_preview_hash), actual_hash):
            raise PermissionTicketError("The supplied preview_hash does not match the approved preview.")

        nonce = str(payload.get("nonce") or "")
        if not nonce:
            raise PermissionTicketError("The permission ticket nonce is missing.")
        with self._lock:
            expired_nonces = [item for item, expires_at in self._consumed_nonces.items() if expires_at < current_time]
            for item in expired_nonces:
                self._consumed_nonces.pop(item, None)
            if nonce in self._consumed_nonces:
                raise PermissionTicketError("The permission ticket has already been used.")
            self._consumed_nonces[nonce] = int(payload.get("exp") or current_time)

        return payload


def _business_arguments(arguments: Dict[str, Any]) -> Dict[str, Any]:
    return {key: value for key, value in dict(arguments or {}).items() if key not in CONTROL_ARGUMENT_KEYS}


def _base64url_encode(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).decode("ascii").rstrip("=")


def _base64url_decode(value: str) -> bytes:
    return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))


permission_ticket_service = PermissionTicketService()


__all__ = [
    "CONTROL_ARGUMENT_KEYS",
    "PermissionGrant",
    "PermissionTicketError",
    "PermissionTicketService",
    "permission_ticket_service",
]
