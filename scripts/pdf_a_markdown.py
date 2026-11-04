#!/usr/bin/env python3
"""Convierte los PDF de la base de conocimiento en Markdown limpio.

Uso (desde la raíz del proyecto):

    python scripts/pdf_a_markdown.py

Lee los PDF de ``docs/fuentes_originales/`` y escribe un ``.md`` por PDF en
``docs/base_conocimiento/``. Cada página queda como una sección::

    ## Página 15 — Estrategias fisiológicas: hidratación, glucemia

para que el índice conserve el número de página del PDF original y las citas
del chat sigan apuntando a la página correcta.

Qué limpia (y por qué mejora la recuperación):
- Avisos de copyright y encabezados/pies de página repetidos en cada página.
- Guiones de fin de línea ("significa-\\ndos") y saltos de línea a mitad de frase.
- Ejercicios del libro de trabajo: preguntas de reflexión (¿...?), espacios
  en blanco ("______") y listas vacías, que no son contenido sino consignas.
- Portadas, índices, hojas de notas y bibliografía (la bibliografía indexada
  produce falsos positivos: nombres de autores y títulos de otros trabajos).
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

from pypdf import PdfReader

RAIZ = Path(__file__).resolve().parent.parent
ORIGEN = RAIZ / "docs" / "fuentes_originales"
DESTINO = RAIZ / "docs" / "base_conocimiento"

COPYRIGHT = re.compile(
    r"©\s*2013\s+Instituto de Desarrollo Infantil.*?escrito del ICD\.?",
    re.DOTALL,
)
ENCABEZADO_TBRI = re.compile(
    r"^(?:(?P<n1>\d{1,2})\s+(?P<t1>[^.?!]{3,100})|(?P<t2>[^.?!]{3,100}?)\s+(?P<n2>\d{1,2}))$"
)
LINEA_VACIA = re.compile(r"^[\s•°\-_.\d]*$")
BIBLIOGRAFIA = re.compile(
    r"^\s*(Referencias|REFERENCIAS|Referencias bibliográficas|References|REFERENCES|Bibliografía)\s*$"
)
PAGINAS_NO_UTILES = re.compile(
    r"(Fort Worth, TX|TCU Box|Notas del participante|^\s*Índice\b)", re.MULTILINE
)
# Encabezados y pies de página de los artículos (texto repetido en cada página).
RUIDO_ARTICULO = [
    re.compile(r"^Es\s*tE\s*Ba\s*n\b.*$"),
    re.compile(r"^EF\s*Ec\s*t\s*iVi\s*d\s*a\s*d\b.*$"),
    re.compile(r"^un\s+dEs\s+aFí\s*o\b.*$"),
    re.compile(r"^TERAPIA PSICOL\S*.*$"),
    re.compile(r"^2008, V\s*ol\..*$"),
    re.compile(r"^Copyright 2008 by.*$"),
    re.compile(r"^ISSN \d{4}-\d{3}[\dX].*$"),
    re.compile(r"^International Journal of Medical Informatics 185.*$"),
    re.compile(r"^M\. Lin-Lewry et al\.$"),
    re.compile(r"^\d{1,3}$"),
]

# nombre del PDF -> (estilo, metadatos del documento)
DOCUMENTOS = {
    "02. (español) TBRI Conexion participante": (
        "taller",
        "TBRI — Principios de Conexión (libro de trabajo del participante)",
    ),
    "03. (español) TBRI Correccion participante": (
        "taller",
        "TBRI — Principios de Corrección (libro de trabajo del participante)",
    ),
    "04. (español) TBRI Empoderamiento participante": (
        "taller",
        "TBRI — Principios de Empoderamiento (libro de trabajo del participante)",
    ),
    "34. Gomez Muzzio": (
        "articulo",
        "Gómez Muzzio, Muñoz y Santelices (2008) — Efectividad de las intervenciones "
        "en apego con infancia vulnerada",
    ),
    "39": (
        "articulo",
        "Lin-Lewry et al. (2024) — Revisión sistemática de intervenciones digitales "
        "de crianza (en inglés)",
    ),
}


def _quitar_preguntas(texto: str) -> str:
    """Elimina las consignas de reflexión del libro de trabajo.

    Se quitan los bloques que *son* una pregunta ("¿Qué va bien...?") y todo lo
    que sigue a "Preguntas para reflexionar". Las preguntas que aparecen dentro
    de un párrafo, como ejemplos de frases para decirle al niño, se conservan.
    """
    texto = re.sub(r"(?is)[–-]?\s*preguntas para reflexionar.*$", " ", texto)
    if re.match(r"^(?:•\s*)?(?:\d+\.\s*)?¿", texto.strip()):
        return ""
    return texto


def _normalizar_espacios(texto: str) -> str:
    texto = re.sub(r"(?<=\w)\s+(?=[,.;:])", "", texto)
    return re.sub(r"[ \t]+", " ", texto).strip()


def _limpiar_pagina_taller(bruto: str) -> tuple[str | None, str]:
    """Limpia una página de libro de trabajo. Devuelve (título, texto)."""
    texto = COPYRIGHT.sub("", bruto)
    lineas = [linea.strip() for linea in texto.splitlines()]
    lineas = [linea for linea in lineas if linea]

    titulo: str | None = None
    for posicion, linea in enumerate(lineas[:3]):
        coincidencia = ENCABEZADO_TBRI.match(linea)
        if coincidencia:
            titulo = (coincidencia.group("t1") or coincidencia.group("t2")).strip()
            del lineas[posicion]
            break

    limpias: list[str] = []
    for linea in lineas:
        if LINEA_VACIA.match(linea) or linea.strip() == "NOTAS":
            limpias.append("")  # separador de bloque
            continue
        linea = re.sub(r"_{2,}", " ", linea)
        limpias.append(linea.strip())

    bloques: list[str] = []
    actual = ""
    ultima_linea = ""

    def cerrar() -> None:
        nonlocal actual, ultima_linea
        if actual.strip():
            bloques.append(actual.strip())
        actual = ""
        ultima_linea = ""

    for linea in limpias:
        if not linea:
            cerrar()
            continue
        if linea.startswith("•"):
            cerrar()
            actual = linea
            ultima_linea = linea
            continue
        if not actual:
            actual = linea
            ultima_linea = linea
            continue
        previa = actual
        # El PDF parte las líneas a ~85-95 caracteres: una línea larga sin
        # punto final continúa en la siguiente; una corta es un título o fin de
        # párrafo.
        if previa.endswith("-") and linea[:1].islower():
            actual = previa[:-1] + linea
        elif (
            linea[:1].islower()
            or previa.endswith((",", ";", "("))
            or (len(ultima_linea) >= 78 and not previa.endswith((".", ":", "?", "!")))
        ):
            actual = f"{previa} {linea}"
        else:
            cerrar()
            actual = linea
        ultima_linea = linea
    cerrar()

    limpios = []
    for bloque in bloques:
        bloque = _normalizar_espacios(_quitar_preguntas(bloque))
        bloque = re.sub(r"^•\s*•+\s*", "• ", bloque)
        bloque = re.sub(r"\s*•\s*$", "", bloque)  # viñeta vacía al final
        if len(bloque) >= 3 and not LINEA_VACIA.match(bloque):
            limpios.append(bloque)

    resultado: list[str] = []
    for posicion, bloque in enumerate(limpios):
        siguiente = limpios[posicion + 1] if posicion + 1 < len(limpios) else ""
        # Consigna de ejercicio ("Dos maneras en que puedo ... son:") sin
        # viñetas con contenido a continuación: no aporta información.
        if bloque.endswith(":") and re.match(
            r"(?i)(algunas|dos|tres|cuatro)\s+(maneras|formas|ideas)", bloque
        ) and not siguiente.startswith("•"):
            continue
        resultado.append(bloque)
    return titulo, "\n\n".join(resultado)


def _limpiar_pagina_articulo(bruto: str) -> tuple[bool, str]:
    """Limpia una página de artículo científico. Devuelve (llegó_bibliografía, texto)."""
    lineas: list[str] = []
    for linea in bruto.splitlines():
        linea = linea.strip()
        if not linea:
            continue
        if BIBLIOGRAFIA.match(linea):
            return True, _unir_flujo(lineas)
        if any(patron.match(linea) for patron in RUIDO_ARTICULO):
            continue
        lineas.append(linea)
    return False, _unir_flujo(lineas)


def _unir_flujo(lineas: list[str]) -> str:
    texto = ""
    for linea in lineas:
        if not texto:
            texto = linea
        elif texto.endswith("-") and linea[:1].islower():
            texto = texto[:-1] + linea  # "significa-" + "dos" -> "significados"
        else:
            texto = f"{texto} {linea}"
    return _normalizar_espacios(texto)


def convertir(pdf: Path, destino: Path) -> tuple[int, int]:
    """Convierte un PDF; devuelve (páginas_escritas, caracteres)."""
    estilo, titulo_doc = DOCUMENTOS.get(
        pdf.stem, ("articulo", pdf.stem)
    )
    partes = [f"# {titulo_doc}", ""]
    paginas = 0
    en_bibliografia = False
    for numero, pagina in enumerate(PdfReader(pdf).pages, start=1):
        if en_bibliografia:
            break
        bruto = pagina.extract_text() or ""
        if estilo == "taller":
            if PAGINAS_NO_UTILES.search(bruto) or len(re.findall(r"\.{5,}", bruto)) >= 3:
                continue
            titulo, texto = _limpiar_pagina_taller(bruto)
        else:
            en_bibliografia, texto = _limpiar_pagina_articulo(bruto)
            titulo = None
        if len(texto) < 250:
            continue
        encabezado = f"## Página {numero}" + (f" — {titulo}" if titulo else "")
        partes += [encabezado, "", texto, ""]
        paginas += 1
    contenido = "\n".join(partes).rstrip() + "\n"
    destino.write_text(contenido, encoding="utf-8")
    return paginas, len(contenido)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--origen", type=Path, default=ORIGEN)
    parser.add_argument("--destino", type=Path, default=DESTINO)
    argumentos = parser.parse_args()

    pdfs = sorted(argumentos.origen.glob("*.pdf"))
    if not pdfs:
        print(f"No hay PDF en {argumentos.origen}", file=sys.stderr)
        return 1
    argumentos.destino.mkdir(parents=True, exist_ok=True)
    for pdf in pdfs:
        salida = argumentos.destino / f"{pdf.stem}.md"
        paginas, caracteres = convertir(pdf, salida)
        print(f"{pdf.name} -> {salida.name}: {paginas} páginas, {caracteres} caracteres")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
