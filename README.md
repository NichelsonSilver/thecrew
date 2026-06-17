# THECREW — Redacción autónoma de inteligencia diaria (CrewAI)

Equipo de agentes que **recopila la noticia más importante del día** en tres
tópicos (Inteligencia Artificial, Cripto, Economía mundial), la **analiza**, y
emite una **opinión objetiva desde la perspectiva de una empresa AI-first
(REALI)**, hasta dejar **entregables listos para publicación**: un artículo para
web y adaptaciones para redes sociales.

Construido sobre [CrewAI](https://docs.crewai.com), orquestando modelos
**Claude (Anthropic)** vía el proveedor `anthropic/` de LiteLLM.

---

## Arquitectura — pipeline de 8 agentes

```
                 ┌─────────────────────────────────────────────┐
   RESEARCH      │  scout_ia    scout_cripto    scout_economia  │  (web search)
                 └───────────────────────┬─────────────────────┘
                                         ▼
   CURACIÓN      │  editor_jefe  → selecciona la #1 por tópico + prioriza │
                                         ▼
   ANÁLISIS      │  analista     → implicancias técnicas / de mercado     │
                                         ▼
   OPINIÓN       │  estratega_reali → lente AI-first (knowledge/)         │
                                         ▼
   PUBLICACIÓN   │  redactor_web → artículo Markdown (output/)            │
                 │  community_manager → LinkedIn / X / Instagram          │
                 └────────────────────────────────────────────┘
```

| # | Agente | Rol | Herramientas |
|---|--------|-----|--------------|
| 1-3 | `scout_*` | Cazadores de noticias por tópico | `SerperDevTool`, `ScrapeWebsiteTool` |
| 4 | `editor_jefe` | Curaduría y priorización editorial | — (razonamiento) |
| 5 | `analista` | Análisis de implicancias | `ScrapeWebsiteTool` (profundizar fuentes) |
| 6 | `estratega_reali` | Opinión objetiva AI-first | `knowledge/` (lente REALI) |
| 7 | `redactor_web` | Artículo para web | — (escritura) |
| 8 | `community_manager` | Posts para RRSS | — (escritura) |

**Por qué este diseño:** separar *research → curaduría → análisis → opinión →
publicación* en agentes especializados produce mejor calidad que un único
prompt monolítico, permite intercambiar el modelo por etapa (los scouts pueden
ir en un modelo más barato, la opinión en el más capaz) y deja puntos de
intervención humana claros antes de publicar.

---

## Modelos — multi-proveedor (multimodal)

CrewAI llama a cualquier LLM a través de **LiteLLM**, así que el string del
modelo lleva el prefijo de proveedor. Todos los modelos soportados son
multimodales. Puedes elegir proveedor **por variable de entorno, sin tocar
código**:

| Proveedor | String de modelo (ejemplo) | Clave en `.env` |
|-----------|----------------------------|-----------------|
| Anthropic (default) | `anthropic/claude-opus-4-8`, `anthropic/claude-haiku-4-5` | `ANTHROPIC_API_KEY` |
| OpenAI    | `openai/gpt-4o`, `openai/gpt-4o-mini` | `OPENAI_API_KEY` |
| Google    | `gemini/gemini-2.0-flash`, `gemini/gemini-1.5-pro` | `GEMINI_API_KEY` |

El pipeline tiene **dos etapas con modelo configurable por separado** (en
`src/thecrew/crew.py`):

- `RESEARCH_MODEL` — los scouts (búsqueda + resumen). Candidato a un modelo más
  barato/rápido (p. ej. `gemini/gemini-2.0-flash` u `openai/gpt-4o-mini`).
- `WRITER_MODEL` — análisis, opinión AI-first y redacción. Conviene el modelo
  más capaz.

Si no defines esas variables, **ambas etapas usan `anthropic/claude-opus-4-8`**.
Verifica los IDs exactos de OpenAI/Gemini en la doc de LiteLLM antes de fijarlos.

---

## Herramientas, MCP y extensibilidad

- **Web search / scraping:** `SerperDevTool` (requiere `SERPER_API_KEY`) y
  `ScrapeWebsiteTool`. Para investigación en tiempo real del día.
- **Publicación (stubs en `tools/publishing_tools.py`):** herramientas custom
  para guardar el artículo y los posts como archivos, listas para conectar a
  un CMS, a la API de LinkedIn/X, o a un MCP.
- **MCP (opcional):** `crew.py` incluye, comentado, el patrón
  `MCPServerAdapter` de `crewai-tools` para exponer servidores MCP (p. ej.
  Notion para publicar la nota, o un MCP de redes sociales) como tools nativas
  de los agentes.

---

## Setup

```bash
# 1. Instalar (requiere Python 3.10–3.13 y uv recomendado por CrewAI)
pip install uv
uv sync           # o: pip install -e .

# 2. Credenciales
cp .env.example .env
#   edita .env y completa ANTHROPIC_API_KEY y SERPER_API_KEY

# 3. Ejecutar el crew (usa la fecha de hoy automáticamente)
crewai run        # o: uv run thecrew
```

Los entregables quedan en `output/`:
- `output/articulo_web.md` — artículo para la página web.
- `output/redes_sociales.md` — posts para LinkedIn, X e Instagram.

---

## Personalización rápida

- **Tópicos:** edita `topics` en `src/thecrew/main.py`.
- **Voz / criterio AI-first:** edita `knowledge/reali_ai_first_lens.md`.
- **Reglas editoriales (objetividad, formato):** `knowledge/editorial_guidelines.md`.
- **Agentes (rol/goal/backstory):** `src/thecrew/config/agents.yaml`.
- **Tareas (instrucciones y salidas):** `src/thecrew/config/tasks.yaml`.

---

## Estado

Scaffold funcional. Definición de "done" del scaffold:
- [x] Estructura CrewAI estándar (config YAML + crew.py + main.py).
- [x] 8 agentes y 8 tareas encadenadas.
- [x] Integración Claude vía LiteLLM, dos LLMs configurables.
- [x] Tools de búsqueda + stubs de publicación + patrón MCP.
- [x] Knowledge base con la lente AI-first de REALI.
- [ ] Conectar credenciales reales y primera corrida de validación.
- [ ] Cablear publicación real (CMS / RRSS / MCP) cuando se valide el output.
