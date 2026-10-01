"""Recuperación de evidencia y generación segura para el chat de CrianzApp."""

import json
import os
import re
import unicodedata
from pathlib import Path
from typing import Any

from src.knowledge_base import BaseConocimientoLocal, FragmentoConocimiento
from src.output_formatter import validar_formato
from src.prompt_builder import build_prompt


BASE_CONOCIMIENTO_DIR = (
    Path(__file__).resolve().parent.parent / "docs" / "base_conocimiento"
)
MODELO_GROQ_PREDETERMINADO = "llama-3.3-70b-versatile"

MENSAJE_SIN_EVIDENCIA = (
    "No encontré información suficiente en la guía de crianza para responder "
    "con seguridad. Puedes reformular la pregunta o consultar a un profesional "
    "de salud infantil."
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


class ChatRAG:
    """Une la base Markdown local con Groq cuando hay una API key configurada."""

    def __init__(self, directorio_conocimiento: str | Path = BASE_CONOCIMIENTO_DIR):
        self.base_conocimiento = BaseConocimientoLocal.cargar(directorio_conocimiento)
        self.api_key = os.getenv("GROQ_API_KEY", "").strip()
        self.modelo = os.getenv("GROQ_MODEL", MODELO_GROQ_PREDETERMINADO).strip()

    def estado(self) -> dict[str, Any]:
        """Devuelve información no sensible para el endpoint de salud."""
        return {
            "status": "ok",
            "knowledge_chunks": len(self.base_conocimiento.fragmentos),
            "llm_configured": bool(self.api_key),
            "model": self.modelo if self.api_key else None,
        }

    def responder(
        self, mensaje: str, historial: list[dict[str, Any]] | None = None
    ) -> dict[str, Any]:
        """Recupera fragmentos, aplica las reglas de seguridad y genera la respuesta."""
        historial_seguro = self._limpiar_historial(historial or [])
        consulta_recuperacion = self._consulta_con_historial(mensaje, historial_seguro)
        fragmentos = self.base_conocimiento.buscar(consulta_recuperacion, limite=4)
        fuentes = self._formatear_fuentes(fragmentos)

        texto_sensible = " ".join(
            [mensaje, *(turno["content"] for turno in historial_seguro)]
        )
        if self._es_situacion_de_riesgo(texto_sensible):
            return {
                "answer": MENSAJE_ALERTA,
                "sources": fuentes,
                "mode": "safety",
                "notice": "Por seguridad, esta situación requiere acompañamiento humano.",
            }

        if not fragmentos:
            return {
                "answer": MENSAJE_SIN_EVIDENCIA,
                "sources": [],
                "mode": "no_evidence",
                "notice": None,
            }

        if not self.api_key:
            return self._respuesta_local(fragmentos, fuentes)

        try:
            respuesta = self._generar_con_groq(mensaje, historial_seguro, fragmentos)
            return {
                "answer": respuesta,
                "sources": fuentes,
                "mode": "groq",
                "notice": None,
            }
        except Exception:
            # El chat sigue siendo utilizable aunque el proveedor remoto no responda.
            return self._respuesta_local(
                fragmentos,
                fuentes,
                notice=(
                    "No fue posible conectar con Groq; te comparto directamente "
                    "la evidencia local recuperada."
                ),
            )

    def _generar_con_groq(
        self,
        mensaje: str,
        historial: list[dict[str, str]],
        fragmentos: list[FragmentoConocimiento],
    ) -> str:
        """Envía a Groq el prompt del proyecto aumentado con evidencia recuperada."""
        from groq import Groq

        contexto = "\n\n".join(
            f"[Fuente: {fragmento.fuente}]\n{fragmento.texto}"
            for fragmento in fragmentos
        )
        antecedentes = "\n".join(
            f"{turno['role']}: {turno['content']}" for turno in historial[-6:]
        )
        prompt = build_prompt(
            contexto_usuario=antecedentes,
            pregunta_usuario=mensaje,
            conocimiento_recuperado=contexto,
        )
        cliente = Groq(api_key=self.api_key, timeout=25.0, max_retries=1)
        completion = cliente.chat.completions.create(
            model=self.modelo,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.2,
            max_tokens=550,
            response_format={"type": "json_object"},
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
        fuentes: list[dict[str, str]],
        notice: str | None = None,
    ) -> dict[str, Any]:
        extractos = [f"• {fragmento.texto}" for fragmento in fragmentos[:3]]
        return {
            "answer": (
                "Encontré estas orientaciones en la guía local. "
                "Te las comparto directamente, sin generar información nueva:\n\n"
                + "\n\n".join(extractos)
            ),
            "sources": fuentes,
            "mode": "local",
            "notice": notice,
        }

    @staticmethod
    def _formatear_fuentes(
        fragmentos: list[FragmentoConocimiento],
    ) -> list[dict[str, str]]:
        return [
            {
                "name": fragmento.fuente,
                "excerpt": fragmento.texto[:240],
            }
            for fragmento in fragmentos
        ]

    @staticmethod
    def _limpiar_historial(historial: list[dict[str, Any]]) -> list[dict[str, str]]:
        limpio = []
        for turno in historial[-8:]:
            if not isinstance(turno, dict):
                continue
            role = turno.get("role")
            content = turno.get("content")
            if role in {"user", "assistant"} and isinstance(content, str):
                content = content.strip()[:800]
                if content:
                    limpio.append({"role": role, "content": content})
        return limpio

    @staticmethod
    def _consulta_con_historial(
        mensaje: str, historial: list[dict[str, str]]
    ) -> str:
        preguntas_previas = [
            turno["content"] for turno in historial if turno["role"] == "user"
        ][-2:]
        return " ".join([*preguntas_previas, mensaje])

    @staticmethod
    def _es_situacion_de_riesgo(texto: str) -> bool:
        normalizado = unicodedata.normalize("NFD", texto.lower())
        sin_acentos = "".join(
            caracter
            for caracter in normalizado
            if unicodedata.category(caracter) != "Mn"
        )
        return bool(PATRONES_ALERTA.search(sin_acentos))
