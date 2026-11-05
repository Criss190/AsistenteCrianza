from pathlib import Path
import re
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from docx import Document
from pypdf import PdfWriter

from src.knowledge_base import (
    EXTENSIONES_ADMITIDAS,
    FUENTES_EXCLUIDAS,
    SOLAPAMIENTO_FRAGMENTO,
    TAMANO_FRAGMENTO,
    BaseConocimientoLocal,
    _archivos_admitidos,
    _leer_texto,
)


class KnowledgeBaseLoaderTests(unittest.TestCase):
    def test_chunking_configuration_is_explicit(self):
        self.assertEqual(TAMANO_FRAGMENTO, 900)
        self.assertEqual(SOLAPAMIENTO_FRAGMENTO, 120)
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

    def test_vectorstore_directory_can_be_configured_with_environment(self):
        with TemporaryDirectory() as directorio:
            raiz = Path(directorio)
            corpus = raiz / "corpus"
            corpus.mkdir()
            (corpus / "guia.md").write_text(
                "# Crianza\nContenido útil.", encoding="utf-8"
            )
            vectorstore = raiz / "persistente"

            with patch.dict("os.environ", {"RAG_VECTORSTORE_DIR": str(vectorstore)}):
                with patch(
                    "src.knowledge_base.BaseConocimientoLocal._preparar_vectores",
                    return_value=(object(), object()),
                ) as preparar_vectores:
                    BaseConocimientoLocal.cargar(corpus)

            self.assertEqual(preparar_vectores.call_args.args[2], vectorstore.resolve())


class KnowledgeBaseRetrievalTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        raiz = Path(__file__).resolve().parents[1]
        cls.base = BaseConocimientoLocal.cargar(
            raiz / "docs" / "base_conocimiento", usar_vectores=False
        )

    def test_in_domain_benchmark_questions_retrieve_expected_sources(self):
        cases = [
            (
                "¿Cuáles son las tres reglas para las relaciones utilizadas "
                "en el grupo de cuidado según TBRI?",
                "03.",
                {12},
            ),
            (
                "¿Qué significan las siglas de la Respuesta IDEAL en los "
                "Principios de Corrección de TBRI?",
                "03.",
                {19},
            ),
            (
                "¿Cuáles son los cuatro Niveles de Respuesta de TBRI frente "
                "a un comportamiento desafiante?",
                "03.",
                {22, 23, 27},
            ),
            (
                "¿Qué funciones cumplen los sentidos según el documento de "
                "Principios de Empoderamiento de TBRI?",
                "04.",
                {8},
            ),
            (
                "¿Qué son los sentidos internos descritos en TBRI y en qué "
                "consisten?",
                "04.",
                {10},
            ),
            (
                "¿Por qué es tan importante la hidratación y el control de "
                "la glucemia cada dos horas en niños con antecedentes difíciles?",
                "04.",
                {16},
            ),
            (
                "¿Qué conductas presentan los bebés con un estilo de apego "
                "evitativo según Bowlby/TBRI?",
                "02.",
                {7, 9},
            ),
            (
                "¿Cuáles son las tres estrategias para relacionarse que se "
                "trabajan en los Principios de Conexión de TBRI?",
                "02.",
                {17},
            ),
            (
                "Según el artículo de Gómez Muzzio et al. (2008), ¿qué es "
                "la sensibilidad parental según Ainsworth?",
                "34.",
                {5},
            ),
            (
                "¿Qué tres modalidades de psicoterapia basadas en evidencia "
                "se revisan en el artículo de Gómez Muzzio (2008)?",
                "34.",
                {7},
            ),
            (
                "Según la revisión sistemática de Lin-Lewry et al. (2024), "
                "¿qué efectos tienen las intervenciones digitales en los "
                "padres durante el primer año postparto?",
                "39.",
                {1, 6, 7, 8},
            ),
            (
                "¿Qué moderadores o factores clave incrementaron la "
                "efectividad de las intervenciones digitales según "
                "Lin-Lewry et al. (2024)?",
                "39.",
                {1, 5, 6},
            ),
        ]

        for consulta, prefijo_fuente, paginas in cases:
            with self.subTest(consulta=consulta):
                fragmentos = self.base.buscar(consulta, limite=6)
                self.assertTrue(fragmentos)
                self.assertTrue(
                    any(
                        fragmento.fuente.startswith(prefijo_fuente)
                        and fragmento.page in paginas
                        for fragmento in fragmentos
                    ),
                    [
                        (fragmento.fuente, fragmento.page)
                        for fragmento in fragmentos
                    ],
                )

    def test_sleep_paraphrases_retrieve_bedtime_evidence_without_food_passages(self):
        consultas = [
            "¿Cómo puedo ayudar a un niño a conciliar el sueño?",
            "¿Qué hago si mi niño tiene dificultades para conciliar el sueño?",
            "¿Qué hábitos puedo implementar antes de acostarlo?",
            "¿Cómo puedo establecer una rutina nocturna para mi hijo?",
        ]
        terminos_de_comida = re.compile(
            r"\b(?:desayuno|glucemia|hidratacion|merienda|comida|waffles)\b",
            re.IGNORECASE,
        )

        for consulta in consultas:
            with self.subTest(consulta=consulta):
                fragmentos = self.base.buscar(consulta, limite=6)
                self.assertTrue(fragmentos)
                self.assertTrue(
                    any(
                        fragmento.page == 20
                        and "Empoderamiento" in fragmento.fuente
                        for fragmento in fragmentos
                    )
                )
                self.assertFalse(
                    any(terminos_de_comida.search(f.texto) for f in fragmentos)
                )

    def test_out_of_domain_benchmark_questions_return_no_evidence(self):
        consultas = [
            "¿Cuál es la velocidad recomendada para la órbita de los satélites "
            "de baja altura alrededor de Marte?",
            "¿Cuáles son las tasas actuales del impuesto a la renta para "
            "empresas en Colombia?",
            "¿En qué año se firmó el tratado de paz de la Primera Guerra "
            "Mundial en Versalles?",
        ]

        for consulta in consultas:
            with self.subTest(consulta=consulta):
                self.assertEqual(self.base.buscar(consulta), [])

    def test_undocumented_vaccine_questions_do_not_match_age_mentions(self):
        consultas = [
            "¿Qué vacuna necesita un niño de tres años?",
            "¿Qué vacuna necesita un niño de 3 años?",
            "¿Qué vacuna necesita un niño de cuatro años?",
            "¿Qué vacuna necesita un niño de 4 años?",
        ]

        for consulta in consultas:
            with self.subTest(consulta=consulta):
                self.assertEqual(self.base.buscar(consulta), [])


if __name__ == "__main__":
    unittest.main()
