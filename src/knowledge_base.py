"""Carga, fragmentación, persistencia y recuperación de conocimiento local."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
import hashlib
from html.parser import HTMLParser
import math
from pathlib import Path
import re
import unicodedata
from typing import Any

import chromadb
from chromadb.config import Settings
from chromadb.utils.embedding_functions import DefaultEmbeddingFunction
from docx import Document as WordDocument
from langchain_text_splitters import RecursiveCharacterTextSplitter
from pypdf import PdfReader


EXTENSIONES_ADMITIDAS = {".pdf", ".docx", ".txt", ".md", ".html", ".htm"}
FUENTES_EXCLUIDAS = {"guia_crianza.md"}
TAMANO_FRAGMENTO = 500
SOLAPAMIENTO_FRAGMENTO = 50
DISTANCIA_MAXIMA = 0.65
DISTANCIA_COINCIDENCIA_UNICA = 0.57
PUNTAJE_BM25_COINCIDENCIA_UNICA = 8.0
NOMBRE_COLECCION = "crianzapp_conocimiento"
MODELO_EMBEDDINGS = "sentence-transformers/all-MiniLM-L6-v2"
TAGS_BLOQUE_HTML = {
    "article", "blockquote", "br", "dd", "div", "dl", "dt", "figcaption",
    "h1", "h2", "h3", "h4", "h5", "h6", "li", "ol", "p", "section", "td",
    "th", "tr", "ul",
}
TAGS_IGNORADOS_HTML = {"head", "script", "style", "noscript", "svg"}
PALABRAS_VACIAS = {
    "a", "al", "algo", "cada", "como", "con", "cual", "cuale", "cuando",
    "colombia", "de", "del", "despues", "documento", "donde", "el", "ella",
    "en", "es", "esta", "este", "hacer", "hay", "la", "las", "le", "lo",
    "los", "me", "mi", "mis", "o", "para", "pero", "por", "primer", "que",
    "se", "segun", "si", "son", "su", "sus", "tener", "un", "una", "y", "yo",
    "puedo", "puede", "debo", "deberia", "quiero", "ser", "fue", "dos",
    "ano",
    "articulo", "evidencia", "durante", "actual", "frente",
    "importante", "tan", "ayudar", "ayudame", "hago", "hace", "haces",
    "tiene", "tienen", "hacerlo", "hacerle", "conciliar", "implementar",
    "establecer", "quisiera", "mejor", "mejore", "seria", "podria",
    "podrias", "puedes", "podemos", "ante", "antes", "utilizada",
    "utilizado", "significan", "significa", "significar", "sigla",
    "siglas", "cumplir", "cumple", "cumplen", "clave", "factor",
    "descrito", "describen", "incrementar", "incrementaron", "basado",
    "basada", "presenta", "presentan", "gomez", "muzzio", "lin", "lewry",
    "et", "revision", "sistematica", "tbri",
    "hijo", "hija", "hijos", "hijas", "nino", "nina", "ninos", "ninas",
}
GRUPOS_SINONIMOS = (
    ("pantalla", "television", "tele"),
    ("rabieta", "berrinche", "frustracion"),
    ("emocion", "sentimiento"),
    (
        "sueno", "dormir", "dormida", "dormido", "dormirse", "acostar",
        "acostarse", "acostarlo", "acostarla", "acostarle", "descanso",
        "descansar", "nocturno", "nocturna", "noche",
    ),
    ("intervencion", "intervention"),
    ("efecto", "effect"),
    ("padre", "padres", "parent", "parents", "parenting", "padr"),
    ("postparto", "postpartum"),
    ("apoyo", "support"),
    ("depresion", "depressive", "depression"),
    ("moderador", "moderators", "moderator"),
    ("efectividad", "effectiveness"),
    ("orientacion", "orientation"),
    ("guiado", "guided"),
    ("autoeficacia", "efficacy", "selfefficacy"),
)
_SINONIMO_CANONICO = {
    sinonimo: grupo[0]
    for grupo in GRUPOS_SINONIMOS
    for sinonimo in grupo
}
_EXPANSIONES_INGLES = {
    "efecto": "effects",
    "intervencion": "interventions",
    "padre": "parenting parents",
    "postparto": "postpartum",
    "apoyo": "support",
    "depresion": "depressive symptoms",
    "moderador": "moderators",
    "efectividad": "effectiveness",
    "orientacion": "orientation",
    "guiado": "guided curriculum",
}


def _tokenizar_relevante(texto: str) -> list[str]:
    """Normaliza palabras de contenido para búsqueda léxica y BM25."""
    normalizado = unicodedata.normalize("NFD", texto.lower())
    sin_acentos = "".join(
        caracter
        for caracter in normalizado
        if unicodedata.category(caracter) != "Mn"
    )
    sin_acentos = re.sub(
        r"\b(?:\d+|uno|una|un|dos|tres|cuatro|cinco|seis|"
        r"siete|ocho|nueve|diez)\s+anos?\b",
        " ",
        sin_acentos,
    )
    terminos: list[str] = []
    for token in re.findall(r"[a-z0-9]+", sin_acentos):
        if re.fullmatch(r"(?:19|20)\d{2}", token):
            continue
        if token.endswith("es") and len(token) > 5:
            token = token[:-2]
        elif token.endswith("s") and len(token) > 4:
            token = token[:-1]
        if token == "cuatro":
            token = "4"
        token = _SINONIMO_CANONICO.get(token, token)
        if token not in PALABRAS_VACIAS:
            terminos.append(token)

    if re.search(
        r"\b(?:que es|que significa|significan las siglas|siglas de|definicion)\b",
        sin_acentos,
    ) or re.search(r"\b(?:que es|definicion|se define)\b", sin_acentos):
        terminos.append("definicion")
    return terminos


def _terminos_relevantes(texto: str) -> set[str]:
    """Obtiene términos de contenido normalizados y sin duplicados."""
    return set(_tokenizar_relevante(texto))


def _consulta_bilingue(terminos: set[str]) -> str | None:
    """Añade una consulta en inglés cuando el corpus mezcla idiomas."""
    expansiones = {
        expansion
        for termino in terminos
        if (expansion := _EXPANSIONES_INGLES.get(termino))
    }
    if "digital" in terminos:
        expansiones.add("digital")
    if len(expansiones) < 2:
        return None
    return " ".join(sorted(expansiones)) or None


def _puntaje_bm25(
    terminos_consulta: set[str],
    terminos_documento: list[str],
    frecuencia_documental: Counter[str],
    cantidad_documentos: int,
    longitud_media: float,
) -> float:
    """Calcula BM25 con parámetros estándar para un fragmento."""
    if not cantidad_documentos or not longitud_media:
        return 0.0

    frecuencias = Counter(terminos_documento)
    puntaje = 0.0
    for termino in terminos_consulta:
        frecuencia = frecuencias[termino]
        documentos_con_termino = frecuencia_documental[termino]
        if not frecuencia or not documentos_con_termino:
            continue
        idf = math.log(
            1
            + (cantidad_documentos - documentos_con_termino + 0.5)
            / (documentos_con_termino + 0.5)
        )
        normalizacion = frecuencia + 1.5 * (
            1 - 0.75 + 0.75 * len(terminos_documento) / longitud_media
        )
        puntaje += idf * (frecuencia * 2.5) / normalizacion
    return puntaje


@dataclass(frozen=True)
class FragmentoConocimiento:
    """Fragmento recuperado con su fuente, ubicación y distancia semántica."""

    fuente: str
    texto: str
    chunk_id: str = ""
    page: int | None = None
    section: str | None = None
    distancia: float = 0.0


class _ExtractorHTML(HTMLParser):
    """Extrae texto visible de HTML y conserva encabezados como secciones."""

    def __init__(self, titulo_inicial: str) -> None:
        super().__init__(convert_charrefs=True)
        self.titulo = titulo_inicial
        self.partes: list[str] = []
        self.secciones: list[tuple[str, str]] = []
        self._ignorar = 0
        self._capturando_encabezado = False
        self._encabezado: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in TAGS_IGNORADOS_HTML:
            self._ignorar += 1
        if self._ignorar:
            return
        if tag in TAGS_BLOQUE_HTML:
            self.partes.append("\n")
        if re.fullmatch(r"h[1-6]", tag):
            self._capturando_encabezado = True
            self._encabezado = []

    def handle_endtag(self, tag: str) -> None:
        if tag in TAGS_IGNORADOS_HTML and self._ignorar:
            self._ignorar -= 1
        if self._ignorar:
            return
        if re.fullmatch(r"h[1-6]", tag) and self._encabezado:
            self._guardar_seccion()
            self.titulo = " ".join("".join(self._encabezado).split())
            self._encabezado = []
            self._capturando_encabezado = False
        if tag in TAGS_BLOQUE_HTML:
            self.partes.append("\n")

    def handle_data(self, data: str) -> None:
        if self._ignorar:
            return
        if self._capturando_encabezado:
            self._encabezado.append(data)
            return
        self.partes.append(data)

    def _guardar_seccion(self) -> None:
        texto = re.sub(r"\s+", " ", "".join(self.partes)).strip()
        if texto:
            self.secciones.append((texto, {"section": self.titulo}))
        self.partes = []


def _leer_html(archivo: Path) -> list[tuple[str, dict[str, Any]]]:
    """Extrae texto visible de HTML y asigna encabezados como metadatos."""
    extractor = _ExtractorHTML(archivo.stem)
    extractor.feed(archivo.read_text(encoding="utf-8"))
    extractor._guardar_seccion()
    return extractor.secciones


def _leer_texto(archivo: Path) -> list[tuple[str, dict[str, Any]]]:
    """Extrae texto y metadatos de ubicación de los formatos admitidos."""
    extension = archivo.suffix.lower()
    if extension == ".pdf":
        return [
            (pagina.extract_text() or "", {"page": numero})
            for numero, pagina in enumerate(PdfReader(archivo).pages, start=1)
        ]

    if extension == ".docx":
        documento = WordDocument(archivo)
        secciones: list[tuple[str, dict[str, Any]]] = []
        titulo = archivo.stem
        parrafos: list[str] = []
        for parrafo in documento.paragraphs:
            texto = parrafo.text.strip()
            if not texto:
                continue
            if parrafo.style.name.startswith("Heading"):
                if parrafos:
                    secciones.append(("\n".join(parrafos), {"section": titulo}))
                titulo = texto
                parrafos = [texto]
            else:
                parrafos.append(texto)
        if parrafos:
            secciones.append(("\n".join(parrafos), {"section": titulo}))
        filas_tablas = [
            " | ".join(celda.text.strip() for celda in fila.cells)
            for tabla in documento.tables
            for fila in tabla.rows
        ]
        if filas_tablas:
            secciones.append(
                ("\n".join(filas_tablas), {"section": f"{titulo} (tablas)"})
            )
        return secciones

    if extension in {".html", ".htm"}:
        return _leer_html(archivo)

    texto = archivo.read_text(encoding="utf-8")
    if extension == ".md":
        secciones = []
        encabezado_actual = archivo.stem
        lineas: list[str] = []
        for linea in texto.splitlines():
            encabezado = re.match(r"^\s{0,3}#{1,6}\s+(.+?)\s*#*\s*$", linea)
            if encabezado:
                if lineas:
                    secciones.append(
                        ("\n".join(lineas), {"section": encabezado_actual})
                    )
                encabezado_actual = encabezado.group(1).strip()
                lineas = [linea]
            else:
                lineas.append(linea)
        if lineas:
            secciones.append(("\n".join(lineas), {"section": encabezado_actual}))
        return secciones

    return [(texto, {"section": archivo.stem})]


def _archivos_admitidos(directorio: Path) -> list[Path]:
    """Lista documentos admitidos sin incorporar la guía provisional retirada."""
    return sorted(
        archivo
        for archivo in directorio.rglob("*")
        if archivo.is_file()
        and archivo.suffix.lower() in EXTENSIONES_ADMITIDAS
        and archivo.relative_to(directorio).as_posix() not in FUENTES_EXCLUIDAS
    )


class BaseConocimientoLocal:
    """Índice Chroma persistente construido desde documentos de conocimiento."""

    def __init__(
        self,
        fragmentos: list[FragmentoConocimiento],
        coleccion: Any,
        client: Any,
    ) -> None:
        self.fragmentos = fragmentos
        self._coleccion = coleccion
        self._client = client
        self._terminos_por_fragmento = {
            fragmento.chunk_id: _tokenizar_relevante(fragmento.texto)
            for fragmento in fragmentos
        }
        self._frecuencia_documental = Counter(
            termino
            for terminos in self._terminos_por_fragmento.values()
            for termino in set(terminos)
        )
        self._longitud_media = (
            sum(map(len, self._terminos_por_fragmento.values()))
            / len(self._terminos_por_fragmento)
            if self._terminos_por_fragmento
            else 0.0
        )

    @classmethod
    def cargar(
        cls,
        directorio: str | Path,
        directorio_vectorstore: str | Path | None = None,
        chunk_size: int = TAMANO_FRAGMENTO,
        chunk_overlap: int = SOLAPAMIENTO_FRAGMENTO,
    ) -> "BaseConocimientoLocal":
        """Carga documentos y crea o actualiza el índice vectorial persistente."""
        if chunk_size <= 0 or chunk_overlap < 0 or chunk_overlap >= chunk_size:
            raise ValueError(
                "chunk_size debe ser positivo y chunk_overlap estar entre "
                "cero y chunk_size - 1."
            )
        ruta = Path(directorio).resolve()
        ruta_vectorstore = (
            Path(directorio_vectorstore).resolve()
            if directorio_vectorstore
            else ruta.parent.parent / "vectorstore"
        )
        splitter = RecursiveCharacterTextSplitter(
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap,
            add_start_index=True,
        )

        documentos: list[dict[str, Any]] = []
        contenido_hash = hashlib.sha256()
        contenido_hash.update(
            f"{chunk_size}:{chunk_overlap}:{MODELO_EMBEDDINGS}".encode("utf-8")
        )
        archivos = _archivos_admitidos(ruta)
        for archivo in archivos:
            fuente = archivo.relative_to(ruta).as_posix()
            contenido_hash.update(fuente.encode("utf-8"))
            contenido_hash.update(archivo.read_bytes())
            indice_fragmento = 0
            for texto, ubicacion in _leer_texto(archivo):
                metadatos = {
                    "source": fuente,
                    "filename": archivo.name,
                    **ubicacion,
                }
                for documento in splitter.create_documents(
                    [texto], metadatas=[metadatos]
                ):
                    texto_fragmento = documento.page_content.strip()
                    if texto_fragmento:
                        chunk_id = (
                            f"{hashlib.sha256(fuente.encode()).hexdigest()[:12]}-"
                            f"{indice_fragmento}"
                        )
                        documentos.append(
                            {
                                "text": texto_fragmento,
                                "metadata": {
                                    **documento.metadata,
                                    "chunk_id": chunk_id,
                                },
                            }
                        )
                        indice_fragmento += 1

        huella_corpus = contenido_hash.hexdigest()
        ruta_vectorstore.mkdir(parents=True, exist_ok=True)
        cliente = chromadb.PersistentClient(
            path=str(ruta_vectorstore),
            settings=Settings(anonymized_telemetry=False),
        )
        embedding_function = DefaultEmbeddingFunction()
        coleccion = cliente.get_or_create_collection(
            name=NOMBRE_COLECCION,
            embedding_function=embedding_function,
            metadata={
                "hnsw:space": "cosine",
                "corpus_hash": huella_corpus,
                "embedding_model": MODELO_EMBEDDINGS,
                "chunk_size": chunk_size,
                "chunk_overlap": chunk_overlap,
            },
        )

        if coleccion.metadata.get("corpus_hash") != huella_corpus or (
            documentos and coleccion.count() == 0
        ):
            cliente.delete_collection(NOMBRE_COLECCION)
            coleccion = cliente.create_collection(
                name=NOMBRE_COLECCION,
                embedding_function=embedding_function,
                metadata={
                    "hnsw:space": "cosine",
                    "corpus_hash": huella_corpus,
                    "embedding_model": MODELO_EMBEDDINGS,
                    "chunk_size": chunk_size,
                    "chunk_overlap": chunk_overlap,
                },
            )
            if documentos:
                coleccion.add(
                    ids=[item["metadata"]["chunk_id"] for item in documentos],
                    documents=[item["text"] for item in documentos],
                    metadatas=[item["metadata"] for item in documentos],
                )

        fragmentos = [
            FragmentoConocimiento(
                fuente=str(item["metadata"]["source"]),
                texto=str(item["text"]),
                chunk_id=str(item["metadata"]["chunk_id"]),
                page=item["metadata"].get("page"),
                section=item["metadata"].get("section"),
            )
            for item in documentos
        ]
        return cls(fragmentos, coleccion, cliente)

    def buscar(self, consulta: str, limite: int = 3) -> list[FragmentoConocimiento]:
        """Combina similitud semántica y BM25, y descarta evidencia débil."""
        if not consulta.strip() or limite <= 0 or self._coleccion.count() == 0:
            return []

        terminos_consulta = _terminos_relevantes(consulta)
        if not terminos_consulta:
            return []

        consultas = [consulta]
        consulta_bilingue = _consulta_bilingue(terminos_consulta)
        if consulta_bilingue:
            consultas.append(consulta_bilingue)
        resultado = self._coleccion.query(
            query_texts=consultas,
            n_results=self._coleccion.count(),
            include=["documents", "metadatas", "distances"],
        )

        candidatos: dict[str, tuple[str, dict[str, Any], float]] = {}
        for ids, documentos, metadatos, distancias in zip(
            resultado["ids"],
            resultado["documents"],
            resultado["metadatas"],
            resultado["distances"],
        ):
            for chunk_id, texto, metadata, distancia in zip(
                ids, documentos, metadatos, distancias
            ):
                distancia_actual = float(distancia)
                candidato = candidatos.get(str(chunk_id))
                if candidato is None or distancia_actual < candidato[2]:
                    candidatos[str(chunk_id)] = (
                        str(texto),
                        metadata,
                        distancia_actual,
                    )

        puntajes: dict[str, float] = {}
        for chunk_id, (texto, _, distancia) in candidatos.items():
            terminos_documento = self._terminos_por_fragmento.get(chunk_id)
            if terminos_documento is None:
                terminos_documento = _tokenizar_relevante(texto)
            compartidos = terminos_consulta & set(terminos_documento)
            if distancia > DISTANCIA_MAXIMA or not compartidos:
                continue

            puntaje = _puntaje_bm25(
                terminos_consulta,
                terminos_documento,
                self._frecuencia_documental,
                len(self.fragmentos),
                self._longitud_media,
            )
            if len(compartidos) == 1 and (
                distancia > DISTANCIA_COINCIDENCIA_UNICA
                or puntaje < PUNTAJE_BM25_COINCIDENCIA_UNICA
            ):
                continue
            puntajes[chunk_id] = puntaje

        maximo_bm25 = max(puntajes.values(), default=0.0)
        candidatos_ordenados: list[tuple[float, float, str]] = []
        for chunk_id, puntaje in puntajes.items():
            texto, _, distancia = candidatos[chunk_id]
            similitud = 1.0 - distancia
            bm25_normalizado = puntaje / maximo_bm25 if maximo_bm25 else 0.0
            penalizacion_indice = min(
                0.12, 0.02 * len(re.findall(r"\.{5,}", texto))
            )
            score = (
                0.4 * similitud
                + 0.6 * bm25_normalizado
                - penalizacion_indice
            )
            candidatos_ordenados.append((score, distancia, chunk_id))
        candidatos_ordenados.sort(key=lambda item: (-item[0], item[1]))

        fragmentos: list[FragmentoConocimiento] = []
        for _, distancia, chunk_id in candidatos_ordenados:
            texto, metadata, _ = candidatos[chunk_id]
            page = metadata.get("page")
            fragmentos.append(
                FragmentoConocimiento(
                    fuente=str(metadata["source"]),
                    texto=str(texto),
                    chunk_id=str(metadata["chunk_id"]),
                    page=int(page) if page is not None else None,
                    section=metadata.get("section"),
                    distancia=float(distancia),
                )
            )
            if len(fragmentos) == limite:
                break
        return fragmentos
