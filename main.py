"""Snake OS Lite — mini escritorio web con Doganiero Search (sin cuentas)."""
from __future__ import annotations
import base64, hashlib, hmac, html as _html, ipaddress, json, os, re, secrets, socket, time, threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, quote, unquote, urlencode, urljoin, urlparse
from urllib.request import HTTPHandler, HTTPSHandler, HTTPRedirectHandler, Request as _UReq, build_opener

from fastapi import FastAPI, Query, Request
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

FETCH_TIMEOUT = 10
MAX_PAGE_BYTES = 2 * 1024 * 1024
PROXY_TOKEN_TTL = 3 * 3600
PROXY_PER_MIN = 60
_PROXY_SECRET = secrets.token_bytes(32)
_proxy_rate: dict[str, list[float]] = {}
_proxy_cache: dict[str, tuple[float, str, str]] = {}
_serp_cache: dict[tuple[str, int], tuple[float, list[dict[str, str]]]] = {}
_SERP_UA = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
PROXY_CSP = "sandbox allow-scripts allow-forms; frame-ancestors 'self'"
ROOT = Path(__file__).resolve().parent

class UrlBlocked(Exception):
    pass

class _SafeRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        _check_host(newurl)
        return super().redirect_request(req, fp, code, msg, headers, newurl)

_opener = build_opener(HTTPHandler, HTTPSHandler, _SafeRedirect)
_opener.addheaders = []

def _check_host(url: str) -> None:
    p = urlparse(url)
    if p.scheme not in ("http", "https") or not p.hostname:
        raise UrlBlocked("URL no válida")
    host = p.hostname.lower()
    if host in ("localhost",) or host.endswith((".local", ".internal", ".localhost")):
        raise UrlBlocked("Host no permitido")
    port = p.port or (443 if p.scheme == "https" else 80)
    if port not in (80, 443, 8080, 8443):
        raise UrlBlocked("Puerto no permitido")
    last = None
    for _ in range(3):
        try:
            infos = socket.getaddrinfo(host, port)
            break
        except OSError as e:
            last = e
            time.sleep(0.25)
    else:
        raise UrlBlocked("No se pudo resolver el dominio") from last
    for info in infos:
        ip = ipaddress.ip_address(info[4][0])
        if not ip.is_global:
            raise UrlBlocked("IP no pública")

def proxy_token(sid: str) -> str:
    exp = int(time.time()) + PROXY_TOKEN_TTL
    msg = f"{sid}.{exp}"
    sig = hmac.new(_PROXY_SECRET, msg.encode(), hashlib.sha256).hexdigest()[:32]
    return f"{msg}.{sig}"

def _proxy_sid(tok: str) -> str | None:
    try:
        sid, exp, sig = tok.split(".")
        good = hmac.new(_PROXY_SECRET, f"{sid}.{exp}".encode(), hashlib.sha256).hexdigest()[:32]
        if hmac.compare_digest(good, sig) and int(exp) > time.time():
            return sid
    except Exception:
        pass
    return None

def _rl(sid: str) -> bool:
    now = time.monotonic()
    calls = [x for x in _proxy_rate.get(sid, []) if x > now - 60]
    if len(calls) >= PROXY_PER_MIN:
        return False
    calls.append(now)
    _proxy_rate[sid] = calls
    return True

def _get(url: str, data: bytes | None = None) -> str:
    req = _UReq(url, data=data, headers={"User-Agent": _SERP_UA, "Accept-Language": "es-ES,es;q=0.9,en;q=0.6"})
    with _opener.open(req, timeout=FETCH_TIMEOUT) as resp:
        return resp.read(MAX_PAGE_BYTES).decode("utf-8", "replace")

def _txt(h: str) -> str:
    return _html.unescape(re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", h or ""))).strip()

def _ddg(q: str, page: int) -> list[dict[str, str]]:
    form = {"q": q, "kl": "es-es"}
    if page > 1:
        form.update({"s": str((page - 1) * 10), "dc": str((page - 1) * 10 + 1), "v": "l", "o": "json", "api": "d.js"})
    try:
        h = _get("https://html.duckduckgo.com/html/", urlencode(form).encode())
    except Exception:
        return []
    out = []
    for blk in re.split(r'<div class="result results_links', h)[1:]:
        if "result--ad" in blk[:200]:
            continue
        m = re.search(r'class="result__a" href="([^"]+)"[^>]*>(.*?)</a>', blk, re.S)
        if not m:
            continue
        url = _html.unescape(m.group(1))
        if "duckduckgo.com/l/?" in url:
            url = unquote(parse_qs(urlparse(url).query).get("uddg", [""])[0])
        sn = re.search(r'class="result__snippet"[^>]*>(.*?)</a>', blk, re.S)
        out.append({"title": _txt(m.group(2)), "url": url, "snippet": _txt(sn.group(1)) if sn else ""})
    return out

_BING_MKTS = ["es-ES", "es-MX", "es-AR", "es-US", "es-CO", "es-CL", "en-US", "en-GB", "es-PE", "es-VE", "en-IE", "en-CA"]

def _bing_url(u: str) -> str:
    if "bing.com/ck/a" in u:
        v = parse_qs(urlparse(_html.unescape(u)).query).get("u", [""])[0]
        if v.startswith("a1"):
            try:
                return base64.urlsafe_b64decode(v[2:] + "=" * (-len(v[2:]) % 4)).decode("utf-8", "replace")
            except Exception:
                return ""
    return _html.unescape(u)

def _bing(q: str, page: int) -> list[dict[str, str]]:
    mkt = _BING_MKTS[(page - 1) % len(_BING_MKTS)]
    try:
        h = _get("https://www.bing.com/search?" + urlencode({"q": q, "setlang": mkt.split("-")[0], "mkt": mkt, "cc": mkt.split("-")[1]}))
    except Exception:
        return []
    out = []
    for blk in re.split(r'<li class="b_algo', h)[1:]:
        m = re.search(r'<h2[^>]*>\s*<a[^>]+href="([^"]+)"[^>]*>(.*?)</a>', blk, re.S)
        if not m:
            continue
        sn = re.search(r'<p[^>]*>(.*?)</p>', blk, re.S)
        out.append({"title": _txt(m.group(2)), "url": _bing_url(m.group(1)), "snippet": _txt(sn.group(1)) if sn else ""})
    return out

def web_index(q: str, page: int = 1) -> list[dict[str, str]]:
    q = q.strip()[:200]
    page = max(1, min(10, int(page or 1)))
    key = (q.lower(), page)
    hit = _serp_cache.get(key)
    if hit and hit[0] > time.time() - 300:
        return hit[1]
    lists = []
    with ThreadPoolExecutor(max_workers=3) as ex:
        futs = [ex.submit(fn, q, pg) for fn, pg in ((_ddg, page), (_bing, page), (_bing, page + 6))]
        for f in futs:
            try:
                lists.append(f.result(timeout=FETCH_TIMEOUT + 2))
            except Exception:
                lists.append([])
    res, seen = [], set()
    for i in range(max([len(x) for x in lists] + [0])):
        for lst in lists:
            if i >= len(lst):
                continue
            it = lst[i]
            u = it.get("url") or ""
            if not re.match(r"https?://", u):
                continue
            k = re.sub(r"^https?://(www\.)?", "", u).rstrip("/")
            if k in seen:
                continue
            seen.add(k)
            dom = urlparse(u).hostname or ""
            res.append({"title": (it.get("title") or "")[:160] or dom, "url": u[:600], "snippet": (it.get("snippet") or "")[:320],
                        "domain": dom, "favicon": f"https://external-content.duckduckgo.com/ip3/{dom}.ico"})
    if res:
        _serp_cache[key] = (time.time(), res)
    return res

def _origin(request: Request) -> str:
    proto = (request.headers.get("x-forwarded-proto") or request.url.scheme or "https").split(",")[0].strip()
    host = request.headers.get("host") or request.url.netloc
    return f"{proto}://{host}"

def _resp(html_text: str, status: int = 200) -> HTMLResponse:
    return HTMLResponse(html_text, status_code=status, headers={
        "Content-Security-Policy": PROXY_CSP, "X-Content-Type-Options": "nosniff",
        "Referrer-Policy": "no-referrer", "Cache-Control": "private, no-store",
    })

def _serp_html(origin: str, tok: str, q: str, page: int, res: list[dict[str, str]]) -> str:
    e = lambda x: _html.escape(str(x or ""), quote=True)
    cfg = json.dumps({"p": origin + "/api/proxy", "t": tok, "u": ("dsearch:" + q if q else "dsearch:"), "o": origin, "serp": True})
    items = "".join(
        f'<div class="r"><div class="s"><img src="{e(r["favicon"])}" referrerpolicy="no-referrer" loading="lazy" alt="">'
        f'<div><div class="d">{e(r["domain"])}</div><div class="u">{e(r["url"])}</div></div></div>'
        f'<a href="{e(r["url"])}">{e(r["title"])}</a><p>{e(r["snippet"])}</p></div>' for r in res)
    sq = quote(q)
    nav = "".join(f'<a data-serp class="{"on" if n == page else ""}" href="{origin}/api/serp?q={sq}&p={n}&t={e(tok)}">{n}</a>' for n in range(1, 6))
    nxt = f'<a data-serp href="{origin}/api/serp?q={sq}&p={page + 1}&t={e(tok)}">Siguiente ›</a>' if res and page < 10 else ""
    css = ("body{margin:0;font-family:arial,system-ui,sans-serif;color:#202124;background:#fff}"
           ".top{display:flex;align-items:center;gap:12px;padding:12px 16px;border-bottom:1px solid #ebebeb;position:sticky;top:0;background:#fff;z-index:2}"
           ".lg{font-weight:800;font-size:1.15rem;letter-spacing:-.5px;color:#ff8a00}.lg b{color:#ff8a00}"
           "form{flex:1;max-width:560px}input{width:100%;box-sizing:border-box;border:1px solid #dfe1e5;border-radius:24px;padding:9px 16px;font-size:15px;box-shadow:0 1px 6px rgba(32,33,36,.18);outline:0}"
           ".st{color:#70757a;font-size:13px;padding:10px 16px 0}.w{padding:4px 16px 20px;max-width:680px}"
           ".r{margin:18px 0}.s{display:flex;gap:10px;align-items:center}.s img{width:18px;height:18px;border-radius:50%;background:#f1f3f4;padding:4px}"
           ".d{font-size:14px}.u{font-size:12px;color:#4d5156;max-width:520px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}"
           ".r>a{display:inline-block;margin-top:4px;font-size:19px;color:#1a0dab;text-decoration:none}.r>a:hover{text-decoration:underline}.r p{margin:3px 0 0;font-size:14px;line-height:1.55;color:#4d5156}"
           ".pg{display:flex;gap:6px;flex-wrap:wrap;padding:8px 16px 30px}.pg a{padding:6px 11px;border-radius:8px;color:#1a0dab;text-decoration:none}.pg a.on{background:#fff3e0;color:#e65100;font-weight:700}"
           ".home{display:flex;flex-direction:column;align-items:center;justify-content:center;min-height:70vh;gap:14px;padding:24px}.home .lg{font-size:2.4rem}.home form{width:min(560px,100%)}.hint{color:#70757a;font-size:13px}")
    head = f"<!doctype html><html><head><meta charset=utf-8><meta name=viewport content='width=device-width,initial-scale=1'><title>{e(q)+' · ' if q else ''}Doganiero Search</title><script>window.__DBP={cfg};</script><script src=\"{origin}/static/dbots-proxy-helper.js?v=1\"></script><style>{css}</style></head><body>"
    if not q:
        return head + f'<div class="home"><div class="lg"><b>Doganiero Search</b></div><form data-serpform action="{origin}/api/serp" method="get"><input name="q" placeholder="Buscar en Doganiero Search…" autofocus><input type="hidden" name="t" value="{e(tok)}"></form><div class="hint">Resultados de muchos sitios</div></div></body></html>'
    return head + f'<div class="top"><div class="lg"><b>Doganiero Search</b></div><form data-serpform action="{origin}/api/serp" method="get"><input name="q" value="{e(q)}" placeholder="Buscar en Doganiero Search…"><input type="hidden" name="t" value="{e(tok)}"></form></div><div class="st">Página {page} · {len(res)} resultados de {len({r["domain"] for r in res})} sitios</div><div class="w">{items or "<p>Sin resultados.</p>"}</div><div class="pg">{nav}{nxt}</div></body></html>'

def _fetch_raw(url: str) -> tuple[str, str, bytes]:
    _check_host(url)
    req = _UReq(url, headers={"User-Agent": _SERP_UA, "Accept": "text/html,application/xhtml+xml,*/*;q=0.8", "Accept-Language": "es-ES,es;q=0.9"})
    try:
        with _opener.open(req, timeout=FETCH_TIMEOUT) as resp:
            final = resp.geturl(); _check_host(final)
            ctype = (resp.headers.get("Content-Type") or "").lower()
            raw = resp.read(MAX_PAGE_BYTES + 1)
    except UrlBlocked:
        raise
    except Exception as exc:
        code = getattr(exc, "code", None)
        raise UrlBlocked(f"La página respondió {code}" if code else "No se pudo abrir la página") from exc
    if len(raw) > MAX_PAGE_BYTES:
        raise UrlBlocked("La página pasa de 2 MB")
    return final, ctype, raw

def _decode(raw: bytes, ctype: str) -> str:
    m = re.search(r"charset=([\w-]+)", ctype) or re.search(rb"<meta[^>]+charset=[\"']?([\w-]+)", raw[:3000], re.I)
    cs = m.group(1) if m else "utf-8"
    if isinstance(cs, bytes):
        cs = cs.decode("ascii", "ignore")
    try:
        return raw.decode(cs, errors="replace")
    except LookupError:
        return raw.decode("utf-8", errors="replace")

def _proxy_doc(origin: str, tok: str, final: str, page: str) -> str:
    page = re.sub(r"<meta[^>]+http-equiv=[\"']?(content-security-policy|x-frame-options|refresh|set-cookie)[^>]*>", "", page, flags=re.I)
    page = re.sub(r"<base\b[^>]*>", "", page, flags=re.I)
    cfg = json.dumps({"p": origin + "/api/proxy", "t": tok, "u": final, "o": origin})
    inject = f'<base href="{_html.escape(final, quote=True)}"><script>window.__DBP={cfg};</script><script src="{origin}/static/dbots-proxy-helper.js?v=1"></script>'
    m = re.search(r"<head\b[^>]*>", page, re.I)
    return page[:m.end()] + inject + page[m.end():] if m else f"<!doctype html><html><head>{inject}</head><body>{page}</body></html>"

def _proxy_error(origin: str, msg: str, url: str) -> str:
    cfg = json.dumps({"p": origin + "/api/proxy", "t": "", "u": url, "o": origin, "error": msg})
    return (f"<!doctype html><html><head><meta charset=utf-8><script>window.__DBP={cfg};</script>"
            f'<script src="{origin}/static/dbots-proxy-helper.js?v=1"></script></head>'
            f'<body style="font-family:system-ui;padding:24px;text-align:center"><p>🚧 {_html.escape(msg)}</p></body></html>')

app = FastAPI(title="Snake OS Lite")

@app.post("/api/token")
def token_ep(request: Request):
    ip = (request.client.host if request.client else "anon")[:64]
    sid = "v" + hashlib.sha256((ip + "|lite").encode()).hexdigest()[:16]  # sin guardar la IP
    return {"t": proxy_token(sid), "ttl": PROXY_TOKEN_TTL}

@app.get("/api/serp")
def serp_ep(request: Request, q: str = Query("", max_length=200), p: int = Query(1, ge=1, le=10), t: str = Query("", max_length=200)):
    origin = _origin(request)
    sid = _proxy_sid(t)
    if sid is None:
        return _resp(_proxy_error(origin, "Recarga Snake OS Lite.", ""), 403)
    if not _rl(sid):
        return _resp(_proxy_error(origin, "Demasiadas búsquedas; espera un minuto.", ""), 429)
    q = q.strip()
    return _resp(_serp_html(origin, t, q, p, web_index(q, p) if q else []))

@app.get("/api/proxy")
def proxy_ep(request: Request, u: str = Query("", max_length=3000), t: str = Query("", max_length=200)):
    origin = _origin(request)
    sid = _proxy_sid(t)
    if sid is None:
        return _resp(_proxy_error(origin, "Enlace caducado.", u), 403)
    if not _rl(sid):
        return _resp(_proxy_error(origin, "Demasiadas páginas; espera un minuto.", u), 429)
    try:
        hit = _proxy_cache.get(u)
        if hit and hit[0] > time.time() - 90:
            final, page = hit[1], hit[2]
        else:
            final, ctype, raw = _fetch_raw(u)
            if ctype and "html" not in ctype and "xml" not in ctype:
                raise UrlBlocked("Este enlace no es una página web")
            page = _decode(raw, ctype)
            _proxy_cache[u] = (time.time(), final, page)
        return _resp(_proxy_doc(origin, t, final, page))
    except UrlBlocked as exc:
        return _resp(_proxy_error(origin, str(exc), u), 200)

@app.get("/api/frame-check")
def frame_check(u: str = Query("", max_length=2000)):
    try:
        _check_host(u)
        req = _UReq(u, method="GET", headers={"User-Agent": "Mozilla/5.0 (SnakeOS Lite)", "Accept": "text/html"})
        with _opener.open(req, timeout=6) as resp:
            xfo = (resp.headers.get("X-Frame-Options") or "").lower()
            csp = (resp.headers.get("Content-Security-Policy") or "").lower()
            final = resp.geturl()
    except UrlBlocked:
        return {"ok": False, "embeddable": False, "reason": "blocked"}
    except Exception as e:
        code = getattr(e, "code", None)
        if code:
            hdrs = getattr(e, "headers", None)
            xfo = ((hdrs.get("X-Frame-Options") if hdrs else "") or "").lower()
            return {"ok": True, "embeddable": not ("deny" in xfo or "sameorigin" in xfo), "status": int(code)}
        return {"ok": False, "embeddable": False, "reason": "unreachable"}
    blocked = "deny" in xfo or "sameorigin" in xfo
    m = re.search(r"frame-ancestors([^;]*)", csp)
    if m and "*" not in m.group(1).split():
        blocked = True
    return {"ok": True, "embeddable": not blocked, "final": final}

@app.get("/")
def index():
    return FileResponse(ROOT / "index.html")

app.mount("/static", StaticFiles(directory=str(ROOT / "static")), name="static")
