import os
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from eval_ragas import (
    _clasificar_dominio,
    _entero_entorno,
    cargar_dataset,
    DATASET_PATH,
    main as ejecutar_evaluacion,
)


class EvaluationDatasetTests(unittest.TestCase):
    def test_dataset_has_at_least_fifteen_mixed_domain_cases(self):
        dataset = cargar_dataset(DATASET_PATH)

        self.assertGreaterEqual(len(dataset), 15)
        dominios = {_clasificar_dominio(fila) for fila in dataset}
        self.assertEqual(dominios, {"in_domain", "out_of_domain"})

    def test_explicit_domain_labels_take_precedence(self):
        fila = {
            "domain": "out_of_domain",
            "ground_truth": "Esta información está en la guía.",
        }

        self.assertEqual(_clasificar_dominio(fila), "out_of_domain")

    def test_integer_pipeline_parameters_validate_ranges(self):
        self.assertEqual(_entero_entorno("NO_EXISTE", 500, 1), 500)
        with patch.dict(os.environ, {"INVALIDO": "no-es-entero"}):
            with self.assertRaises(ValueError):
                _entero_entorno("INVALIDO", 500, 1)

    def test_out_of_domain_ground_truth_is_not_sent_to_ragas_metrics(self):
        from unittest.mock import MagicMock
        from unittest.mock import patch as mock_patch

        import eval_ragas

        datos = [
            {
                "question": "Pregunta de crianza",
                "ground_truth": "Respuesta disponible en el corpus.",
                "domain": "in_domain",
            },
            {
                "question": "Pregunta fuera de dominio",
                "ground_truth": "La información no está en la base.",
                "domain": "out_of_domain",
            },
        ]
        fake_chat = MagicMock()
        fake_chat.responder.side_effect = [
            {
                "contexts": ["Evidencia textual del corpus."],
                "answer": "Respuesta sustentada en el corpus.",
                "mode": "local",
            },
            {
                "contexts": [],
                "answer": "No dispongo de esa información en la base de conocimientos.",
                "mode": "no_evidence",
            },
        ]
        fake_result = MagicMock()
        fake_result.scores = [
            {
                "faithfulness": 0.8,
                "answer_relevancy": 0.8,
                "context_precision": 0.8,
                "context_recall": 0.8,
            }
        ]
        fake_dataset = mock_patch(
            "eval_ragas.Dataset.from_list", return_value=object()
        )
        mock_environment = {"GOOGLE_API_KEY": "configured"}
        with tempfile.TemporaryDirectory() as temporary:
            result_path = Path(temporary) / "ragas-results.json"
            with (
                mock_patch.dict(os.environ, mock_environment),
                mock_patch("eval_ragas.RESULTS_PATH", result_path),
                mock_patch("eval_ragas.cargar_dataset", return_value=datos),
                mock_patch("eval_ragas.ChatRAG", return_value=fake_chat),
                fake_dataset as from_list,
                mock_patch("eval_ragas.ChatGoogleGenerativeAI"),
                mock_patch("eval_ragas.GoogleGenerativeAIEmbeddings"),
                mock_patch("eval_ragas.LangchainEmbeddingsWrapper"),
                mock_patch("eval_ragas.LangchainLLMWrapper"),
                mock_patch("eval_ragas.evaluate", return_value=fake_result),
            ):
                ejecutar_evaluacion()

            registros_ragas = from_list.call_args.args[0]
            self.assertEqual(len(registros_ragas), 1)
            self.assertEqual(registros_ragas[0]["question"], "Pregunta de crianza")
            resultado_guardado = json.loads(
                result_path.read_text(encoding="utf-8")
            )
            self.assertEqual(
                resultado_guardado["evaluation"]["out_of_domain_count"], 1
            )


if __name__ == "__main__":
    unittest.main()
