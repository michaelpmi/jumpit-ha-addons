#!/usr/bin/env python3
"""Reverse-Proxy in Home Assistant (>= 2026.8) über die offizielle WebSocket-API freigeben.

Seit HA 2026.8 liegt die HTTP-Konfiguration nicht mehr in configuration.yaml,
sondern im Store .storage/http und wird über diese Kommandos verwaltet:
    http/config            lesen   (stable / pending / revert_at)
    http/config/configure  setzen  (speichert "pending", Core startet selbst neu)
    http/config/promote    bestätigen (sonst Rollback auf "stable" nach ca. 5 min)

Aufruf:
    ha_http_config.py configure <proxy> [<proxy> ...]
    ha_http_config.py status <proxy> [<proxy> ...]
    ha_http_config.py promote

Ausgabe (eine Zeile) und Exit-Code:
    configure: restart (0)   Konfiguration gesetzt, Core startet neu, danach testen + promote
               pending (0)   Freigabe steht schon als pending, nur noch promote nötig
               unchanged (3) Freigabe steht schon als stable
               unsupported (4)  HA kennt http/config nicht (älter als 2026.8)
               error:<text> (1)
    status:    stable (0)    Freigabe ist dauerhaft gespeichert
               pending (0)   Freigabe gesetzt, aber noch nicht bestätigt
               none (3)      Freigabe fehlt
               unsupported (4) | error:<text> (1)
    promote:   promoted (0) | error:<text> (1)

Gesprochen wird mit ws://supervisor/core/websocket und dem SUPERVISOR_TOKEN
(Add-on-Option homeassistant_api: true). Token und Konfigurationswerte werden nie ausgegeben.
"""
import asyncio
import ipaddress
import json
import os
import sys

URL = os.environ.get("HA_WS_URL", "ws://supervisor/core/websocket")
ALLOWED = {
    "server_host", "server_port", "ssl_certificate", "ssl_peer_certificate", "ssl_key",
    "cors_allowed_origins", "use_x_forwarded_for", "trusted_proxies",
    "login_attempts_threshold", "ip_ban_enabled", "ssl_profile", "use_x_frame_options",
}


class WsError(Exception):
    def __init__(self, code: str, message: str = ""):
        super().__init__(f"{code}: {message}")
        self.code = code


def _net(value: str):
    try:
        return ipaddress.ip_network(value, strict=False)
    except ValueError:
        return None


def build_config(base: dict | None, proxies: list[str]) -> tuple[dict, bool]:
    """Neue Konfiguration aus der bestehenden ableiten. Rückgabe: (config, geändert?)."""
    cfg = {k: v for k, v in (base or {}).items() if k in ALLOWED}
    changed = False
    if cfg.get("use_x_forwarded_for") is not True:
        cfg["use_x_forwarded_for"] = True
        changed = True
    existing = list(cfg.get("trusted_proxies") or [])
    have = [n for n in (_net(str(e)) for e in existing) if n is not None]
    for p in proxies:
        net = _net(p)
        if net is None:
            raise WsError("invalid_proxy", "ungültige Proxy-Adresse")
        if not any(net.version == h.version and net.subnet_of(h) for h in have):
            existing.append(p)
            have.append(net)
            changed = True
    cfg["trusted_proxies"] = existing
    return cfg, changed


def has_proxies(cfg: dict | None, proxies: list[str]) -> bool:
    if not cfg:
        return False
    try:
        _, changed = build_config(cfg, proxies)
    except WsError:
        return False
    return not changed


class Client:
    def __init__(self, ws):
        self.ws = ws
        self._id = 0

    async def call(self, payload: dict):
        self._id += 1
        await self.ws.send(json.dumps({"id": self._id, **payload}))
        while True:
            msg = json.loads(await self.ws.recv())
            if msg.get("id") != self._id:
                continue
            if msg.get("success"):
                return msg.get("result")
            err = msg.get("error") or {}
            raise WsError(str(err.get("code", "error")), str(err.get("message", "")))


async def connect():
    import websockets  # erst hier, damit Tests die reinen Funktionen ohne Paket laden können

    token = os.environ.get("SUPERVISOR_TOKEN", "")
    ws = await websockets.connect(URL, max_size=2**22, open_timeout=15)
    hello = json.loads(await ws.recv())
    if hello.get("type") != "auth_required":
        raise WsError("protocol", "unerwartete Begrüßung")
    await ws.send(json.dumps({"type": "auth", "access_token": token}))
    reply = json.loads(await ws.recv())
    if reply.get("type") != "auth_ok":
        raise WsError("auth", "Anmeldung am Core abgelehnt")
    return Client(ws), ws


async def cmd_configure(proxies: list[str]) -> int:
    client, ws = await connect()
    try:
        try:
            state = await client.call({"type": "http/config"})
        except WsError as e:
            if e.code in ("unknown_command", "not_found"):
                print("unsupported")
                return 4
            raise
        state = state or {}
        pending, stable = state.get("pending"), state.get("stable")
        if pending and has_proxies(pending, proxies):
            print("pending")
            return 0
        if not pending and has_proxies(stable, proxies):
            print("unchanged")
            return 3
        cfg, _ = build_config(pending or stable, proxies)
        try:
            res = await client.call({"type": "http/config/configure", "config": cfg})
        except Exception as e:  # Core kann beim Neustart die Verbindung kappen
            if isinstance(e, WsError):
                raise
            print("restart")
            return 0
        restart = (res or {}).get("restart", True)
        print("restart" if restart else "unchanged")
        return 0 if restart else 3
    finally:
        try:
            await ws.close()
        except Exception:
            pass


async def cmd_status(proxies: list[str]) -> int:
    client, ws = await connect()
    try:
        try:
            state = await client.call({"type": "http/config"})
        except WsError as e:
            if e.code in ("unknown_command", "not_found"):
                print("unsupported")
                return 4
            raise
        state = state or {}
        if state.get("pending") and has_proxies(state.get("pending"), proxies):
            print("pending")
            return 0
        if not state.get("pending") and has_proxies(state.get("stable"), proxies):
            print("stable")
            return 0
        print("none")
        return 3
    finally:
        try:
            await ws.close()
        except Exception:
            pass


async def cmd_promote() -> int:
    client, ws = await connect()
    try:
        await client.call({"type": "http/config/promote"})
        print("promoted")
        return 0
    finally:
        try:
            await ws.close()
        except Exception:
            pass


def main(argv: list[str]) -> int:
    if len(argv) < 2 or argv[1] not in ("configure", "status", "promote"):
        print("usage: ha_http_config.py configure|status <proxy>... | promote", file=sys.stderr)
        return 1
    try:
        if argv[1] in ("configure", "status"):
            if len(argv) < 3:
                print("error:keine Proxy-Adresse")
                return 1
            fn = cmd_configure if argv[1] == "configure" else cmd_status
            return asyncio.run(fn(argv[2:]))
        return asyncio.run(cmd_promote())
    except WsError as e:
        print(f"error:{e.code}")
        return 1
    except Exception as e:  # keine Details (könnten Pfade/Token enthalten), nur Typ und HTTP-Status
        code = getattr(getattr(e, "response", None), "status_code", None)
        print(f"error:{type(e).__name__}" + (f":{code}" if code else ""))
        return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
