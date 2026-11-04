import json
import unittest
from unittest.mock import patch

from main import app, chat_rag
from src.rag_chat import ChatRAG


class ChatAppTests(unittest.TestCase):
    def setUp(self):
        self.api_key_original = chat_rag.api_key
        chat_rag.api_key = ""
        self.client = app.test_client()

    def tearDown(self):
        chat_rag.api_key = self.api_key_original

    def post(self, mensaje, ruta="/chat"):
        return self.client.post(ruta, json={"message": mensaje}).get_json()

    def test_home_and_health_are_available(self):
        self.assertEqual(self.client.get("/").status_code, 200)
        health = self.client.get("/api/health").get_json()
        self.assertGreater(health["knowledge_chunks"], 0)
        self.assertFalse(health["llm_configured"])

    def test_rituals_question_returns_cited_local_evidence(self):
        data = self.post("¿Cuál es la diferencia entre rutinas y rituales a la hora de dormir?")
        self.assertEqual(data["mode"], "local")
        self.assertIn("rituales", data["answer"])
        self.assertRegex(data["answer"], r"\[Fuentes? [0-9, ]+\]")
        self.assertTrue(any(s["page"] == 20 for s in data["sources"]))

    def test_citations_match_returned_sources(self):
        data = self.post("¿Qué rutinas de transición ayudan a un niño que se aterra al salir de casa?")
        if data["mode"] == "local":
            nums = ChatRAG._numeros_citados(data["answer"])
            self.assertTrue(nums)
            self.assertLessEqual(max(nums), len(data["sources"]))

    def test_child_hitting_parent_is_not_an_abuse_disclosure(self):
        data = self.post("Mi hijo me golpeó cuando le daba la comida")
        self.assertNotEqual(data["mode"], "safety")
        self.assertNotIn("141", data["answer"])

    def test_aggressive_child_is_not_flagged_as_violence_report(self):
        self.assertNotEqual(self.post("Mi hijo es violento cuando se frustra")["mode"], "safety")

    def test_safety_signals_bypass_generation_and_show_no_sources(self):
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

    def test_losing_patience_is_a_parenting_question_not_a_crisis(self):
        data = self.post("Siento que pierdo la paciencia y estoy a punto de gritar")
        self.assertNotEqual(data["mode"], "safety")

    def test_unrelated_history_does_not_leak_into_safety_or_retrieval(self):
        data = self.client.post("/chat", json={
            "message": "¿Cuál es la capital de Francia?",
            "history": [{"role": "user", "content": "Mi hija me contó que un familiar la toca"}],
        }).get_json()
        self.assertEqual(data["mode"], "no_evidence")

    def test_elliptical_follow_up_is_resolved_with_previous_turn(self):
        primero = self.post("¿Cuáles son los Niveles de Respuesta frente a un comportamiento desafiante?")
        self.assertEqual(primero["mode"], "local")
        segundo = self.client.post("/chat", json={
            "message": "¿Y el segundo nivel en qué consiste?",
            "history": [
                {"role": "user", "content": "¿Cuáles son los Niveles de Respuesta frente a un comportamiento desafiante?"},
                {"role": "assistant", "content": primero["answer"]},
            ],
        }).get_json()
        self.assertNotEqual(segundo["mode"], "no_evidence")
        self.assertTrue(segundo["sources"])

    def test_out_of_scope_and_undocumented_topics_abstain(self):
        for texto in ("¿Cuál es la capital de Francia?", "¿Qué vacuna necesita un niño de tres años?",
                      "¿Y qué puedo hacer después para calmarlo?"):
            with self.subTest(texto=texto):
                data = self.post(texto)
                self.assertEqual(data["mode"], "no_evidence")
                self.assertEqual(data["sources"], [])
                self.assertIn("información suficiente", data["answer"].lower())

    def test_groq_json_is_rendered_and_sources_renumbered(self):
        chat_rag.api_key = "configured"
        contenido = json.dumps({
            "validacion": "Te entiendo.", "lectura_conducta": None,
            "estrategias": ["Ofrece agua y meriendas cada dos horas [Fuente 2]."],
            "limite_de_la_guia": None, "senal_alerta": None, "derivar_a_profesional": False,
        })
        with patch.object(chat_rag, "_llamar_groq", return_value=contenido):
            data = self.post("¿De qué manera influye la deshidratación en las crisis de un niño?")
        self.assertEqual(data["mode"], "groq")
        self.assertIn("[Fuente 1]", data["answer"])
        self.assertEqual(len(data["sources"]), 1)

    def test_invalid_groq_output_falls_back_to_local_evidence(self):
        chat_rag.api_key = "configured"
        with patch.object(chat_rag, "_llamar_groq", return_value="no es json"):
            data = self.post("¿Cuál es la diferencia entre rutinas y rituales a la hora de dormir?")
        self.assertEqual(data["mode"], "local")
        self.assertIn("No fue posible", data["notice"])

    def test_invalid_input_is_rejected(self):
        self.assertEqual(self.client.post("/api/chat", json={"message": "  "}).status_code, 400)
        r = self.client.post("/chat", json={"message": "x", "history": [{"role": "system"}]})
        self.assertEqual(r.status_code, 400)


if __name__ == "__main__":
    unittest.main()
