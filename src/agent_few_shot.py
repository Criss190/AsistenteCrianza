"""Pocos ejemplos (few-shot) con los roles reales de tool-calling, para
anclar el comportamiento del agente antes del turno real. A diferencia del
Avance 2 (JSON-como-texto), aquí se usan los roles nativos que espera Groq:
`assistant` con `tool_calls`, `tool` con el resultado, y el `assistant` final.
"""

import json


def _tool_call(id_: str, nombre: str, argumentos: dict) -> dict:
    return {
        "id": id_,
        "type": "function",
        "function": {"name": nombre, "arguments": json.dumps(argumentos, ensure_ascii=False)},
    }


def construir_few_shot() -> list[dict]:
    """Devuelve los mensajes de ejemplo a anteponer al turno real.

    Deliberadamente corto: cada mensaje few-shot se repite en cada llamada
    del loop (incluidas las de corrección de formato), y el plan gratuito de
    Groq tiene un límite de tokens por minuto muy ajustado para un agente
    multi-turno. Un solo ejemplo compacto (tool-calling con una sola
    evidencia) basta para anclar el formato; el detalle de cuándo usar cada
    tool ya está en el System Prompt.
    """
    return [
        # Saludo casual -> sin tools.
        {"role": "user", "content": "Hola, ¿cómo estás?"},
        {"role": "assistant", "content": "¡Hola! Muy bien, gracias. ¿Qué necesitas hoy?"},
        # Pregunta de la guía -> una tool, respuesta final citando.
        {"role": "user", "content": "Mi hijo grita cuando le apago la pantalla. ¿Qué hago?"},
        {
            "role": "assistant",
            "content": None,
            "tool_calls": [_tool_call("ej1", "buscar_en_base", {"consulta": "rabieta calmar niño"})],
        },
        {
            "role": "tool",
            "tool_call_id": "ej1",
            "content": json.dumps(
                [
                    {
                        "documento": "TBRI — Principios de Corrección",
                        "pagina": 25,
                        "seccion": None,
                        "texto": "El adulto baja el tono de voz y ofrece un lugar seguro elegido de antemano.",
                    }
                ],
                ensure_ascii=False,
            ),
        },
        {
            "role": "assistant",
            "content": json.dumps(
                {
                    "validacion": "Qué desgastante llegar al grito en plena rabieta.",
                    "lectura_conducta": None,
                    "estrategias": [
                        "Baja tu voz y ofrécele un lugar seguro elegido de antemano "
                        "(Fuente: TBRI — Principios de Corrección, p.25)."
                    ],
                    "limite_de_la_guia": None,
                    "senal_alerta": None,
                    "derivar_a_profesional": False,
                },
                ensure_ascii=False,
            ),
        },
    ]
