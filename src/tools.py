"""Tools del agente de CrianzApp (Avance 3).

Cada función es invocable directamente sin LLM (para probarla o para que el
agente la ejecute) y expone, además, el esquema JSON que se envía a Groq en
`TOOLS_SCHEMA`. Los límites (cantidad de fragmentos, longitud, dominios web
permitidos) están fijos en este archivo, no en el prompt: el LLM no puede
ampliarlos describiendo algo distinto en su mensaje.
"""

from __future__ import annotations

import logging
import os
import re
import unicodedata
from typing import Any

from tavily import TavilyClient

from src.knowledge_base import BaseConocimientoLocal

LOGGER = logging.getLogger(__name__)

# ----------------------------------------------------------- buscar_en_base
MAX_FRAGMENTOS_TOOL = 4
MAX_CARACTERES_FRAGMENTO = 600


def buscar_en_base(consulta: str, base: BaseConocimientoLocal) -> list[dict[str, Any]]:
    """Busca evidencia en la guía de crianza (TBRI y artículos académicos).

    Úsala para cualquier pregunta sobre crianza, apego, regulación emocional,
    corrección respetuosa o cualquier práctica descrita en la guía. Es la
    tool que debes intentar primero, siempre. Devuelve como máximo 4
    fragmentos (cada uno truncado a 600 caracteres) con su documento y
    página o sección, para poder citarlos. Si no hay evidencia suficiente
    devuelve una lista vacía: no inventes una respuesta en ese caso.
    """
    if not consulta.strip():
        return []
    fragmentos = base.buscar(consulta, limite=MAX_FRAGMENTOS_TOOL)
    return [
        {
            "documento": fragmento.titulo or fragmento.fuente,
            "pagina": fragmento.page,
            "seccion": fragmento.section,
            "texto": fragmento.texto[:MAX_CARACTERES_FRAGMENTO],
        }
        for fragmento in fragmentos
    ]


# --------------------------------------------------------- generar_referencia_apa
# Datos reales tomados de los PDF originales en docs/fuentes_originales/
# (portada y encabezados). No se inventa ningún dato bibliográfico.
_REFERENCIAS_APA: dict[str, str] = {
    "conexion": (
        "Instituto de Desarrollo Infantil Karyn Purvis (ICD). (2013). "
        "Principios de Conexión de TBRI®: Libro de trabajo del participante."
    ),
    "correccion": (
        "Instituto de Desarrollo Infantil Karyn Purvis (ICD). (2013). "
        "Principios de Corrección de TBRI®: Libro de trabajo del participante."
    ),
    "empoderamiento": (
        "Instituto de Desarrollo Infantil Karyn Purvis (ICD). (2013). "
        "Principios de Empoderamiento de TBRI®: Libro de trabajo del "
        "participante."
    ),
    "gomez muzzio": (
        "Gómez Muzzio, E., Muñoz, M. M., & Santelices, M. P. (2008). "
        "Efectividad de las intervenciones en apego con infancia vulnerada y "
        "en riesgo social: Un desafío prioritario para Chile. Terapia "
        "Psicológica, 26(2), 241-251."
    ),
    "lin-lewry": (
        "Lin-Lewry, M., Nguyen, C. T. T., Huda, M. H., Tsai, S.-Y., "
        "Chipojola, R., & Kuo, S.-Y. (2024). Effects of digital parenting "
        "interventions on self-efficacy, social support, and depressive "
        "symptoms in the transition to parenthood: A systematic review and "
        "meta-analysis. International Journal of Medical Informatics, 185, "
        "105405. https://doi.org/10.1016/j.ijmedinf.2024.105405"
    ),
}
# Palabras clave que identifican cada documento en lenguaje libre.
_ALIAS_DOCUMENTO: dict[str, str] = {
    "conexion": "conexion",
    "connection": "conexion",
    "correccion": "correccion",
    "correction": "correccion",
    "empoderamiento": "empoderamiento",
    "empowerment": "empoderamiento",
    "gomez": "gomez muzzio",
    "muzzio": "gomez muzzio",
    "apego": "gomez muzzio",
    "lin lewry": "lin-lewry",
    "lin-lewry": "lin-lewry",
    "lewry": "lin-lewry",
    "digital": "lin-lewry",
    "postparto": "lin-lewry",
}


def _sin_tildes(texto: str) -> str:
    normalizado = unicodedata.normalize("NFD", texto.lower())
    return "".join(c for c in normalizado if unicodedata.category(c) != "Mn")


def generar_referencia_apa(documento: str) -> dict[str, str]:
    """Genera la referencia bibliográfica en formato APA de un documento del
    corpus (los tres libros de participante de TBRI® o los dos artículos
    académicos).

    Úsala cuando te pidan citar, referenciar o dar la referencia APA de un
    documento. Recibe el nombre o tema del documento tal como lo mencione la
    persona (p. ej. "el de empoderamiento" o "el artículo de Gómez Muzzio").
    Las referencias son fijas y reales (tomadas de los PDF originales): la
    tool nunca inventa datos bibliográficos. Si el documento no se reconoce,
    devuelve un error en vez de adivinar una referencia.
    """
    clave_normalizada = _sin_tildes(documento)
    for alias, clave in _ALIAS_DOCUMENTO.items():
        if alias in clave_normalizada:
            return {"documento": clave, "referencia_apa": _REFERENCIAS_APA[clave]}
    return {
        "error": (
            "Documento no reconocido en la base. Los documentos disponibles "
            "son: TBRI Conexión, TBRI Corrección, TBRI Empoderamiento, "
            "Gómez Muzzio (2008) y Lin-Lewry (2024)."
        )
    }


# ----------------------------------------------------------------- buscar_en_web
MAX_RESULTADOS_WEB = 3
MAX_CARACTERES_EXTRACTO_WEB = 300
# Fijo en código: el LLM no puede ampliar ni cambiar esta lista.
DOMINIOS_PERMITIDOS_WEB = [
    "child.tcu.edu",      # Instituto Karyn Purvis / TBRI oficial
    "icbf.gov.co",        # Autoridad colombiana de protección infantil
    "who.int",            # Organización Mundial de la Salud
    "unicef.org",         # UNICEF
    "healthychildren.org",  # Academia Americana de Pediatría (AAP)
    "cdc.gov",            # Centros para el Control de Enfermedades (EE. UU.)
]


def buscar_en_web(consulta: str, se_uso_base: bool) -> list[dict[str, Any]]:
    """Busca información pública y vigente en sitios oficiales/confiables.

    Solo debes llamar esta tool si antes intentaste `buscar_en_base` para la
    misma pregunta y no encontró evidencia suficiente, Y la pregunta trata de
    información pública o actual (una norma vigente, una definición general,
    una cifra o versión reciente) y no de contenido interno de la guía TBRI.
    Nunca la uses como primera opción. Busca solo en un conjunto fijo de
    sitios oficiales/confiables (no en todo internet) y devuelve como máximo
    3 resultados, cada uno con título, URL y un extracto corto marcado como
    "web", nunca el contenido completo de la página.
    """
    if not se_uso_base:
        return [
            {
                "error": (
                    "Debes intentar buscar_en_base primero para esta "
                    "pregunta antes de buscar en la web."
                )
            }
        ]
    api_key = os.getenv("TAVILY_API_KEY", "").strip()
    if not api_key:
        return [{"error": "La búsqueda web no está configurada (falta TAVILY_API_KEY)."}]
    try:
        cliente = TavilyClient(api_key=api_key)
        resultado = cliente.search(
            query=consulta,
            include_domains=DOMINIOS_PERMITIDOS_WEB,
            max_results=MAX_RESULTADOS_WEB,
        )
    except Exception:
        LOGGER.warning("Falló la búsqueda web con Tavily", exc_info=True)
        return [{"error": "No se pudo completar la búsqueda web en este momento."}]
    return [
        {
            "titulo": item.get("title", ""),
            "url": item.get("url", ""),
            "extracto": (item.get("content") or "")[:MAX_CARACTERES_EXTRACTO_WEB],
            "origen": "web",
        }
        for item in (resultado.get("results") or [])[:MAX_RESULTADOS_WEB]
    ]


# --------------------------------------------------------------- esquema Groq
TOOLS_SCHEMA = [
    {
        "type": "function",
        "function": {
            "name": "buscar_en_base",
            "description": buscar_en_base.__doc__.strip(),
            "parameters": {
                "type": "object",
                "properties": {
                    "consulta": {
                        "type": "string",
                        "description": "Pregunta o tema a buscar en la guía de crianza.",
                    }
                },
                "required": ["consulta"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "generar_referencia_apa",
            "description": generar_referencia_apa.__doc__.strip(),
            "parameters": {
                "type": "object",
                "properties": {
                    "documento": {
                        "type": "string",
                        "description": "Nombre o tema del documento a referenciar.",
                    }
                },
                "required": ["documento"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "buscar_en_web",
            "description": buscar_en_web.__doc__.strip(),
            "parameters": {
                "type": "object",
                "properties": {
                    "consulta": {
                        "type": "string",
                        "description": "Qué buscar en la web.",
                    },
                    "se_uso_base": {
                        "type": "boolean",
                        "description": (
                            "true solo si ya llamaste a buscar_en_base para "
                            "esta misma pregunta en este turno."
                        ),
                    },
                },
                "required": ["consulta", "se_uso_base"],
            },
        },
    },
]
