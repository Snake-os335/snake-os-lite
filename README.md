# Snake OS Lite

Mini escritorio web con **Doganiero Search**. Login obligatorio con cuentas existentes `@dogaemail.com` (misma base que Snake OS VP, montada en solo lectura).

## Local

```bash
cp .env.example .env   # TUNNEL_TOKEN opcional
docker compose up -d --build
# http://127.0.0.1:8990
```

## Dominio público

Hostname previsto: `snake-os-lite.softportweb.com`

1. Crear túnel Cloudflare y poner `TUNNEL_TOKEN=...` en `.env`
2. `docker compose up -d`

## GitHub

Repo previsto: `Snake-os335/snake-os-lite` (hay que crear el repo vacío en GitHub y luego `git push -u origin main`).
