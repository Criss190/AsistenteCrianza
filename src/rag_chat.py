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

from src.knowledge_base import (
    BaseConocimientoLocal,
    FragmentoConocimiento,
    SOLAPAMIENTO_FRAGMENTO,
    TAMANO_FRAGMENTO,
    _expandir_consulta,
    _terminos_relevantes,
)
from src.output_formatter import limpiar_texto_modelo, validar_formato
from src.prompt_builder import build_prompt


BASE_CONOCIMIENTO_DIR = (
    Path(__file__).resolve().parent.parent / "docs" / "base_conocimiento"
)
MODELO_GROQ_PREDETERMINADO = "openai/gpt-oss-120b"
TOP_K_PREDETERMINADO = 4
MAX_TOKENS_RESPUESTA = 2500  # los modelos de razonamiento gastan parte en pensar
INTENTOS_GENERACION = 2
MAX_TURNOS_HISTORIAL = 4  # hasta 2 intercambios previos (usuario+asistente)
MAX_TOKENS_CONDENSACION = 120

MENSAJE_SIN_EVIDENCIA = (
    "Mi especialidad es la crianza responsable y no encontré información "
    "suficiente en la guía para responder esto con seguridad. La guía trata "
    "sobre crianza basada en la confianza (TBRI): conexión y apego, regulación "
    "del cuerpo y las emociones (hidratación, alimentación, sentidos, "
    "transiciones, rituales) y corrección respetuosa de la conducta. Si tu "
    "consulta es de crianza, intenta contarme la situación con otras palabras; "
    "para temas médicos, de salud mental o legales, consulta a un profesional."
)
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
EJERCICIO_DE_LIBRO = re.compile(
    r"^(?:piense|reflexione|mire|complete|llene|escriba|analice|anote|"
    r"considere|imagine|pregunte)\b",
    re.IGNORECASE,
)
LOGGER = logging.getLogger(__name__)


def _entero_entorno(nombre: str, predeterminado: int) -> int:
    valor = os.getenv(nombre, "").strip()
    if not valor:
        return predeterminado
    try:
        entero = int(valor)
    except ValueError:
        LOGGER.warning("%s debe ser un entero; se usa %s.", nombre, predeterminado)
        return predeterminado
    return entero if entero > 0 else predeterminado


class ChatRAG:
    """Combina la búsqueda híbrida, el prompt de CrianzApp y Groq si hay clave."""

    def __init__(
        self,
        directorio_conocimiento: str | Path = BASE_CONOCIMIENTO_DIR,
        directorio_vectorstore: str | Path | None = None,
        chunk_size: int | None = None,
        chunk_overlap: int | None = None,
        top_k: int | None = None,
    ) -> None:
        chunk_size = chunk_size or _entero_entorno("RAG_CHUNK_SIZE", TAMANO_FRAGMENTO)
        chunk_overlap = (
            chunk_overlap
            if chunk_overlap is not None
            else _entero_entorno("RAG_CHUNK_OVERLAP", SOLAPAMIENTO_FRAGMENTO)
        )
        top_k = top_k or _entero_entorno("RAG_TOP_K", TOP_K_PREDETERMINADO)
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
        self._cliente: Any = None
        if not self.api_key:
            LOGGER.warning(
                "GROQ_API_KEY no está configurada: CrianzApp responderá solo con "
                "extractos de la guía (sin redacción con IA). Define la variable "
                "en .env o en el panel de Render para activar las respuestas."
            )

    def estado(self) -> dict[str, Any]:
        """Devuelve información de disponibilidad sin revelar credenciales."""
        return {
            "status": "ok",
            "knowledge_chunks": len(self.base_conocimiento.fragmentos),
            "llm_configured": bool(self.api_key),
            "model": self.modelo if self.api_key else None,
            "retrieval": (
                "hybrid" if self.base_conocimiento.vectores_disponibles else "lexical"
            ),
        }

    # ------------------------------------------------------------------ flujo
    def responder(
        self, mensaje: str, historial: list[dict[str, Any]] | None = None
    ) -> dict[str, Any]:
        """Responde al turno actual con evidencia recuperada y, si existe, el
        intercambio inmediatamente anterior para resolver seguimientos.

        El historial nunca decide el riesgo de seguridad (eso depende solo del
        mensaje actual) ni aporta hechos: solo ayuda a (1) recuperar evidencia
        cuando la pregunta sola no basta por tratarse de un seguimiento elíptico
        ("¿y el segundo?") y (2) interpretar esas referencias en la generación.
        """
        historial = [
            turno
            for turno in (historial or [])
            if isinstance(turno, dict) and isinstance(turno.get("content"), str)
        ][-MAX_TURNOS_HISTORIAL:]

        tipo_riesgo = self._clasificar_riesgo(mensaje)
        if tipo_riesgo:
            mensajes = {
                "autolesion": MENSAJE_AUTOLESION,
                "riesgo_adulto": MENSAJE_RIESGO_ADULTO,
                "abuso": MENSAJE_ALERTA,
            }
            return self._resultado(
                mensajes[tipo_riesgo],
                [],
                [],
                "safety",
                "Por seguridad, esta situación requiere acompañamiento humano.",
            )

        fragmentos = self.base_conocimiento.buscar(mensaje, limite=self.top_k)
        consulta_resuelta = mensaje
        if not fragmentos and historial:
            consulta_recuperacion = self._consulta_de_seguimiento(mensaje, historial)
            if consulta_recuperacion != mensaje:
                fragmentos = self.base_conocimiento.buscar(
                    consulta_recuperacion, limite=self.top_k
                )
                if fragmentos:
                    consulta_resuelta = consulta_recuperacion
        if not fragmentos:
            return self._resultado(MENSAJE_SIN_EVIDENCIA, [], [], "no_evidence", None)

        fuentes = self._formatear_fuentes(fragmentos)
        contextos = [fragmento.texto for fragmento in fragmentos]

        if not self.api_key:
            # En modo local, la extracción de frases debe filtrar con la misma
            # consulta (resuelta) que encontró los fragmentos, o un seguimiento
            # elíptico ("¿y el segundo?") no coincidiría con ninguna frase.
            return self._respuesta_local(consulta_resuelta, fragmentos, fuentes, contextos)

        contexto_previo = self._contexto_previo(historial)
        try:
            respuesta = self._generar_con_groq(mensaje, fragmentos, contexto_previo)
        except Exception:
            LOGGER.exception("No se pudo generar una respuesta válida con Groq")
            return self._respuesta_local(
                mensaje,
                fragmentos,
                fuentes,
                contextos,
                notice=(
                    "No fue posible redactar una respuesta personalizada; te "
                    "comparto directamente los pasajes más relevantes de la guía."
                ),
            )
        respuesta, fuentes, contextos = self._renumerar_citas(
            respuesta, fuentes, contextos
        )
        return self._resultado(respuesta, fuentes, contextos, "groq", None)

    # ------------------------------------------------------------------- Groq
    def _obtener_cliente(self) -> Any:
        if self._cliente is None:
            from groq import Groq

            self._cliente = Groq(api_key=self.api_key, timeout=40.0, max_retries=1)
        return self._cliente

    def _generar_con_groq(
        self,
        mensaje: str,
        fragmentos: list[FragmentoConocimiento],
        contexto_previo: str = "",
    ) -> str:
        """Genera una respuesta estructurada a partir de los fragmentos citados.

        Reintenta una vez indicando al modelo qué incumplió el formato.
        """
        contexto = "\n\n".join(
            f"[Fuente {indice}: {fragmento.titulo or fragmento.fuente}"
            f"{f', página {fragmento.page}' if fragmento.page else ''}]\n"
            f"{fragmento.texto}"
            for indice, fragmento in enumerate(fragmentos, start=1)
        )
        mensajes = build_prompt(mensaje, contexto, contexto_previo)
        ultimo_error: Exception | None = None
        for intento in range(INTENTOS_GENERACION):
            contenido = self._llamar_groq(mensajes)
            try:
                return self._componer_respuesta(contenido, len(fragmentos))
            except (ValueError, KeyError, TypeError) as error:
                ultimo_error = error
                LOGGER.warning(
                    "Respuesta del modelo fuera del contrato (intento %s): %s",
                    intento + 1,
                    error,
                )
                mensajes = [
                    *mensajes,
                    {"role": "assistant", "content": contenido or "{}"},
                    {
                        "role": "user",
                        "content": (
                            f"Tu respuesta no cumplió el formato ({error}). "
                            "Devuelve únicamente el JSON corregido, con las "
                            "mismas claves y citas [Fuente N] válidas."
                        ),
                    },
                ]
        raise ValueError(f"El modelo no cumplió el contrato: {ultimo_error}")

    def _llamar_groq(self, mensajes: list[dict[str, str]]) -> str:
        parametros: dict[str, Any] = {
            "model": self.modelo,
            "messages": mensajes,
            "temperature": 0.3,
            "max_completion_tokens": MAX_TOKENS_RESPUESTA,
            "response_format": {"type": "json_object"},
        }
        if "gpt-oss" in self.modelo:
            parametros["reasoning_effort"] = "low"
        inicio = perf_counter()
        completion = self._obtener_cliente().chat.completions.create(**parametros)
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
        if not contenido or not contenido.strip():
            raise ValueError("Groq devolvió una respuesta vacía.")
        return contenido

    @staticmethod
    def _extraer_json(contenido: str) -> dict[str, Any]:
        """Lee el JSON aunque el modelo lo rodee de texto o de vallas ```."""
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
    def _componer_respuesta(cls, contenido: str, cantidad_fuentes: int) -> str:
        """Valida el JSON del modelo y lo convierte en texto para la persona."""
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

        texto_con_citas = " ".join(
            [datos["lectura_conducta"] or "", *datos["estrategias"]]
        )
        citas = cls._numeros_citados(texto_con_citas)
        if not citas:
            raise ValueError("Ninguna estrategia cita una fuente [Fuente N].")
        invalidas = [n for n in cls._numeros_citados(json.dumps(datos, ensure_ascii=False))
                     if not 1 <= n <= cantidad_fuentes]
        if invalidas:
            raise ValueError(f"Cita fuentes inexistentes: {sorted(set(invalidas))}.")

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

    # ------------------------------------------------------- seguimientos
    def _consulta_de_seguimiento(
        self, mensaje: str, historial: list[dict[str, Any]]
    ) -> str:
        """Reformula un seguimiento elíptico en una pregunta autónoma para buscar.

        Solo se usa cuando `mensaje` solo no encontró evidencia. El resultado
        se usa exclusivamente para recuperar fragmentos; la pregunta mostrada y
        respondida sigue siendo la original.
        """
        if self.api_key:
            return self._condensar_pregunta(mensaje, historial)
        anterior = self._ultimo_mensaje_usuario(historial)
        return f"{anterior} {mensaje}".strip() if anterior else mensaje

    def _condensar_pregunta(
        self, mensaje: str, historial: list[dict[str, Any]]
    ) -> str:
        """Pide al modelo una versión autónoma de la pregunta de seguimiento."""
        anterior = self._ultimo_mensaje_usuario(historial)
        if not anterior:
            return mensaje
        try:
            completado = self._obtener_cliente().chat.completions.create(
                model=self.modelo,
                temperature=0,
                max_completion_tokens=MAX_TOKENS_CONDENSACION,
                messages=[
                    {
                        "role": "system",
                        "content": (
                            "Reescribe la ÚLTIMA pregunta como una pregunta completa "
                            "e independiente, usando la pregunta anterior solo para "
                            "resolver pronombres o referencias ('eso', 'el segundo', "
                            "'y después'). No agregues datos nuevos ni la respondas. "
                            "Responde solo con la pregunta reescrita, sin comillas."
                        ),
                    },
                    {"role": "user", "content": f"Pregunta anterior: {anterior}"},
                    {"role": "user", "content": f"Última pregunta: {mensaje}"},
                ],
            )
            texto = (completado.choices[0].message.content or "").strip()
            return texto or f"{anterior} {mensaje}"
        except Exception:
            LOGGER.warning(
                "No se pudo condensar la pregunta de seguimiento", exc_info=True
            )
            return f"{anterior} {mensaje}"

    @staticmethod
    def _ultimo_mensaje_usuario(historial: list[dict[str, Any]]) -> str:
        for turno in reversed(historial):
            if turno.get("role") == "user":
                contenido = turno.get("content", "")
                if isinstance(contenido, str) and contenido.strip():
                    return contenido.strip()
        return ""

    @staticmethod
    def _contexto_previo(historial: list[dict[str, Any]]) -> str:
        """Resumen breve del último intercambio, solo para interpretar referencias."""
        ultimo_usuario = ultimo_asistente = ""
        for turno in reversed(historial):
            contenido = turno.get("content", "")
            if not isinstance(contenido, str) or not contenido.strip():
                continue
            if turno.get("role") == "assistant" and not ultimo_asistente:
                ultimo_asistente = contenido.strip()[:300]
            elif turno.get("role") == "user" and not ultimo_usuario:
                ultimo_usuario = contenido.strip()[:300]
            if ultimo_usuario and ultimo_asistente:
                break
        if not ultimo_usuario:
            return ""
        bloque = f"Pregunta anterior: {ultimo_usuario}"
        if ultimo_asistente:
            bloque += f"\nRespuesta anterior (resumen): {ultimo_asistente}"
        return bloque

    # ---------------------------------------------------------------- citas
    _PATRON_CITA = re.compile(r"\[Fuentes?\s+([\d,\sy]+)\]")

    @classmethod
    def _numeros_citados(cls, texto: str) -> list[int]:
        return [
            int(numero)
            for cita in cls._PATRON_CITA.finditer(texto)
            for numero in re.findall(r"\d+", cita.group(1))
        ]

    @classmethod
    def _renumerar_citas(
        cls,
        respuesta: str,
        fuentes: list[dict[str, Any]],
        contextos: list[str],
    ) -> tuple[str, list[dict[str, Any]], list[str]]:
        """Deja solo las fuentes citadas y renumera [Fuente N] desde 1."""
        indices = sorted(
            {n for n in cls._numeros_citados(respuesta) if 1 <= n <= len(fuentes)}
        )
        if not indices:
            return respuesta, fuentes, contextos
        nuevo = {anterior: posicion for posicion, anterior in enumerate(indices, 1)}

        def sustituir(coincidencia: re.Match[str]) -> str:
            numeros = sorted({
                nuevo[int(n)]
                for n in re.findall(r"\d+", coincidencia.group(1))
                if int(n) in nuevo
            })
            if not numeros:
                return ""
            etiqueta = "Fuente" if len(numeros) == 1 else "Fuentes"
            return f"[{etiqueta} {', '.join(map(str, numeros))}]"

        respuesta = cls._PATRON_CITA.sub(sustituir, respuesta)
        # "[Fuente 1] [Fuente 2]" -> "[Fuentes 1, 2]"
        anterior = None
        while anterior != respuesta:
            anterior = respuesta
            respuesta = re.sub(
                r"\[Fuentes?\s+([\d, ]+)\]\s*\[Fuentes?\s+([\d, ]+)\]",
                lambda m: "[Fuentes "
                + ", ".join(sorted(
                    set(re.findall(r"\d+", m.group(1) + " " + m.group(2))), key=int
                ))
                + "]",
                respuesta,
            )
        return (
            respuesta,
            [fuentes[i - 1] for i in indices],
            [contextos[i - 1] for i in indices],
        )

    # -------------------------------------------------------- modo sin IA
    @staticmethod
    def _respuesta_local(
        mensaje: str,
        fragmentos: list[FragmentoConocimiento],
        fuentes: list[dict[str, Any]],
        contextos: list[str],
        notice: str | None = None,
    ) -> dict[str, Any]:
        """Sin LLM: muestra las frases de la guía que mejor responden."""
        extractos = ChatRAG._extractos_locales(mensaje, fragmentos)
        if not extractos:
            return ChatRAG._resultado(
                MENSAJE_SIN_EVIDENCIA, [], [], "no_evidence", notice
            )
        respuesta = (
            "Esto es lo que dice la guía sobre tu consulta:\n\n"
            + "\n\n".join(extractos)
        )
        respuesta, fuentes, contextos = ChatRAG._renumerar_citas(
            respuesta, fuentes, contextos
        )
        return ChatRAG._resultado(
            respuesta,
            fuentes,
            contextos,
            "local",
            notice
            or "Te muestro los pasajes más relevantes de la guía tal como están escritos.",
        )

    @staticmethod
    def _normalizar(texto: str) -> str:
        normalizado = unicodedata.normalize("NFD", texto.lower())
        sin_acentos = "".join(
            caracter
            for caracter in normalizado
            if unicodedata.category(caracter) != "Mn"
        )
        return re.sub(r"\s+", " ", sin_acentos).strip()

    @staticmethod
    def _extractos_locales(
        mensaje: str, fragmentos: list[FragmentoConocimiento], maximo: int = 3
    ) -> list[str]:
        """Frases completas de la evidencia que comparten al menos dos señales
        con la pregunta (palabras propias o su expansión al vocabulario TBRI)."""
        base = _terminos_relevantes(mensaje)
        extra = _terminos_relevantes(" ".join(_expandir_consulta(mensaje))) - base
        candidatos: list[tuple[float, int, int, str]] = []
        for numero, fragmento in enumerate(fragmentos, start=1):
            texto = fragmento.texto
            if fragmento.section and texto.startswith(fragmento.section):
                texto = texto[len(fragmento.section):]
            posicion = 0
            for bloque in re.split(r"\n\s*\n", texto):
                bloque = bloque.strip().lstrip("•°- ").strip()
                if not bloque:
                    continue
                es_vineta = len(bloque) < 220 and not re.search(r"[.!?:]$", bloque)
                frases = (
                    [bloque]
                    if es_vineta
                    else re.split(r"(?<=[.!?])\s+", bloque)
                )
                for frase in frases:
                    frase = frase.strip()
                    posicion += 1
                    if (
                        not 30 <= len(frase) <= 320
                        or "?" in frase
                        or "¿" in frase
                        or EJERCICIO_DE_LIBRO.match(frase)
                        or frase.endswith(":")
                    ):
                        continue
                    terminos = _terminos_relevantes(frase)
                    unidades = len(base & terminos) + 0.5 * len(extra & terminos)
                    if unidades >= 2:
                        candidatos.append((unidades, numero, posicion, frase))
        candidatos.sort(key=lambda c: (-c[0], c[1], c[2]))
        extractos: list[str] = []
        vistas: set[str] = set()
        for _, numero, _, frase in candidatos:
            clave = ChatRAG._normalizar(frase)
            if clave in vistas:
                continue
            vistas.add(clave)
            if not frase.endswith((".", "!", ")", '"')):
                frase += "."
            extractos.append(f"• {frase} [Fuente {numero}]")
            if len(extractos) == maximo:
                break
        return extractos

    # ------------------------------------------------------------ utilidades
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
                "title": fragmento.titulo,
                "excerpt": fragmento.texto,
                "chunk_id": fragmento.chunk_id,
                "page": fragmento.page,
                "section": fragmento.section,
            }
            for fragmento in fragmentos
        ]

    @staticmethod
    def _clasificar_riesgo(texto: str) -> str | None:
        """Devuelve 'autolesion', 'riesgo_adulto', 'abuso' o None."""
        normalizado = ChatRAG._normalizar(texto)
        if PATRONES_AUTOLESION.search(normalizado):
            return "autolesion"
        if PATRONES_RIESGO_ADULTO.search(normalizado):
            return "riesgo_adulto"
        if PATRONES_ABUSO.search(normalizado) or PATRONES_DANO_A_NINO.search(
            normalizado
        ):
            return "abuso"
        return None

    @staticmethod
    def _es_situacion_de_riesgo(texto: str) -> bool:
        return ChatRAG._clasificar_riesgo(texto) is not None
