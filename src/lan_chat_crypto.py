# -*- coding: utf-8 -*-
"""Server-managed chat encryption for the zero-configuration LAN build.

The encryption key is normally supplied by a durable database-backed provider.
A local key file is kept only as a compatibility mirror/fallback so upgrading
from older LAN releases does not make previously readable messages unavailable.
"""
from __future__ import annotations

import hashlib
import json
import os
import tempfile
import threading
from typing import Any, Callable, Optional

from cryptography.fernet import Fernet, InvalidToken


_KEY_FILENAME = "server_chat_fernet.key"
_KEY_LOCK = threading.RLock()


class ServerChatCrypto:
    marker = "taskhub-server-chat-v1"

    def __init__(self, base_dir: str, key_provider: Optional[Callable[[], bytes]] = None):
        data_dir = os.path.join(base_dir, "taskhub_data")
        os.makedirs(data_dir, exist_ok=True)
        self.key_path = os.path.join(data_dir, _KEY_FILENAME)
        self._key_provider = key_provider
        self._key = self._load_key()
        self._fernet = Fernet(self._key)

    @staticmethod
    def validate_key(key: bytes) -> bytes:
        key = bytes(key or b"").strip()
        Fernet(key)
        return key

    def read_file_key(self) -> Optional[bytes]:
        try:
            with open(self.key_path, "rb") as handle:
                return self.validate_key(handle.read())
        except FileNotFoundError:
            return None

    def mirror_key_file(self, key: bytes) -> None:
        """Atomically mirror the authoritative key beside the executable."""
        key = self.validate_key(key)
        directory = os.path.dirname(self.key_path)
        os.makedirs(directory, exist_ok=True)
        current = self.read_file_key()
        if current == key:
            return
        fd, temp_path = tempfile.mkstemp(prefix="chat-key-", dir=directory)
        try:
            with os.fdopen(fd, "wb") as handle:
                handle.write(key)
                handle.flush()
                os.fsync(handle.fileno())
            try:
                os.chmod(temp_path, 0o600)
            except OSError:
                pass
            os.replace(temp_path, self.key_path)
        finally:
            try:
                if os.path.exists(temp_path):
                    os.remove(temp_path)
            except OSError:
                pass

    def _load_key(self) -> bytes:
        with _KEY_LOCK:
            if self._key_provider is not None:
                key = self.validate_key(self._key_provider())
                # Best-effort compatibility backup. The database remains the
                # source of truth if writing beside the executable is blocked.
                try:
                    self.mirror_key_file(key)
                except OSError:
                    pass
                return key

            key = self.read_file_key()
            if key is None:
                key = Fernet.generate_key()
                self.mirror_key_file(key)
            return key

    @property
    def fingerprint(self) -> str:
        return hashlib.sha256(self._key).hexdigest()[:16]

    def encrypt_json(self, value: Any) -> str:
        raw = json.dumps(value, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        return self._fernet.encrypt(raw).decode("ascii")

    def decrypt_json(self, token: str) -> Any:
        try:
            raw = self._fernet.decrypt(str(token or "").encode("ascii"))
            return json.loads(raw.decode("utf-8"))
        except (InvalidToken, UnicodeError, ValueError, TypeError) as exc:
            raise ValueError("Server-encrypted chat payload is invalid") from exc

    def encrypt_bytes(self, raw: bytes) -> bytes:
        return self._fernet.encrypt(raw)

    def decrypt_bytes(self, token: bytes) -> bytes:
        try:
            return self._fernet.decrypt(token)
        except InvalidToken as exc:
            raise ValueError("Server-encrypted chat file is invalid") from exc
