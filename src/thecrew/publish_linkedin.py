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
from datetime import date
from pathlib import Path

import httpx
from dotenv import load_dotenv

API_POSTS = "https://api.linkedin.com/rest/posts"
API_USERINFO = "https://api.linkedin.com/v2/userinfo"
API_ORG_ACLS = "https://api.linkedin.com/rest/organizationAcls"
API_IMAGES_INIT = "https://api.linkedin.com/rest/images?action=initializeUpload"
MAX_COMMENTARY = 3000  # límite de LinkedIn para el cuerpo del post

IMG_DIR = Path("imagenes")  # deja aquí la imagen del día: imagenes/AAAA-MM-DD.png
IMG_EXTS = (".png", ".jpg", ".jpeg", ".webp", ".gif")


def _imagen_del_dia(override: str | None) -> Path | None:
    """Resuelve la imagen a adjuntar: --imagen explícita, o imagenes/<hoy>.<ext>."""
    if override:
        p = Path(override)
        if not p.exists():
            raise FileNotFoundError(f"No existe la imagen indicada: {p}")
        return p
    hoy = date.today().isoformat()
    for ext in IMG_EXTS:
        p = IMG_DIR / f"{hoy}{ext}"
        if p.exists():
            return p
    if IMG_DIR.exists():  # acepta también 'AAAA-MM-DD algo.png'
        for p in sorted(IMG_DIR.glob(f"{hoy}*")):
            if p.suffix.lower() in IMG_EXTS:
                return p
    return None


def _versiones_api() -> list[str]:
    """Versiones LinkedIn-Version a probar (YYYYMM), de más nueva a más vieja.

    LinkedIn rota las versiones y desactiva las de >~12 meses (HTTP 426). En vez
    de hardcodear una fecha que expira, calculamos el mes actual y caemos hacia
    atrás. Override explícito con LINKEDIN_API_VERSION.
    """
    env = os.getenv("LINKEDIN_API_VERSION", "").strip()
    if env:
        return [env]
    cands, y, m = [], date.today().year, date.today().month
    for _ in range(4):  # mes actual + 3 anteriores
        cands.append(f"{y}{m:02d}")
        m -= 1
        if m == 0:
            m, y = 12, y - 1
    return cands


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


def _org_urn(client: httpx.Client, token: str) -> str:
    """URN de la organización: de LINKEDIN_ORG_URN o resuelto vía organizationAcls.

    El auto-resolver lista las páginas que administras (rol ADMINISTRATOR). Si
    administras varias, hay que fijar LINKEDIN_ORG_URN para desambiguar.
    Requiere el scope rw_organization_admin en el token.
    """
    urn = os.getenv("LINKEDIN_ORG_URN", "").strip()
    if urn:
        return urn
    r = None
    for version in _versiones_api():
        r = client.get(
            API_ORG_ACLS,
            params={"q": "roleAssignee", "role": "ADMINISTRATOR", "state": "APPROVED"},
            headers={
                "Authorization": f"Bearer {token}",
                "X-Restli-Protocol-Version": "2.0.0",
                "LinkedIn-Version": version,
            },
        )
        if r.status_code != 426:
            break
    if r.status_code != 200:
        raise RuntimeError(
            "No pude listar las páginas que administras "
            f"(HTTP {r.status_code}). Define LINKEDIN_ORG_URN en .env, o asegura "
            "el scope rw_organization_admin (producto Community Management API). "
            f"Detalle: {r.text[:300]}"
        )
    orgs = [e.get("organization") for e in r.json().get("elements", []) if e.get("organization")]
    if not orgs:
        raise RuntimeError(
            "No administras ninguna página aprobada (o falta el scope). "
            "Define LINKEDIN_ORG_URN en .env (formato urn:li:organization:XXXX)."
        )
    if len(orgs) > 1:
        raise RuntimeError(
            "Administras varias páginas: " + ", ".join(orgs) + ". "
            "Fija LINKEDIN_ORG_URN con la que quieras usar."
        )
    return orgs[0]


def _subir_imagen(client: httpx.Client, token: str, owner: str, ruta: Path) -> str:
    """Sube una imagen y devuelve su URN (urn:li:image:…) para adjuntar al post."""
    init = None
    for version in _versiones_api():
        init = client.post(
            API_IMAGES_INIT,
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
                "X-Restli-Protocol-Version": "2.0.0",
                "LinkedIn-Version": version,
            },
            json={"initializeUploadRequest": {"owner": owner}},
        )
        if init.status_code != 426:
            break
    if init.status_code not in (200, 201):
        raise RuntimeError(
            f"No pude inicializar la subida de imagen (HTTP {init.status_code}): "
            f"{init.text[:300]}"
        )
    value = init.json()["value"]
    up = client.put(
        value["uploadUrl"],
        content=ruta.read_bytes(),
        headers={"Authorization": f"Bearer {token}"},
    )
    if up.status_code not in (200, 201):
        raise RuntimeError(
            f"Falló la subida de la imagen (HTTP {up.status_code}): {up.text[:300]}"
        )
    return value["image"]


def publicar_en_linkedin(
    texto: str,
    *,
    dry_run: bool = True,
    como_empresa: bool = False,
    imagen: Path | None = None,
) -> str:
    """Publica `texto` en LinkedIn. En dry_run no llama a la API.

    como_empresa=True publica como página de organización (author = urn:li:
    organization:…); requiere el scope w_organization_social en el token.
    imagen: ruta a una imagen para adjuntar (mejor enganche); opcional.
    """
    if not texto:
        raise ValueError("El texto del post está vacío.")
    if len(texto) > MAX_COMMENTARY:
        raise ValueError(
            f"El post tiene {len(texto)} caracteres; el máximo de LinkedIn es "
            f"{MAX_COMMENTARY}. Acórtalo antes de publicar."
        )

    if dry_run:
        destino = "página de empresa" if como_empresa else "tu perfil"
        flag = " --empresa" if como_empresa else ""
        img = f"con imagen: {imagen.name}" if imagen else "SIN imagen (deja una en imagenes/)"
        return (
            f"[DRY-RUN] No se publicó. {len(texto)} caracteres para {destino}, {img}.\n"
            f"Para publicar de verdad: uv run publicar_linkedin --publicar{flag}"
        )

    token = os.getenv("LINKEDIN_ACCESS_TOKEN", "").strip()
    if not token:
        raise RuntimeError("Falta LINKEDIN_ACCESS_TOKEN en el entorno (.env).")

    payload = {
        "author": None,  # se completa con el autor resuelto
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

    with httpx.Client(timeout=30) as client:
        payload["author"] = _org_urn(client, token) if como_empresa else _author_urn(client, token)
        if imagen is not None:
            image_urn = _subir_imagen(client, token, payload["author"], imagen)
            payload["content"] = {"media": {"id": image_urn}}
        ultima = None
        for version in _versiones_api():
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
            if r.status_code in (200, 201):
                post_id = r.headers.get("x-restli-id") or r.headers.get("x-linkedin-id") or "?"
                return f"Publicado en LinkedIn (v{version}). ID: {post_id}"
            ultima = r
            if r.status_code != 426:  # 426 = versión inactiva (no crea post); otro error: corta
                break

    raise RuntimeError(
        f"LinkedIn rechazó la publicación (HTTP {ultima.status_code}): {ultima.text[:500]}"
    )


def main() -> None:
    # Windows usa cp1252 por defecto; el post lleva acentos y símbolos.
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8")
        except (AttributeError, ValueError):
            pass

    load_dotenv()  # uv run no inyecta .env; este script no pasa por CrewAI
    args = sys.argv[1:]
    publicar = "--publicar" in args
    empresa = "--empresa" in args
    archivo = Path("output/redes_sociales.md")
    if "--archivo" in args:
        archivo = Path(args[args.index("--archivo") + 1])
    imagen_arg = args[args.index("--imagen") + 1] if "--imagen" in args else None

    if not archivo.exists():
        sys.exit(
            f"No existe {archivo}. Corre primero el pipeline "
            "(uv run run_dia / run_semana)."
        )

    imagen = _imagen_del_dia(imagen_arg)
    texto = extraer_seccion_linkedin(archivo)
    print("─" * 70)
    print(texto)
    print("─" * 70)
    destino = "PÁGINA DE EMPRESA" if empresa else "PERFIL personal"
    img_txt = imagen.name if imagen else f"NINGUNA (deja una en {IMG_DIR}/{date.today().isoformat()}.png)"
    print(f"({len(texto)} caracteres · destino: {destino} · imagen: {img_txt})\n")

    resultado = publicar_en_linkedin(
        texto, dry_run=not publicar, como_empresa=empresa, imagen=imagen
    )
    print(resultado)


if __name__ == "__main__":
    main()
