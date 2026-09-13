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


def _tokens(texto: str) -> set[str]:
    return set(re.findall(r"[a-z0-9]+", _normalizar(texto)))


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