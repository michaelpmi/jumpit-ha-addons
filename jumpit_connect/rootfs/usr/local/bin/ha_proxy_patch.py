#!/usr/bin/env python3
"""Ergänzt den http:-Block der Home-Assistant-configuration.yaml um den Reverse-Proxy.

Rein textbasiert (nur Standardbibliothek), damit Kommentare, !include und !secret
des Kunden unverändert bleiben. Es wird nur das Nötigste eingefügt:

    http:
      use_x_forwarded_for: true
      trusted_proxies:
        - 127.0.0.1

Aufruf:  ha_proxy_patch.py <configuration.yaml> <proxy> [<proxy> ...]
Exit:    0 = Datei geändert, 3 = war schon korrekt, 4 = nicht automatisch änderbar
         (z. B. http: !include …, Flow-Schreibweise), 1 = Fehler.
Ausgabe: eine Zeile mit dem Ergebnis (changed|unchanged|manual:<Grund>).
"""
import os
import re
import sys

TOP_KEY = re.compile(r"^([A-Za-z0-9_\-\"']+)\s*:(.*)$")
HTTP_KEY = re.compile(r"^http\s*:\s*(#.*)?$")


class Manual(Exception):
    pass


def _ignorable(line: str) -> bool:
    s = line.strip()
    return s == "" or s.startswith("#")


def _indent(line: str) -> int:
    return len(line) - len(line.lstrip(" "))


def _find_key(body: list[str], child: int, key: str):
    found = None
    for k, line in enumerate(body):
        if not _ignorable(line) and _indent(line) == child and re.match(rf"{key}\s*:", line.strip()):
            found = k
    return found


def patch(text: str, proxies: list[str]) -> tuple[str, bool]:
    lines = text.splitlines()
    nl = "\n"

    start = None
    for i, line in enumerate(lines):
        if line.startswith((" ", "\t")) or _ignorable(line):
            continue
        m = TOP_KEY.match(line)
        if m and m.group(1).strip("\"'") == "http":
            if start is not None:
                raise Manual("http: kommt mehrfach vor")
            if not HTTP_KEY.match(line):
                raise Manual("http: nutzt !include oder Flow-Schreibweise")
            start = i

    if start is None:
        block = ["", "# Von JumpIT Connect ergänzt (Reverse-Proxy für den Fernzugriff)",
                 "http:", "  use_x_forwarded_for: true", "  trusted_proxies:"]
        block += [f"    - {p}" for p in proxies]
        return nl.join(lines + block) + nl, True

    end = len(lines)
    for j in range(start + 1, len(lines)):
        if lines[j].startswith((" ", "\t")) or _ignorable(lines[j]):
            continue
        end = j
        break
    while end > start + 1 and _ignorable(lines[end - 1]) and _indent(lines[end - 1]) == 0:
        end -= 1

    body = lines[start + 1:end]
    if any(l.startswith("\t") or "\t" in l[:_indent(l) + 1] for l in body if not _ignorable(l)):
        raise Manual("Tabs im http-Block")
    child = next((_indent(l) for l in body if not _ignorable(l)), 2)
    pad = " " * child
    changed = False

    idx = _find_key(body, child, "use_x_forwarded_for")
    if idx is None:
        body.insert(0, f"{pad}use_x_forwarded_for: true")
        changed = True
    else:
        val = body[idx].split(":", 1)[1].split("#", 1)[0].strip().lower()
        if val not in ("true", "yes", "on"):
            body[idx] = f"{pad}use_x_forwarded_for: true"
            changed = True

    idx = _find_key(body, child, "trusted_proxies")
    if idx is None:
        body += [f"{pad}trusted_proxies:"] + [f"{pad}  - {p}" for p in proxies]
        changed = True
    else:
        rest = body[idx].split(":", 1)[1].split("#", 1)[0].strip()
        if rest:
            raise Manual("trusted_proxies in Flow-Schreibweise oder !include")
        k, last, item_indent, existing = idx + 1, idx, None, []
        while k < len(body):
            line = body[k]
            if _ignorable(line):
                k += 1
                continue
            if _indent(line) < child or (_indent(line) == child and not line.strip().startswith("-")):
                break
            if not line.strip().startswith("-"):
                raise Manual("trusted_proxies hat unerwartete Struktur")
            if item_indent is None:
                item_indent = _indent(line)
            existing.append(line.strip()[1:].split("#", 1)[0].strip().strip("\"'"))
            last = k
            k += 1
        if item_indent is None:
            item_indent = child + 2
        missing = [p for p in proxies if p not in existing]
        if missing:
            body[last + 1:last + 1] = [" " * item_indent + f"- {p}" for p in missing]
            changed = True

    if not changed:
        return text, False
    return nl.join(lines[:start + 1] + body + lines[end:]) + nl, True


def main(argv: list[str]) -> int:
    if len(argv) < 3:
        print("usage: ha_proxy_patch.py <configuration.yaml> <proxy>...", file=sys.stderr)
        return 1
    path, proxies = argv[1], argv[2:]
    with open(path, encoding="utf-8") as fh:
        text = fh.read()
    try:
        new, changed = patch(text, proxies)
    except Manual as e:
        print(f"manual:{e}")
        return 4
    if not changed:
        print("unchanged")
        return 3
    tmp = path + ".jumpit-tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        fh.write(new)
    os.replace(tmp, path)
    print("changed")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
