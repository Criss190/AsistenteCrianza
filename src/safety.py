"""Clasificación determinística de señales de riesgo, compartida por el
pipeline fijo (`ChatRAG`, Avance 2) y el agente (`AgenteCrianza`, Avance 3).

El riesgo nunca se delega al LLM: depende solo de patrones léxicos sobre el
mensaje actual, para que sea confiable y no dependa del historial ni de la
disponibilidad de Groq.
"""

from __future__ import annotations

import re
import unicodedata

MENSAJE_ALERTA = (
    "Gracias por contarlo. La seguridad del niño o la niña es lo primero. "
    "Cree en lo que te cuenta, escúchale con calma y evita confrontar a la "
    "persona señalada o pedirle que repita la historia. Busca ayuda de "
    "protección infantil de inmediato; en Colombia puedes llamar al ICBF, "
    "línea 141. Si existe peligro inmediato, llama al 123."
)
MENSAJE_AUTOLESION = (
    "Gracias por contarlo; lo que se siente importa y no tienes que "
    "enfrentarlo a solas. Si hay peligro inmediato, llama al 123. En Colombia "
    "también puedes hablar ahora con la Línea 106, gratuita, confidencial y "
    "disponible las 24 horas, con profesionales de salud mental. Si se trata "
    "de tu hijo o hija, quédate a su lado, escúchale sin juzgar, retira lo que "
    "pueda usar para hacerse daño y busca atención de salud mental cuanto antes."
)
MENSAJE_RIESGO_ADULTO = (
    "Gracias por decirlo con honestidad: frenar a tiempo es lo más protector "
    "que puedes hacer. Asegúrate de que el niño o la niña esté en un lugar "
    "seguro, aléjate unos minutos a otro espacio, respira despacio y toma "
    "agua. Si puedes, pide a otro adulto que se quede con él o ella. En "
    "Colombia, la Línea 106 (gratuita, confidencial, 24 horas) te acompaña en "
    "ese momento; si hay peligro inmediato, llama al 123. La línea 141 del "
    "ICBF orienta a las familias sobre protección y crianza."
)
PATRONES_ABUSO = re.compile(
    r"\b(abuso(?: sexual)?|abusad\w*|violacion\w*|acoso sexual|"
    r"explotacion sexual|tocamiento\w*|maltrato infantil|"
    r"violencia (?:intrafamiliar|domestica|sexual|familiar|en casa))\b|"
    r"\bfamiliar\w*.{0,60}\b(?:la|lo)\s+(?:toca|toco)\b"
)
PATRONES_AUTOLESION = re.compile(
    r"\b(suicid\w*|autolesion\w*|hacerme dano|hacerse dano|quiere morir|"
    r"quiero morir|no quiero vivir|quitarme la vida|quitarse la vida|"
    r"matarme|matarse|cortarme las venas)\b"
)
PATRONES_RIESGO_ADULTO = re.compile(
    r"\b(?:ganas de|voy a|temo|me da miedo|miedo de|siento que (?:le )?voy a|"
    r"no puedo evitar|no me controlo|podria)\b.{0,50}"
    r"\b(?:hacerle dano|lastimarl[oae]|golpearl[oae]|pegarle|matarl[oae])\b"
)
PATRONES_DANO_A_NINO = re.compile(
    r"\b(?:mi hijo|mi hija|mi nino|mi nina|el nino|la nina|menor)\b"
    r".{0,60}\b(?:fue golpead\w*|fue maltratad\w*|le pegaron|"
    r"la golpearon|lo golpearon|la maltrataron|lo maltrataron)\b|"
    r"\b(?:adulto|familiar|padrastro|madrastra|cuidador|maestro|docente)\w*"
    r".{0,60}\b(?:golpeo|pego|maltrato|amenazo)\b"
    r".{0,40}\b(?:mi hijo|mi hija|mi nino|mi nina|menor)\b"
)

MENSAJES_POR_TIPO = {
    "autolesion": MENSAJE_AUTOLESION,
    "riesgo_adulto": MENSAJE_RIESGO_ADULTO,
    "abuso": MENSAJE_ALERTA,
}


def normalizar(texto: str) -> str:
    """Minúsculas y sin tildes, para que los patrones no dependan de acentos."""
    normalizado = unicodedata.normalize("NFD", texto.lower())
    sin_acentos = "".join(
        caracter for caracter in normalizado if unicodedata.category(caracter) != "Mn"
    )
    return re.sub(r"\s+", " ", sin_acentos).strip()


def clasificar_riesgo(texto: str) -> str | None:
    """Devuelve 'autolesion', 'riesgo_adulto', 'abuso' o None.

    Depende únicamente del texto recibido (nunca del historial de la
    conversación), para que una revelación en un turno anterior no "contamine"
    una pregunta nueva no relacionada, y para que el comportamiento sea el
    mismo sin importar si responde el pipeline fijo o el agente.
    """
    normalizado = normalizar(texto)
    if PATRONES_AUTOLESION.search(normalizado):
        return "autolesion"
    if PATRONES_RIESGO_ADULTO.search(normalizado):
        return "riesgo_adulto"
    if PATRONES_ABUSO.search(normalizado) or PATRONES_DANO_A_NINO.search(normalizado):
        return "abuso"
    return None


def es_situacion_de_riesgo(texto: str) -> bool:
    return clasificar_riesgo(texto) is not None


def mensaje_de_seguridad(tipo_riesgo: str) -> str:
    return MENSAJES_POR_TIPO[tipo_riesgo]
