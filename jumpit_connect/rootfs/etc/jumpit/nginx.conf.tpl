worker_processes 1;
pid /tmp/jumpit-nginx.pid;
error_log /proc/1/fd/2 warn;

events { worker_connections 512; }

http {
    access_log off;
    client_body_temp_path /tmp/nginx-body;
    proxy_temp_path /tmp/nginx-proxy;

    map $http_upgrade $connection_upgrade {
        default upgrade;
        ''      close;
    }

    server {
        # Nur auf der Tunnel-IP – im LAN ist nichts zusätzlich offen.
        # Die Edge (llamp) reicht TLS per SNI-Passthrough durch und
        # stellt PROXY-Protocol v1 voran (echte Client-IP).
        listen __TUNNEL_IP__:443 ssl proxy_protocol;
        http2 on;
        server_name __FQDN__;

        ssl_certificate     __CRT__;
        ssl_certificate_key __KEY__;
        ssl_protocols TLSv1.2 TLSv1.3;
        ssl_session_cache shared:jc:5m;

        set_real_ip_from __SERVER_IP__;
        real_ip_header proxy_protocol;

        client_max_body_size 0;

        location / {
            proxy_pass __UPSTREAM__;
            proxy_ssl_verify off;
            proxy_http_version 1.1;
            proxy_set_header Host $host;
            proxy_set_header X-Forwarded-For $remote_addr;
            proxy_set_header X-Forwarded-Proto https;
            proxy_set_header Upgrade $http_upgrade;
            proxy_set_header Connection $connection_upgrade;
            proxy_read_timeout 3600s;
            proxy_send_timeout 3600s;
            proxy_buffering off;
        }
    }
}
