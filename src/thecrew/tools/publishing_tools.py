"""Herramientas custom de publicación (stubs listos para extender).

El scaffold ya escribe los entregables a disco vía `output_file` en las tareas.
Estas tools custom existen como punto de partida para cablear publicación REAL:
un CMS, la API de LinkedIn/X, o un MCP. Hoy guardan a disco; reemplaza el cuerpo
de `_run` por la llamada real cuando valides el output.
"""

from pathlib import Path
from typing import Type

from crewai.tools import BaseTool
from pydantic import BaseModel, Field


class GuardarArchivoInput(BaseModel):
    """Esquema de entrada para GuardarArchivoTool."""

    nombre_archivo: str = Field(..., description="Nombre del archivo, ej: 'post.md'")
    contenido: str = Field(..., description="Contenido a escribir")


class GuardarArchivoTool(BaseTool):
    name: str = "guardar_archivo"
    description: str = (
        "Guarda contenido en un archivo dentro de output/. Úsalo para persistir "
        "entregables (artículos, posts) listos para publicar."
    )
    args_schema: Type[BaseModel] = GuardarArchivoInput

    def _run(self, nombre_archivo: str, contenido: str) -> str:
        output_dir = Path("output")
        output_dir.mkdir(exist_ok=True)
        destino = output_dir / nombre_archivo
        destino.write_text(contenido, encoding="utf-8")
        return f"Guardado en {destino}"


# --- Stubs para publicación real (descomentar y completar al integrar) -------
#
# class PublicarLinkedInInput(BaseModel):
#     texto: str = Field(..., description="Texto del post de LinkedIn")
#
# class PublicarLinkedInTool(BaseTool):
#     name: str = "publicar_linkedin"
#     description: str = "Publica un post en LinkedIn vía la API oficial."
#     args_schema: Type[BaseModel] = PublicarLinkedInInput
#
#     def _run(self, texto: str) -> str:
#         # TODO: llamar a la API de LinkedIn con LINKEDIN_ACCESS_TOKEN.
#         raise NotImplementedError("Cablear API de LinkedIn antes de usar.")
