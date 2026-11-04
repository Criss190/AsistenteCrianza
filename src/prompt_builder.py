"""Construye mensajes estructurados para la generación RAG."""

import json

from src.few_shot_examples import FEW_SHOT_EXAMPLES
from src.system_prompt import SYSTEM_PROMPT


def _serializar_datos(
    pregunta: str, evidencia: str, contexto_previo: str = ""
) -> str:
    """Serializa entradas no confiables como datos, no como delimitadores."""
    datos = {"pregunta": pregunta.strip(), "evidencia": evidencia.strip()}
    if contexto_previo.strip():
        datos["contexto_previo"] = contexto_previo.strip()
    return json.dumps(datos, ensure_ascii=False)


def build_prompt(
    pregunta_usuario: str,
    conocimiento_recuperado: str,
    contexto_previo: str = "",
) -> list[dict[str, str]]:
    """Devuelve instrucciones, ejemplos breves y la consulta actual en roles separados.

    `contexto_previo` (si llega) solo se adjunta al turno real, nunca a los
    ejemplos few-shot, para no alterar su contrato ya validado.
    """
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
                pregunta_usuario, conocimiento_recuperado, contexto_previo
            ),
        }
    )
    return mensajes
