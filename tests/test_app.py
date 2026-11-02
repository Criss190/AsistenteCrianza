import unittest

from main import app, chat_rag


class ChatAppTests(unittest.TestCase):
    def setUp(self):
        self.api_key_original = chat_rag.api_key
        chat_rag.api_key = ""
        self.client = app.test_client()

    def tearDown(self):
        chat_rag.api_key = self.api_key_original

    def test_home_and_health_are_available(self):
        home = self.client.get("/")
        health = self.client.get("/api/health").get_json()

        self.assertEqual(home.status_code, 200)
        self.assertIn(b"CrianzApp", home.data)
        self.assertGreater(health["knowledge_chunks"], 0)
        self.assertFalse(health["llm_configured"])

    def test_rag_returns_local_evidence_and_sources(self):
        response = self.client.post(
            "/chat",
            json={"message": "Mi hijo hace rabietas cuando apago la television"},
        )

        data = response.get_json()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(data["mode"], "local")
        self.assertEqual(data["respuesta"], data["answer"])
        self.assertEqual(data["fuentes"], data["sources"])
        self.assertTrue(data["sources"])
        self.assertIn("rabietas", data["answer"].lower())
        self.assertTrue(data["sources"][0]["chunk_id"])
        self.assertTrue(data["sources"][0]["excerpt"])

    def test_chat_ignores_history_and_answers_the_current_turn_only(self):
        response = self.client.post(
            "/chat",
            json={
                "message": "¿Cuál es la capital de Francia?",
                "history": [
                    {
                        "role": "user",
                        "content": "Mi hija me contó que un familiar la toca",
                    },
                    {
                        "role": "assistant",
                        "content": "Busca ayuda de protección infantil.",
                    },
                ],
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()["mode"], "no_evidence")
        self.assertEqual(response.get_json()["fuentes"], [])

    def test_follow_up_without_topic_context_abstains_instead_of_guessing(self):
        response = self.client.post(
            "/chat",
            json={
                "message": "¿Y qué puedo hacer después para calmarlo?",
            },
        )

        data = response.get_json()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(data["mode"], "no_evidence")
        self.assertEqual(data["fuentes"], [])

    def test_unknown_topic_abstains(self):
        response = self.client.post(
            "/api/chat", json={"message": "¿Cuál es la capital de Francia?"}
        )

        self.assertEqual(response.get_json()["mode"], "no_evidence")

    def test_new_out_of_domain_topic_does_not_reuse_previous_domain_history(self):
        response = self.client.post(
            "/chat",
            json={
                "message": "¿Cuál es la velocidad orbital de satélites alrededor de Marte?",
                "history": [
                    {
                        "role": "user",
                        "content": "Mi hijo hace rabietas cuando apago la televisión",
                    },
                    {
                        "role": "assistant",
                        "content": "Anticipa el límite y valida su emoción.",
                    },
                ],
            },
        )

        data = response.get_json()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(data["mode"], "no_evidence")
        self.assertEqual(data["fuentes"], [])

    def test_safety_signal_bypasses_generation(self):
        response = self.client.post(
            "/api/chat",
            json={"message": "Mi hija me contó que un familiar la toca"},
        )

        data = response.get_json()
        self.assertEqual(data["mode"], "safety")
        self.assertIn("141", data["answer"])

    def test_invalid_groq_output_falls_back_to_local_evidence(self):
        from unittest.mock import patch
        from src.knowledge_base import FragmentoConocimiento

        chat_rag.api_key = "configured"
        fragmento = FragmentoConocimiento(
            fuente="guia_test.md",
            texto="Anticipa el límite y valida la emoción con calma.",
            chunk_id="test-1",
        )
        with (
            patch.object(
                chat_rag.base_conocimiento,
                "buscar",
                return_value=[fragmento],
            ),
            patch.object(
                chat_rag,
                "_generar_con_groq",
                side_effect=ValueError("JSON inválido"),
            ),
        ):
            response = self.client.post(
                "/chat",
                json={"message": "Mi hijo hace rabietas cuando apago la televisión"},
            )

        data = response.get_json()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(data["mode"], "local")
        self.assertTrue(data["sources"])
        self.assertIn("No fue posible generar", data["notice"])

    def test_invalid_message_is_rejected(self):
        response = self.client.post("/api/chat", json={"message": "   "})

        self.assertEqual(response.status_code, 400)
        self.assertIn("error", response.get_json())

    def test_invalid_history_is_rejected(self):
        response = self.client.post(
            "/chat",
            json={"message": "¿Qué hago?", "history": [{"role": "system"}]},
        )

        self.assertEqual(response.status_code, 400)


if __name__ == "__main__":
    unittest.main()
