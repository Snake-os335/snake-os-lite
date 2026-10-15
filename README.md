# Snake OS Lite

Mini escritorio web con **Doganiero Search**, Terminal y editor de Código (JS/Python aislado).

- Inicio local: `docker compose up -d --build web` → http://127.0.0.1:8990
- Dominio previsto: `snake-os-lite.softportweb.com` (túnel Cloudflare; ver `.env.example`)
- Sin cuentas ni cookies de usuario. El proxy de páginas no reenvía cookies y tiene protección SSRF.
- Cursor: puntero del sistema (sin cursor personalizado de Snake OS).

## Cloudflare

1. Zero Trust → Networks → Tunnels → Create a tunnel.
2. Public hostname: `snake-os-lite.softportweb.com` → service `http://web:8000`.
3. Copia el token en `.env` como `TUNNEL_TOKEN=...` (no lo subas a git).
4. `docker compose up -d`.
