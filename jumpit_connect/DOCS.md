# JumpIT Connect

Sicherer Fernzugriff auf Ihr Home Assistant – ohne Portfreigabe, auch hinter
Starlink oder CGNAT. Die Verbindung ist Ende-zu-Ende verschlüsselt: JumpIT
leitet nur verschlüsselten Verkehr weiter und kann nicht mitlesen.

## Einrichtung

1. Aktivierungscode aus Ihrer JumpIT-Bestellung in der Konfiguration bei
   **Aktivierungscode** eintragen und speichern.
2. Add-on starten. Im Protokoll erscheint nach ca. einer Minute
   „Fernzugriff aktiv: https://….ha.jumpit.eu“.
3. Falls das Protokoll darum bittet: in `configuration.yaml` ergänzen und
   Home Assistant neu starten:

   ```yaml
   http:
     use_x_forwarded_for: true
     trusted_proxies:
       - 127.0.0.1
       - ::1
   ```

4. In der Home-Assistant-App unter **Einstellungen → Companion-App →
   Server** die angezeigte Adresse als externe URL eintragen.

## Neues Gerät / neu installiert

Im JumpIT-Kundenportal einen neuen Aktivierungscode anfordern und eintragen.
Der alte Zugang wird dabei automatisch deaktiviert.

## Sicherheit

- Aktivieren Sie die Zwei-Faktor-Authentifizierung in Ihrem HA-Benutzerprofil.
- Der private WireGuard-Schlüssel und das TLS-Zertifikat werden nur auf Ihrem
  Gerät erzeugt bzw. gespeichert.
