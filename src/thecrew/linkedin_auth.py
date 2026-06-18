"""Obtención del access token de LinkedIn (OAuth 2.0 Authorization Code).

LinkedIn no entrega un token de publicación solo con Client ID/Secret: requiere
tu autorización como miembro en el navegador (flujo 3-legged). Este helper hace
el flujo completo y guarda el token en .env, sin imprimirlo.

Requisitos (una vez, en el portal de LinkedIn Developers):
  • Productos "Share on LinkedIn" (scope w_member_social) y "Sign In with
    OpenID Connect" (scopes openid, profile) habilitados en la app.
  • En Auth -> Authorized redirect URLs, agrega EXACTAMENTE:
        http://localhost:8765/callback
  • En .env: LINKEDIN_CLIENT_ID y LINKEDIN_CLIENT_SECRET.

Uso:
  uv run linkedin_token

Al terminar escribe en .env: LINKEDIN_ACCESS_TOKEN (y refresh token si la app lo
habilita). Imprime solo confirmación enmascarada + caducidad.
"""

import os
import secrets
import sys
import threading
import urllib.parse
import webbrowser
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

import httpx
from dotenv import load_dotenv

PORT = 8765
REDIRECT_URI = f"http://localhost:{PORT}/callback"
AUTH_URL = "https://www.linkedin.com/oauth/v2/authorization"
TOKEN_URL = "https://www.linkedin.com/oauth/v2/accessToken"
# Por defecto, publicar como miembro. Con --empresa se añaden los scopes de
# organización (requieren el producto Community Management API aprobado).
SCOPES_MIEMBRO = "openid profile w_member_social"
SCOPES_EMPRESA = SCOPES_MIEMBRO + " w_organization_social rw_organization_admin"
ENV_PATH = Path(".env")

_resultado: dict[str, str] = {}


class _Handler(BaseHTTPRequestHandler):
    def do_GET(self):  # noqa: N802
        parsed = urllib.parse.urlparse(self.path)
        if parsed.path != "/callback":
            self.send_response(404)
            self.end_headers()
            return
        params = urllib.parse.parse_qs(parsed.query)
        _resultado["code"] = params.get("code", [""])[0]
        _resultado["state"] = params.get("state", [""])[0]
        _resultado["error"] = params.get("error_description", params.get("error", [""]))[0]
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.end_headers()
        msg = "Error de autorizacion." if _resultado["error"] else "Listo. Vuelve a la terminal."
        self.wfile.write(f"<html><body><h2>{msg}</h2></body></html>".encode("utf-8"))

    def log_message(self, *_):  # silencia el log del server
        pass


def _escribir_env(updates: dict[str, str]) -> None:
    """Inserta/actualiza claves en .env sin tocar el resto."""
    lineas = ENV_PATH.read_text(encoding="utf-8").splitlines() if ENV_PATH.exists() else []
    restantes = dict(updates)
    salida = []
    for l in lineas:
        clave = l.split("=", 1)[0].strip().lstrip("# ").strip() if "=" in l else ""
        if clave in restantes:
            salida.append(f"{clave}={restantes.pop(clave)}")
        else:
            salida.append(l)
    for clave, valor in restantes.items():
        salida.append(f"{clave}={valor}")
    ENV_PATH.write_text("\n".join(salida) + "\n", encoding="utf-8")


def main() -> None:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8")
        except (AttributeError, ValueError):
            pass

    load_dotenv()  # uv run no inyecta .env; este script no pasa por CrewAI

    client_id = os.getenv("LINKEDIN_CLIENT_ID", "").strip()
    client_secret = os.getenv("LINKEDIN_CLIENT_SECRET", "").strip()
    if not client_id or not client_secret:
        sys.exit(
            "Faltan LINKEDIN_CLIENT_ID y/o LINKEDIN_CLIENT_SECRET en .env.\n"
            "Cópialos del portal de LinkedIn Developers (pestaña Auth)."
        )

    empresa = "--empresa" in sys.argv[1:]
    scopes = SCOPES_EMPRESA if empresa else SCOPES_MIEMBRO
    if empresa:
        print("Modo EMPRESA: pediré scopes de organización "
              "(requieren Community Management API aprobado en tu app).\n")

    state = secrets.token_urlsafe(16)
    auth_url = AUTH_URL + "?" + urllib.parse.urlencode({
        "response_type": "code",
        "client_id": client_id,
        "redirect_uri": REDIRECT_URI,
        "scope": scopes,
        "state": state,
    })

    server = HTTPServer(("localhost", PORT), _Handler)
    threading.Thread(target=server.handle_request, daemon=True).start()

    print(f"Abriendo el navegador para autorizar (redirect: {REDIRECT_URI}).")
    print("Si no abre solo, pega esta URL en tu navegador:\n")
    print(auth_url + "\n")
    webbrowser.open(auth_url)
    print("Esperando la autorización...")

    # Bloquea hasta que el handler reciba el callback.
    import time
    for _ in range(300):  # ~5 min de margen
        if _resultado:
            break
        time.sleep(1)
    server.server_close()

    if not _resultado:
        sys.exit("No llegó el callback (timeout). Reintenta: uv run linkedin_token")
    if _resultado.get("error"):
        sys.exit(f"LinkedIn devolvió error: {_resultado['error']}")
    if _resultado.get("state") != state:
        sys.exit("El 'state' no coincide (posible CSRF). Reintenta.")
    code = _resultado.get("code")
    if not code:
        sys.exit("No se recibió 'code'. Reintenta.")

    r = httpx.post(
        TOKEN_URL,
        data={
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": REDIRECT_URI,
            "client_id": client_id,
            "client_secret": client_secret,
        },
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        timeout=30,
    )
    if r.status_code != 200:
        sys.exit(f"Falló el intercambio del token (HTTP {r.status_code}): {r.text[:400]}")

    data = r.json()
    token = data.get("access_token", "")
    if not token:
        sys.exit(f"La respuesta no trae access_token: {data}")

    updates = {"LINKEDIN_ACCESS_TOKEN": token}
    if data.get("refresh_token"):
        updates["LINKEDIN_REFRESH_TOKEN"] = data["refresh_token"]
    _escribir_env(updates)

    dias = round(int(data.get("expires_in", 0)) / 86400, 1)
    enmascarado = token[:6] + "…" + token[-4:]
    print(f"\nToken guardado en .env  ({enmascarado}). Caduca en ~{dias} días.")
    if "LINKEDIN_REFRESH_TOKEN" in updates:
        print("Refresh token también guardado.")
    print("Prueba ahora:  uv run publicar_linkedin   (preview)")


if __name__ == "__main__":
    main()
