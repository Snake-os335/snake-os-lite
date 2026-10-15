# Snake OS Lite

Mini escritorio web 🐍 con búsqueda, terminal, código y **Snakemoji** (~5000 emojis Snake OS; tecla **S**).

Login con cuentas existentes `@dogaemail.com` (misma base que Snake OS VP, solo lectura).

## Local

```bash
cp .env.example .env
docker compose up -d --build
# http://127.0.0.1:8990
```

## Público

https://snake-os-lite.softportweb.com/

## Nota

Los SVG de Snakemoji viven en `static/assets/snk-emoji-*.svg`. El logo de Doganiero Search **no** se usa aquí (solo en snake-os-vp).
