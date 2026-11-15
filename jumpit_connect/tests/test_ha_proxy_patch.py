import importlib.util
import pathlib
import unittest

SRC = pathlib.Path(__file__).parents[1] / "rootfs/usr/local/bin/ha_proxy_patch.py"
spec = importlib.util.spec_from_file_location("ha_proxy_patch", SRC)
hp = importlib.util.module_from_spec(spec)
spec.loader.exec_module(hp)

P = ["127.0.0.1", "::1"]


class PatchTests(unittest.TestCase):
    def test_kein_http_block_wird_angehaengt(self):
        src = "homeassistant:\n  name: Zuhause  # Kommentar\nlight: !include lights.yaml\n"
        out, changed = hp.patch(src, P)
        self.assertTrue(changed)
        self.assertTrue(out.startswith(src.rstrip("\n")))  # Original unverändert
        self.assertIn("http:\n  use_x_forwarded_for: true\n  trusted_proxies:\n    - 127.0.0.1\n    - ::1", out)

    def test_http_mit_port_wird_ergaenzt(self):
        src = "http:\n  server_port: 80\n\nlight: []\n"
        out, changed = hp.patch(src, P)
        self.assertTrue(changed)
        self.assertEqual(
            out,
            "http:\n  use_x_forwarded_for: true\n  server_port: 80\n  trusted_proxies:\n    - 127.0.0.1\n    - ::1\n\nlight: []\n",
        )

    def test_bereits_korrekt_bleibt_unveraendert(self):
        src = "http:\n  use_x_forwarded_for: true\n  trusted_proxies:\n    - 127.0.0.1\n    - ::1\n"
        out, changed = hp.patch(src, P)
        self.assertFalse(changed)
        self.assertEqual(out, src)

    def test_vorhandene_proxyliste_wird_erweitert(self):
        src = "http:\n  use_x_forwarded_for: true\n  trusted_proxies:\n    - 172.30.33.0/24  # NPM\n  ip_ban_enabled: true\n"
        out, changed = hp.patch(src, P)
        self.assertTrue(changed)
        self.assertIn("    - 172.30.33.0/24  # NPM\n    - 127.0.0.1\n    - ::1\n  ip_ban_enabled: true", out)

    def test_nur_fehlende_eintraege(self):
        src = "http:\n  use_x_forwarded_for: true\n  trusted_proxies:\n    - 127.0.0.1\n"
        out, changed = hp.patch(src, P)
        self.assertTrue(changed)
        self.assertEqual(out.count("127.0.0.1"), 1)
        self.assertIn("    - ::1", out)

    def test_forwarded_false_wird_true(self):
        src = "http:\n  use_x_forwarded_for: false\n  trusted_proxies:\n    - 127.0.0.1\n    - ::1\n"
        out, changed = hp.patch(src, P)
        self.assertTrue(changed)
        self.assertIn("use_x_forwarded_for: true", out)

    def test_include_wird_nicht_angefasst(self):
        with self.assertRaises(hp.Manual):
            hp.patch("http: !include http.yaml\n", P)

    def test_flow_liste_wird_nicht_angefasst(self):
        with self.assertRaises(hp.Manual):
            hp.patch("http:\n  trusted_proxies: [10.0.0.1]\n", P)

    def test_http_mehrfach_ist_manuell(self):
        with self.assertRaises(hp.Manual):
            hp.patch("http:\n  a: 1\nhttp:\n  b: 2\n", P)

    def test_kommentarzeile_http_wird_ignoriert(self):
        src = "# http:\n#   server_port: 8123\nlight: []\n"
        out, changed = hp.patch(src, P)
        self.assertTrue(changed)
        self.assertEqual(out.count("\nhttp:\n"), 1)

    def test_idempotent(self):
        src = "http:\n  server_port: 80\n"
        once, _ = hp.patch(src, P)
        twice, changed = hp.patch(once, P)
        self.assertFalse(changed)
        self.assertEqual(once, twice)

    def test_einrueckung_4_bleibt_4(self):
        src = "http:\n    server_port: 80\n"
        out, _ = hp.patch(src, P)
        self.assertIn("    use_x_forwarded_for: true", out)
        self.assertIn("    trusted_proxies:\n      - 127.0.0.1", out)


if __name__ == "__main__":
    unittest.main()
