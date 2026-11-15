"""Tests für ha_http_config.py gegen einen Fake-Core (WebSocket), ohne echte Home Assistant."""
import asyncio
import importlib.util
import json
import os
import pathlib
import unittest

import websockets

SRC = pathlib.Path(__file__).parents[1] / "rootfs/usr/local/bin/ha_http_config.py"
spec = importlib.util.spec_from_file_location("ha_http_config", SRC)
hc = importlib.util.module_from_spec(spec)
spec.loader.exec_module(hc)

P = ["127.0.0.1", "::1"]


class FakeCore:
    """Minimaler Core: auth + http/config, http/config/configure, http/config/promote."""

    def __init__(self, stable=None, pending=None, supported=True, token="tok"):
        self.stable, self.pending, self.supported, self.token = stable, pending, supported, token
        self.received = []

    async def handler(self, ws):
        await ws.send(json.dumps({"type": "auth_required"}))
        auth = json.loads(await ws.recv())
        if auth.get("access_token") != self.token:
            await ws.send(json.dumps({"type": "auth_invalid"}))
            return
        await ws.send(json.dumps({"type": "auth_ok"}))
        async for raw in ws:
            msg = json.loads(raw)
            self.received.append(msg)
            i, t = msg["id"], msg["type"]
            if not self.supported:
                out = {"id": i, "type": "result", "success": False,
                       "error": {"code": "unknown_command", "message": "Unknown command."}}
            elif t == "http/config":
                out = {"id": i, "type": "result", "success": True,
                       "result": {"stable": self.stable, "pending": self.pending, "revert_at": None}}
            elif t == "http/config/configure":
                self.pending = msg["config"]
                out = {"id": i, "type": "result", "success": True, "result": {"restart": True}}
            elif t == "http/config/promote":
                self.stable, self.pending = self.pending, None
                out = {"id": i, "type": "result", "success": True, "result": None}
            else:
                out = {"id": i, "type": "result", "success": False, "error": {"code": "unknown_command", "message": ""}}
            await ws.send(json.dumps(out))


def run_cmd(core: FakeCore, *argv, token="tok"):
    async def go():
        server = await websockets.serve(core.handler, "127.0.0.1", 0)
        port = server.sockets[0].getsockname()[1]
        hc.URL = f"ws://127.0.0.1:{port}"
        os.environ["SUPERVISOR_TOKEN"] = token
        try:
            if argv[0] == "configure":
                return await hc.cmd_configure(list(argv[1:]))
            return await hc.cmd_promote()
        finally:
            server.close()
            await server.wait_closed()

    return asyncio.run(go())


class BuildConfigTests(unittest.TestCase):
    def test_leere_basis(self):
        cfg, changed = hc.build_config({}, P)
        self.assertTrue(changed)
        self.assertEqual(cfg, {"use_x_forwarded_for": True, "trusted_proxies": ["127.0.0.1", "::1"]})

    def test_metadaten_werden_entfernt_rest_bleibt(self):
        base = {"server_port": 80, "created_at": "2026-11-15T12:00:00+00:00", "error": None,
                "error_message": None, "ip_ban_enabled": True, "use_x_forwarded_for": False}
        cfg, changed = hc.build_config(base, P)
        self.assertTrue(changed)
        self.assertEqual(cfg["server_port"], 80)
        self.assertTrue(cfg["ip_ban_enabled"])
        for k in ("created_at", "error", "error_message"):
            self.assertNotIn(k, cfg)

    def test_netz_notation_zaehlt_als_vorhanden(self):
        base = {"use_x_forwarded_for": True, "trusted_proxies": ["127.0.0.1/32", "::1/128"]}
        cfg, changed = hc.build_config(base, P)
        self.assertFalse(changed)
        self.assertEqual(cfg["trusted_proxies"], ["127.0.0.1/32", "::1/128"])

    def test_breiteres_netz_deckt_ab(self):
        base = {"use_x_forwarded_for": True, "trusted_proxies": ["127.0.0.0/8", "::1"]}
        _, changed = hc.build_config(base, P)
        self.assertFalse(changed)

    def test_vorhandene_proxies_bleiben_erhalten(self):
        base = {"use_x_forwarded_for": True, "trusted_proxies": ["172.30.33.0/24"]}
        cfg, changed = hc.build_config(base, P)
        self.assertTrue(changed)
        self.assertEqual(cfg["trusted_proxies"], ["172.30.33.0/24", "127.0.0.1", "::1"])

    def test_ungueltige_adresse(self):
        with self.assertRaises(hc.WsError):
            hc.build_config({}, ["kein-ip"])

    def test_nie_alles_freigeben(self):
        cfg, _ = hc.build_config({}, P)
        self.assertNotIn("0.0.0.0/0", cfg["trusted_proxies"])


class CommandTests(unittest.TestCase):
    def test_configure_setzt_pending_und_behaelt_port(self):
        core = FakeCore(stable={"server_port": 80, "use_x_forwarded_for": False, "created_at": "x"})
        self.assertEqual(run_cmd(core, "configure", *P), 0)
        sent = [m for m in core.received if m["type"] == "http/config/configure"][0]["config"]
        self.assertEqual(sent["server_port"], 80)
        self.assertTrue(sent["use_x_forwarded_for"])
        self.assertEqual(sent["trusted_proxies"], P)
        self.assertNotIn("created_at", sent)

    def test_stable_schon_korrekt_ist_unveraendert(self):
        core = FakeCore(stable={"use_x_forwarded_for": True, "trusted_proxies": ["127.0.0.1/32", "::1/128"]})
        self.assertEqual(run_cmd(core, "configure", *P), 3)
        self.assertFalse([m for m in core.received if m["type"] == "http/config/configure"])

    def test_pending_schon_korrekt_nur_promote_noetig(self):
        core = FakeCore(stable={}, pending={"use_x_forwarded_for": True, "trusted_proxies": P})
        self.assertEqual(run_cmd(core, "configure", *P), 0)
        self.assertFalse([m for m in core.received if m["type"] == "http/config/configure"])

    def test_aeltere_ha_version_ist_unsupported(self):
        core = FakeCore(supported=False)
        self.assertEqual(run_cmd(core, "configure", *P), 4)

    def test_promote(self):
        core = FakeCore(stable={}, pending={"use_x_forwarded_for": True, "trusted_proxies": P})
        self.assertEqual(run_cmd(core, "promote"), 0)
        self.assertIsNone(core.pending)
        self.assertEqual(core.stable["trusted_proxies"], P)

    def test_falsches_token_wird_abgelehnt(self):
        core = FakeCore(token="richtig")
        with self.assertRaises(hc.WsError):
            run_cmd(core, "configure", *P, token="falsch")


if __name__ == "__main__":
    unittest.main()
