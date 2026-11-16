"""Tests für ha_entities.py gegen einen lokalen Fake-Core (REST /api/states)."""
import http.server
import importlib.util
import json
import os
import pathlib
import threading
import unittest

SRC = pathlib.Path(__file__).parents[1] / "rootfs/usr/local/bin/ha_entities.py"
spec = importlib.util.spec_from_file_location("ha_entities", SRC)
he = importlib.util.module_from_spec(spec)
spec.loader.exec_module(he)

URL = "https://ha-test01.ha.jumpit.eu"


class Fake(http.server.BaseHTTPRequestHandler):
    log: list = []
    status = 200

    def _do(self):
        n = int(self.headers.get("Content-Length") or 0)
        body = json.loads(self.rfile.read(n)) if n else None
        Fake.log.append((self.command, self.path, self.headers.get("Authorization"), body))
        self.send_response(Fake.status)
        self.end_headers()

    do_POST = do_DELETE = _do

    def log_message(self, *a):
        pass


class EntityTests(unittest.TestCase):
    def setUp(self):
        Fake.log, Fake.status = [], 200
        self.srv = http.server.HTTPServer(("127.0.0.1", 0), Fake)
        threading.Thread(target=self.srv.serve_forever, daemon=True).start()
        he.API = f"http://127.0.0.1:{self.srv.server_port}/api"
        os.environ["SUPERVISOR_TOKEN"] = "tok"

    def tearDown(self):
        self.srv.shutdown()
        self.srv.server_close()

    def test_states_adresse_ist_der_zustand(self):
        s = he.states(URL, 12, 80, "0.1.5")
        self.assertEqual(s[he.ADDRESS]["state"], URL)
        self.assertEqual(s[he.ADDRESS]["attributes"]["zertifikat_gueltig_tage"], 80)
        self.assertEqual(s[he.LINK]["state"], "on")

    def test_verbunden_grenzen(self):
        self.assertEqual(he.states(URL, 180, 1, "v")[he.LINK]["state"], "on")
        self.assertEqual(he.states(URL, 181, 1, "v")[he.LINK]["state"], "off")
        self.assertEqual(he.states(URL, 99999, 1, "v")[he.LINK]["state"], "off")

    def test_publish_sendet_beide_entitaeten_mit_token(self):
        self.assertEqual(he.main(["x", "publish", URL, "5", "80", "0.1.5"]), 0)
        paths = [(m, p) for m, p, _, _ in Fake.log]
        self.assertEqual(paths, [("POST", f"/api/states/{he.ADDRESS}"), ("POST", f"/api/states/{he.LINK}")])
        self.assertTrue(all(a == "Bearer tok" for _, _, a, _ in Fake.log))

    def test_delete_entfernt_beide(self):
        self.assertEqual(he.main(["x", "delete"]), 0)
        self.assertEqual([(m, p) for m, p, _, _ in Fake.log],
                         [("DELETE", f"/api/states/{he.ADDRESS}"), ("DELETE", f"/api/states/{he.LINK}")])

    def test_delete_404_ist_kein_fehler(self):
        Fake.status = 404
        self.assertEqual(he.main(["x", "delete"]), 0)

    def test_core_fehler_gibt_exit_1(self):
        Fake.status = 500
        self.assertEqual(he.main(["x", "publish", URL, "5", "80", "0.1.5"]), 1)

    def test_core_nicht_erreichbar_gibt_exit_1(self):
        he.API = "http://127.0.0.1:1/api"
        self.assertEqual(he.main(["x", "publish", URL, "5", "80", "0.1.5"]), 1)

    def test_ungueltige_zahlen_werden_abgefangen(self):
        self.assertEqual(he.main(["x", "publish", URL, "n/a", "?", "0.1.5"]), 0)
        body = Fake.log[1][3]
        self.assertEqual(body["state"], "off")


if __name__ == "__main__":
    unittest.main()
