"""Prueba cada tool del agente directamente, sin pasar por el LLM."""

import unittest
from unittest.mock import patch

from src.knowledge_base import BaseConocimientoLocal
from src.rag_chat import BASE_CONOCIMIENTO_DIR
from src.tools import (
    DOMINIOS_PERMITIDOS_WEB,
    MAX_CARACTERES_FRAGMENTO,
    MAX_FRAGMENTOS_TOOL,
    buscar_en_base,
    buscar_en_web,
    generar_referencia_apa,
)


class BuscarEnBaseTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.base = BaseConocimientoLocal.cargar(
            BASE_CONOCIMIENTO_DIR, chunk_size=900, chunk_overlap=120
        )

    def test_invoke_directo_devuelve_documento_y_pagina_o_seccion(self):
        resultado = buscar_en_base(
            "Niveles de Respuesta frente a un comportamiento desafiante", self.base
        )
        self.assertGreater(len(resultado), 0)
        for fragmento in resultado:
            self.assertIn("documento", fragmento)
            self.assertTrue(fragmento["pagina"] or fragmento["seccion"])

    def test_limite_de_fragmentos_esta_en_codigo(self):
        resultado = buscar_en_base(
            "crianza apego TBRI corrección conexión empoderamiento", self.base
        )
        self.assertLessEqual(len(resultado), MAX_FRAGMENTOS_TOOL)

    def test_limite_de_longitud_por_fragmento_esta_en_codigo(self):
        resultado = buscar_en_base(
            "Niveles de Respuesta frente a un comportamiento desafiante", self.base
        )
        for fragmento in resultado:
            self.assertLessEqual(len(fragmento["texto"]), MAX_CARACTERES_FRAGMENTO)

    def test_pregunta_fuera_de_dominio_devuelve_lista_vacia(self):
        resultado = buscar_en_base("¿Cuál es la capital de Francia?", self.base)
        self.assertEqual(resultado, [])


class GenerarReferenciaApaTests(unittest.TestCase):
    def test_reconoce_documento_por_tema(self):
        resultado = generar_referencia_apa("el de empoderamiento")
        self.assertEqual(resultado["documento"], "empoderamiento")
        self.assertIn("2013", resultado["referencia_apa"])
        self.assertIn("Empoderamiento", resultado["referencia_apa"])

    def test_reconoce_articulo_academico_real(self):
        resultado = generar_referencia_apa("artículo de Gómez Muzzio")
        self.assertIn("Terapia Psicológica", resultado["referencia_apa"])
        self.assertIn("2008", resultado["referencia_apa"])

    def test_documento_no_reconocido_no_inventa_cita(self):
        resultado = generar_referencia_apa("un documento que no existe")
        self.assertIn("error", resultado)
        self.assertNotIn("referencia_apa", resultado)


class BuscarEnWebTests(unittest.TestCase):
    def test_rechaza_si_no_se_uso_la_base_primero(self):
        resultado = buscar_en_web("normas vigentes de protección infantil", se_uso_base=False)
        self.assertEqual(len(resultado), 1)
        self.assertIn("error", resultado[0])

    def test_dominios_permitidos_son_fijos_en_codigo(self):
        self.assertIn("icbf.gov.co", DOMINIOS_PERMITIDOS_WEB)
        self.assertIn("who.int", DOMINIOS_PERMITIDOS_WEB)

    def test_usa_tavily_con_dominios_permitidos_y_marca_origen_web(self):
        resultados_falsos = {
            "results": [
                {"title": "T1", "url": "https://icbf.gov.co/x", "content": "c" * 500},
                {"title": "T2", "url": "https://who.int/y", "content": "c2"},
            ]
        }
        with patch.dict("os.environ", {"TAVILY_API_KEY": "clave-de-prueba"}), patch(
            "src.tools.TavilyClient"
        ) as ClienteFalso:
            ClienteFalso.return_value.search.return_value = resultados_falsos
            resultado = buscar_en_web("tema público", se_uso_base=True)

        self.assertEqual(len(resultado), 2)
        for item in resultado:
            self.assertEqual(item["origen"], "web")
            self.assertLessEqual(len(item["extracto"]), 300)
        llamada = ClienteFalso.return_value.search.call_args.kwargs
        self.assertEqual(llamada["include_domains"], DOMINIOS_PERMITIDOS_WEB)
        self.assertLessEqual(llamada["max_results"], 3)


if __name__ == "__main__":
    unittest.main()
