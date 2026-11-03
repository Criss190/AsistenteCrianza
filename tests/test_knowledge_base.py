from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from docx import Document
from pypdf import PdfWriter

from src.knowledge_base import (
    EXTENSIONES_ADMITIDAS,
    FUENTES_EXCLUIDAS,
    SOLAPAMIENTO_FRAGMENTO,
    TAMANO_FRAGMENTO,
    _archivos_admitidos,
    _leer_texto,
)


class KnowledgeBaseLoaderTests(unittest.TestCase):
    def test_chunking_configuration_is_explicit(self):
        self.assertEqual(TAMANO_FRAGMENTO, 500)
        self.assertEqual(SOLAPAMIENTO_FRAGMENTO, 50)
        self.assertEqual(
            EXTENSIONES_ADMITIDAS,
            {".pdf", ".docx", ".txt", ".md", ".html", ".htm"},
        )

    def test_provisional_markdown_is_excluded_but_derived_markdown_is_allowed(self):
        with TemporaryDirectory() as directorio:
            raiz = Path(directorio)
            (raiz / "guia_crianza.md").write_text(
                "Contenido provisional.", encoding="utf-8"
            )
            (raiz / "34.md").write_text(
                "# Documento derivado\nContenido extraído.", encoding="utf-8"
            )

            archivos = _archivos_admitidos(raiz)

        self.assertEqual(FUENTES_EXCLUIDAS, {"guia_crianza.md"})
        self.assertEqual([archivo.name for archivo in archivos], ["34.md"])

    def test_loaders_extract_text_and_location_metadata(self):
        with TemporaryDirectory() as directorio:
            raiz = Path(directorio)
            archivo_txt = raiz / "guia.txt"
            archivo_txt.write_text("Contenido de texto.", encoding="utf-8")

            archivo_md = raiz / "guia.md"
            archivo_md.write_text(
                "# Sección principal\nContenido Markdown.", encoding="utf-8"
            )
            archivo_html = raiz / "guia.html"
            archivo_html.write_text(
                "<html><head><title>No se indexa</title></head><body>"
                "<h1>Encabezado útil</h1><p>Texto visible&nbsp;para indexar.</p>"
                "<script>secreto()</script></body></html>",
                encoding="utf-8",
            )

            archivo_docx = raiz / "guia.docx"
            documento = Document()
            documento.add_heading("Sección DOCX", level=1)
            documento.add_paragraph("Contenido de Word.")
            documento.save(archivo_docx)

            archivo_pdf = raiz / "guia.pdf"
            escritor = PdfWriter()
            escritor.add_blank_page(width=612, height=792)
            with archivo_pdf.open("wb") as archivo:
                escritor.write(archivo)

            txt = _leer_texto(archivo_txt)
            markdown = _leer_texto(archivo_md)
            docx = _leer_texto(archivo_docx)
            pdf = _leer_texto(archivo_pdf)
            html = _leer_texto(archivo_html)

        self.assertIn("Contenido de texto.", txt[0][0])
        self.assertEqual(markdown[0][1]["section"], "Sección principal")
        self.assertEqual(docx[0][1]["section"], "Sección DOCX")
        self.assertEqual(pdf[0][1]["page"], 1)
        self.assertEqual(html[0][1]["section"], "Encabezado útil")
        self.assertIn("Texto visible para indexar.", html[0][0])
        self.assertNotIn("secreto", " ".join(texto for texto, _ in html))


if __name__ == "__main__":
    unittest.main()
