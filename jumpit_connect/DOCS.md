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
   Add-on gibt den Proxy über die offizielle Home-Assistant-Schnittstelle frei
   (Einstellungen → System → Netzwerk → HTTP-Server) und Home Assistant startet
   **einmalig** neu. Die Änderung gilt erst, wenn der Fernzugriff getestet
   wurde. Sonst setzt Home Assistant sie nach etwa 5 Minuten selbst zurück. Sie
   müssen nichts bearbeiten. Lässt sich die Freigabe nicht automatisch setzen,
   erscheint eine Benachrichtigung in Home Assistant, und der JumpIT-Support
   hilft.
4. In der Home-Assistant-App unter **Einstellungen → Companion-App →
   Server** die angezeigte Adresse als externe URL eintragen.

Voraussetzung: Home Assistant ab Version 2026.8.

## Optionen

- **auto_configure_ha** (Standard: an): Proxy-Freigabe in Home Assistant
  automatisch einrichten. Ausschalten, wenn Sie die HTTP-Einstellungen selbst
  verwalten.
- **ha_upstream** (optional): Adresse von Home Assistant. Normalerweise nicht
  nötig, Port und SSL werden automatisch erkannt.

## Neues Gerät / neu installiert

Im JumpIT-Kundenportal einen neuen Aktivierungscode anfordern und eintragen.
Der alte Zugang wird dabei automatisch deaktiviert.

## Sicherheit

- Aktivieren Sie die Zwei-Faktor-Authentifizierung in Ihrem HA-Benutzerprofil.
- Der private WireGuard-Schlüssel und das TLS-Zertifikat werden nur auf Ihrem
  Gerät erzeugt bzw. gespeichert.
