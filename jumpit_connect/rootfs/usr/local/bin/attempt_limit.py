#!/usr/bin/env python3
"""Begrenzt automatische Wiederholversuche (z. B. HA-Neustart durch die Proxy-Freigabe).

Ersetzt den früheren Dauer-Merker: Ein einmal gescheiterter Versuch blockierte die
Freigabe für immer und erzwang bei Updates eine Neuinstallation. Jetzt gilt:
höchstens <max> Versuche pro <window> Sekunden und mindestens <gap> Sekunden Abstand.

Aufruf:
    attempt_limit.py check  <datei> <max> <window_s> <gap_s>   Exit 0 = erlaubt, 1 = gesperrt
    attempt_limit.py record <datei> <window_s>                 Versuch vermerken
Die Datei enthält pro Zeile einen Unix-Zeitstempel. Fehlt oder ist sie kaputt, gilt: erlaubt.
"""
import os
import sys
import time


def load(path: str, window: int, now: float) -> list[float]:
    try:
        with open(path, encoding="utf-8") as fh:
            stamps = [float(x) for x in fh.read().split() if x.strip()]
    except (OSError, ValueError):
        return []
    return [t for t in stamps if 0 <= now - t < window]


def allowed(stamps: list[float], now: float, maximum: int, gap: int) -> tuple[bool, str]:
    if stamps and now - max(stamps) < gap:
        return False, "zu kurz nach dem letzten Versuch"
    if len(stamps) >= maximum:
        return False, "zu viele Versuche im Zeitfenster"
    return True, "ok"


def main(argv: list[str], now: float | None = None) -> int:
    now = time.time() if now is None else now
    try:
        if len(argv) == 6 and argv[1] == "check":
            ok, why = allowed(load(argv[2], int(argv[4]), now), now, int(argv[3]), int(argv[5]))
            print("allowed" if ok else f"blocked:{why}")
            return 0 if ok else 1
        if len(argv) == 4 and argv[1] == "record":
            stamps = load(argv[2], int(argv[3]), now) + [now]
            tmp = argv[2] + ".tmp"
            with open(tmp, "w", encoding="utf-8") as fh:
                fh.write("\n".join(f"{t:.0f}" for t in stamps) + "\n")
            os.replace(tmp, argv[2])
            print("recorded")
            return 0
    except (ValueError, OSError):
        print("error")
        return 1
    print("usage: attempt_limit.py check <datei> <max> <window_s> <gap_s> | record <datei> <window_s>", file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
