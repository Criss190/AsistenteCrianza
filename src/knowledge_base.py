"""Carga, fragmentación, persistencia y recuperación de conocimiento local.

Recuperación híbrida: BM25 sobre raíces de palabras en español (señal principal,
porque el corpus es casi todo en español y el modelo de embeddings por defecto de
Chroma es inglés) combinado con similitud vectorial (señal secundaria). Si el
modelo de embeddings no se puede cargar, el sistema sigue funcionando solo con la
parte léxica en lugar de fallar al arrancar.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
import hashlib
from html.parser import HTMLParser
import logging
import math
import os
from pathlib import Path
import re
import unicodedata
from typing import Any

from docx import Document as WordDocument
from nltk.stem.snowball import SpanishStemmer
from pypdf import PdfReader

LOGGER = logging.getLogger(__name__)

EXTENSIONES_ADMITIDAS = {".pdf", ".docx", ".txt", ".md", ".html", ".htm"}
FUENTES_EXCLUIDAS = {"guia_crianza.md"}
TAMANO_FRAGMENTO = 900
SOLAPAMIENTO_FRAGMENTO = 120
VERSION_INDICE = "3"  # súbela si cambia la forma de fragmentar o indexar
# Umbrales calibrados con el corpus real: las preguntas de crianza dan un BM25
# máximo >= 9.9 y las preguntas ajenas (satélites, impuestos, vacunas...) <= 8.1.
PUNTAJE_BM25_MINIMO = 9.0
UNIDADES_MINIMAS = 2.0  # coincidencias de palabras (las expandidas valen 0.5)
PUNTAJE_BM25_COINCIDENCIA_UNICA = 12.0
DISTANCIA_COINCIDENCIA_UNICA = 0.57
CANDIDATOS_VECTORIALES = 40
K_RRF = 60
NOMBRE_COLECCION = "crianzapp_conocimiento"
MODELO_EMBEDDINGS = "sentence-transformers/all-MiniLM-L6-v2"
TAGS_BLOQUE_HTML = {
    "article", "blockquote", "br", "dd", "div", "dl", "dt", "figcaption",
    "h1", "h2", "h3", "h4", "h5", "h6", "li", "ol", "p", "section", "td",
    "th", "tr", "ul",
}
TAGS_IGNORADOS_HTML = {"head", "script", "style", "noscript", "svg"}

# Palabras funcionales y de relleno: aparecen en cualquier pregunta o documento
# y no ayudan a decidir si hay evidencia. Se comparan sin tildes.
PALABRAS_VACIAS = set(
    """
    a al algo algun alguna algunas alguno algunos ante antes aqui asi aun aunque
    cada casi como con contra cual cuales cuando cuanto de del demas desde donde
    dos durante e el ella ellas ello ellos en entre era eran es esa esas ese eso
    esos esta estaba estan estar este esto estos fue fueron ha han hasta hay he
    hace haces hacer hago hacerle hacerlo la las le les lo los mas me mi mis mucho
    muy nada ni no nos nosotros o os otra otras otro otros para pero poco por
    porque primer puede puedo puedes pueden podria podrias podemos que quien
    quiero quisiera se segun ser si sin sobre son su sus tal tambien tan tanto te
    tener tiene tienen todo todos tu tus un una uno unas unos usted va vez voy y
    ya yo
    debo deberia dia siempre mejor ayudar ayudame importante actual frente
    articulo documento evidencia tbri gomez muzzio lin lewry et colombia
    hijo hija hijos hijas nino nina ninos ninas bebe
    ano anos mal bien mucha muchas muchos
    alrededor bajo baja bajos bajas necesita necesito necesitan necesitar
    actual actuales cuesta costo conciliar dificultad dificultades
    """.split()
)
_ESTADO_STEM = SpanishStemmer()

# Grupos de equivalencia para vocabulario cotidiano frente a vocabulario del
# corpus. Se aplican a las palabras ya sin tildes y antes de derivar la raíz.
GRUPOS_SINONIMOS = (
    ("pantalla", "television", "tele"),
    ("rabieta", "berrinche", "pataleta"),
    ("emocion", "sentimiento"),
    (
        "sueno", "dormir", "dormida", "dormido", "dormirse", "acostar",
        "acostarse", "acostarlo", "acostarla", "acostarle", "descanso",
        "descansar", "nocturno", "nocturna", "noche",
    ),
    ("intervencion", "intervention"),
    ("efecto", "effect"),
    ("padre", "padres", "parent", "parents", "parenting"),
    ("postparto", "postpartum"),
    ("apoyo", "support"),
    ("depresion", "depressive", "depression"),
    ("moderador", "moderators", "moderator"),
    ("efectividad", "effectiveness"),
    ("orientacion", "orientation"),
    ("guiado", "guided"),
    ("autoeficacia", "efficacy", "selfefficacy"),
    ("desregulado", "desregulada", "desregularse", "desregulacion"),
)
_SINONIMO_CANONICO = {
    sinonimo: grupo[0] for grupo in GRUPOS_SINONIMOS for sinonimo in grupo
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

# Del lenguaje de una madre o un padre al vocabulario del corpus (TBRI). Cada
# regla añade términos de búsqueda, con la mitad de peso que las palabras
# originales; no sustituye ni inventa contenido: solo ayuda a encontrarlo.
_EXPANSIONES_CRIANZA = (
    (  # crisis emocionales
        r"\b(rabieta|berrinche|pataleta|crisis|explot\w*|desborda\w*|descontrol\w*|"
        r"llora\w*|llanto|grita\w*|desregul\w*|colera|ataque de)",
        "autorregulación interacción para calmar niveles de respuesta emociones",
    ),
    (  # agresión física o conducta destructiva
        r"\b(pega\w*|golpe\w*|muerde\w*|muerdo|empuj\w*|patea\w*|agred\w*|agresiv\w*|"
        r"destru\w*|rompe\w*|violent\w*|lastim\w*)",
        "comportamiento desafiante niveles de respuesta interacción para proteger "
        "sin lastimar",
    ),
    (  # desobediencia y respuestas desafiantes
        r"\b(no me escucha|no escucha|no obedece|desobedec\w*|desafia\w*|grosero|"
        r"grosera|irrespetuos\w*|contesta\w*|habla mal|insolente|retador\w*|re-?do)",
        "interacción divertida respuesta ideal repetición intentarlo de nuevo con "
        "respeto escuchar obedecer",
    ),
    (  # castigo, límites y disciplina
        r"\b(castig\w*|regaña\w*|regañ\w*|disciplin\w*|limite\w*|norma\w*|regla\w*|"
        r"consecuencia\w*|premio\w*|recompensa\w*|tradicional\w*)",
        "corrección estrategias proactivas respuesta ideal estilos de cuidado "
        "autoritativo autoritario permisivo estructura cuidado",
    ),
    (  # transiciones y cambios
        r"\b(transicion\w*|cambio\w* de|mudanza|mudarse|salir de casa|nuevo hermano|"
        r"llegada de|cambiar de colegio|cambio de rutina|aterra\w*)",
        "transiciones horario de transiciones diarias predecibilidad ambientes "
        "predecibles",
    ),
    (  # cuerpo: alimentación e hidratación
        r"\b(hambre|comer|come|comida\w*|aliment\w*|azucar|glucosa|glucemia|"
        r"deshidrat\w*|merienda\w*|agua|esconde comida)",
        "hidratación glucemia meriendas cada dos horas acaparamiento de alimentos",
    ),
    (  # sistema sensorial y estrés corporal
        r"\b(sensorial\w*|sobrecarga|ruido\w*|hipervigilan\w*|ansiedad|ansios\w*|"
        r"miedo\w*|alerta|estres\w*|inquiet\w*|tension|senal\w* (?:del )?cuerpo|"
        r"corporal\w*)",
        "sentidos procesamiento sensorial sensación de seguridad lucha huida "
        "paralización",
    ),
    (  # apego, confianza y rechazo
        r"\b(confianza|confiar|ruptura\w*|adopt\w*|acogimiento|acogida|acogido|"
        r"abandono|apego|vinculo\w*|rechaz\w*|rechazo\w*|cuidadores anteriores)",
        "apego confianza conexión relación basada en la confianza",
    ),
    (  # contacto físico y consuelo
        r"\b(consol\w*|abraz\w*|contacto|tocar|acercar\w*|acercarme|caricia\w*)",
        "contacto saludable contacto visual apego conexión calmar",
    ),
    (  # juego
        r"\b(jug\w*|juego\w*|ludic\w*|divertid\w*|playful)",
        "interacción divertida juego alegría risas",
    ),
    (  # sentimientos y su validación
        r"\b(validar|valido|emocion\w*|sentimiento\w*|enojo|rabia|tristeza|"
        r"frustraci\w*)",
        "emociones sentimientos autorregulación estados emocionales gráfica de "
        "sentimientos adultos modelan",
    ),
    (  # el propio adulto
        r"\b(paciencia|culpa|desgaste|agotamiento|agotad\w*|perder el control|"
        r"desesper\w*|pierdo|presencia comprometida|atencion plena)",
        "adultos modelan autorregulación presencia tranquila conciencia "
        "sintonización calmar",
    ),
    (  # elogio, voz y poder
        r"\b(elogi\w*|motivar|opciones|elegir|decidir|negociar|empoderar\w*|"
        r"autonom\w*|poder compartido)",
        "dar opciones acuerdos compartir el poder dar una voz admiración elogios "
        "aliento",
    ),
    (  # hermanos y relaciones
        r"\b(hermano\w*|celos|pelea\w*|peleas)",
        "relacionarse conexión tres reglas para las relaciones mantenerse juntos "
        "sin lastimar",
    ),
    (  # mentiras
        r"\b(mentir\w*|miente|mentira\w*)",
        "corrección respuesta ideal niveles de respuesta interacción estructurada",
    ),
    (  # sueño
        r"\b(sueno|dormir|dormirse|duerm\w*|acost\w*|noche|nocturn\w*|conciliar)",
        "rutina hora de dormir rituales luces libro",
    ),
    (  # rutinas y rituales
        r"\b(rutina\w*|ritual\w*|habito\w*)",
        "rituales diarios rutinas conexión",
    ),
    (  # escuela
        r"\b(colegio|escuela|tarea\w*|maestr\w*|profesor\w*|clase\w*)",
        "escuela salón de clases meriendas transiciones autorregulación",
    ),
)
_EXPANSIONES_CRIANZA = tuple(
    (re.compile(patron), expansion) for patron, expansion in _EXPANSIONES_CRIANZA
)


def _sin_tildes(texto: str) -> str:
    normalizado = unicodedata.normalize("NFD", texto.lower())
    return "".join(c for c in normalizado if unicodedata.category(c) != "Mn")


def _raiz(palabra: str) -> str:
    raiz = _ESTADO_STEM.stem(palabra)
    # "desregulado" y "autorregulación" comparten raíz con "regulación".
    if raiz in {"desregul", "autorregul", "rregul"}:
        return "regul"
    return raiz


def _tokenizar_relevante(texto: str) -> list[str]:
    """Palabras de contenido: sin tildes, sin palabras vacías, con raíz."""
    sin_acentos = _sin_tildes(texto)
    # "4 años", "tres años": la edad no debe coincidir con cifras del corpus.
    sin_acentos = re.sub(
        r"\b(?:\d+|uno|una|un|dos|tres|cuatro|cinco|seis|siete|ocho|nueve|diez|"
        r"once|doce)\s+anos?\b",
        " ",
        sin_acentos,
    )
    terminos: list[str] = []
    for token in re.findall(r"[a-z0-9]+", sin_acentos):
        if token.isdigit() or len(token) < 3:
            continue
        token = _SINONIMO_CANONICO.get(token, token)
        if token in PALABRAS_VACIAS:
            continue
        terminos.append(_raiz(token))
    if re.search(
        r"\b(?:que es|que significa|significan las siglas|siglas de|definicion|se define)\b",
        sin_acentos,
    ):
        terminos.append("definicion")
    return terminos


def _terminos_relevantes(texto: str) -> set[str]:
    """Obtiene términos de contenido normalizados y sin duplicados."""
    return set(_tokenizar_relevante(texto))


def _expandir_consulta(consulta: str) -> list[str]:
    """Términos del vocabulario del corpus que corresponden a la consulta."""
    normalizada = _sin_tildes(consulta)
    expansiones = [
        texto for patron, texto in _EXPANSIONES_CRIANZA if patron.search(normalizada)
    ]
    terminos = _terminos_relevantes(consulta)
    ingles = {
        _EXPANSIONES_INGLES[t] for t in terminos if t in _EXPANSIONES_INGLES
    }
    if "digital" in terminos:
        ingles.add("digital")
    if len(ingles) >= 2:
        expansiones.append(" ".join(sorted(ingles)))
    return expansiones


def _puntaje_bm25(
    pesos: dict[str, float],
    terminos_documento: list[str],
    frecuencia_documental: Counter[str],
    cantidad_documentos: int,
    longitud_media: float,
) -> float:
    """BM25 (k1=1.5, b=0.75) con peso por término de la consulta."""
    if not cantidad_documentos or not longitud_media:
        return 0.0
    frecuencias = Counter(terminos_documento)
    puntaje = 0.0
    for termino, peso in pesos.items():
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
        puntaje += peso * idf * (frecuencia * 2.5) / normalizacion
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
    titulo: str | None = None


class _ExtractorHTML(HTMLParser):
    """Extrae texto visible de HTML y conserva encabezados como secciones."""

    def __init__(self, titulo_inicial: str) -> None:
        super().__init__(convert_charrefs=True)
        self.titulo = titulo_inicial
        self.partes: list[str] = []
        self.secciones: list[tuple[str, dict[str, Any]]] = []
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


_ENCABEZADO_MD = re.compile(r"^\s{0,3}(#{1,6})\s+(.+?)\s*#*\s*$")
_ENCABEZADO_PAGINA = re.compile(r"^P[áa]gina\s+(\d+)(?:\s*[—–-]\s*(.+))?$")


def _leer_markdown(texto: str, nombre: str) -> list[tuple[str, dict[str, Any]]]:
    """Divide Markdown por encabezados; reconoce `## Página N — Título`.

    Los `.md` generados por `scripts/pdf_a_markdown.py` usan ese formato para
    conservar el número de página del PDF original en las citas.
    """
    secciones: list[tuple[str, dict[str, Any]]] = []
    metadatos: dict[str, Any] = {"section": nombre}
    titulo_documento: str | None = None
    lineas: list[str] = []

    def cerrar() -> None:
        contenido = "\n".join(lineas).strip()
        if contenido:
            datos = dict(metadatos)
            if titulo_documento:
                datos["document_title"] = titulo_documento
            secciones.append((contenido, datos))

    for linea in texto.splitlines():
        coincidencia = _ENCABEZADO_MD.match(linea)
        if not coincidencia:
            lineas.append(linea)
            continue
        nivel, encabezado = len(coincidencia.group(1)), coincidencia.group(2).strip()
        pagina = _ENCABEZADO_PAGINA.match(encabezado)
        if nivel == 1 and not secciones and not "".join(lineas).strip():
            titulo_documento = encabezado
            metadatos = {"section": encabezado}
            lineas = []
            continue
        cerrar()
        if pagina:
            metadatos = {"page": int(pagina.group(1))}
            if pagina.group(2):
                metadatos["section"] = pagina.group(2).strip()
            lineas = []
        else:
            metadatos = {"section": encabezado}
            lineas = [linea]
    cerrar()
    return secciones


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
        return _leer_markdown(texto, archivo.stem)

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


def _unidades_de_texto(texto: str, tamano: int) -> list[str]:
    """Divide en párrafos, luego frases y, si hace falta, palabras."""
    unidades: list[str] = []
    for parrafo in re.split(r"\n\s*\n", texto):
        parrafo = parrafo.strip()
        if not parrafo:
            continue
        if len(parrafo) <= tamano:
            unidades.append(parrafo)
            continue
        for frase in re.split(r"(?<=[.!?;:])\s+", parrafo):
            if len(frase) <= tamano:
                unidades.append(frase)
                continue
            actual = ""
            for palabra in frase.split():
                if actual and len(actual) + 1 + len(palabra) > tamano:
                    unidades.append(actual)
                    actual = palabra
                else:
                    actual = f"{actual} {palabra}".strip()
            if actual:
                unidades.append(actual)
    return unidades


def _fragmentar(texto: str, tamano: int, solapamiento: int) -> list[str]:
    """Agrupa párrafos/frases completos hasta `tamano` caracteres.

    Nunca corta a mitad de frase y repite al inicio del siguiente fragmento las
    últimas unidades del anterior (hasta `solapamiento` caracteres) para no
    perder el contexto en el límite.
    """
    fragmentos: list[str] = []
    actual: list[str] = []
    longitud = 0
    for unidad in _unidades_de_texto(texto, tamano):
        if actual and longitud + 2 + len(unidad) > tamano:
            fragmentos.append("\n\n".join(actual))
            arrastre: list[str] = []
            acumulado = 0
            for previa in reversed(actual):
                if acumulado + len(previa) > solapamiento:
                    break
                arrastre.insert(0, previa)
                acumulado += len(previa) + 2
            actual, longitud = arrastre, acumulado
        actual.append(unidad)
        longitud += len(unidad) + 2
    if actual:
        fragmentos.append("\n\n".join(actual))
    # Un fragmento que solo repite el arrastre del anterior no aporta nada.
    return [
        f for i, f in enumerate(fragmentos)
        if i == 0 or f not in fragmentos[i - 1]
    ]


class BaseConocimientoLocal:
    """Índice híbrido (BM25 + Chroma opcional) sobre documentos locales."""

    def __init__(
        self,
        fragmentos: list[FragmentoConocimiento],
        coleccion: Any,
        client: Any,
    ) -> None:
        self.fragmentos = fragmentos
        self._coleccion = coleccion
        self._client = client
        self._por_id = {f.chunk_id: f for f in fragmentos}
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
        self._vectores_disponibles = coleccion is not None

    @property
    def vectores_disponibles(self) -> bool:
        return self._vectores_disponibles

    @classmethod
    def cargar(
        cls,
        directorio: str | Path,
        directorio_vectorstore: str | Path | None = None,
        chunk_size: int = TAMANO_FRAGMENTO,
        chunk_overlap: int = SOLAPAMIENTO_FRAGMENTO,
        embedding_function: Any | None = None,
        usar_vectores: bool = True,
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
            else Path(
                os.getenv("RAG_VECTORSTORE_DIR", "").strip()
                or ruta.parent.parent / "vectorstore"
            ).resolve()
        )

        documentos: list[dict[str, Any]] = []
        contenido_hash = hashlib.sha256()
        contenido_hash.update(
            f"{VERSION_INDICE}:{chunk_size}:{chunk_overlap}:{MODELO_EMBEDDINGS}".encode(
                "utf-8"
            )
        )
        for archivo in _archivos_admitidos(ruta):
            fuente = archivo.relative_to(ruta).as_posix()
            contenido_hash.update(fuente.encode("utf-8"))
            contenido_hash.update(archivo.read_bytes())
            indice_fragmento = 0
            for texto, ubicacion in _leer_texto(archivo):
                ubicacion = dict(ubicacion)
                titulo_documento = ubicacion.pop("document_title", None)
                seccion = ubicacion.get("section")
                for trozo in _fragmentar(texto, chunk_size, chunk_overlap):
                    trozo = trozo.strip()
                    if not trozo:
                        continue
                    # El título de la página ayuda a encontrar el fragmento
                    # ("Estrategias fisiológicas: hidratación, glucemia").
                    if (
                        "page" in ubicacion
                        and seccion
                        and not trozo.startswith(seccion)
                    ):
                        trozo = f"{seccion}\n\n{trozo}"
                    chunk_id = (
                        f"{hashlib.sha256(fuente.encode()).hexdigest()[:12]}-"
                        f"{indice_fragmento}"
                    )
                    metadatos: dict[str, Any] = {
                        "source": fuente,
                        "filename": archivo.name,
                        "chunk_id": chunk_id,
                        **ubicacion,
                    }
                    if titulo_documento:
                        metadatos["document_title"] = titulo_documento
                    documentos.append({"text": trozo, "metadata": metadatos})
                    indice_fragmento += 1

        fragmentos = [
            FragmentoConocimiento(
                fuente=str(item["metadata"]["source"]),
                texto=str(item["text"]),
                chunk_id=str(item["metadata"]["chunk_id"]),
                page=item["metadata"].get("page"),
                section=item["metadata"].get("section"),
                titulo=item["metadata"].get("document_title"),
            )
            for item in documentos
        ]

        cliente = coleccion = None
        if usar_vectores:
            try:
                cliente, coleccion = cls._preparar_vectores(
                    documentos,
                    contenido_hash.hexdigest(),
                    ruta_vectorstore,
                    chunk_size,
                    chunk_overlap,
                    embedding_function,
                )
            except Exception:
                LOGGER.warning(
                    "No se pudo preparar el índice vectorial (¿sin conexión para "
                    "descargar el modelo de embeddings?). Se usará solo la "
                    "búsqueda léxica BM25.",
                    exc_info=True,
                )
                cliente = coleccion = None
        return cls(fragmentos, coleccion, cliente)

    @staticmethod
    def _preparar_vectores(
        documentos: list[dict[str, Any]],
        huella_corpus: str,
        ruta_vectorstore: Path,
        chunk_size: int,
        chunk_overlap: int,
        embedding_function: Any | None,
    ) -> tuple[Any, Any]:
        import chromadb
        from chromadb.config import Settings
        from chromadb.utils.embedding_functions import DefaultEmbeddingFunction

        ruta_vectorstore.mkdir(parents=True, exist_ok=True)
        cliente = chromadb.PersistentClient(
            path=str(ruta_vectorstore),
            settings=Settings(anonymized_telemetry=False),
        )
        funcion = embedding_function or DefaultEmbeddingFunction()
        metadatos = {
            "hnsw:space": "cosine",
            "corpus_hash": huella_corpus,
            "embedding_model": MODELO_EMBEDDINGS,
            "chunk_size": chunk_size,
            "chunk_overlap": chunk_overlap,
        }
        coleccion = cliente.get_or_create_collection(
            name=NOMBRE_COLECCION,
            embedding_function=funcion,
            metadata=metadatos,
        )
        if coleccion.metadata.get("corpus_hash") != huella_corpus or (
            documentos and coleccion.count() == 0
        ):
            cliente.delete_collection(NOMBRE_COLECCION)
            coleccion = cliente.create_collection(
                name=NOMBRE_COLECCION,
                embedding_function=funcion,
                metadata=metadatos,
            )
            if documentos:
                coleccion.add(
                    ids=[item["metadata"]["chunk_id"] for item in documentos],
                    documents=[item["text"] for item in documentos],
                    metadatas=[item["metadata"] for item in documentos],
                )
        return cliente, coleccion

    def _idf(self, termino: str) -> float:
        n = len(self.fragmentos)
        df = self._frecuencia_documental.get(termino, 0)
        return math.log(1 + (n - df + 0.5) / (df + 0.5))

    def _distancias_vectoriales(self, consultas: list[str]) -> dict[str, float]:
        """Distancia coseno mínima por fragmento; vacío si no hay vectores."""
        if not self._vectores_disponibles:
            return {}
        try:
            resultado = self._coleccion.query(
                query_texts=consultas,
                n_results=min(CANDIDATOS_VECTORIALES, self._coleccion.count()),
                include=["distances"],
            )
        except Exception:
            LOGGER.warning(
                "Falló la consulta vectorial; se continúa solo con BM25.",
                exc_info=True,
            )
            self._vectores_disponibles = False
            return {}
        distancias: dict[str, float] = {}
        for ids, valores in zip(resultado["ids"], resultado["distances"]):
            for chunk_id, distancia in zip(ids, valores):
                actual = distancias.get(str(chunk_id))
                if actual is None or distancia < actual:
                    distancias[str(chunk_id)] = float(distancia)
        return distancias

    def buscar(self, consulta: str, limite: int = 3) -> list[FragmentoConocimiento]:
        """Combina BM25 y similitud semántica y descarta evidencia débil.

        Un fragmento solo cuenta como evidencia si coincide en al menos dos
        señales (palabras de la pregunta o de su expansión al vocabulario TBRI)
        y supera un puntaje BM25 mínimo: una pregunta ajena al corpus puede
        compartir una palabra suelta ("recomendada") pero no alcanza ese puntaje.
        """
        if not consulta.strip() or limite <= 0 or not self.fragmentos:
            return []

        base = _terminos_relevantes(consulta)
        if not base:
            return []
        expansiones = _expandir_consulta(consulta)
        extra = _terminos_relevantes(" ".join(expansiones)) - base
        pesos = {termino: 1.0 for termino in base}
        pesos.update({termino: 0.5 for termino in extra})

        distancias = self._distancias_vectoriales(
            [consulta, f"{consulta} {' '.join(expansiones)}"]
            if expansiones
            else [consulta]
        )

        puntajes: dict[str, float] = {}
        for fragmento in self.fragmentos:
            terminos = self._terminos_por_fragmento[fragmento.chunk_id]
            presentes = set(terminos)
            en_base = base & presentes
            en_extra = extra & presentes
            if not en_base and len(en_extra) < 2:
                continue
            unidades = len(en_base) + 0.5 * len(en_extra)
            puntaje = _puntaje_bm25(
                pesos,
                terminos,
                self._frecuencia_documental,
                len(self.fragmentos),
                self._longitud_media,
            )
            if unidades >= UNIDADES_MINIMAS:
                if puntaje < PUNTAJE_BM25_MINIMO:
                    continue
            else:
                # Coincidencia de una sola palabra: solo con señal muy fuerte.
                distancia = distancias.get(fragmento.chunk_id, 1.0)
                if puntaje < PUNTAJE_BM25_COINCIDENCIA_UNICA or (
                    distancias and distancia > DISTANCIA_COINCIDENCIA_UNICA
                ):
                    continue
            puntajes[fragmento.chunk_id] = puntaje

        if not puntajes:
            return []

        # Fusión por rango recíproco: BM25 manda, los vectores desempatan.
        orden_lexico = sorted(puntajes, key=lambda i: -puntajes[i])
        fusion: dict[str, float] = {
            chunk_id: 1.0 / (K_RRF + rango)
            for rango, chunk_id in enumerate(orden_lexico, start=1)
        }
        if distancias:
            orden_vectorial = sorted(distancias, key=lambda i: distancias[i])
            for rango, chunk_id in enumerate(orden_vectorial, start=1):
                if chunk_id in fusion:
                    fusion[chunk_id] += 0.5 / (K_RRF + rango)

        elegidos = sorted(fusion, key=lambda i: -fusion[i])[:limite]
        return [
            FragmentoConocimiento(
                fuente=self._por_id[i].fuente,
                texto=self._por_id[i].texto,
                chunk_id=i,
                page=self._por_id[i].page,
                section=self._por_id[i].section,
                distancia=distancias.get(i, 0.0),
                titulo=self._por_id[i].titulo,
            )
            for i in elegidos
        ]
