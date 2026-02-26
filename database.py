from __future__ import annotations

import logging
import struct
from dataclasses import dataclass


LOGGER = logging.getLogger(__name__)

DB_PATH = "weather_bot.db"


@dataclass(slots=True)
class EncryptedFloat:
    ciphertext: bytes
    nonce: bytes


class AesGcmCoordinateCipher:
    """AES-GCM encryption for float coordinates."""

    def __init__(self, key: bytes):
        if len(key) != 32:
            raise ValueError("Cheia AES trebuie sa aiba exact 32 bytes.")

        try:
            from cryptography.hazmat.primitives.ciphers.aead import AESGCM
        except ModuleNotFoundError as exc:
            raise RuntimeError(
                "Lipseste dependinta 'cryptography'. Instaleaza: pip install cryptography"
            ) from exc

        self._aesgcm = AESGCM(key)

    def encrypt_float(self, value: float) -> EncryptedFloat:
        payload = struct.pack(">d", float(value))

        # 96-bit nonce required for AES-GCM best practices.
        import secrets

        nonce = secrets.token_bytes(12)
        ciphertext = self._aesgcm.encrypt(nonce, payload, None)
        return EncryptedFloat(ciphertext=ciphertext, nonce=nonce)

    def decrypt_float(self, encrypted: EncryptedFloat) -> float:
        payload = self._aesgcm.decrypt(encrypted.nonce, encrypted.ciphertext, None)
        return struct.unpack(">d", payload)[0]
