"""Read Chrome's debugging port while another call is stuck on it.

The DevTools session the scraper drives is busy inside the page load, and it is
already dead by the time a ProtocolError surfaces. This talks to the debugging
port directly, so the last title and screenshot are still available.
"""

from __future__ import annotations

import base64
import json
import os
import socket
import struct
import urllib.request


def debug_port(command: list[str]) -> int | None:
    for arg in command:
        if arg.startswith("--remote-debugging-port="):
            try:
                return int(arg.split("=", 1)[1])
            except ValueError:
                return None
    return None


def page_target(listing: list) -> dict | None:
    pages = [item for item in listing if isinstance(item, dict) and item.get("type") == "page"]
    for item in pages:
        url = str(item.get("url") or "")
        if url.startswith("http://") or url.startswith("https://"):
            return item
    return pages[-1] if pages else None


def chrome_pages(port: int, timeout: float = 2.0) -> list:
    with urllib.request.urlopen(f"http://127.0.0.1:{port}/json/list", timeout=timeout) as response:
        body = json.loads(response.read(1_000_000) or b"[]")
    return body if isinstance(body, list) else []


def _recv_exact(sock: socket.socket, size: int) -> bytes:
    chunks = []
    while size > 0:
        chunk = sock.recv(size)
        if not chunk:
            raise ConnectionError("closed")
        chunks.append(chunk)
        size -= len(chunk)
    return b"".join(chunks)


def _ws_open(host: str, port: int, path: str) -> socket.socket:
    sock = socket.create_connection((host, port), timeout=3)
    key = base64.b64encode(os.urandom(16)).decode()
    sock.sendall(
        f"GET {path} HTTP/1.1\r\nHost: {host}:{port}\r\nUpgrade: websocket\r\n"
        f"Connection: Upgrade\r\nSec-WebSocket-Key: {key}\r\nSec-WebSocket-Version: 13\r\n\r\n".encode()
    )
    head = b""
    while b"\r\n\r\n" not in head:
        head += _recv_exact(sock, 1)
    if b" 101 " not in head.split(b"\r\n", 1)[0]:
        sock.close()
        raise ConnectionError("upgrade failed")
    return sock


def _ws_send(sock: socket.socket, text: str) -> None:
    payload = text.encode()
    mask = os.urandom(4)
    header = bytearray([0x81])
    length = len(payload)
    if length < 126:
        header.append(0x80 | length)
    elif length < 65536:
        header.append(0x80 | 126)
        header += struct.pack("!H", length)
    else:
        header.append(0x80 | 127)
        header += struct.pack("!Q", length)
    header += mask
    masked = bytes(byte ^ mask[index % 4] for index, byte in enumerate(payload))
    sock.sendall(bytes(header) + masked)


def _ws_recv(sock: socket.socket) -> str:
    parts = []
    while True:
        first, second = _recv_exact(sock, 2)
        opcode = first & 0x0F
        masked = second & 0x80
        length = second & 0x7F
        if length == 126:
            length = struct.unpack("!H", _recv_exact(sock, 2))[0]
        elif length == 127:
            length = struct.unpack("!Q", _recv_exact(sock, 8))[0]
        mask = _recv_exact(sock, 4) if masked else b""
        payload = _recv_exact(sock, length)
        if mask:
            payload = bytes(byte ^ mask[index % 4] for index, byte in enumerate(payload))
        if opcode == 0x8:
            raise ConnectionError("closed")
        if opcode == 0x1:
            parts.append(payload)
        if first & 0x80:
            return b"".join(parts).decode("utf-8", "replace")


def capture_screenshot(websocket_url: str) -> bytes:
    parsed = urllib.request.urlparse(websocket_url)
    sock = _ws_open(parsed.hostname or "127.0.0.1", parsed.port or 80, parsed.path or "/")
    try:
        _ws_send(sock, json.dumps({"id": 1, "method": "Page.captureScreenshot", "params": {"format": "png"}}))
        while True:
            message = json.loads(_ws_recv(sock) or "{}")
            if message.get("id") == 1:
                return base64.b64decode(str((message.get("result") or {}).get("data") or ""))
    finally:
        sock.close()
