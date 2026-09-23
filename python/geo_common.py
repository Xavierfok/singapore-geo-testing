"""Shared config, checks and a tiny auth forwarder for the Python recipes. Stdlib only.

Every recipe reads the same environment variables, so you can switch framework without
changing your CI config. See the README for the full list.
"""
import base64
import json
import os
import re
import socket
import sys
import threading
from urllib.parse import quote, unquote, urlsplit

DEFAULT_TARGET = "https://www.cloudflare.com/cdn-cgi/trace"
DEFAULT_EXPECT = r"loc=SG"

# Singapore geolocation (Raffles Place) for browsers that ask for it.
SG_LAT, SG_LON = 1.2840, 103.8510


def proxy_settings():
    """Return (server, username, password), each None when unset.

    `server` is scheme://host:port with no credentials, which is what browsers want.
    SG_PROXY_* (exported by setup-singapore-proxy) wins over the usual *_PROXY variables.
    """
    server = os.environ.get("SG_PROXY_SERVER")
    if server:
        return (server,
                os.environ.get("SG_PROXY_USERNAME") or None,
                os.environ.get("SG_PROXY_PASSWORD") or None)
    for name in ("HTTPS_PROXY", "https_proxy", "ALL_PROXY", "all_proxy", "HTTP_PROXY", "http_proxy"):
        url = os.environ.get(name)
        if not url:
            continue
        if "://" not in url:
            url = "http://" + url
        p = urlsplit(url)
        port = f":{p.port}" if p.port else ""
        return (f"{p.scheme}://{p.hostname}{port}",
                unquote(p.username) if p.username else None,
                unquote(p.password) if p.password else None)
    return None, None, None


def proxy_url_with_auth():
    """The proxy as one URL with credentials, for plain HTTP clients."""
    server, user, pw = proxy_settings()
    if not server or not user:
        return server
    p = urlsplit(server)
    return f"{p.scheme}://{quote(user, safe='')}:{quote(pw or '', safe='')}@{p.netloc}"


def config():
    target = os.environ.get("TARGET_URL") or DEFAULT_TARGET
    default_expect = DEFAULT_EXPECT if target == DEFAULT_TARGET else ""
    return {
        "target_url": target,
        "expect_text": os.environ.get("EXPECT_TEXT", default_expect),
        "forbid_text": os.environ.get("FORBID_TEXT", ""),
        "expect_url": os.environ.get("EXPECT_URL", ""),
        "consent_selector": os.environ.get("CONSENT_SELECTOR", ""),
        "consent_expect": os.environ.get("CONSENT_EXPECT", "absent").lower(),
        "timezone": os.environ.get("GEO_TIMEZONE", "Asia/Singapore"),
        "locale": os.environ.get("GEO_LOCALE", "en-SG"),
        "screenshot": os.environ.get("SCREENSHOT", ""),
        "headless": os.environ.get("HEADLESS", "1") != "0",
        "timeout_ms": int(os.environ.get("TIMEOUT_MS", "45000")),
        "settle_ms": int(os.environ.get("SETTLE_MS", "1500")),
    }


def _snippet(pattern, text):
    m = re.search(pattern, text)
    return m.group(0)[:80] if m else None


def evaluate(cfg, final_url, status, text, consent_present, browser_tz):
    """Run the configured checks against what the browser saw. Returns a summary dict."""
    checks = []

    def add(name, ok, detail):
        checks.append({"check": name, "ok": bool(ok), "detail": detail})

    add("http_status", status is not None and status < 400, f"status {status}")
    if cfg["expect_url"]:
        add("final_url", re.search(cfg["expect_url"], final_url),
            f"{final_url} vs /{cfg['expect_url']}/")
    if cfg["expect_text"]:
        hit = _snippet(cfg["expect_text"], text)
        add("expect_text", hit, f"found {hit!r}" if hit else f"no match for /{cfg['expect_text']}/")
    if cfg["forbid_text"]:
        hit = _snippet(cfg["forbid_text"], text)
        add("forbid_text", not hit, f"found {hit!r}" if hit else f"no match for /{cfg['forbid_text']}/")
    if cfg["consent_selector"]:
        want = cfg["consent_expect"] == "present"
        add("consent_banner", consent_present == want,
            f"{cfg['consent_selector']} {'present' if consent_present else 'absent'}, expected {cfg['consent_expect']}")
    add("browser_timezone", browser_tz == cfg["timezone"], f"{browser_tz}, expected {cfg['timezone']}")
    return {"target": cfg["target_url"], "final_url": final_url,
            "ok": all(c["ok"] for c in checks), "checks": checks}


def report(summary):
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # Windows consoles default to cp1252
    print(json.dumps(summary, indent=2, ensure_ascii=False))
    return 0 if summary["ok"] else 1


class AuthForwarder:
    """Local proxy on 127.0.0.1 that adds Proxy-Authorization and hands everything to the upstream proxy.

    Chrome has no command-line flag for proxy credentials, so Selenium points Chrome here instead.
    CONNECT tunnels are piped as-is after the first request. Plain-HTTP requests get
    `Connection: close`, so every request arrives on a fresh connection and gets the header.
    """

    def __init__(self, upstream_host, upstream_port, username, password):
        self.upstream = (upstream_host, int(upstream_port))
        token = base64.b64encode(f"{username}:{password or ''}".encode()).decode()
        self.auth_line = f"Proxy-Authorization: Basic {token}\r\n".encode()
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.sock.bind(("127.0.0.1", 0))
        self.sock.listen(64)
        self.port = self.sock.getsockname()[1]

    def start(self):
        threading.Thread(target=self._accept, daemon=True).start()
        return self

    def _accept(self):
        while True:
            try:
                client, _ = self.sock.accept()
            except OSError:
                return
            threading.Thread(target=self._handle, args=(client,), daemon=True).start()

    def _handle(self, client):
        upstream = None
        try:
            buf = b""
            while b"\r\n\r\n" not in buf:
                chunk = client.recv(65536)
                if not chunk:
                    return
                buf += chunk
                if len(buf) > 65536:
                    return
            head, rest = buf.split(b"\r\n\r\n", 1)
            lines = head.split(b"\r\n")
            is_connect = lines[0].upper().startswith(b"CONNECT ")
            drop = (b"proxy-authorization:", b"proxy-connection:", b"connection:")
            kept = [ln for ln in lines[1:] if not ln.lower().startswith(drop)]
            out = lines[0] + b"\r\n" + b"".join(ln + b"\r\n" for ln in kept) + self.auth_line
            if not is_connect:
                out += b"Connection: close\r\n"
            upstream = socket.create_connection(self.upstream, timeout=30)
            upstream.settimeout(None)  # tunnels can sit idle between requests
            upstream.sendall(out + b"\r\n" + rest)
            t = threading.Thread(target=_pipe, args=(upstream, client), daemon=True)
            t.start()
            _pipe(client, upstream)
            t.join(timeout=60)
        except OSError:
            pass
        finally:
            for s in (client, upstream):
                if s is not None:
                    try:
                        s.close()
                    except OSError:
                        pass


def _pipe(src, dst):
    try:
        while True:
            data = src.recv(65536)
            if not data:
                break
            dst.sendall(data)
    except OSError:
        pass
    finally:
        try:
            dst.shutdown(socket.SHUT_WR)
        except OSError:
            pass


def die(msg):
    print(f"error: {msg}", file=sys.stderr)
    sys.exit(2)
