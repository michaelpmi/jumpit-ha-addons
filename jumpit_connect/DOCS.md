# JumpIT Connect

Sicherer Fernzugriff auf Ihr Home Assistant – ohne Portfreigabe, auch hinter
Starlink oder CGNAT. Die Verbindung ist Ende-zu-Ende verschlüsselt: JumpIT
leitet nur verschlüsselten Verkehr weiter und kann nicht mitlesen.

## Einrichtung

1. Aktivierungscode aus Ihrer JumpIT-Bestellung in der Konfiguration bei
   **Aktivierungscode** eintragen und speichern.
2. Add-on starten. Im Protokoll erscheint nach ca. einer Minute
   „Fernzugriff aktiv: https://….ha.jumpit.eu“.
3. Home Assistant wird dabei automatisch für den Fernzugriff vorbereitet: Das
   Add-on ergänzt die `configuration.yaml` um die Proxy-Freigabe, prüft die
   Konfiguration und startet Home Assistant **einmalig** neu. Eine Sicherung
   liegt als `configuration.yaml.jumpit-backup` daneben. Sie müssen nichts
   bearbeiten. Lässt sich die Datei nicht automatisch ändern, erscheint eine
   Benachrichtigung in Home Assistant, und der JumpIT-Support hilft.
4. In der Home-Assistant-App unter **Einstellungen → Companion-App →
   Server** die angezeigte Adresse als externe URL eintragen.

## Optionen

- **auto_configure_ha** (Standard: an): Proxy-Freigabe in Home Assistant
  automatisch einrichten. Ausschalten, wenn Sie die `configuration.yaml`
  selbst verwalten.
- **ha_upstream** (optional): Adresse von Home Assistant. Normalerweise nicht
  nötig, Port und SSL werden automatisch erkannt.

## Neues Gerät / neu installiert

Im JumpIT-Kundenportal einen neuen Aktivierungscode anfordern und eintragen.
Der alte Zugang wird dabei automatisch deaktiviert.

## Sicherheit

- Aktivieren Sie die Zwei-Faktor-Authentifizierung in Ihrem HA-Benutzerprofil.
- Der private WireGuard-Schlüssel und das TLS-Zertifikat werden nur auf Ihrem
  Gerät erzeugt bzw. gespeichert.
