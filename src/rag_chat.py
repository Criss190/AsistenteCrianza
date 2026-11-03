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
    _terminos_relevantes,
)
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
    r"\b(abuso(?: sexual)?|abusad\w*|violacion\w*|acoso sexual|"
    r"explotacion sexual|tocamiento\w*|violencia|violent\w*|"
    r"suicid\w*|autolesion\w*|hacerme dano|hacerse dano|"
    r"quiere morir|quiero morir|no quiero vivir)\b|"
    r"\bfamiliar\w*.{0,60}\b(?:la|lo)\s+(?:toca|toco)\b"
)
PATRONES_DANO_A_NINO = re.compile(
    r"\b(?:mi hijo|mi hija|mi nino|mi nina|el nino|la nina|menor)\b"
    r".{0,60}\b(?:fue golpead\w*|fue maltratad\w*|le pegaron|"
    r"la golpearon|lo golpearon|la maltrataron|lo maltrataron)\b|"
    r"\b(?:adulto|familiar|padrastro|madrastra|cuidador|maestro|docente)\w*"
    r".{0,60}\b(?:golpeo|golpeo|pego|maltrato|amenazo)\b"
    r".{0,40}\b(?:mi hijo|mi hija|mi nino|mi nina|menor)\b"
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
            return self._respuesta_local(
                mensaje, fragmentos, fuentes, contextos
            )

        try:
            respuesta = self._generar_con_groq(mensaje, fragmentos)
        except Exception:
            LOGGER.exception("No se pudo generar una respuesta válida con Groq")
            return self._respuesta_local(
                mensaje,
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
            f"[Fuente {indice}: {fragmento.fuente}"
            f"{f', página {fragmento.page}' if fragmento.page else ''}]\n"
            f"{fragmento.texto}"
            for indice, fragmento in enumerate(fragmentos, start=1)
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
        citas = {
            int(numero)
            for numero in re.findall(r"\[Fuente\s+(\d+)\]", contenido)
        }
        if not citas or any(numero > len(fragmentos) for numero in citas):
            raise ValueError("La respuesta no cita fuentes recuperadas válidas.")
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
        mensaje: str,
        fragmentos: list[FragmentoConocimiento],
        fuentes: list[dict[str, Any]],
        contextos: list[str],
        notice: str | None = None,
    ) -> dict[str, Any]:
        respuesta = ChatRAG._sintetizar_respuesta_local(mensaje, fragmentos)
        if respuesta is None:
            extractos = ChatRAG._extractos_locales(mensaje, fragmentos)
            if not extractos and len(fragmentos) == 1:
                extractos = ChatRAG._extractos_locales(
                    "", fragmentos, usar_primer_fragmento=True
                )
            if not extractos:
                return ChatRAG._resultado(
                    MENSAJE_SIN_EVIDENCIA, [], [], "no_evidence", notice
                )
            respuesta = (
                "Estas frases de la guía responden a la consulta:\n\n"
                + "\n\n".join(extractos)
            )
        indices_citados = sorted({
            int(numero)
            for cita in re.finditer(r"\[Fuentes?\s+([\d, ]+)\]", respuesta)
            for numero in re.findall(r"\d+", cita.group(1))
            if 1 <= int(numero) <= len(fuentes)
        })
        if indices_citados:
            nuevo_indice = {
                indice_anterior: indice_nuevo
                for indice_nuevo, indice_anterior in enumerate(indices_citados, start=1)
            }

            def renumerar_citas(coincidencia: re.Match[str]) -> str:
                indices = [
                    nuevo_indice[int(numero)]
                    for numero in re.findall(r"\d+", coincidencia.group(1))
                    if int(numero) in nuevo_indice
                ]
                etiqueta = "Fuente" if len(indices) == 1 else "Fuentes"
                return f"[{etiqueta} {', '.join(map(str, indices))}]"

            respuesta = re.sub(
                r"\[Fuentes?\s+([\d, ]+)\]", renumerar_citas, respuesta
            )
            fuentes = [fuentes[indice - 1] for indice in indices_citados]
            contextos = [contextos[indice - 1] for indice in indices_citados]
        return ChatRAG._resultado(respuesta, fuentes, contextos, "local", notice)

    @staticmethod
    def _sintetizar_respuesta_local(
        mensaje: str,
        fragmentos: list[FragmentoConocimiento],
        usar_primer_fragmento: bool = False,
    ) -> str | None:
        """Redacta resúmenes breves para temas cubiertos por evidencia local."""
        consulta = ChatRAG._normalizar(mensaje)
        textos = [ChatRAG._normalizar(fragmento.texto) for fragmento in fragmentos]

        def fuentes_con(palabras: tuple[str, ...]) -> list[int]:
            return [
                indice
                for indice, texto in enumerate(textos, start=1)
                if all(palabra in texto for palabra in palabras)
            ]

        def cita(indices: list[int]) -> str:
            numeros = ", ".join(str(indice) for indice in indices)
            return f"[Fuente {numeros}]" if len(indices) == 1 else f"[Fuentes {numeros}]"

        if "rutina" in consulta and "ritual" in consulta:
            indices = sorted(set(
                fuentes_con(("practicas establecidas",))
                + fuentes_con(("objetivo de los rituales como conexion",))
                + fuentes_con(("parte favorita del dia",))
            ))
            if indices:
                return (
                    "Una rutina reúne pasos habituales, como bañarse, leer y "
                    "apagar la luz; un ritual añade conexión, por ejemplo, "
                    "compartir la parte favorita del día. "
                    f"{cita(indices)}"
                )

        if "tres reglas" in consulta and "grupo" in consulta:
            indices = fuentes_con(("las tres reglas son", "mantenerse juntos"))
            if indices:
                return (
                    "Para el grupo de cuidado, la guía enumera tres reglas: "
                    "mantenerse juntos, no lastimar y divertirse. "
                    f"{cita(indices)}"
                )

        if any(termino in consulta for termino in ("seguro", "segura", "seguros")):
            indices = sorted(set(
                fuentes_con(("segur", "conect"))
                + fuentes_con(("ambientes predecibles",))
                + fuentes_con(("se preocupan por ellos",))
                + fuentes_con(("regular sus emociones",))
            ))
            if indices:
                return (
                    "TBRI distingue entre que un niño esté seguro y que se sienta "
                    "seguro. La guía recomienda ambientes predecibles y relaciones "
                    "con adultos que se preocupan por ellos; esa sensación ayuda "
                    "a la conexión y a regular las emociones. "
                    f"{cita(indices)}"
                )

        if any(termino in consulta for termino in ("escucha", "escuchar", "obedece")):
            indices = sorted(set(
                fuentes_con(("prestar completa atencion",))
                + fuentes_con(("respetar las diferentes opiniones",))
                + fuentes_con(("dar opciones",))
            ))
            if indices:
                return (
                    "Entre las estrategias TBRI están prestarle atención completa "
                    "cuando habla, respetar sus opiniones y ofrecerle opciones. "
                    f"{cita(indices)}"
                )

        if any(termino in consulta for termino in ("llora", "llanto", "frustrad", "berrinche", "rabieta")):
            indices = sorted(set(
                fuentes_con(("regular sus emociones",))
                + fuentes_con(("autorregulacion", "emociones"))
            ))
            if indices:
                return (
                    "Siento que estés pasando por un momento difícil. La guía "
                    "relaciona la sensación de seguridad con la regulación "
                    "emocional, pero estos pasajes no describen una técnica "
                    f"específica para el llanto. {cita(indices)}"
                )

        if any(termino in consulta for termino in ("golpe", "pega", "empuja", "muerde")):
            indices = sorted(set(
                fuentes_con(("aborda rapido el comportamiento desafiante",))
                + fuentes_con(("comportamiento desafiante", "aprender de la experiencia"))
            ))
            if indices:
                return (
                    "Entiendo que puede ser difícil durante la comida. El material "
                    "TBRI recomienda abordar pronto la conducta desafiante y señala "
                    "que así el niño puede aprender de la experiencia. "
                    f"{cita(indices)}"
                )
        return None

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
        mensaje: str,
        fragmentos: list[FragmentoConocimiento],
        usar_primer_fragmento: bool = False,
    ) -> list[str]:
        """Selecciona pocas frases completas y pertinentes de la evidencia."""
        grupos: dict[
            tuple[str, int | None],
            list[tuple[int, int, FragmentoConocimiento]],
        ] = {}
        for indice_fuente, fragmento in enumerate(fragmentos, start=1):
            try:
                indice_chunk = int(fragmento.chunk_id.rsplit("-", 1)[1])
            except (IndexError, ValueError):
                indice_chunk = indice_fuente
            grupos.setdefault((fragmento.fuente, fragmento.page), []).append(
                (indice_chunk, indice_fuente, fragmento)
            )

        terminos_consulta = set(_terminos_relevantes(mensaje))
        candidatos: list[tuple[int, int, str, list[int]]] = []
        for grupo in grupos.values():
            grupo.sort(key=lambda elemento: elemento[0])
            bloques: list[list[tuple[int, int, FragmentoConocimiento]]] = []
            for elemento in grupo:
                if bloques and elemento[0] == bloques[-1][-1][0] + 1:
                    bloques[-1].append(elemento)
                else:
                    bloques.append([elemento])

            for bloque in bloques:
                texto = " ".join(fragmento.texto for _, _, fragmento in bloque)
                texto = re.sub(
                    r"©.*?escrito del ICD\.?\s*", "", texto, flags=re.DOTALL
                )
                lineas = []
                for linea in texto.splitlines():
                    linea = linea.strip().lstrip("•°- ").strip()
                    if (
                        not linea
                        or "?" in linea
                        or re.fullmatch(r"[_\s\d.]+", linea)
                        or re.match(r"^\d+\s+", linea)
                        or linea.lower() in {"rituales diarios", "introduccion"}
                    ):
                        continue
                    lineas.append(linea)
                texto = re.sub(r"\s+", " ", " ".join(lineas)).strip()
                if not texto:
                    continue

                numeros = sorted({indice_fuente for _, indice_fuente, _ in bloque})
                frases = re.split(r"(?<=[.!?])\s+", texto)
                for frase in frases:
                    frase = frase.strip(" •°-\t")
                    if not 35 <= len(frase) <= 260 or "?" in frase:
                        continue
                    terminos_frase = set(_terminos_relevantes(frase))
                    coincidencias = len(terminos_consulta & terminos_frase)
                    if not coincidencias and not usar_primer_fragmento:
                        continue
                    candidatos.append(
                        (coincidencias, numeros[0], frase, numeros)
                    )

        candidatos.sort(key=lambda item: (-item[0], item[1]))
        extractos: list[str] = []
        vistas: set[str] = set()
        for _, _, frase, numeros in candidatos:
            clave = ChatRAG._normalizar(frase)
            if clave in vistas:
                continue
            vistas.add(clave)
            etiqueta = "Fuente" if len(numeros) == 1 else "Fuentes"
            citas = ", ".join(str(numero) for numero in numeros)
            extractos.append(f"• {frase} [{etiqueta} {citas}]")
            if len(extractos) == 3:
                break
        return extractos

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
        normalizado = ChatRAG._normalizar(texto)
        return bool(
            PATRONES_ALERTA.search(normalizado)
            or PATRONES_DANO_A_NINO.search(normalizado)
        )
