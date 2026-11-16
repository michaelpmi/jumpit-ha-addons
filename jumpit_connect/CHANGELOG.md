# Änderungen

## 0.1.8

- Ist Ihr Zugang beendet (Laufzeit abgelaufen, gekündigt oder durch einen neuen Code ersetzt), sagt die App
  das jetzt klar: im Protokoll und als Benachrichtigung in Home Assistant, mit der Anleitung, wie Sie Ihre
  Adresse nach einer Verlängerung zurückbekommen. Das gilt auch, wenn die App nach dem Ende neu startet.
  Vorher erschien dort die irreführende Meldung „Kein Handshake, UDP blockiert?“.

## 0.1.7

- Testzugang: Ist die Testzeit abgelaufen, erscheint eine klare Meldung im Protokoll und
  als Benachrichtigung in Home Assistant. Der Zugang startet nach der Freischaltung im
  JumpIT-Kundenbereich von selbst wieder, mit derselben Adresse und ohne neuen Code.

## 0.1.6

- Zertifikat: Schlägt die automatische Erneuerung beim Start fehl, startet der
  Fernzugriff trotzdem mit dem noch gültigen Zertifikat. In den letzten 30 Tagen
  wird die Erneuerung stündlich versucht (vorher alle 12 Stunden).
- Behoben: Die Restlaufzeit des Zertifikats wurde falsch berechnet. Das Add-on hat
  dadurch bei jedem Start unnötig eine Erneuerung angestoßen und zeigte falsche Tage an.
- Die Erneuerung wartet nicht mehr bis zu vier Minuten.

## 0.1.5

- Neu: Ihre Adresse und der Verbindungsstatus erscheinen in Home Assistant als
  Entitäten (`sensor.jumpit_connect_adresse`, `binary_sensor.jumpit_connect_verbunden`).
- Neu: Updates laufen ohne Neuinstallation und ohne neuen Aktivierungscode. Die
  automatische Proxy-Freigabe ist auf höchstens drei Versuche pro Tag begrenzt und
  prüft sich nach Updates und alle 12 Stunden selbst.
- Die Bestätigung der Proxy-Freigabe wird bei einem noch startenden Home Assistant
  wiederholt, bis sie angenommen ist.

## 0.1.3

- Home Assistant 2026.8 und neuer: Die Proxy-Freigabe läuft über die offizielle
  Schnittstelle von Home Assistant (Einstellungen → System → Netzwerk). Das Add-on
  braucht keinen Schreibzugriff mehr auf die Home-Assistant-Konfiguration.

## 0.1.1

- Behoben: Das Add-on startete nicht („Unable to access the API, forbidden“).
- JumpIT-Signet als Add-on-Symbol.
