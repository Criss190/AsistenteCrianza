"""Agente CrianzApp (Avance 3): el LLM decide cuándo y qué tool usar.

A diferencia de `src/rag_chat.py` (Avance 2, pipeline fijo: siempre recupera
evidencia y la inyecta en el prompt), aquí el modelo recibe únicamente las
tools (`src/tools.py`) y decide si las llama, en qué orden y cuántas veces,
hasta `MAX_ITERACIONES` idas y vueltas con Groq. La clasificación de riesgo
sigue siendo determinística (`src/safety.py`), igual que en Avance 2.
"""

from __future__ import annotations

import json
import logging
import os
import re
import time
from pathlib import Path
from typing import Any

from src.agent_few_shot import construir_few_shot
from src.agent_system_prompt import AGENTE_SYSTEM_PROMPT
from src.knowledge_base import (
    BaseConocimientoLocal,
    SOLAPAMIENTO_FRAGMENTO,
    TAMANO_FRAGMENTO,
)
from src.output_formatter import limpiar_texto_modelo, validar_formato
from src.rag_chat import BASE_CONOCIMIENTO_DIR, _entero_entorno
from src.safety import clasificar_riesgo, mensaje_de_seguridad
from src.tools import TOOLS_SCHEMA, buscar_en_base, buscar_en_web, generar_referencia_apa

LOGGER = logging.getLogger(__name__)

MODELO_GROQ_PREDETERMINADO = "openai/gpt-oss-120b"
MAX_TOKENS_RESPUESTA = 2500
MAX_ITERACIONES = 4
MAX_TURNOS_HISTORIAL = 4

MENSAJE_SIN_EVIDENCIA = (
    "Mi especialidad es la crianza responsable y no encontré información "
    "suficiente en la guía ni en fuentes públicas confiables para responder "
    "esto con seguridad."
)
MENSAJE_SIN_LLM = (
    "El agente necesita un modelo con tool calling (GROQ_API_KEY) para "
    "decidir qué herramienta usar; no está configurado en este entorno."
)

LOG_PATH = (
    Path(__file__).resolve().parent.parent
    / "scripts_ragas"
    / "results"
    / "agent_log.jsonl"
)

_PATRON_CITA_BASE = re.compile(r"\(Fuente:\s*[^)]+\)")
_PATRON_CITA_WEB = re.compile(r"\[web:\s*[^\]]+\]")


def _tiene_cita(texto: str) -> bool:
    return bool(_PATRON_CITA_BASE.search(texto) or _PATRON_CITA_WEB.search(texto))


class AgenteCrianza:
    """Loop de tool-calling con Groq sobre las tools de `src/tools.py`."""

    def __init__(
        self,
        directorio_conocimiento: str | Path = BASE_CONOCIMIENTO_DIR,
        directorio_vectorstore: str | Path | None = None,
        chunk_size: int | None = None,
        chunk_overlap: int | None = None,
    ) -> None:
        chunk_size = chunk_size or _entero_entorno("RAG_CHUNK_SIZE", TAMANO_FRAGMENTO)
        chunk_overlap = (
            chunk_overlap
            if chunk_overlap is not None
            else _entero_entorno("RAG_CHUNK_OVERLAP", SOLAPAMIENTO_FRAGMENTO)
        )
        self.base_conocimiento = BaseConocimientoLocal.cargar(
            directorio_conocimiento,
            directorio_vectorstore,
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap,
        )
        self.api_key = os.getenv("GROQ_API_KEY", "").strip()
        self.modelo = os.getenv("GROQ_MODEL", MODELO_GROQ_PREDETERMINADO).strip()
        self._cliente: Any = None
        if not self.api_key:
            LOGGER.warning(
                "GROQ_API_KEY no está configurada: el agente no puede "
                "decidir ni llamar tools sin un modelo con tool calling."
            )

    def estado(self) -> dict[str, Any]:
        return {
            "status": "ok",
            "knowledge_chunks": len(self.base_conocimiento.fragmentos),
            "llm_configured": bool(self.api_key),
            "model": self.modelo if self.api_key else None,
        }

    # ------------------------------------------------------------------ flujo
    def responder(
        self, mensaje: str, historial: list[dict[str, Any]] | None = None
    ) -> dict[str, Any]:
        tipo_riesgo = clasificar_riesgo(mensaje)
        if tipo_riesgo:
            return self._resultado(
                mensaje_de_seguridad(tipo_riesgo),
                [],
                [],
                "safety",
                "Por seguridad, esta situación requiere acompañamiento humano.",
                tool_calls=[],
                llamadas_llm=0,
            )

        if not self.api_key:
            return self._resultado(
                MENSAJE_SIN_LLM, [], [], "no_llm", None, tool_calls=[], llamadas_llm=0
            )

        historial = [
            turno
            for turno in (historial or [])
            if isinstance(turno, dict) and isinstance(turno.get("content"), str)
        ][-MAX_TURNOS_HISTORIAL:]

        mensajes: list[dict[str, Any]] = [
            {"role": "system", "content": AGENTE_SYSTEM_PROMPT.strip()},
            *construir_few_shot(),
            *[{"role": t["role"], "content": t["content"]} for t in historial],
            {"role": "user", "content": mensaje},
        ]

        registro_tools: list[dict[str, Any]] = []
        fuentes_base: list[dict[str, Any]] = []
        fuentes_web: list[dict[str, Any]] = []
        se_uso_base = False
        se_uso_apa = False
        llamadas_llm = 0
        tokens_totales = 0
        inicio = time.perf_counter()
        resultado_final: dict[str, Any] | None = None
        modo_correccion = False  # Groq no permite combinar tools+json_object:
        # la llamada normal lleva tools; una corrección de formato se hace
        # en una llamada aparte sin tools y con json_object forzado.

        for _ in range(MAX_ITERACIONES):
            llamadas_llm += 1
            try:
                completion = self._llamar_groq(mensajes, forzar_json=modo_correccion)
            except Exception:
                LOGGER.exception("Falló la llamada a Groq con tools")
                break
            uso = completion.usage
            tokens_totales += getattr(uso, "total_tokens", 0) or 0
            mensaje_modelo = completion.choices[0].message

            if mensaje_modelo.tool_calls:
                mensajes.append(
                    {
                        "role": "assistant",
                        "content": mensaje_modelo.content,
                        "tool_calls": [
                            {
                                "id": tc.id,
                                "type": "function",
                                "function": {
                                    "name": tc.function.name,
                                    "arguments": tc.function.arguments,
                                },
                            }
                            for tc in mensaje_modelo.tool_calls
                        ],
                    }
                )
                for tc in mensaje_modelo.tool_calls:
                    nombre = tc.function.name
                    try:
                        argumentos = json.loads(tc.function.arguments or "{}")
                    except json.JSONDecodeError:
                        argumentos = {}
                    resultado_tool = self._ejecutar_tool(nombre, argumentos, se_uso_base)
                    registro_tools.append({"tool": nombre, "argumentos": argumentos})
                    if nombre == "buscar_en_base":
                        se_uso_base = True
                        if isinstance(resultado_tool, list):
                            fuentes_base.extend(resultado_tool)
                    elif nombre == "generar_referencia_apa":
                        se_uso_apa = True
                    elif nombre == "buscar_en_web":
                        if isinstance(resultado_tool, list):
                            fuentes_web.extend(
                                r for r in resultado_tool if "error" not in r
                            )
                    mensajes.append(
                        {
                            "role": "tool",
                            "tool_call_id": tc.id,
                            "content": json.dumps(resultado_tool, ensure_ascii=False),
                        }
                    )
                continue

            contenido = mensaje_modelo.content or ""
            if not registro_tools and not contenido.lstrip().startswith("{"):
                # No se llamó ninguna tool y la respuesta no parece el JSON
                # del contrato (saludo/charla casual): se acepta como texto
                # plano, sin exigir el contrato. Si sí parece JSON (p. ej. el
                # modelo arma una abstención estructurada sin llamar tools,
                # como ante una instrucción maliciosa), igual se intenta
                # formatear abajo en vez de mostrar el JSON crudo.
                resultado_final = contenido.strip() or None
                break
            try:
                resultado_final = self._componer_respuesta(contenido, exigir_cita=not se_uso_apa)
                break
            except (ValueError, KeyError, TypeError) as error:
                LOGGER.warning("Respuesta final fuera del contrato: %s", error)
                if not registro_tools:
                    # Sin tools de por medio no hay nada que corregir con
                    # otra llamada (no hay evidencia ni citas que pedir):
                    # se muestra el texto tal cual en vez de reintentar.
                    resultado_final = contenido.strip() or None
                    break
                mensajes.append({"role": "assistant", "content": contenido})
                mensajes.append(
                    {
                        "role": "user",
                        "content": (
                            f"Tu respuesta no cumplió el formato ({error}). "
                            "Devuelve únicamente el JSON corregido, con las "
                            "mismas claves y citas (Fuente: ...) o [web: ...] "
                            "válidas."
                        ),
                    }
                )
                modo_correccion = True

        latencia_ms = (time.perf_counter() - inicio) * 1000
        self._registrar(mensaje, registro_tools, llamadas_llm, tokens_totales, latencia_ms)

        if resultado_final is None:
            return self._resultado(
                MENSAJE_SIN_EVIDENCIA,
                [],
                [],
                "no_evidence",
                "No se pudo completar una respuesta válida con las tools disponibles.",
                tool_calls=registro_tools,
                llamadas_llm=llamadas_llm,
                tokens=tokens_totales,
                latencia_ms=latencia_ms,
            )

        fuentes = self._formatear_fuentes(fuentes_base, fuentes_web)
        return self._resultado(
            resultado_final,
            fuentes,
            [f.get("texto", "") for f in fuentes_base],
            "agent",
            None,
            tool_calls=registro_tools,
            llamadas_llm=llamadas_llm,
            tokens=tokens_totales,
            latencia_ms=latencia_ms,
        )

    # ------------------------------------------------------------------- Groq
    def _obtener_cliente(self) -> Any:
        if self._cliente is None:
            from groq import Groq

            self._cliente = Groq(api_key=self.api_key, timeout=40.0, max_retries=1)
        return self._cliente

    def _llamar_groq(self, mensajes: list[dict[str, Any]], forzar_json: bool) -> Any:
        """`forzar_json=True` es la llamada de corrección de formato: Groq no
        permite combinar `tools` con `response_format=json_object`, así que
        esa llamada se hace sin tools (ya no se esperan más en ese turno)."""
        parametros: dict[str, Any] = {
            "model": self.modelo,
            "messages": mensajes,
            "temperature": 0.3,
            "max_completion_tokens": MAX_TOKENS_RESPUESTA,
        }
        if forzar_json:
            parametros["response_format"] = {"type": "json_object"}
        else:
            parametros["tools"] = TOOLS_SCHEMA
            parametros["tool_choice"] = "auto"
        if "gpt-oss" in self.modelo:
            parametros["reasoning_effort"] = "low"
        return self._obtener_cliente().chat.completions.create(**parametros)

    def _ejecutar_tool(
        self, nombre: str, argumentos: dict[str, Any], se_uso_base: bool
    ) -> Any:
        try:
            if nombre == "buscar_en_base":
                return buscar_en_base(argumentos.get("consulta", ""), self.base_conocimiento)
            if nombre == "generar_referencia_apa":
                return generar_referencia_apa(argumentos.get("documento", ""))
            if nombre == "buscar_en_web":
                return buscar_en_web(
                    argumentos.get("consulta", ""),
                    se_uso_base=bool(argumentos.get("se_uso_base", se_uso_base)),
                )
            return {"error": f"Tool desconocida: {nombre}"}
        except Exception:
            LOGGER.exception("Falló la ejecución de la tool %s", nombre)
            return {"error": "La tool falló al ejecutarse."}

    # --------------------------------------------------------------- respuesta
    @staticmethod
    def _extraer_json(contenido: str) -> dict[str, Any]:
        try:
            datos = json.loads(contenido)
        except json.JSONDecodeError:
            coincidencia = re.search(r"\{.*\}", contenido, re.DOTALL)
            if not coincidencia:
                raise ValueError("La respuesta no contiene un objeto JSON.")
            datos = json.loads(coincidencia.group(0))
        if not isinstance(datos, dict):
            raise ValueError("La respuesta debe ser un objeto JSON.")
        return datos

    @classmethod
    def _componer_respuesta(cls, contenido: str, exigir_cita: bool = True) -> str:
        """Valida el JSON del modelo y lo convierte en texto para la persona.

        `exigir_cita=False` se usa cuando la única tool llamada fue
        `generar_referencia_apa`: la referencia devuelta ya es, en sí misma,
        la cita, y no necesita además un marcador (Fuente: ...)/[web: ...].
        """
        datos = cls._extraer_json(contenido)
        for clave in ("validacion", "lectura_conducta", "limite_de_la_guia", "senal_alerta"):
            if isinstance(datos.get(clave), str):
                datos[clave] = limpiar_texto_modelo(datos[clave]) or None
        if isinstance(datos.get("estrategias"), list):
            datos["estrategias"] = [
                limpiar_texto_modelo(item) if isinstance(item, str) else item
                for item in datos["estrategias"]
            ]
        validar_formato(datos)

        texto_estrategias = " ".join(datos["estrategias"])
        es_abstencion = texto_estrategias.strip().rstrip(".") == MENSAJE_SIN_EVIDENCIA.rstrip(".")
        if exigir_cita and not es_abstencion and not _tiene_cita(
            (datos["lectura_conducta"] or "") + " " + texto_estrategias
        ):
            raise ValueError(
                "Ninguna estrategia cita una fuente (Fuente: ...) o [web: ...]."
            )

        partes = [datos["validacion"].strip()]
        if datos["lectura_conducta"]:
            partes.append(datos["lectura_conducta"].strip())
        partes.append(
            "Qué puedes intentar:\n"
            + "\n".join(f"• {texto.strip()}" for texto in datos["estrategias"])
        )
        if datos["limite_de_la_guia"]:
            partes.append(f"Lo que la guía no cubre: {datos['limite_de_la_guia'].strip()}")
        if datos["senal_alerta"]:
            partes.append(f"Nota importante: {datos['senal_alerta'].strip()}")
        if datos["derivar_a_profesional"]:
            partes.append(
                "Esta orientación no reemplaza la atención de un profesional."
            )
        return "\n\n".join(partes)

    # ------------------------------------------------------------ utilidades
    @staticmethod
    def _formatear_fuentes(
        fuentes_base: list[dict[str, Any]], fuentes_web: list[dict[str, Any]]
    ) -> list[dict[str, Any]]:
        vistas: set[tuple] = set()
        fuentes: list[dict[str, Any]] = []
        for f in fuentes_base:
            clave = (f.get("documento"), f.get("pagina"), f.get("seccion"))
            if clave in vistas:
                continue
            vistas.add(clave)
            fuentes.append({**f, "origen": "base"})
        for f in fuentes_web:
            clave = (f.get("url"),)
            if clave in vistas:
                continue
            vistas.add(clave)
            fuentes.append(f)
        return fuentes

    @staticmethod
    def _registrar(
        pregunta: str,
        tool_calls: list[dict[str, Any]],
        llamadas_llm: int,
        tokens: int,
        latencia_ms: float,
    ) -> None:
        """Escribe una línea JSONL con el uso de tools de este turno."""
        try:
            LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
            with LOG_PATH.open("a", encoding="utf-8") as archivo:
                archivo.write(
                    json.dumps(
                        {
                            "pregunta": pregunta,
                            "tool_calls": tool_calls,
                            "llamadas_llm": llamadas_llm,
                            "tokens": tokens,
                            "latencia_ms": round(latencia_ms, 1),
                            "timestamp": time.time(),
                        },
                        ensure_ascii=False,
                    )
                    + "\n"
                )
        except OSError:
            LOGGER.warning("No se pudo escribir el log de tools", exc_info=True)

    @staticmethod
    def _resultado(
        respuesta: str,
        fuentes: list[dict[str, Any]],
        contextos: list[str],
        modo: str,
        aviso: str | None,
        tool_calls: list[dict[str, Any]],
        llamadas_llm: int,
        tokens: int = 0,
        latencia_ms: float = 0.0,
    ) -> dict[str, Any]:
        return {
            "answer": respuesta,
            "respuesta": respuesta,
            "sources": fuentes,
            "fuentes": fuentes,
            "contexts": contextos,
            "mode": modo,
            "notice": aviso,
            "tool_calls": tool_calls,
            "llm_calls": llamadas_llm,
            "tokens": tokens,
            "latencia_ms": latencia_ms,
        }
