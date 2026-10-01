"""Carga y búsqueda local de una base de conocimiento en texto."""

from dataclasses import dataclass
from pathlib import Path
import re
import unicodedata


@dataclass(frozen=True)
class FragmentoConocimiento:
    """Fragmento recuperable junto con la fuente local de origen."""

    fuente: str
    texto: str
    puntuacion: int = 0


def _normalizar(texto: str) -> str:
    texto = unicodedata.normalize("NFD", texto.lower())
    return "".join(
        caracter for caracter in texto
        if unicodedata.category(caracter) != "Mn"
    )


PALABRAS_COMUNES = {
    "a", "al", "cada", "con", "como", "de", "del", "el", "en", "es",
    "esta", "este", "hacer", "la", "las", "le", "los", "mi", "no",
    "niña", "niño", "o", "para", "que", "se", "su", "tiene", "un", "una",
    "y", "años", "hijo", "hija", "hijos", "hijas", "cuando", "hace",
    "apago",
}

PALABRAS_COMUNES_NORMALIZADAS = {_normalizar(palabra) for palabra in PALABRAS_COMUNES}
SINONIMOS_CONSULTA = {
    "television": {"pantalla"},
    "pantalla": {"television"},
    "berrinche": {"rabieta"},
    "rabieta": {"berrinche"},
    "enojo": {"frustracion"},
    "enojado": {"frustracion"},
    "sentimiento": {"emocion"},
    "sentimientos": {"emocion"},
}


def _tokens(texto: str) -> set[str]:
    tokens = set(re.findall(r"[a-z0-9]+", _normalizar(texto)))
    return {
        token[:-1] if token.endswith("s") and len(token) > 4 else token
        for token in tokens - PALABRAS_COMUNES_NORMALIZADAS
    }


class BaseConocimientoLocal:
    """Repositorio de fragmentos leído exclusivamente desde disco."""

    EXTENSIONES_ADMITIDAS = {".md", ".txt"}

    def __init__(self, fragmentos: list[FragmentoConocimiento]):
        self.fragmentos = fragmentos

    @classmethod
    def cargar(cls, directorio: str | Path) -> "BaseConocimientoLocal":
        ruta = Path(directorio)
        fragmentos = []
        for archivo in sorted(ruta.rglob("*")):
            if archivo.is_file() and archivo.suffix.lower() in cls.EXTENSIONES_ADMITIDAS:
                contenido = archivo.read_text(encoding="utf-8")
                for bloque in re.split(r"\n\s*\n", contenido):
                    bloque = bloque.strip()
                    if bloque:
                        fragmentos.append(
                            FragmentoConocimiento(
                                fuente=str(archivo.relative_to(ruta)),
                                texto=bloque,
                            )
                        )
        return cls(fragmentos)

    def buscar(self, consulta: str, limite: int = 3) -> list[FragmentoConocimiento]:
        """Devuelve los fragmentos con mayor coincidencia léxica."""
        tokens_consulta = _tokens(consulta)
        tokens_consulta.update(
            sinonimo
            for token in tuple(tokens_consulta)
            for sinonimo in SINONIMOS_CONSULTA.get(token, set())
        )
        puntuados = []
        for fragmento in self.fragmentos:
            coincidencias = tokens_consulta & _tokens(fragmento.texto)
            if coincidencias:
                puntuados.append(
                    FragmentoConocimiento(
                        fuente=fragmento.fuente,
                        texto=fragmento.texto,
                        puntuacion=len(coincidencias),
                    )
                )
        puntuados.sort(key=lambda fragmento: (-fragmento.puntuacion, fragmento.fuente))
        return puntuados[:limite]