"""Punto de entrada de THECREW.

Dos disparadores EXPLÍCITOS, sin default silencioso:
  - `dia`    : la noticia más importante de las últimas 24 horas (on-demand).
  - `semana` : la más importante de los últimos 7 días (corrida semanal).

Uso:
  uv run run_crew dia
  uv run run_crew semana
  (o los atajos: uv run run_dia  /  uv run run_semana)

La ventana se inyecta como inputs y queda disponible en agents.yaml /
tasks.yaml como {ventana}, {periodo}, {alcance} y {today}.
"""

import sys
import warnings
from datetime import date, timedelta

from thecrew.crew import Thecrew

warnings.filterwarnings("ignore", category=SyntaxWarning, module="pysbd")

VENTANAS = ("dia", "semana")

_TOPICS = {
    "topic_ia": "Inteligencia Artificial",
    "topic_cripto": "Cripto y activos digitales",
    "topic_economia": "Economía mundial",
}


def _inputs(ventana: str) -> dict:
    """Construye los inputs del crew según la ventana temporal elegida."""
    hoy = date.today()
    if ventana == "dia":
        periodo = f"las últimas 24 horas (al {hoy.isoformat()})"
        alcance = "del día"
    else:  # semana
        inicio = hoy - timedelta(days=7)
        periodo = f"los últimos 7 días ({inicio.isoformat()} a {hoy.isoformat()})"
        alcance = "de la semana"
    return {
        "today": hoy.isoformat(),
        "ventana": ventana,
        "periodo": periodo,
        "alcance": alcance,
        **_TOPICS,
    }


def _ventana_desde_argv() -> str:
    """Exige un trigger explícito (`dia`|`semana`). Sin default silencioso."""
    elegido = next((a.lower() for a in sys.argv[1:] if a.lower() in VENTANAS), None)
    if elegido is None:
        sys.exit(
            "Trigger explícito requerido. Uso: run_crew <dia|semana>\n"
            "  dia    -> noticia más importante de las últimas 24 horas\n"
            "  semana -> noticia más importante de los últimos 7 días"
        )
    return elegido


def _kickoff(ventana: str):
    try:
        return Thecrew().crew().kickoff(inputs=_inputs(ventana))
    except Exception as e:  # noqa: BLE001
        raise RuntimeError(f"Error al ejecutar el crew ({ventana}): {e}") from e


def run():
    """Corre el crew con la ventana pasada por argumento (dia|semana)."""
    _kickoff(_ventana_desde_argv())


def run_dia():
    """Atajo de trigger diario / on-demand (24 horas)."""
    _kickoff("dia")


def run_semana():
    """Atajo de trigger semanal (7 días)."""
    _kickoff("semana")


def train():
    """Entrena el crew durante n iteraciones. Uso: train <n> <filename> [dia|semana]."""
    ventana = next((a.lower() for a in sys.argv[3:] if a.lower() in VENTANAS), "dia")
    try:
        Thecrew().crew().train(
            n_iterations=int(sys.argv[1]),
            filename=sys.argv[2],
            inputs=_inputs(ventana),
        )
    except Exception as e:  # noqa: BLE001
        raise RuntimeError(f"Error al entrenar el crew: {e}") from e


def replay():
    """Re-ejecuta desde una tarea específica. Uso: replay <task_id>."""
    try:
        Thecrew().crew().replay(task_id=sys.argv[1])
    except Exception as e:  # noqa: BLE001
        raise RuntimeError(f"Error en replay: {e}") from e


def test():
    """Testea el crew. Uso: test <n_iterations> <eval_llm> [dia|semana]."""
    ventana = next((a.lower() for a in sys.argv[3:] if a.lower() in VENTANAS), "dia")
    try:
        Thecrew().crew().test(
            n_iterations=int(sys.argv[1]),
            eval_llm=sys.argv[2],
            inputs=_inputs(ventana),
        )
    except Exception as e:  # noqa: BLE001
        raise RuntimeError(f"Error al testear el crew: {e}") from e


if __name__ == "__main__":
    run()
