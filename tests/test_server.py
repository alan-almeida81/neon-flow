import json
import threading
import unittest
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer

from neon_flow.server import FlowSource, make_handler


class ServerSecurityTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.srv = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(FlowSource(), {"localhost", "127.0.0.1"}))
        cls.base = f"http://127.0.0.1:{cls.srv.server_address[1]}"
        threading.Thread(target=cls.srv.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        cls.srv.shutdown()

    def call(self, path, body=None, headers=None):
        req = urllib.request.Request(self.base + path, data=body, headers=headers or {}, method="POST" if body is not None else "GET")
        try:
            with urllib.request.urlopen(req) as r:
                return r.status, r.read()
        except urllib.error.HTTPError as e:
            return e.code, e.read()

    def test_page_and_xterm_are_served(self):
        self.assertEqual(self.call("/")[0], 200)
        self.assertEqual(self.call("/vendor/xterm/xterm.js")[0], 200)

    def test_prompt_rejects_forms_and_other_origins(self):
        self.assertEqual(self.call("/api/prompt", b"a=1", {"Content-Type": "application/x-www-form-urlencoded"})[0], 403)
        self.assertEqual(self.call("/api/prompt", b"{}", {"Content-Type": "application/json", "Origin": "https://evil.example"})[0], 403)
        self.assertEqual(self.call("/", headers={"Origin": "https://evil.example"})[0], 403)

    def test_prompt_validates_before_touching_maestri(self):
        status, body = self.call("/api/prompt", json.dumps({"terminalId": "x", "text": "oi"}).encode(), {"Content-Type": "application/json"})
        self.assertEqual(status, 400)
        status, _ = self.call("/api/prompt", json.dumps({"terminalId": "00000000-0000-0000-0000-000000000000", "text": " "}).encode(),
                              {"Content-Type": "application/json"})
        self.assertEqual(status, 400)


if __name__ == "__main__":
    unittest.main()
