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
            "/api/chat",
            json={"message": "Mi hijo hace rabietas cuando apago la television"},
        )

        data = response.get_json()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(data["mode"], "local")
        self.assertTrue(data["sources"])
        self.assertIn("rabietas", data["answer"].lower())

    def test_unknown_topic_abstains(self):
        response = self.client.post(
            "/api/chat", json={"message": "¿Cuál es la capital de Francia?"}
        )

        self.assertEqual(response.get_json()["mode"], "no_evidence")

    def test_safety_signal_bypasses_generation(self):
        response = self.client.post(
            "/api/chat",
            json={"message": "Mi hija me contó que un familiar la toca"},
        )

        data = response.get_json()
        self.assertEqual(data["mode"], "safety")
        self.assertIn("141", data["answer"])

    def test_invalid_message_is_rejected(self):
        response = self.client.post("/api/chat", json={"message": "   "})

        self.assertEqual(response.status_code, 400)
        self.assertIn("error", response.get_json())


if __name__ == "__main__":
    unittest.main()
