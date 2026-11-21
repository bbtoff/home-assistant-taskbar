"""Image en direct d'une camera Home Assistant.

Lit le flux MJPEG de Home Assistant (/api/camera_proxy_stream/<camera>) : une suite d'images JPEG sur une
seule connexion. Si la camera n'en fournit pas (ou pour une entite image.*), on revient a une photo
toutes les `snapshot_s` secondes, et on reessaie le flux de temps en temps.
"""
import time
import urllib.error
import urllib.parse
import urllib.request

import imaging
from i18n import _

MAX_FPS = 10              # au-dela, on saute des images : inutile pour un apercu, et ca coute du processeur
FIRST_FRAME_S = 10.0      # sans image dans ce delai, le flux est considere comme absent
RETRY_STREAM_S = 60.0     # apres un echec du flux, photos seulement pendant ce temps


def _frames(resp, alive):
    """Images JPEG (bytes) d'une reponse multipart/x-mixed-replace. Utilise Content-Length quand la partie
    en donne un, sinon cherche le debut (FFD8) et la fin (FFD9) de chaque JPEG."""
    buf = b""
    while alive():
        chunk = resp.read1(65536) if hasattr(resp, "read1") else resp.read(65536)
        if not chunk:
            return
        buf += chunk
        while True:
            start = buf.find(b"\xff\xd8")
            if start < 0:
                buf = buf[-1:]          # garde un eventuel FF coupe en deux
                break
            head = buf[:start].lower()
            i = head.rfind(b"content-length:")
            end = -1
            if i >= 0:
                try:
                    n = int(head[i + 15:].split(b"\r\n", 1)[0].strip())
                    if len(buf) >= start + n:
                        end = start + n
                    else:
                        buf = buf[max(0, i - 2):]
                        break
                except ValueError:
                    pass
            if end < 0:
                e = buf.find(b"\xff\xd9", start + 2)
                if e < 0:
                    buf = buf[start:]
                    break
                end = e + 2
            yield buf[start:end]
            buf = buf[end:]
        if len(buf) > 8 * 1024 * 1024:  # flux illisible : on repart de zero
            buf = b""


def _error_text(e):
    code = getattr(e, "code", None)
    if code in (404, 500, 503):
        return _("Caméra indisponible dans Home Assistant")
    if code:
        return _("Image indisponible : %s") % code
    return _("Image indisponible : %s") % str(getattr(e, "reason", e))[:60]


def run(ha, eid, size, alive, on_frame, on_error, snapshot_s=2.0):
    """Boucle a lancer dans un fil : appelle on_frame(png_base64) pour chaque image affichee et
    on_error(texte) en cas de probleme, tant que alive() est vrai. size() -> (largeur, hauteur) max."""
    stream_ok_at = 0.0 if eid.startswith("camera.") else float("inf")
    while alive():
        if time.monotonic() >= stream_ok_at:
            try:
                got = _stream(ha, eid, size, alive, on_frame)
            except Exception:
                got = False
            if not alive():
                return
            if got:
                continue                # flux coupe apres avoir marche : on se reconnecte tout de suite
            stream_ok_at = time.monotonic() + RETRY_STREAM_S
        # photo seule
        try:
            w, h = size()
            png, _w, _h = imaging.to_png(ha.camera_image(eid), w, h, level=1)
            on_frame(png)
            delay = snapshot_s
        except Exception as e:
            on_error(_error_text(e))
            delay = 15.0 if getattr(e, "code", None) else 5.0
        end = time.monotonic() + delay
        while alive() and time.monotonic() < end:
            time.sleep(0.1)


def _stream(ha, eid, size, alive, on_frame):
    """Lit le flux jusqu'a sa fin. Renvoie True si au moins une image a ete affichee."""
    req = urllib.request.Request("%s/api/camera_proxy_stream/%s" % (ha.url, urllib.parse.quote(eid)),
                                 headers={"Authorization": "Bearer " + ha.token})
    got = False
    last = 0.0
    with urllib.request.urlopen(req, timeout=FIRST_FRAME_S, context=ha.ctx) as resp:
        if "multipart" not in (resp.headers.get("Content-Type") or "").lower():
            return False
        for jpeg in _frames(resp, alive):
            now = time.monotonic()
            if now - last < 1.0 / MAX_FPS:
                continue
            try:
                w, h = size()
                png, _w, _h = imaging.to_png(jpeg, w, h, level=1)
            except OSError:
                continue                # image coupee ou illisible : on attend la suivante
            last = now
            got = True
            on_frame(png)
    return got
