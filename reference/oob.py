"""Out-of-Band (OOB) callback detection — async port of the Hypervisor
OOBManager (Interactsh protocol).

Generates unique DNS-payload domains; any DNS/HTTP/SMTP interaction with such
a domain proves blind injection (SSRF, blind XSS, RCE, XXE). Sessions are
end-to-end encrypted: the Interactsh server only ever sees ciphertext that
this client decrypts locally with its own RSA key.

Differences from the Hypervisor original:
  * fully async (``httpx``) — safe inside the MCP event loop
  * ``cryptography`` instead of ``pycryptodome`` (one fewer dependency)
  * per-session payload history survives polls (dedup by interaction id)
"""

from __future__ import annotations

import base64
import json
import re
import uuid
from typing import Any

import httpx
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes


class OOBSession:
    """One encrypted Interactsh session."""

    def __init__(self, server_domain: str, poll_url: str = "") -> None:
        self.server = server_domain
        self.poll_url = poll_url
        self._key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        pub_pem = self._key.public_key().public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo,
        )
        self.pub_key_b64 = base64.b64encode(pub_pem).decode()
        self.secret = str(uuid.uuid4())
        self.correlation_id = str(uuid.uuid4()).replace("-", "")[:20]
        self.nonce = str(uuid.uuid4()).replace("-", "")[:13]
        self.base_domain = f"{self.correlation_id}{self.nonce}.{self.server}"
        self.registered = False
        self.history: list[dict[str, Any]] = []
        self._client = httpx.AsyncClient(verify=False, timeout=15)

    # ------------------------------------------------------------------ session

    async def register(self) -> None:
        if self.registered:
            return
        try:
            resp = await self._client.post(
                f"https://{self.server}/register",
                json={
                    "public-key": self.pub_key_b64,
                    "secret-key": self.secret,
                    "correlation-id": self.correlation_id,
                },
                headers={"Content-Type": "application/json"},
            )
            if resp.status_code == 200:
                self.registered = True
        except httpx.HTTPError as exc:
            raise RuntimeError(f"OOB registration failed: {exc}") from exc

    def generate_payload(self, tag: str) -> str:
        """Return a payload domain like ``<tag>.<session>.<oob-server>``."""
        clean = re.sub(r"[^a-zA-Z0-9]", "", (tag or "").lower())[:20]
        if not clean:
            clean = "payload"
        return f"{clean}.{self.base_domain}"

    # ------------------------------------------------------------------ polling

    async def poll(self) -> list[dict[str, Any]]:
        """Fetch + decrypt new interactions (deduped against history)."""
        if not self.registered:
            return []
        url = (
            self.poll_url
            if self.poll_url
            else f"https://{self.server}/poll?id={self.correlation_id}&secret={self.secret}"
        )
        try:
            resp = await self._client.get(url)
            if resp.status_code != 200:
                return []
            data = resp.json().get("data", [])
        except (httpx.HTTPError, ValueError):
            return []

        new_interactions: list[dict[str, Any]] = []
        seen_ids = {h.get("unique-id") for h in self.history}
        for item in data:
            try:
                interaction = self._decrypt_interaction(item)
            except Exception:
                continue
            uid = interaction.get("unique-id")
            if uid and uid not in seen_ids:
                seen_ids.add(uid)
                self.history.append(interaction)
                new_interactions.append(interaction)
        return new_interactions

    def _decrypt_interaction(self, item: dict[str, Any]) -> dict[str, Any]:
        aes_key = self._key.decrypt(
            base64.b64decode(item["aes_key"]),
            padding.OAEP(
                mgf=padding.MGF1(algorithm=hashes.SHA1()),
                algorithm=hashes.SHA1(),
                label=None,
            ),
        )
        enc = base64.b64decode(item["data"])
        iv, ciphertext = enc[:16], enc[16:]
        decryptor = Cipher(algorithms.AES(aes_key), modes.CFB(iv)).decryptor()
        plaintext = decryptor.update(ciphertext) + decryptor.finalize()
        return json.loads(plaintext.decode("utf-8"))

    # ------------------------------------------------------------------ teardown

    async def close(self) -> None:
        try:
            if self.registered:
                await self._client.post(
                    f"https://{self.server}/deregister",
                    json={
                        "correlation-id": self.correlation_id,
                        "secret-key": self.secret,
                    },
                )
        except httpx.HTTPError:
            pass
        await self._client.aclose()

    # ------------------------------------------------------------------ report

    @staticmethod
    def format_interactions(interactions: list[dict[str, Any]]) -> str:
        if not interactions:
            return "No new OOB interactions detected yet."
        report = "🚨 NEW OUT-OF-BAND (OOB) CALLBACKS DETECTED 🚨\n"
        for i in interactions:
            proto = i.get("protocol", "UNKNOWN").upper()
            full_id = i.get("full-id", "")
            tag = full_id.split(".")[0] if "." in full_id else "unknown"
            remote = i.get("remote-address", "")
            raw = i.get("raw-request", "") or i.get("raw-respone", "")
            report += (
                f"\n--- [{proto}] Hit on tag: '{tag}' from IP: {remote} ---\n"
                f"{str(raw)[:500]}\n"
            )
        return report


class OOBManager:
    """Manages the active OOB session for the runtime (lazily created)."""

    def __init__(self, server_domain: str, poll_url: str = "") -> None:
        self.server_domain = server_domain
        self.poll_url = poll_url
        self.session: OOBSession | None = None

    async def get_session(self) -> OOBSession:
        if self.session is None:
            self.session = OOBSession(self.server_domain, self.poll_url)
            await self.session.register()
        return self.session

    async def reset(self) -> OOBSession:
        if self.session is not None:
            await self.session.close()
        self.session = None
        return await self.get_session()

    async def close(self) -> None:
        if self.session is not None:
            await self.session.close()
            self.session = None
