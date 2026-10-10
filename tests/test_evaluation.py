import unittest

from eval_ragas import _clasificar_dominio, cargar_dataset, DATASET_PATH


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


if __name__ == "__main__":
    unittest.main()
