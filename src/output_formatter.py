# -*- coding: utf-8 -*-
"""
output_formatter.py
---------------------
Define el "contrato" de salida del asistente (el mismo formato exigido en
el System Prompt) y una función de validación que comprueba que una
respuesta cumple ese contrato.

Al no conectarse a un LLM real en este proyecto, `output_formatter`
genera respuestas deterministas a partir de fragmentos recuperados desde
la base de conocimiento local y conserva una ruta de simulación para
compatibilidad con la demo original.
"""

CLAVES_ESPERADAS = {
    "resumen_breve": str,
    "estrategias": list,
    "senal_alerta": (str, type(None)),
    "derivar_a_profesional": bool,
}

PALABRAS_ALERTA = [
    "abuso", "toca", "golpea", "golpe", "maltrato", "violencia",
    "encierra", "amenaza", "abandono", "self-harm", "suicid",
]


def validar_formato(respuesta: dict) -> bool:
    """
    Verifica que `respuesta` tenga exactamente las claves y tipos
    definidos en CLAVES_ESPERADAS. Lanza ValueError con el detalle si no
    cumple el contrato.
    """
    claves_respuesta = set(respuesta.keys())
    claves_definidas = set(CLAVES_ESPERADAS.keys())

    if claves_respuesta != claves_definidas:
        faltantes = claves_definidas - claves_respuesta
        sobrantes = claves_respuesta - claves_definidas
        raise ValueError(
            f"Formato inválido. Faltan claves: {faltantes or 'ninguna'} | "
            f"Claves no permitidas: {sobrantes or 'ninguna'}"
        )

    for clave, tipo_esperado in CLAVES_ESPERADAS.items():
        if not isinstance(respuesta[clave], tipo_esperado):
            raise ValueError(
                f"La clave '{clave}' debe ser de tipo {tipo_esperado}, "
                f"llegó {type(respuesta[clave])}."
            )
    return True


def generar_respuesta_simulada(contexto: str, pregunta: str) -> dict:
    """
    Genera una respuesta de ejemplo (NO usa ningún LLM) para demostrar
    cómo luciría la salida del asistente cumpliendo el formato definido
    en el System Prompt. La lógica es una regla simple basada en
    palabras clave, suficiente para el alcance de este entregable
    (diseño de prompts, no inferencia real).
    """
    texto_completo = f"{contexto} {pregunta}".lower()
    hay_alerta = any(palabra in texto_completo for palabra in PALABRAS_ALERTA)

    if hay_alerta:
        respuesta = {
            "resumen_breve": (
                "Gracias por compartir esta situación; lo que describes "
                "requiere atención profesional inmediata."
            ),
            "estrategias": [
                "Cree en lo que el niño o niña te está contando.",
                "No lo confrontes ni lo hagas repetir la historia varias veces.",
                "Contacta cuanto antes a una entidad especializada en "
                "protección infantil (en Colombia: ICBF, línea 141).",
            ],
            "senal_alerta": (
                "El relato contiene indicios de posible riesgo o "
                "vulneración hacia el menor."
            ),
            "derivar_a_profesional": True,
        }
    else:
        respuesta = {
            "resumen_breve": (
                "Entiendo la situación que describes; es un reto habitual "
                "en esta etapa del desarrollo."
            ),
            "estrategias": [
                "Anticipa el límite antes del momento de conflicto.",
                "Valida la emoción del niño/a sin ceder el límite.",
                "Mantén la calma y la coherencia en la respuesta.",
                "Refuerza positivamente cuando logre regularse.",
            ],
            "senal_alerta": None,
            "derivar_a_profesional": False,
        }

    validar_formato(respuesta)
    return respuesta


def generar_respuesta_local(contexto: str, pregunta: str, fragmentos: list) -> dict:
    """Responde con fragmentos de la base local, sin usar un LLM."""
    texto_completo = f"{contexto} {pregunta}".lower()
    hay_alerta = any(palabra in texto_completo for palabra in PALABRAS_ALERTA)

    if hay_alerta:
        respuesta = {
            "resumen_breve": (
                "Gracias por compartir esta situación; lo que describes "
                "requiere atención profesional inmediata."
            ),
            "estrategias": [
                "Cree en lo que el niño o niña te está contando.",
                "No lo confrontes ni lo hagas repetir la historia varias veces.",
                "Contacta cuanto antes a una entidad especializada en "
                "protección infantil (en Colombia: ICBF, línea 141).",
            ],
            "senal_alerta": (
                "El relato contiene indicios de posible riesgo o "
                "vulneración hacia el menor."
            ),
            "derivar_a_profesional": True,
        }
    elif fragmentos:
        respuesta = {
            "resumen_breve": (
                "Encontré información relacionada en la base de "
                "conocimiento local. Estas son las orientaciones "
                "recuperadas para tu consulta."
            ),
            "estrategias": [fragmento.texto for fragmento in fragmentos[:4]],
            "senal_alerta": None,
            "derivar_a_profesional": False,
        }
    else:
        respuesta = {
            "resumen_breve": (
                "No encontré información suficiente en la base de "
                "conocimiento local para responder con seguridad."
            ),
            "estrategias": [
                "Reformula la pregunta con términos más específicos.",
                "Consulta una fuente profesional relacionada con tu situación.",
            ],
            "senal_alerta": None,
            "derivar_a_profesional": False,
        }

    validar_formato(respuesta)
    return respuesta
