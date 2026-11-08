"""Read-only Maestri Wire client: pairing by code, pinned TLS, feed snapshots.

The device token lives in the OS keyring; the pairing metadata (host, port, server key hash, device id)
lives in ~/.neon-flow/wire.json. The only input ever sent to a terminal is what the operator types in
the terminal viewer (send_prompt).
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import http.client
import ipaddress
import json
from pathlib import Path
import re
import socket
import ssl
from urllib.parse import quote, urlsplit

from cryptography import x509
from cryptography.hazmat.primitives import serialization

CONFIG = Path.home() / ".neon-flow" / "wire.json"
SERVICE = "neon-flow Maestri Wire"
DEVICE = "Neon Flow"
MAX_RESPONSE = 8 * 1024 * 1024


def _host(value: str) -> tuple[str, int]:
    parsed = urlsplit(value if "://" in value else "https://" + value)
    host = parsed.hostname or ""
    if parsed.scheme != "https" or parsed.username or parsed.password or parsed.path not in ("", "/") or parsed.query or parsed.fragment:
        raise ValueError("Informe o endereço HTTPS do Maestri, sem caminho.")
    private_ip = False
    try:
        private_ip = ipaddress.ip_address(host).is_private
    except ValueError:
        pass
    if not (host == "localhost" or host.endswith((".local", ".ts.net")) or private_ip):
        raise ValueError("Endereço de host inválido: use localhost, .local, .ts.net ou IP privado.")
    return host, parsed.port or 7434


def _server_key_hash(sock: ssl.SSLSocket) -> str:
    cert = x509.load_der_x509_certificate(sock.getpeercert(binary_form=True))
    key = cert.public_key().public_bytes(serialization.Encoding.DER, serialization.PublicFormat.SubjectPublicKeyInfo)
    return base64.b64encode(hashlib.sha256(key).digest()).decode("ascii")


def _tls(host: str, port: int, pin: str) -> ssl.SSLSocket:
    raw = socket.create_connection((host, port), timeout=8)
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    context.minimum_version = ssl.TLSVersion.TLSv1_2
    context.check_hostname = False
    context.verify_mode = ssl.CERT_NONE   # trust comes from the pinned key below, not from a CA
    try:
        secure = context.wrap_socket(raw, server_hostname=host)
        if not hmac.compare_digest(_server_key_hash(secure), pin):
            raise ValueError("A chave de segurança do host não confere com o QR do Maestri.")
        secure.settimeout(20)
        return secure
    except Exception:
        raw.close()
        raise


def request(host: str, port: int, pin: str, method: str, path: str, body=None, token: str | None = None) -> dict:
    sock = _tls(host, port, pin)
    try:
        payload = b"" if body is None else json.dumps(body, ensure_ascii=False).encode("utf-8")
        headers = [f"{method} {path} HTTP/1.1", f"Host: {host}:{port}", "Connection: close", "Accept: application/json"]
        if body is not None:
            headers += ["Content-Type: application/json", f"Content-Length: {len(payload)}"]
        if token:
            headers.append(f"Authorization: Bearer {token}")
        sock.sendall(("\r\n".join(headers) + "\r\n\r\n").encode("ascii") + payload)
        response = http.client.HTTPResponse(sock)
        response.begin()
        data = response.read(MAX_RESPONSE + 1)
        if len(data) > MAX_RESPONSE:
            raise ValueError("Resposta do Maestri excede 8 MiB.")
        if not 200 <= response.status < 300:
            try:
                detail = json.loads(data).get("error", {}).get("message", "")
            except (ValueError, AttributeError):
                detail = ""
            if path == "/pair" and response.status == 401:
                detail = ("O Maestri recusou o código: gere outro em Settings → Wire → Pairing e mantenha a tela "
                          "aberta até concluir. O código expira em cinco minutos e só pode ser usado uma vez.")
            raise RuntimeError(detail or f"Maestri Wire respondeu HTTP {response.status}.")
        return json.loads(data) if data else {}
    finally:
        sock.close()


def _keyring():
    import keyring
    return keyring


def pair(host: str, server_key_hash: str, code: str) -> dict:
    """Pair this machine with Maestri Wire using the 6-digit code and the serverKeyHash from the QR."""
    host_name, port = _host(host)
    if not re.fullmatch(r"\d{6}", code) or len(base64.b64decode(server_key_hash, validate=True)) != 32:
        raise ValueError("Informe o código de seis dígitos e a chave serverKeyHash do QR.")
    info = request(host_name, port, server_key_hash, "GET", "/api/info")
    caps = info.get("capabilities", [])
    if info.get("protocolVersion") != 1 or "pairingCodes" not in caps or "feedSnapshots" not in caps:
        raise RuntimeError("O host não oferece pareamento Maestri Wire v1 por código.")
    paired = request(host_name, port, server_key_hash, "POST", "/pair", {"deviceName": DEVICE, "code": code})
    _keyring().set_password(SERVICE, paired["deviceId"], paired["token"])
    saved = {"host": host_name, "port": port, "serverKeyHash": server_key_hash, "deviceId": paired["deviceId"],
             "role": paired.get("role", "guest"), "name": info.get("name", host_name)}
    CONFIG.parent.mkdir(parents=True, exist_ok=True)
    CONFIG.write_text(json.dumps(saved, ensure_ascii=False), encoding="utf-8")
    return {"name": saved["name"], "role": saved["role"]}


def credentials() -> tuple[dict, str]:
    """Saved pairing and its token (from the system keyring). Never sent to the browser."""
    if not CONFIG.exists():
        raise RuntimeError("Pareie com o Maestri Wire primeiro: python -m neon_flow pair --help")
    saved = json.loads(CONFIG.read_text(encoding="utf-8"))
    token = _keyring().get_password(SERVICE, saved["deviceId"])
    if not token:
        raise RuntimeError("Token local não encontrado; pareie novamente.")
    return saved, token


def api(path: str) -> dict:
    saved, token = credentials()
    return request(saved["host"], saved["port"], saved["serverKeyHash"], "GET", path, token=token)


def send_prompt(terminal_id: str, text: str) -> dict:
    """Send the operator's text to one terminal, exactly as typed (Maestri requires the paired role to allow it)."""
    saved, token = credentials()
    return request(saved["host"], saved["port"], saved["serverKeyHash"], "POST",
                   f"/api/terminals/{quote(terminal_id, safe='')}/prompt", {"text": text}, token=token)


def feed() -> dict:
    """Snapshot of the active Maestri workspace (terminals, notes, canvas connections, floors)."""
    workspace = api("/api/info")["activeWorkspaceId"]
    snap = api(f"/api/workspaces/{quote(workspace, safe='')}/feed")
    # The feed mirrors the floor open in Maestri; the ground canvas holds the Orquestrador's links
    # and the cross-floor connectors, so use it whatever floor the operator is looking at.
    try:
        ground = api(f"/api/workspaces/{quote(workspace, safe='')}/feed?floor=ground").get("canvas")
    except Exception:
        ground = None
    return {**snap, "canvas": ground} if ground else snap
