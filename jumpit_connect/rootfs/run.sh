#!/usr/bin/with-contenv bashio
# shellcheck shell=bash
# JumpIT Connect – Home-Assistant-Add-on
# Baut einen ausgehenden WireGuard-Tunnel zur JumpIT-Edge auf und
# terminiert TLS lokal (Ende-zu-Ende: die Edge sieht nur verschlüsselten Verkehr).
set -o pipefail

readonly VERSION="0.1.3"
readonly DATA=/data
readonly KEY="${DATA}/wg.key"
readonly PSK="${DATA}/wg.psk"
readonly STATE="${DATA}/state.json"
readonly LEGO_PATH="${DATA}/lego"
readonly IFACE="wg-jumpit"
readonly NGINX_TPL=/etc/jumpit/nginx.conf.tpl
readonly NGINX_CONF=/tmp/jumpit-nginx.conf
readonly NGINX_PID=/tmp/jumpit-nginx.pid

API_URL="$(bashio::config 'api_url')"
API_URL="${API_URL%/}"
PROXY_DONE="${DATA}/ha_proxy_attempted"

# Upstream: Standard ist die Adresse, die der Supervisor für Home Assistant meldet
# (Port/SSL werden automatisch erkannt). Die Option ha_upstream überschreibt das.
detect_upstream() {
    local scheme=http port
    if bashio::config.has_value 'ha_upstream'; then
        bashio::config 'ha_upstream'
        return
    fi
    if [[ "$(bashio::core.ssl 2>/dev/null || true)" == "true" ]]; then scheme=https; fi
    port="$(bashio::core.port 2>/dev/null || true)"
    if ! [[ "$port" =~ ^[0-9]+$ ]]; then
        # Supervisor gibt den Port nicht her: den Port nehmen, auf dem HA antwortet
        port=8123
        for p in 8123 80; do
            if [[ "$(curl -s -m 3 -o /dev/null -w '%{http_code}' "${scheme}://127.0.0.1:${p}/manifest.json" 2>/dev/null || true)" =~ ^[1-5][0-9][0-9]$ ]]; then
                port="$p"
                break
            fi
        done
    fi
    echo "${scheme}://127.0.0.1:${port}"
}
UPSTREAM="$(detect_upstream)"
UPSTREAM="${UPSTREAM%/}"

umask 077

# ---------------------------------------------------------------- helpers
st() { jq -r --arg k "$1" '.[$k] // empty' "$STATE"; }

normalize_code() {
    # Großbuchstaben, ohne Bindestriche/Leerzeichen
    tr '[:lower:]' '[:upper:]' <<<"$1" | tr -d ' -'
}

code_fingerprint() {
    printf '%s' "$(normalize_code "$1")" | sha256sum | cut -d' ' -f1
}

teardown() {
    if [[ -f "$NGINX_PID" ]]; then
        nginx -c "$NGINX_CONF" -s quit 2>/dev/null || true
    fi
    ip link del "$IFACE" 2>/dev/null || true
}

on_exit() {
    bashio::log.info "Beende JumpIT Connect …"
    teardown
}
trap on_exit EXIT
trap 'exit 0' TERM INT

# ---------------------------------------------------------------- aktivierung
ensure_key() {
    if [[ ! -s "$KEY" ]]; then
        bashio::log.info "Erzeuge WireGuard-Schlüssel (verlässt das Gerät nie)."
        wg genkey >"$KEY"
    fi
}

activate() {
    local code="$1" pub payload resp http
    pub="$(wg pubkey <"$KEY")"
    payload="$(jq -nc --arg c "$code" --arg k "$pub" --arg v "$VERSION" \
        '{activation_code:$c, public_key:$k, addon_version:$v}')"

    bashio::log.info "Aktiviere bei ${API_URL} …"
    resp="$(curl -sS -m 30 -w '\n%{http_code}' -H 'Content-Type: application/json' \
        -d "$payload" "${API_URL}/api/v1/activate")" || {
        bashio::log.error "JumpIT-API nicht erreichbar."
        return 1
    }
    http="${resp##*$'\n'}"
    resp="${resp%$'\n'*}"
    if [[ "$http" != "200" ]]; then
        bashio::log.error "Aktivierung abgelehnt (HTTP ${http}): $(jq -r '.detail // .' <<<"$resp" 2>/dev/null)"
        return 1
    fi

    # Pflichtfelder prüfen, bevor irgendetwas gespeichert wird
    if ! jq -e '.fqdn and .address and .server_public_key and .endpoint
                and .allowed_ips and .preshared_key and .device_token
                and .server_tunnel_ip' >/dev/null <<<"$resp"; then
        bashio::log.error "Unvollständige Antwort der API."
        return 1
    fi

    jq --arg fp "$(code_fingerprint "$code")" '. + {code_fingerprint:$fp}' \
        <<<"$resp" >"${STATE}.tmp" && mv "${STATE}.tmp" "$STATE"
    jq -r '.preshared_key' "$STATE" >"$PSK"
    bashio::log.info "Aktiviert: https://$(st fqdn)"
}

validate_state() {
    [[ "$(st fqdn)" =~ ^[a-z0-9-]+(\.[a-z0-9-]+)+$ ]] || return 1
    [[ "$(st address)" =~ ^10\.[0-9]{1,3}\.[0-9]{1,3}\.[0-9]{1,3}/32$ ]] || return 1
    [[ "$(st server_tunnel_ip)" =~ ^10\.[0-9]{1,3}\.[0-9]{1,3}\.[0-9]{1,3}$ ]] || return 1
    [[ "$(st endpoint)" =~ ^[A-Za-z0-9.-]+:[0-9]{2,5}$ ]] || return 1
    [[ "$(st allowed_ips)" =~ ^[0-9./,]+$ ]] || return 1
    return 0
}

# ---------------------------------------------------------------- tunnel
tunnel_up() {
    local allowed net
    allowed="$(st allowed_ips)"
    ip link del "$IFACE" 2>/dev/null || true
    ip link add "$IFACE" type wireguard
    wg set "$IFACE" private-key "$KEY" \
        peer "$(st server_public_key)" \
        preshared-key "$PSK" \
        endpoint "$(st endpoint)" \
        allowed-ips "$allowed" \
        persistent-keepalive 25
    ip address add "$(st address)" dev "$IFACE"
    ip link set "$IFACE" mtu 1380 up
    # Split-Tunnel: nur das Edge-Netz geht durch den Tunnel
    for net in ${allowed//,/ }; do
        ip route replace "$net" dev "$IFACE"
    done
}

handshake_age() {
    local hs
    hs="$(wg show "$IFACE" latest-handshakes 2>/dev/null | awk 'NR==1{print $2}')"
    if [[ -z "$hs" || "$hs" == "0" ]]; then
        echo 999999
    else
        echo $(($(date +%s) - hs))
    fi
}

wait_handshake() {
    local i
    for i in $(seq 1 30); do
        if (($(handshake_age) < 180)); then
            bashio::log.info "Tunnel steht (Handshake nach ~$((i * 2)) s)."
            return 0
        fi
        sleep 2
    done
    return 1
}

# ---------------------------------------------------------------- zertifikat
lego_env() {
    export HTTPREQ_ENDPOINT="${API_URL}/api/v1/acme"
    HTTPREQ_USERNAME="$(st fqdn)"
    HTTPREQ_PASSWORD="$(st device_token)"
    export HTTPREQ_USERNAME HTTPREQ_PASSWORD
    export HTTPREQ_PROPAGATION_TIMEOUT=300
    export HTTPREQ_POLLING_INTERVAL=10
}

cert_file() { echo "${LEGO_PATH}/certificates/$(st fqdn).crt"; }
key_file() { echo "${LEGO_PATH}/certificates/$(st fqdn).key"; }

cert_days_left() {
    local end
    [[ -s "$(cert_file)" ]] || {
        echo -1
        return
    }
    end="$(openssl x509 -enddate -noout -in "$(cert_file)" | cut -d= -f2)"
    echo $((($(date -d "$end" +%s 2>/dev/null || echo 0) - $(date +%s)) / 86400))
}

obtain_or_renew_cert() {
    local email args=()
    email="$(st acme_email)"
    if [[ -n "$email" ]]; then args+=(--email "$email"); fi
    lego_env
    if [[ -s "$(cert_file)" ]]; then
        (($(cert_days_left) > 30)) && return 0
        bashio::log.info "Erneuere Zertifikat …"
        lego "${args[@]}" --accept-tos --dns httpreq --domains "$(st fqdn)" \
            --path "$LEGO_PATH" renew --days 30 || return 1
        return 2 # erneuert -> nginx reload
    fi
    bashio::log.info "Hole Zertifikat für $(st fqdn) (DNS-01) …"
    lego "${args[@]}" --accept-tos --dns httpreq --domains "$(st fqdn)" \
        --path "$LEGO_PATH" run
}

# ---------------------------------------------------------------- nginx
nginx_render() {
    local tip
    tip="$(st address)"
    tip="${tip%/32}"
    sed -e "s|__TUNNEL_IP__|${tip}|g" \
        -e "s|__FQDN__|$(st fqdn)|g" \
        -e "s|__CRT__|$(cert_file)|g" \
        -e "s|__KEY__|$(key_file)|g" \
        -e "s|__SERVER_IP__|$(st server_tunnel_ip)|g" \
        -e "s|__UPSTREAM__|${UPSTREAM}|g" \
        "$NGINX_TPL" >"$NGINX_CONF"
    nginx -t -q -c "$NGINX_CONF"
}

nginx_start() {
    mkdir -p /tmp/nginx-body /tmp/nginx-proxy
    nginx -c "$NGINX_CONF"
}

selftest_code() {
    local tip
    tip="$(st address)"
    tip="${tip%/32}"
    curl -sk -m 10 --haproxy-protocol --resolve "$(st fqdn):443:${tip}" \
        -o /dev/null -w '%{http_code}' "https://$(st fqdn)/manifest.json" || true
}

selftest() {
    local code
    code="$(selftest_code)"
    case "$code" in
        200) bashio::log.info "Selbsttest OK – Home Assistant antwortet über den Tunnel." ;;
        400) bashio::log.info "Home Assistant verlangt die Freigabe des Proxys (HTTP 400)." ;;
        *) bashio::log.warning "Selbsttest: unerwartete Antwort (${code:-keine}). Läuft HA unter ${UPSTREAM}?" ;;
    esac
    echo "${code:-0}"
}

# ------------------------------------------------- HA-Proxy automatisch freigeben
sup() { # sup <METHOD> <pfad> [curl-args…]
    local m="$1" path="$2"
    shift 2
    curl -sS -m 180 -X "$m" -H "Authorization: Bearer ${SUPERVISOR_TOKEN}" \
        -H 'Content-Type: application/json' "$@" "http://supervisor${path}"
}

ha_notify() { # ha_notify <titel> <text>
    sup POST /core/api/services/persistent_notification/create -o /dev/null \
        -d "$(jq -nc --arg t "$1" --arg m "$2" '{title:$t,message:$m,notification_id:"jumpit_connect"}')" || true
}

ha_manual_hint() {
    bashio::log.warning "Die Freigabe konnte nicht automatisch erfolgen: $1"
    bashio::log.warning "Bitte in Home Assistant unter Einstellungen > System > Netzwerk > HTTP-Server"
    bashio::log.warning "\"X-Forwarded-For vertrauen\" aktivieren und als vertrauenswürdige Proxys eintragen: ${PROXIES[*]}"
    ha_notify "JumpIT Connect: Einrichtung nicht abgeschlossen" \
        "Der Fernzugriff ist verbunden, Home Assistant braucht aber noch eine Freigabe. Bitte wenden Sie sich an den JumpIT-Support. Grund: $1"
}

# Vertrauenswürdige Proxy-Adressen: Add-on läuft im Host-Netz, HA sieht 127.0.0.1
# (oder die LAN-Adresse, falls ha_upstream darauf zeigt).
PROXIES=(127.0.0.1 ::1)
_host="${UPSTREAM#*://}"
_host="${_host%%[:/]*}"
if [[ "$_host" =~ ^[0-9]+\.[0-9]+\.[0-9]+\.[0-9]+$ && "$_host" != "127.0.0.1" ]]; then PROXIES+=("$_host"); fi

# Rückgabe 0 = freigegeben, 1 = manuell nötig.
# Home Assistant >= 2026.8 verwaltet die HTTP-Einstellungen nicht mehr in der
# configuration.yaml, sondern über seine WebSocket-API. Die Änderung gilt zuerst als
# "pending" (Core startet neu) und wird nur bei bestandenem Test bestätigt – sonst
# setzt Home Assistant sie nach ca. 5 Minuten selbst zurück.
ha_proxy_setup() {
    local res rc=0 i code=""
    if [[ -f "$PROXY_DONE" ]]; then
        ha_manual_hint "automatische Freigabe wurde bereits einmal versucht"
        return 1
    fi
    if ! bashio::config.true 'auto_configure_ha'; then
        ha_manual_hint "automatische Einrichtung ist in den Add-on-Optionen deaktiviert"
        return 1
    fi

    res="$(python3 /usr/local/bin/ha_http_config.py configure "${PROXIES[@]}")" || rc=$?
    case "$rc:$res" in
        0:restart) bashio::log.info "Proxy-Freigabe an Home Assistant übergeben – Home Assistant startet einmalig neu …" ;;
        0:pending) bashio::log.info "Proxy-Freigabe wartet auf Bestätigung – prüfe …" ;;
        4:*) ha_manual_hint "Home Assistant ist älter als 2026.8 (bitte aktualisieren)"; return 1 ;;
        3:*) ha_manual_hint "die Freigabe steht schon in der Konfiguration, Home Assistant lehnt sie trotzdem ab"; return 1 ;;
        *) ha_manual_hint "Home Assistant hat die Änderung nicht angenommen (${res:-keine Antwort})"; return 1 ;;
    esac
    touch "$PROXY_DONE"

    sleep 20
    for i in $(seq 1 60); do
        code="$(selftest_code)"
        [[ "$code" == "200" ]] && break
        sleep 5
    done
    if [[ "$code" != "200" ]]; then
        ha_manual_hint "Home Assistant antwortet nach dem Neustart nicht wie erwartet (HTTP ${code:-keine}); die Änderung wird automatisch zurückgenommen"
        return 1
    fi

    res="$(python3 /usr/local/bin/ha_http_config.py promote)" || rc=$?
    if [[ "$res" != "promoted" ]]; then
        ha_manual_hint "Bestätigung bei Home Assistant fehlgeschlagen (${res:-keine Antwort})"
        return 1
    fi
    bashio::log.info "Home Assistant akzeptiert den Proxy – Einstellung bestätigt."
    ha_notify "JumpIT Connect eingerichtet" \
        "Der Fernzugriff ist aktiv: https://$(st fqdn). Home Assistant wurde dafür einmalig neu gestartet."
    return 0
}

# ---------------------------------------------------------------- heartbeat
heartbeat() {
    local payload http
    payload="$(jq -nc --argjson h "$(handshake_age)" --argjson c "$(cert_days_left)" \
        --arg v "$VERSION" --arg s "${LAST_SELFTEST:-0}" \
        '{handshake_age:$h, cert_days_left:$c, addon_version:$v, selftest:$s}')"
    http="$(curl -sS -m 20 -o /dev/null -w '%{http_code}' \
        -H "Authorization: Bearer $(st device_token)" -H 'Content-Type: application/json' \
        -d "$payload" "${API_URL}/api/v1/heartbeat" 2>/dev/null || echo 000)"
    echo "$http"
}

# ================================================================= main
bashio::log.info "JumpIT Connect ${VERSION} startet."
ensure_key

CODE="$(bashio::config 'activation_code')"
NEED_ACTIVATION=false
if [[ ! -s "$STATE" ]]; then
    NEED_ACTIVATION=true
elif [[ -n "$CODE" && "$(code_fingerprint "$CODE")" != "$(st code_fingerprint)" ]]; then
    bashio::log.info "Neuer Aktivierungscode erkannt – aktiviere neu."
    NEED_ACTIVATION=true
fi

if [[ "$NEED_ACTIVATION" == true ]]; then
    if [[ -z "$CODE" ]]; then
        bashio::exit.nok "Bitte den Aktivierungscode aus der JumpIT-Bestellung in der Konfiguration eintragen."
    fi
    activate "$CODE" || bashio::exit.nok "Aktivierung fehlgeschlagen."
fi

validate_state || bashio::exit.nok "Gespeicherte Konfiguration ist ungültig – bitte neuen Aktivierungscode anfordern."

tunnel_up
wait_handshake || bashio::exit.nok "Kein WireGuard-Handshake mit der JumpIT-Edge (UDP $(st endpoint) blockiert?)."

# bashio läuft mit errexit – Rückgabecodes daher immer explizit abfangen
while true; do
    rc=0
    obtain_or_renew_cert || rc=$?
    ((rc == 0 || rc == 2)) && break
    bashio::log.warning "Zertifikat konnte nicht geholt werden – neuer Versuch in 10 min."
    sleep 600
done

nginx_render || bashio::exit.nok "nginx-Konfiguration ungültig."
nginx_start
LAST_SELFTEST="$(selftest | tail -n1)"
if [[ "$LAST_SELFTEST" == "400" ]]; then
    rc=0
    ha_proxy_setup || rc=$?
    ((rc == 0)) && LAST_SELFTEST="200"
fi

bashio::log.info "Fernzugriff aktiv: https://$(st fqdn)"

tick=0
while true; do
    sleep 60
    tick=$((tick + 1))

    # Tunnel-Wächter
    if (($(handshake_age) > 300)); then
        bashio::log.warning "Kein Handshake seit >5 min – baue Tunnel neu auf."
        tunnel_up
    fi

    # Heartbeat alle 5 min
    if ((tick % 5 == 0)); then
        case "$(heartbeat)" in
            410)
                bashio::log.error "Dienst wurde gekündigt – Fernzugriff beendet."
                teardown
                rm -f "$STATE" "$PSK"
                bashio::exit.nok "Gekündigt."
                ;;
            403)
                bashio::log.warning "Dienst gesperrt – Fernzugriff pausiert."
                teardown
                until [[ "$(heartbeat)" == "200" ]]; do sleep 600; done
                bashio::log.info "Dienst wieder freigeschaltet."
                tunnel_up
                wait_handshake || true
                nginx_start
                ;;
        esac
    fi

    # Zertifikat alle 12 h prüfen
    if ((tick % 720 == 0)); then
        rc=0
        obtain_or_renew_cert || rc=$?
        if ((rc == 2)); then
            nginx -c "$NGINX_CONF" -s reload && bashio::log.info "Zertifikat erneuert."
        fi
        LAST_SELFTEST="$(selftest | tail -n1)"
    fi
done
