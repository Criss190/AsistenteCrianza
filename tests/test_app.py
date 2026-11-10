"""Integración Flask + agente. La lógica profunda del agente (qué tool llama,
cuántas llamadas al LLM, los 7 casos de comportamiento) ya está cubierta en
tests/test_agent.py y tests/test_tools.py; aquí solo se verifica que la app
esté bien conectada: validación de entrada, salud, y que la respuesta HTTP
tenga la forma esperada (fuentes, tool_calls, llm_calls).
"""

import json
import types
import unittest
from unittest.mock import patch

from main import agente, app


def _completion(contenido=None, tool_calls=None):
    llamadas = None
    if tool_calls:
        llamadas = [
            types.SimpleNamespace(
                id=tc["id"],
                function=types.SimpleNamespace(
                    name=tc["name"], arguments=json.dumps(tc["arguments"], ensure_ascii=False)
                ),
            )
            for tc in tool_calls
        ]
    mensaje = types.SimpleNamespace(content=contenido, tool_calls=llamadas)
    return types.SimpleNamespace(
        choices=[types.SimpleNamespace(message=mensaje)],
        usage=types.SimpleNamespace(total_tokens=100),
    )


class ChatAppTests(unittest.TestCase):
    def setUp(self):
        self.client = app.test_client()

    def post(self, mensaje, ruta="/chat", historial=None):
        payload = {"message": mensaje}
        if historial is not None:
            payload["history"] = historial
        return self.client.post(ruta, json=payload).get_json()

    def test_home_and_health_are_available(self):
        self.assertEqual(self.client.get("/").status_code, 200)
        health = self.client.get("/api/health").get_json()
        self.assertGreater(health["knowledge_chunks"], 0)
        self.assertIn("llm_configured", health)

    def test_invalid_input_is_rejected(self):
        self.assertEqual(self.client.post("/api/chat", json={"message": "  "}).status_code, 400)
        r = self.client.post("/chat", json={"message": "x", "history": [{"role": "system"}]})
        self.assertEqual(r.status_code, 400)

    def test_safety_signals_bypass_the_agent_and_show_no_sources(self):
        for texto, esperado in (
            ("Mi hija me contó que un familiar la toca", "141"),
            ("Mi niño fue abusado, ¿qué puedo hacer?", "141"),
            ("Mi hijo dice que quiere morir", "106"),
            ("Siento que voy a hacerle daño a mi hijo", "106"),
        ):
            with self.subTest(texto=texto):
                data = self.post(texto, "/api/chat")
                self.assertEqual(data["mode"], "safety")
                self.assertIn(esperado, data["answer"])
                self.assertEqual(data["sources"], [])
                self.assertEqual(data["tool_calls"], [])

    def test_child_hitting_parent_is_not_an_abuse_disclosure(self):
        with patch.object(agente, "_llamar_groq", return_value=_completion("Respuesta cualquiera.")):
            data = self.post("Mi hijo me golpeó cuando le daba la comida")
        self.assertNotEqual(data["mode"], "safety")

    def test_agent_response_includes_tool_calls_and_sources(self):
        secuencia = [
            _completion(
                tool_calls=[
                    {"id": "a", "name": "buscar_en_base", "arguments": {"consulta": "rituales"}}
                ]
            ),
            _completion(
                json.dumps(
                    {
                        "validacion": "Entiendo.",
                        "lectura_conducta": None,
                        "estrategias": ["Mantén una rutina (Fuente: Doc A, p.3)."],
                        "limite_de_la_guia": None,
                        "senal_alerta": None,
                        "derivar_a_profesional": False,
                    },
                    ensure_ascii=False,
                )
            ),
        ]
        fragmentos = [{"documento": "Doc A", "pagina": 3, "seccion": None, "texto": "x"}]
        with patch.object(agente, "_llamar_groq", side_effect=secuencia), patch(
            "src.agent.buscar_en_base", return_value=fragmentos
        ):
            data = self.post("¿Qué son los rituales a la hora de dormir?")
        self.assertEqual(data["mode"], "agent")
        self.assertEqual(data["llm_calls"], 2)
        self.assertEqual([t["tool"] for t in data["tool_calls"]], ["buscar_en_base"])
        self.assertTrue(data["sources"])
        self.assertEqual(data["sources"][0]["origen"], "base")


if __name__ == "__main__":
    unittest.main()
