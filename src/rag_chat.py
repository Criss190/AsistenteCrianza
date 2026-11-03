"""Recuperación de evidencia y generación conversacional segura."""

from __future__ import annotations

import json
import logging
import os
import re
import unicodedata
from pathlib import Path
from time import perf_counter
from typing import Any

from src.knowledge_base import BaseConocimientoLocal, FragmentoConocimiento
from src.output_formatter import validar_formato
from src.prompt_builder import build_prompt


BASE_CONOCIMIENTO_DIR = (
    Path(__file__).resolve().parent.parent / "docs" / "base_conocimiento"
)
MODELO_GROQ_PREDETERMINADO = "openai/gpt-oss-120b"
MENSAJE_SIN_EVIDENCIA = (
    "Mi especialidad es la crianza responsable y no encontré información "
    "suficiente en la base de conocimientos para responder con seguridad. "
    "Si tienes una consulta relacionada con crianza, puedo ayudarte."
)
MENSAJE_ALERTA = (
    "Gracias por contarlo. La seguridad del niño o la niña es lo primero. "
    "Cree en lo que te cuenta, escúchale con calma y evita confrontar a la "
    "persona señalada o pedirle que repita la historia. Busca ayuda de "
    "protección infantil de inmediato; en Colombia puedes llamar al ICBF, "
    "línea 141. Si existe peligro inmediato, llama al 123."
)
PATRONES_ALERTA = re.compile(
    r"\b(abuso|abusos|abusad\w*|violencia|violent\w*|maltrat\w*|"
    r"golpe\w*|pega\w*|amenaz\w*|toca\w*|tocamiento\w*|"
    r"violacion|violaciones|acoso sexual|abuso sexual|explotacion sexual|"
    r"suicid\w*|autolesion\w*|hacerme dano|hacerse dano|"
    r"quiere morir|quiero morir|no quiero vivir)\b"
)
LOGGER = logging.getLogger(__name__)


class ChatRAG:
    """Combina Chroma, el prompt de CrianzApp y Groq si hay una clave."""

    def __init__(
        self,
        directorio_conocimiento: str | Path = BASE_CONOCIMIENTO_DIR,
        directorio_vectorstore: str | Path | None = None,
        chunk_size: int = 500,
        chunk_overlap: int = 50,
        top_k: int = 3,
    ) -> None:
        if top_k <= 0:
            raise ValueError("top_k debe ser mayor que cero.")
        self.base_conocimiento = BaseConocimientoLocal.cargar(
            directorio_conocimiento,
            directorio_vectorstore,
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap,
        )
        self.top_k = top_k
        self.api_key = os.getenv("GROQ_API_KEY", "").strip()
        self.modelo = os.getenv("GROQ_MODEL", MODELO_GROQ_PREDETERMINADO).strip()

    def estado(self) -> dict[str, Any]:
        """Devuelve información de disponibilidad sin revelar credenciales."""
        return {
            "status": "ok",
            "knowledge_chunks": len(self.base_conocimiento.fragmentos),
            "llm_configured": bool(self.api_key),
            "model": self.modelo if self.api_key else None,
        }

    def responder(
        self, mensaje: str, historial: list[dict[str, Any]] | None = None
    ) -> dict[str, Any]:
        """Responde solo a partir del mensaje actual y evidencia recuperada.

        `historial` se conserva por compatibilidad con clientes anteriores,
        pero se ignora para evitar arrastre de temas y envío de datos al LLM.
        """
        del historial
        fragmentos = self.base_conocimiento.buscar(mensaje, limite=self.top_k)
        fuentes = self._formatear_fuentes(fragmentos)
        contextos = [fragmento.texto for fragmento in fragmentos]

        if self._es_situacion_de_riesgo(mensaje):
            return self._resultado(
                MENSAJE_ALERTA,
                fuentes,
                contextos,
                "safety",
                "Por seguridad, esta situación requiere acompañamiento humano.",
            )

        if not fragmentos:
            return self._resultado(
                MENSAJE_SIN_EVIDENCIA, [], [], "no_evidence", None
            )

        if not self.api_key:
            return self._respuesta_local(fragmentos, fuentes, contextos)

        try:
            respuesta = self._generar_con_groq(mensaje, fragmentos)
        except Exception:
            LOGGER.exception("No se pudo generar una respuesta válida con Groq")
            return self._respuesta_local(
                fragmentos,
                fuentes,
                contextos,
                notice=(
                    "No fue posible generar una respuesta; te comparto "
                    "directamente la evidencia local recuperada."
                ),
            )
        return self._resultado(respuesta, fuentes, contextos, "groq", None)

    def _generar_con_groq(
        self,
        mensaje: str,
        fragmentos: list[FragmentoConocimiento],
    ) -> str:
        """Genera una respuesta estructurada a partir de los fragmentos citados."""
        from groq import Groq

        contexto = "\n\n".join(
            f"[Fuente: {fragmento.fuente}]\n{fragmento.texto}"
            for fragmento in fragmentos
        )
        mensajes = build_prompt(mensaje, contexto)
        cliente = Groq(api_key=self.api_key, timeout=25.0, max_retries=1)
        inicio = perf_counter()
        completion = cliente.chat.completions.create(
            model=self.modelo,
            messages=mensajes,
            temperature=0.2,
            max_tokens=350,
            response_format={"type": "json_object"},
        )
        uso = completion.usage
        LOGGER.info(
            "Groq completado model=%s input_tokens=%s output_tokens=%s "
            "latency_ms=%.0f",
            self.modelo,
            getattr(uso, "prompt_tokens", None),
            getattr(uso, "completion_tokens", None),
            (perf_counter() - inicio) * 1000,
        )
        contenido = completion.choices[0].message.content
        if not contenido:
            raise ValueError("Groq devolvió una respuesta vacía.")

        datos = json.loads(contenido)
        validar_formato(datos)
        estrategias = datos["estrategias"]
        if not isinstance(datos["resumen_breve"], str) or not all(
            isinstance(estrategia, str) and estrategia.strip()
            for estrategia in estrategias
        ):
            raise ValueError("El modelo devolvió una respuesta fuera del contrato.")

        partes = [datos["resumen_breve"].strip()]
        if estrategias:
            partes.append("\n".join(f"• {texto.strip()}" for texto in estrategias))
        if datos["senal_alerta"]:
            partes.append(f"Nota importante: {datos['senal_alerta'].strip()}")
        if datos["derivar_a_profesional"]:
            partes.append(
                "Esta orientación no reemplaza la atención de un profesional."
            )
        return "\n\n".join(partes)

    @staticmethod
    def _respuesta_local(
        fragmentos: list[FragmentoConocimiento],
        fuentes: list[dict[str, Any]],
        contextos: list[str],
        notice: str | None = None,
    ) -> dict[str, Any]:
        extractos = [f"• {fragmento.texto}" for fragmento in fragmentos]
        respuesta = (
            "Encontré estas orientaciones en la guía local. "
            "Te las comparto directamente, sin generar información nueva:\n\n"
            + "\n\n".join(extractos)
        )
        return ChatRAG._resultado(respuesta, fuentes, contextos, "local", notice)

    @staticmethod
    def _resultado(
        respuesta: str,
        fuentes: list[dict[str, Any]],
        contextos: list[str],
        modo: str,
        aviso: str | None,
    ) -> dict[str, Any]:
        """Incluye claves de compatibilidad y campos en español para la API."""
        return {
            "answer": respuesta,
            "respuesta": respuesta,
            "sources": fuentes,
            "fuentes": fuentes,
            "contexts": contextos,
            "mode": modo,
            "notice": aviso,
        }

    @staticmethod
    def _formatear_fuentes(
        fragmentos: list[FragmentoConocimiento],
    ) -> list[dict[str, Any]]:
        return [
            {
                "name": fragmento.fuente,
                "source": fragmento.fuente,
                "excerpt": fragmento.texto,
                "chunk_id": fragmento.chunk_id,
                "page": fragmento.page,
                "section": fragmento.section,
            }
            for fragmento in fragmentos
        ]

    @staticmethod
    def _es_situacion_de_riesgo(texto: str) -> bool:
        normalizado = unicodedata.normalize("NFD", texto.lower())
        sin_acentos = "".join(
            caracter
            for caracter in normalizado
            if unicodedata.category(caracter) != "Mn"
        )
        return bool(PATRONES_ALERTA.search(sin_acentos))
