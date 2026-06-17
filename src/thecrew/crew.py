"""Ensamblaje del crew: agentes, tareas, herramientas y modelos Claude.

CrewAI llama a Claude a través de LiteLLM, por eso el string del modelo lleva
el prefijo de proveedor `anthropic/`. La API key se lee de ANTHROPIC_API_KEY.
"""

import os
from pathlib import Path

from crewai import Agent, Crew, LLM, Process, Task
from crewai.project import CrewBase, agent, crew, task
from crewai.agents.agent_builder.base_agent import BaseAgent
from crewai_tools import ScrapeWebsiteTool, SerperDevTool

# --- Conocimiento de marca (inyección directa, sin RAG/embeddings) -----------
# Antes esto iba como knowledge_sources (RAG), pero eso obliga a un proveedor de
# embeddings (OpenAI por default). Para dos documentos pequeños y estáticos es
# más simple y robusto inyectarlos directo en el backstory del agente que los
# usa: cero embeddings, cero dependencia de un proveedor extra.
_KNOWLEDGE = Path(__file__).resolve().parent.parent.parent / "knowledge"


def _load(nombre: str) -> str:
    return (_KNOWLEDGE / nombre).read_text(encoding="utf-8")


REALI_LENS = _load("reali_ai_first_lens.md")
EDITORIAL = _load("editorial_guidelines.md")


def _con_contexto(cfg: dict, titulo: str, doc: str) -> dict:
    """Devuelve una copia del config del agente con `doc` anexado al backstory."""
    nuevo = dict(cfg)
    nuevo["backstory"] = f"{cfg.get('backstory', '')}\n\n# {titulo}\n{doc}"
    return nuevo

# --- Modelos (multi-proveedor vía LiteLLM) -----------------------------------
# CrewAI llama a cualquier LLM a través de LiteLLM (es el router, no un modelo):
# el string lleva el prefijo de proveedor. Todos son multimodales. Cambia de
# proveedor SIN tocar código definiendo las variables en .env.
#
# Pipeline en TRES tiers, asignados por costo/calidad de cada etapa:
#
#   1) RESEARCH  -> Gemini Flash   (scouts): barato/rápido, con tier gratis.
#   2) ANALYSIS  -> Claude         (curaduría, análisis, estrategia REALI): el
#                                   núcleo de razonamiento, donde la calidad paga.
#   3) WRITING   -> GPT            (redacción web, community manager): redacción.
#
# Defaults pensados para la opción más económica/gratuita de cada proveedor.
# Sube de gama (p. ej. ANALYSIS_MODEL=anthropic/claude-opus-4-8) cuando el output
# vaya a publicación real. Verifica los IDs vigentes en la doc de LiteLLM.
DEFAULT_RESEARCH_MODEL = "gemini/gemini-2.0-flash"      # GEMINI_API_KEY (tier gratis)
DEFAULT_ANALYSIS_MODEL = "anthropic/claude-haiku-4-5"   # ANTHROPIC_API_KEY
DEFAULT_WRITING_MODEL = "openai/gpt-4o-mini"            # OPENAI_API_KEY

llm_research = LLM(model=os.getenv("RESEARCH_MODEL", DEFAULT_RESEARCH_MODEL))
llm_analysis = LLM(model=os.getenv("ANALYSIS_MODEL", DEFAULT_ANALYSIS_MODEL))
llm_writing = LLM(model=os.getenv("WRITING_MODEL", DEFAULT_WRITING_MODEL))

# --- Herramientas ------------------------------------------------------------
# SerperDevTool requiere SERPER_API_KEY. ScrapeWebsiteTool no requiere clave.
search_tool = SerperDevTool()
scrape_tool = ScrapeWebsiteTool()


@CrewBase
class Thecrew:
    """Redacción autónoma de inteligencia diaria."""

    agents: list[BaseAgent]
    tasks: list[Task]

    agents_config = "config/agents.yaml"
    tasks_config = "config/tasks.yaml"

    # --- Agentes -------------------------------------------------------------
    # Los scouts comparten herramientas de research. El estratega lee la lente
    # AI-first desde knowledge/ (cableado en el Crew, abajo).

    @agent
    def scout_ia(self) -> Agent:
        return Agent(
            config=self.agents_config["scout_ia"],
            tools=[search_tool, scrape_tool],
            llm=llm_research,
            verbose=True,
        )

    @agent
    def scout_cripto(self) -> Agent:
        return Agent(
            config=self.agents_config["scout_cripto"],
            tools=[search_tool, scrape_tool],
            llm=llm_research,
            verbose=True,
        )

    @agent
    def scout_economia(self) -> Agent:
        return Agent(
            config=self.agents_config["scout_economia"],
            tools=[search_tool, scrape_tool],
            llm=llm_research,
            verbose=True,
        )

    @agent
    def editor_jefe(self) -> Agent:  # curaduría -> Claude
        return Agent(
            config=self.agents_config["editor_jefe"],
            llm=llm_analysis,
            verbose=True,
        )

    @agent
    def analista(self) -> Agent:  # análisis -> Claude
        return Agent(
            config=self.agents_config["analista"],
            tools=[scrape_tool],
            llm=llm_analysis,
            verbose=True,
        )

    @agent
    def estratega_reali(self) -> Agent:  # estrategia REALI -> Claude
        return Agent(
            config=_con_contexto(
                self.agents_config["estratega_reali"], "Lente AI-first de REALI", REALI_LENS
            ),
            llm=llm_analysis,
            verbose=True,
        )

    @agent
    def redactor_web(self) -> Agent:  # redacción web -> GPT
        return Agent(
            config=_con_contexto(
                self.agents_config["redactor_web"], "Reglas editoriales", EDITORIAL
            ),
            llm=llm_writing,
            verbose=True,
        )

    @agent
    def community_manager(self) -> Agent:  # community manager -> GPT
        return Agent(
            config=_con_contexto(
                self.agents_config["community_manager"], "Reglas editoriales", EDITORIAL
            ),
            llm=llm_writing,
            verbose=True,
        )

    # --- Tareas --------------------------------------------------------------
    @task
    def research_ia(self) -> Task:
        return Task(config=self.tasks_config["research_ia"])

    @task
    def research_cripto(self) -> Task:
        return Task(config=self.tasks_config["research_cripto"])

    @task
    def research_economia(self) -> Task:
        return Task(config=self.tasks_config["research_economia"])

    @task
    def curaduria_editorial(self) -> Task:
        return Task(config=self.tasks_config["curaduria_editorial"])

    @task
    def analisis_implicancias(self) -> Task:
        return Task(config=self.tasks_config["analisis_implicancias"])

    @task
    def opinion_ai_first(self) -> Task:
        return Task(config=self.tasks_config["opinion_ai_first"])

    @task
    def redaccion_web(self) -> Task:
        return Task(config=self.tasks_config["redaccion_web"])

    @task
    def adaptacion_redes(self) -> Task:
        return Task(config=self.tasks_config["adaptacion_redes"])

    # --- Crew ----------------------------------------------------------------
    @crew
    def crew(self) -> Crew:
        """Pipeline secuencial: research -> curaduría -> análisis -> opinión -> publicación.

        El conocimiento de marca (lente AI-first y reglas editoriales) se inyecta
        directo en el backstory de los agentes que lo usan (ver `_con_contexto`),
        sin RAG ni embeddings — evita depender de un proveedor de embeddings.
        """
        return Crew(
            agents=self.agents,  # creados por los decoradores @agent
            tasks=self.tasks,  # creadas por los decoradores @task
            process=Process.sequential,
            verbose=True,
            # memory=True,  # requiere proveedor de embeddings; off por ahora
        )

    # -------------------------------------------------------------------------
    # OPCIONAL — Integración MCP (servidores externos como tools de los agentes).
    # Patrón de crewai-tools. Útil para publicar la nota en Notion o disparar
    # RRSS vía un MCP. Descomenta y añade las tools al agente correspondiente.
    #
    # from crewai_tools import MCPServerAdapter
    # from mcp import StdioServerParameters
    #
    # mcp_params = StdioServerParameters(command="npx", args=["-y", "<mcp-server>"])
    # with MCPServerAdapter(mcp_params) as mcp_tools:
    #     publisher = Agent(..., tools=[*mcp_tools])
