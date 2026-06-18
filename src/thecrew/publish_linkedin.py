"""Publicación en LinkedIn del post generado por el pipeline.

Lee el bloque `## LinkedIn` de output/redes_sociales.md y lo publica en el perfil
del miembro vía la Posts API de LinkedIn.

SEGURIDAD: publicar es outward-facing e irreversible. Por eso el comando hace
PREVIEW por defecto (dry-run) y solo publica de verdad con `--publicar`.
NO está cableado al cron: el cron genera, tú revisas y publicas a mano.

Uso:
  uv run publicar_linkedin                 # preview (no publica)
  uv run publicar_linkedin --publicar      # publica de verdad
  uv run publicar_linkedin --archivo output/redes_sociales.md --publicar

Requiere en .env:
  LINKEDIN_ACCESS_TOKEN   token de miembro con scope w_member_social (obligatorio)
  LINKEDIN_AUTHOR_URN     urn:li:person:XXXX (opcional; si falta se resuelve vía
                          /v2/userinfo, que requiere scope openid/profile)
  LINKEDIN_API_VERSION    versión de la API, formato YYYYMM (opcional)
"""

import os
import sys
from pathlib import Path

import httpx

API_POSTS = "https://api.linkedin.com/rest/posts"
API_USERINFO = "https://api.linkedin.com/v2/userinfo"
DEFAULT_VERSION = "202405"
MAX_COMMENTARY = 3000  # límite de LinkedIn para el cuerpo del post


def extraer_seccion_linkedin(md_path: Path) -> str:
    """Devuelve el texto del bloque '## LinkedIn' de un .md de RRSS.

    El bloque va desde el encabezado '## LinkedIn' hasta el siguiente '## ' o
    el separador '---' que lo cierra. Quita la línea de 'primer comentario'
    (logística de publicación, no parte del post).
    """
    texto = md_path.read_text(encoding="utf-8")
    lineas = texto.splitlines()
    inicio = next(
        (i for i, l in enumerate(lineas) if l.strip().lower() == "## linkedin"), None
    )
    if inicio is None:
        raise ValueError(f"No encontré una sección '## LinkedIn' en {md_path}")

    cuerpo: list[str] = []
    for l in lineas[inicio + 1 :]:
        s = l.strip()
        if s.startswith("## ") or s == "---":
            break
        if s.startswith("→") and "comentario" in s.lower():
            continue  # nota de logística, no va en el post
        cuerpo.append(l)
    return "\n".join(cuerpo).strip()


def _author_urn(client: httpx.Client, token: str) -> str:
    """URN del autor: de LINKEDIN_AUTHOR_URN o resuelto vía /v2/userinfo."""
    urn = os.getenv("LINKEDIN_AUTHOR_URN", "").strip()
    if urn:
        return urn
    r = client.get(API_USERINFO, headers={"Authorization": f"Bearer {token}"})
    if r.status_code != 200:
        raise RuntimeError(
            "No pude resolver el autor vía /v2/userinfo "
            f"(HTTP {r.status_code}). Define LINKEDIN_AUTHOR_URN en .env "
            "o asegura el scope openid/profile en el token. Detalle: "
            f"{r.text[:300]}"
        )
    sub = r.json().get("sub")
    if not sub:
        raise RuntimeError("userinfo no devolvió 'sub'; define LINKEDIN_AUTHOR_URN.")
    return f"urn:li:person:{sub}"


def publicar_en_linkedin(texto: str, *, dry_run: bool = True) -> str:
    """Publica `texto` en LinkedIn. En dry_run no llama a la API."""
    if not texto:
        raise ValueError("El texto del post está vacío.")
    if len(texto) > MAX_COMMENTARY:
        raise ValueError(
            f"El post tiene {len(texto)} caracteres; el máximo de LinkedIn es "
            f"{MAX_COMMENTARY}. Acórtalo antes de publicar."
        )

    if dry_run:
        return (
            f"[DRY-RUN] No se publicó. {len(texto)} caracteres listos.\n"
            "Para publicar de verdad: uv run publicar_linkedin --publicar"
        )

    token = os.getenv("LINKEDIN_ACCESS_TOKEN", "").strip()
    if not token:
        raise RuntimeError("Falta LINKEDIN_ACCESS_TOKEN en el entorno (.env).")
    version = os.getenv("LINKEDIN_API_VERSION", DEFAULT_VERSION).strip()

    with httpx.Client(timeout=30) as client:
        author = _author_urn(client, token)
        payload = {
            "author": author,
            "commentary": texto,
            "visibility": "PUBLIC",
            "distribution": {
                "feedDistribution": "MAIN_FEED",
                "targetEntities": [],
                "thirdPartyDistributionChannels": [],
            },
            "lifecycleState": "PUBLISHED",
            "isReshareDisabledByAuthor": False,
        }
        r = client.post(
            API_POSTS,
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
                "X-Restli-Protocol-Version": "2.0.0",
                "LinkedIn-Version": version,
            },
            json=payload,
        )
    if r.status_code not in (200, 201):
        raise RuntimeError(
            f"LinkedIn rechazó la publicación (HTTP {r.status_code}): {r.text[:500]}"
        )
    post_id = r.headers.get("x-restli-id") or r.headers.get("x-linkedin-id") or "?"
    return f"Publicado en LinkedIn. ID: {post_id}"


def main() -> None:
    # Windows usa cp1252 por defecto; el post lleva acentos y símbolos.
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except (AttributeError, ValueError):
        pass
    args = sys.argv[1:]
    publicar = "--publicar" in args
    archivo = Path("output/redes_sociales.md")
    if "--archivo" in args:
        archivo = Path(args[args.index("--archivo") + 1])

    if not archivo.exists():
        sys.exit(
            f"No existe {archivo}. Corre primero el pipeline "
            "(uv run run_dia / run_semana)."
        )

    texto = extraer_seccion_linkedin(archivo)
    print("─" * 70)
    print(texto)
    print("─" * 70)
    print(f"({len(texto)} caracteres)\n")

    resultado = publicar_en_linkedin(texto, dry_run=not publicar)
    print(resultado)


if __name__ == "__main__":
    main()
