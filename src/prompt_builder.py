"""Construye mensajes estructurados para la generación RAG."""

import json

from src.few_shot_examples import FEW_SHOT_EXAMPLES
from src.system_prompt import SYSTEM_PROMPT


def _serializar_datos(pregunta: str, evidencia: str) -> str:
    """Serializa entradas no confiables como datos, no como delimitadores."""
    return json.dumps(
        {"pregunta": pregunta.strip(), "evidencia": evidencia.strip()},
        ensure_ascii=False,
    )


def build_prompt(pregunta_usuario: str, conocimiento_recuperado: str) -> list[dict[str, str]]:
    """Devuelve instrucciones, ejemplos breves y la consulta actual en roles separados."""
    mensajes = [{"role": "system", "content": SYSTEM_PROMPT.strip()}]
    for ejemplo in FEW_SHOT_EXAMPLES:
        mensajes.append(
            {
                "role": "user",
                "content": _serializar_datos(
                    ejemplo["pregunta"], ejemplo["evidencia"]
                ),
            }
        )
        mensajes.append(
            {
                "role": "assistant",
                "content": json.dumps(
                    ejemplo["respuesta_json"],
                    ensure_ascii=False,
                    separators=(",", ":"),
                ),
            }
        )
    mensajes.append(
        {
            "role": "user",
            "content": _serializar_datos(
                pregunta_usuario, conocimiento_recuperado
            ),
        }
    )
    return mensajes
