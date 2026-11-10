"""
Connexion en temps reel a Home Assistant (API WebSocket), sans dependance externe.

Un petit client WebSocket (RFC 6455) sur socket + ssl, et un fil d'execution qui reste connecte a
Home Assistant, s'abonne aux changements d'etat et aux notifications, et se reconnecte tout seul.
Les messages sont envoyes a l'interface par une file (queue) :
  ("rt_status", (connecte, detail))
  ("rt_state", (entity_id, nouvel_etat ou None))
  ("rt_notify", (titre, message))
"""
import base64
import json
import os
import select
import socket
import ssl
import struct
import threading
import time
import urllib.parse

EVENT_NOTIFY = "ha_taskbar_notify"      # evenement HA -> notification Windows (automatisations)
PING_EVERY = 30                         # secondes
DEAD_AFTER = 75                         # plus rien recu depuis... -> connexion morte


class WSClosed(Exception):
    pass


class AuthFailed(Exception):
    pass


class WebSocket:
    """Client WebSocket minimal : messages texte, ping/pong, fragmentation. Un seul fil l'utilise."""

    def __init__(self, base_url, verify_ssl=True, timeout=10):
        u = urllib.parse.urlsplit(base_url)
        secure = u.scheme in ("https", "wss")
        host = u.hostname or ""
        port = u.port or (443 if secure else 80)
        path = (u.path or "").rstrip("/") + "/api/websocket"
        sock = socket.create_connection((host, port), timeout=timeout)
        try:
            if secure:
                ctx = ssl.create_default_context()
                if not verify_ssl:
                    ctx.check_hostname = False
                    ctx.verify_mode = ssl.CERT_NONE
                sock = ctx.wrap_socket(sock, server_hostname=host)
            hosthdr = "[%s]" % host if ":" in host else host
            if port not in (80, 443):
                hosthdr += ":%d" % port
            key = base64.b64encode(os.urandom(16)).decode()
            sock.sendall(("GET %s HTTP/1.1\r\nHost: %s\r\nUpgrade: websocket\r\nConnection: Upgrade\r\n"
                          "Sec-WebSocket-Key: %s\r\nSec-WebSocket-Version: 13\r\nUser-Agent: HATaskbar\r\n\r\n"
                          % (path, hosthdr, key)).encode())
            buf = b""
            while b"\r\n\r\n" not in buf:
                chunk = sock.recv(4096)
                if not chunk:
                    raise WSClosed("le serveur a fermé la connexion")
                buf += chunk
                if len(buf) > 65536:
                    raise WSClosed("réponse invalide")
            head, rest = buf.split(b"\r\n\r\n", 1)
            status = head.split(b"\r\n", 1)[0].decode("latin-1")
            if " 101" not in status:
                raise WSClosed("connexion refusée (%s)" % status.strip())
        except Exception:
            sock.close()
            raise
        sock.settimeout(30)
        self.sock = sock
        self._buf = bytearray(rest)
        self._frag = None

    # ---------------- envoi
    def _send(self, opcode, data):
        n = len(data)
        hdr = bytearray([0x80 | opcode])
        if n < 126:
            hdr.append(0x80 | n)
        elif n < 65536:
            hdr.append(0x80 | 126)
            hdr += struct.pack(">H", n)
        else:
            hdr.append(0x80 | 127)
            hdr += struct.pack(">Q", n)
        mask = os.urandom(4)
        hdr += mask
        if n:
            # masque XOR applique d'un coup sur un grand entier (rapide, sans boucle Python)
            m = (mask * (n // 4 + 1))[:n]
            data = (int.from_bytes(data, "big") ^ int.from_bytes(m, "big")).to_bytes(n, "big")
        self.sock.sendall(bytes(hdr) + data)

    def send_json(self, obj):
        self._send(0x1, json.dumps(obj).encode("utf-8"))

    # ---------------- reception
    def _frame(self):
        """Trame complete prise dans le tampon, ou None s'il n'y en a pas encore une entiere."""
        b = self._buf
        if len(b) < 2:
            return None
        n, i = b[1] & 0x7F, 2
        if n == 126:
            if len(b) < 4:
                return None
            n, i = struct.unpack(">H", bytes(b[2:4]))[0], 4
        elif n == 127:
            if len(b) < 10:
                return None
            n, i = struct.unpack(">Q", bytes(b[2:10]))[0], 10
        mask = None
        if b[1] & 0x80:
            if len(b) < i + 4:
                return None
            mask, i = bytes(b[i:i + 4]), i + 4
        if len(b) < i + n:
            return None
        fin, opcode = b[0] & 0x80, b[0] & 0x0F
        payload = bytes(b[i:i + n])
        del b[:i + n]
        if mask and n:
            m = (mask * (n // 4 + 1))[:n]
            payload = (int.from_bytes(payload, "big") ^ int.from_bytes(m, "big")).to_bytes(n, "big")
        return fin, opcode, payload

    def recv(self, timeout):
        """Message texte suivant, ou None si rien n'arrive pendant `timeout` secondes."""
        deadline = time.monotonic() + timeout
        while True:
            fr = self._frame()
            if fr is not None:
                fin, op, payload = fr
                if op == 0x8:
                    raise WSClosed("connexion fermée par Home Assistant")
                if op == 0x9:
                    self._send(0xA, payload)
                    continue
                if op == 0xA:
                    continue
                if op in (0x1, 0x2):
                    self._frag = bytearray(payload)
                elif op == 0x0 and self._frag is not None:
                    self._frag += payload
                else:
                    continue
                if fin:
                    data, self._frag = bytes(self._frag), None
                    return data.decode("utf-8", "replace")
                continue
            left = deadline - time.monotonic()
            if left <= 0:
                return None
            pending = self.sock.pending() if isinstance(self.sock, ssl.SSLSocket) else 0
            if not pending:
                r, _w, _x = select.select([self.sock], [], [], left)
                if not r:
                    return None
            chunk = self.sock.recv(65536)
            if not chunk:
                raise WSClosed("connexion perdue")
            self._buf += chunk

    def close(self):
        try:
            self._send(0x8, b"")
        except Exception:
            pass
        try:
            self.sock.close()
        except Exception:
            pass


class Realtime:
    """Fil d'execution : connexion permanente a Home Assistant, reconnexion automatique."""

    def __init__(self, url, token, verify_ssl, out, notifications=True):
        self.url, self.token, self.verify = (url or "").rstrip("/"), token or "", verify_ssl
        self.out = out
        self.notifications = notifications
        self.stop_ev = threading.Event()
        self.ws = None
        self.connected = False
        threading.Thread(target=self.run, daemon=True).start()

    def stop(self):
        self.stop_ev.set()
        ws = self.ws
        if ws is not None:
            try:
                ws.sock.close()
            except Exception:
                pass

    def _status(self, ok, detail=""):
        if ok != self.connected or not ok:
            self.connected = ok
            if not self.stop_ev.is_set():
                self.out.put(("rt_status", (ok, detail)))

    def run(self):
        delay = 2
        while not self.stop_ev.is_set():
            try:
                self.session()
                delay = 2
            except AuthFailed as e:
                self._status(False, str(e))
                delay = 300          # jeton refuse : inutile d'insister
            except Exception as e:
                self._status(False, str(e) or e.__class__.__name__)
            if self.stop_ev.wait(delay):
                break
            delay = min(60, delay * 2)

    def session(self):
        if not self.url or not self.token:
            raise AuthFailed("adresse ou jeton manquant")
        ws = self.ws = WebSocket(self.url, self.verify)
        try:
            msg = json.loads(ws.recv(15) or "null")
            if not msg or msg.get("type") != "auth_required":
                raise WSClosed("réponse inattendue de Home Assistant")
            ws.send_json({"type": "auth", "access_token": self.token})
            msg = json.loads(ws.recv(15) or "null")
            if not msg or msg.get("type") != "auth_ok":
                raise AuthFailed("jeton refusé")
            ws.send_json({"id": 1, "type": "subscribe_events", "event_type": "state_changed"})
            if self.notifications:
                ws.send_json({"id": 2, "type": "persistent_notification/subscribe"})
                ws.send_json({"id": 3, "type": "subscribe_events", "event_type": EVENT_NOTIFY})
            self._status(True)
            last_rx = next_ping = time.monotonic()
            next_ping += PING_EVERY
            nid = 10
            while not self.stop_ev.is_set():
                text = ws.recv(5)
                now = time.monotonic()
                if text is not None:
                    last_rx = now
                    try:
                        data = json.loads(text)
                    except ValueError:
                        data = None
                    for m in (data if isinstance(data, list) else [data]):
                        if isinstance(m, dict):
                            self.handle(m)
                if now >= next_ping:
                    nid += 1
                    ws.send_json({"id": nid, "type": "ping"})
                    next_ping = now + PING_EVERY
                if now - last_rx > DEAD_AFTER:
                    raise WSClosed("Home Assistant ne répond plus")
        finally:
            self.ws = None
            ws.close()

    def handle(self, m):
        if m.get("type") != "event":
            return
        ev = m.get("event") or {}
        mid = m.get("id")
        if mid == 1:
            d = ev.get("data") or {}
            if d.get("entity_id"):
                self.out.put(("rt_state", (d["entity_id"], d.get("new_state"))))
        elif mid == 2:
            if ev.get("type") == "added":         # "current" = deja presentes a la connexion
                for n in (ev.get("notifications") or {}).values():
                    self.out.put(("rt_notify", (n.get("title") or "Home Assistant", n.get("message") or "")))
        elif mid == 3:
            d = ev.get("data") or {}
            self.out.put(("rt_notify", (str(d.get("title") or "Home Assistant"), str(d.get("message") or ""))))
