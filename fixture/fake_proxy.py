"""CI fixture: an authenticating forward proxy that also plays a fake Singapore storefront.

There's no DNS for `.test`, so a request for http://shop.test/ can only succeed through this
proxy. A passing run therefore proves the browser really used the proxy and sent the
credentials, without any real proxy or third-party site involved.

    python fixture/fake_proxy.py [port]      # default 8899, user ci-user / pass ci-pass
"""
import base64
import json
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlsplit

USER, PASS = "ci-user", "ci-pass"
EXPECTED = "Basic " + base64.b64encode(f"{USER}:{PASS}".encode()).decode()

SG_PAGE = """<!doctype html><html lang="en-SG"><head><meta charset="utf-8"><title>Shop (SG)</title></head>
<body><h1>Wireless earbuds</h1><p class="price">S$ 129.00</p><p>Free delivery across Singapore.</p>
<script>document.body.insertAdjacentHTML('beforeend',
  '<p id="tz">' + Intl.DateTimeFormat().resolvedOptions().timeZone + '</p>');</script></body></html>"""

EU_PAGE = """<!doctype html><html lang="de"><head><meta charset="utf-8"><title>Shop (EU)</title></head>
<body><div id="consent">We use cookies. Accept all / Reject all</div>
<h1>Kabellose Ohrhörer</h1><p class="price">129,00 €</p></body></html>"""


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.0"  # one request per connection

    def log_message(self, fmt, *args):
        sys.stderr.write("fixture: " + fmt % args + "\n")

    def _send(self, code, body=b"", ctype="text/html; charset=utf-8", extra=None):
        self.send_response(code)
        for k, v in (extra or {}).items():
            self.send_header(k, v)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)

    def do_CONNECT(self):
        # Chrome may try https:// first. Refuse so it falls back to http:// on this fixture.
        self._send(502, b"fixture serves plain http only", "text/plain")

    def do_GET(self):
        if self.headers.get("Proxy-Authorization") != EXPECTED:
            return self._send(407, b"proxy auth required", "text/plain",
                              {"Proxy-Authenticate": 'Basic realm="fixture"'})
        u = urlsplit(self.path)
        if not u.scheme:
            return self._send(400, b"this is a proxy: send an absolute URL", "text/plain")
        host, path = u.hostname, u.path or "/"
        if host == "shop.test":
            if path == "/":
                return self._send(302, extra={"Location": "http://shop.test/sg/"})
            if path == "/sg/":
                return self._send(200, SG_PAGE.encode())
            if path == "/eu/":
                return self._send(200, EU_PAGE.encode())
            if path == "/cdn-cgi/trace":
                return self._send(200, b"ip=203.0.113.7\nloc=SG\n", "text/plain")
        if host == "ipinfo.test" and path == "/json":
            body = {"ip": "203.0.113.7", "country": "SG", "org": "AS45143 SingTel Mobile (fixture)"}
            return self._send(200, json.dumps(body).encode(), "application/json")
        return self._send(404, b"not in fixture", "text/plain")

    do_HEAD = do_GET


if __name__ == "__main__":
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8899
    print(f"fixture proxy on 127.0.0.1:{port}", flush=True)
    ThreadingHTTPServer(("127.0.0.1", port), Handler).serve_forever()
