import base64
import os
import socket
import threading
import unittest
from unittest import mock

import geo_common as g


class ProxySettings(unittest.TestCase):
    def test_sg_proxy_wins(self):
        env = {"SG_PROXY_SERVER": "http://sg.example:8000", "SG_PROXY_USERNAME": "a",
               "SG_PROXY_PASSWORD": "b", "HTTPS_PROXY": "http://x:y@other:1"}
        with mock.patch.dict(os.environ, env, clear=True):
            self.assertEqual(g.proxy_settings(), ("http://sg.example:8000", "a", "b"))

    def test_https_proxy_split_and_decoded(self):
        with mock.patch.dict(os.environ, {"HTTPS_PROXY": "http://us%40er:p%3Ass@host.example:8123"}, clear=True):
            self.assertEqual(g.proxy_settings(), ("http://host.example:8123", "us@er", "p:ss"))
            self.assertEqual(g.proxy_url_with_auth(), "http://us%40er:p%3Ass@host.example:8123")

    def test_none(self):
        with mock.patch.dict(os.environ, {}, clear=True):
            self.assertEqual(g.proxy_settings(), (None, None, None))


class Evaluate(unittest.TestCase):
    def cfg(self):
        env = {"TARGET_URL": "http://shop.test/", "EXPECT_URL": "/sg/$", "EXPECT_TEXT": r"S\$",
               "FORBID_TEXT": "€", "CONSENT_SELECTOR": "#consent"}
        with mock.patch.dict(os.environ, env, clear=True):
            return g.config()

    def test_default_target_expects_sg(self):
        with mock.patch.dict(os.environ, {}, clear=True):
            self.assertEqual(g.config()["expect_text"], "loc=SG")

    def test_pass(self):
        r = g.evaluate(self.cfg(), "http://shop.test/sg/", 200, "S$ 129.00", False, "Asia/Singapore")
        self.assertTrue(r["ok"])

    def test_fail_names_each_check(self):
        r = g.evaluate(self.cfg(), "http://shop.test/eu/", 200, "129,00 €", True, "Europe/Berlin")
        self.assertEqual([c["check"] for c in r["checks"] if not c["ok"]],
                         ["final_url", "expect_text", "forbid_text", "consent_banner", "browser_timezone"])

    def test_proxy_auth_failure(self):
        r = g.evaluate(self.cfg(), "http://shop.test/", 407, "", False, "Asia/Singapore")
        self.assertFalse(r["checks"][0]["ok"])


class Forwarder(unittest.TestCase):
    def test_adds_auth_and_strips_client_header(self):
        upstream = socket.socket()
        upstream.bind(("127.0.0.1", 0))
        upstream.listen(1)
        seen = {}

        def serve():
            c, _ = upstream.accept()
            data = b""
            while b"\r\n\r\n" not in data:
                data += c.recv(4096)
            seen["head"] = data
            c.sendall(b"HTTP/1.0 200 OK\r\nContent-Length: 2\r\n\r\nok")
            c.close()

        threading.Thread(target=serve, daemon=True).start()
        fwd = g.AuthForwarder("127.0.0.1", upstream.getsockname()[1], "u", "p").start()
        client = socket.create_connection(("127.0.0.1", fwd.port))
        client.sendall(b"GET http://shop.test/ HTTP/1.1\r\nHost: shop.test\r\n"
                       b"Proxy-Authorization: Basic stale\r\nProxy-Connection: keep-alive\r\n\r\n")
        reply = b""
        while True:
            chunk = client.recv(4096)
            if not chunk:
                break
            reply += chunk
        client.close()

        head = seen["head"].decode()
        token = base64.b64encode(b"u:p").decode()
        self.assertIn(f"Proxy-Authorization: Basic {token}", head)
        self.assertNotIn("stale", head)
        self.assertNotIn("Proxy-Connection", head)
        self.assertIn("Connection: close", head)
        self.assertTrue(reply.endswith(b"ok"))


if __name__ == "__main__":
    unittest.main()
