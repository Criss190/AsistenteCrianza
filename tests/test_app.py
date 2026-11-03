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
            json={
                "message": (
                    "¿Cuáles son las tres reglas para las relaciones "
                    "utilizadas en el grupo de cuidado según TBRI?"
                )
            },
        )

        data = response.get_json()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(data["mode"], "local")
        self.assertEqual(data["respuesta"], data["answer"])
        self.assertEqual(data["fuentes"], data["sources"])
        self.assertTrue(data["sources"])
        self.assertIn("tres reglas", data["answer"].lower())
        self.assertNotEqual(data["sources"][0]["name"], "guia_crianza.md")
        self.assertTrue(data["sources"][0]["chunk_id"])
        self.assertTrue(data["sources"][0]["excerpt"])

    def test_local_answer_joins_passage_and_cites_retrieved_page(self):
        response = self.client.post(
            "/chat",
            json={
                "message": (
                    "¿Cuál es la diferencia entre rutinas y rituales "
                    "a la hora de dormir?"
                )
            },
        )

        data = response.get_json()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(data["mode"], "local")
        self.assertIn("parte favorita del día.", data["answer"])
        self.assertIn("un ritual añade conexión", data["answer"])
        self.assertNotIn("ilustrar la diferencia", data["answer"])
        self.assertRegex(data["answer"], r"\[Fuentes? [0-9, ]+\]")
        self.assertTrue(data["sources"])
        self.assertTrue(
            all(
                source["name"].startswith("04.") and source["page"] == 20
                for source in data["sources"]
            )
        )

    def test_child_hitting_parent_is_not_mislabeled_as_abuse_disclosure(self):
        response = self.client.post(
            "/chat",
            json={"message": "Mi hijo me golpeó cuando le daba la comida"},
        )

        data = response.get_json()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(data["mode"], "local")
        self.assertIn("conducta desafiante", data["answer"])
        self.assertNotIn("141", data["answer"])
        self.assertTrue(
            any(source["page"] == 19 for source in data["sources"])
        )

    def test_everyday_parenting_concerns_receive_short_evidence_synthesis(self):
        cases = [
            (
                "Mi hijo ya no me escucha",
                "prestarle atención completa",
                17,
            ),
            (
                "Estoy frustrada porque mi hijo llora mucho",
                "no describen una técnica específica para el llanto",
                17,
            ),
            (
                "¿Cómo ayudo a los niños bajo mi cuidado a sentirse seguros?",
                "ambientes predecibles",
                7,
            ),
        ]

        for pregunta, frase_esperada, pagina in cases:
            with self.subTest(pregunta=pregunta):
                data = self.client.post(
                    "/chat", json={"message": pregunta}
                ).get_json()
                self.assertEqual(data["mode"], "local")
                self.assertIn(frase_esperada, data["answer"])
                self.assertNotIn(pregunta.lower(), data["answer"].lower())
                self.assertTrue(
                    any(source["page"] == pagina for source in data["sources"])
                )

    def test_explicit_child_abuse_disclosure_still_uses_safety_response(self):
        response = self.client.post(
            "/chat", json={"message": "Mi niño fue abusado, ¿qué puedo hacer?"}
        )

        data = response.get_json()
        self.assertEqual(data["mode"], "safety")
        self.assertIn("141", data["answer"])

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
        data = response.get_json()
        self.assertEqual(data["mode"], "no_evidence")
        self.assertEqual(data["fuentes"], [])
        self.assertIn("crianza responsable", data["answer"].lower())

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

    def test_undocumented_parenting_question_abstains_with_scope_message(self):
        response = self.client.post(
            "/chat",
            json={"message": "¿Qué vacuna necesita un niño de tres años?"},
        )

        data = response.get_json()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(data["mode"], "no_evidence")
        self.assertEqual(data["sources"], [])
        self.assertIn("crianza responsable", data["answer"].lower())
        self.assertIn("información suficiente", data["answer"].lower())

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
