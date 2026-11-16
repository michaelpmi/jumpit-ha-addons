#!/usr/bin/env python3
"""Zeigt den JumpIT-Fernzugriff als Entitäten in Home Assistant an.

Setzt zwei Zustände über die Core-REST-API (POST /api/states/<entity_id>):
    sensor.jumpit_connect_adresse        Zustand = Adresse (https://….ha.jumpit.eu)
    binary_sensor.jumpit_connect_verbunden   an = Tunnel steht (Handshake < 3 min)

Diese Entitäten liegen nicht in der Geräteregistrierung (kein unique_id), sind aber
in Dashboards, Automationen und unter Entwicklerwerkzeuge > Zustände sichtbar.
Nach einem Neustart von Home Assistant sind sie weg, bis das Add-on sie erneut setzt
(spätestens nach 60 s). Beim Beenden des Add-ons werden sie entfernt.

Aufruf:
    ha_entities.py publish <url> <handshake_age_s> <cert_days_left> <addon_version>
    ha_entities.py delete
Umgebung: SUPERVISOR_TOKEN, optional HA_API_URL (Standard http://supervisor/core/api)
Exit: 0 = ok, 1 = Fehler (Ausgabe error:<Typ>), das Add-on läuft dann trotzdem weiter.
"""
import json
import os
import sys
import urllib.error
import urllib.request

API = os.environ.get("HA_API_URL", "http://supervisor/core/api").rstrip("/")
ADDRESS = "sensor.jumpit_connect_adresse"
LINK = "binary_sensor.jumpit_connect_verbunden"
CONNECTED_MAX_AGE = 180


def states(url: str, handshake_age: int, cert_days: int, version: str) -> dict[str, dict]:
    connected = 0 <= handshake_age <= CONNECTED_MAX_AGE
    base = {"addon_version": version}
    return {
        ADDRESS: {
            "state": url,
            "attributes": {
                **base,
                "friendly_name": "JumpIT Fernzugriff Adresse",
                "icon": "mdi:link-variant",
                "verbunden": connected,
                "handshake_vor_s": handshake_age,
                "zertifikat_gueltig_tage": cert_days,
            },
        },
        LINK: {
            "state": "on" if connected else "off",
            "attributes": {
                **base,
                "friendly_name": "JumpIT Fernzugriff verbunden",
                "device_class": "connectivity",
                "adresse": url,
            },
        },
    }


def _request(method: str, entity_id: str, body: dict | None = None) -> None:
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(
        f"{API}/states/{entity_id}", data=data, method=method,
        headers={"Authorization": f"Bearer {os.environ.get('SUPERVISOR_TOKEN', '')}",
                 "Content-Type": "application/json"},
    )
    try:
        urllib.request.urlopen(req, timeout=15).close()
    except urllib.error.HTTPError as e:
        if method == "DELETE" and e.code == 404:  # war schon weg
            return
        raise


def publish(url: str, handshake_age: int, cert_days: int, version: str) -> None:
    for entity_id, body in states(url, handshake_age, cert_days, version).items():
        _request("POST", entity_id, body)


def delete() -> None:
    for entity_id in (ADDRESS, LINK):
        _request("DELETE", entity_id)


def _int(value: str, default: int) -> int:
    try:
        return int(float(value))
    except ValueError:
        return default


def main(argv: list[str]) -> int:
    try:
        if len(argv) >= 6 and argv[1] == "publish":
            publish(argv[2], _int(argv[3], 99999), _int(argv[4], -1), argv[5])
            return 0
        if len(argv) == 2 and argv[1] == "delete":
            delete()
            return 0
    except Exception as e:  # keine Details (Token/Adressen)
        code = getattr(e, "code", None)
        print(f"error:{type(e).__name__}" + (f":{code}" if code else ""))
        return 1
    print("usage: ha_entities.py publish <url> <handshake_age_s> <cert_days_left> <version> | delete", file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
