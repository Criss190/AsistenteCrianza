"""Evalúa la recuperación y generación del chat con las métricas de Ragas."""

from __future__ import annotations

import json
import math
import os
from pathlib import Path
from typing import Any

from datasets import Dataset
from langchain_openai import ChatOpenAI, OpenAIEmbeddings
import pandas as pd
from ragas import evaluate
from ragas.metrics import (
    answer_relevancy,
    context_precision,
    context_recall,
    faithfulness,
)
from ragas.run_config import RunConfig

from src.rag_chat import ChatRAG


ROOT = Path(__file__).resolve().parent
DATASET_PATH = Path(
    os.getenv("RAGAS_EVAL_DATASET", str(ROOT / "eval_dataset.json"))
)
RESULTS_PATH = ROOT / "ragas_results.json"
METRIC_NAMES = (
    "faithfulness",
    "answer_relevancy",
    "context_precision",
    "context_recall",
)


def _clasificar_dominio(fila: dict[str, str]) -> str:
    """Lee la etiqueta del dataset o reconoce referencias de abstención."""
    etiqueta = fila.get("domain")
    if etiqueta in {"in_domain", "out_of_domain"}:
        return etiqueta
    referencia = fila["ground_truth"].lower()
    frases_de_abstencion = (
        "no se encuentra en la base",
        "no dispongo de esa información",
        "no está disponible en la base",
    )
    return (
        "out_of_domain"
        if any(frase in referencia for frase in frases_de_abstencion)
        else "in_domain"
    )


def cargar_dataset(ruta: Path) -> list[dict[str, str]]:
    """Carga y valida preguntas con respuesta de referencia."""
    datos = json.loads(ruta.read_text(encoding="utf-8"))
    if not isinstance(datos, list) or len(datos) < 15:
        raise ValueError("El dataset debe contener al menos 15 preguntas.")
    for numero, fila in enumerate(datos, start=1):
        if not isinstance(fila, dict) or not all(
            isinstance(fila.get(campo), str) and fila[campo].strip()
            for campo in ("question", "ground_truth")
        ):
            raise ValueError(
                f"La fila {numero} debe incluir question y ground_truth."
            )
    dominios = {_clasificar_dominio(fila) for fila in datos}
    if not {"in_domain", "out_of_domain"} <= dominios:
        raise ValueError(
            "El dataset debe incluir preguntas del dominio y fuera de dominio."
        )
    return datos


def recolectar_evidencia(
    datos: list[dict[str, str]], chat: ChatRAG
) -> list[dict[str, Any]]:
    """Ejecuta el RAG y reúne las cuatro columnas requeridas por Ragas."""
    chat.api_key = ""
    evaluacion: list[dict[str, Any]] = []
    for fila in datos:
        resultado = chat.responder(fila["question"])
        evaluacion.append(
            {
                "question": fila["question"],
                "contexts": resultado["contexts"],
                "answer": resultado["answer"],
                "ground_truth": fila["ground_truth"],
            }
        )
    return evaluacion


def main() -> None:
    """Ejecuta Ragas, muestra el promedio de métricas y guarda resultados."""
    if not os.getenv("OPENAI_API_KEY", "").strip():
        raise RuntimeError(
            "Configura OPENAI_API_KEY en el entorno para ejecutar el juez Ragas."
        )

    datos = cargar_dataset(DATASET_PATH)
    registros = recolectar_evidencia(datos, ChatRAG())
    conjunto = Dataset.from_list(registros)
    juez = ChatOpenAI(
        model=os.getenv("RAGAS_LLM_MODEL", "gpt-4o-mini"),
        temperature=0,
    )
    embeddings = OpenAIEmbeddings(
        model=os.getenv("RAGAS_EMBEDDING_MODEL", "text-embedding-3-small")
    )
    resultado = evaluate(
        conjunto,
        metrics=[
            faithfulness,
            answer_relevancy,
            context_precision,
            context_recall,
        ],
        llm=juez,
        embeddings=embeddings,
        run_config=RunConfig(timeout=60, max_retries=0, max_workers=4),
        raise_exceptions=True,
    )

    if len(resultado.scores) != len(registros):
        raise RuntimeError(
            "Ragas no produjo una puntuación para cada pregunta; "
            "revisa las credenciales, cuota y compatibilidad del entorno."
        )
    tabla = pd.DataFrame(
        [
            {
                **registro,
                **puntuaciones,
                "domain": _clasificar_dominio(fila),
            }
            for fila, registro, puntuaciones in zip(
                datos, registros, resultado.scores
            )
        ]
    )
    for metrica in METRIC_NAMES:
        if metrica not in tabla:
            tabla[metrica] = float("nan")
    print(tabla[["question", "domain", *METRIC_NAMES]].to_string(index=False))
    resumen = tabla[list(METRIC_NAMES)].mean(numeric_only=True)
    print("\nPromedio de métricas Ragas:")
    print(resumen.to_frame("score").to_string())

    filas_salida = []
    for fila in tabla.to_dict(orient="records"):
        salida = {
            "question": fila["question"],
            "domain": fila["domain"],
        }
        for metrica in METRIC_NAMES:
            valor = fila.get(metrica)
            salida[metrica] = (
                float(valor)
                if valor is not None and math.isfinite(float(valor))
                else None
            )
        filas_salida.append(salida)
    RESULTS_PATH.write_text(
        json.dumps(
            {
                "metrics": {
                    metrica: (
                        float(resumen[metrica])
                        if math.isfinite(float(resumen[metrica]))
                        else None
                    )
                    for metrica in METRIC_NAMES
                },
                "results": filas_salida,
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    print(f"\nResultados guardados en {RESULTS_PATH}")


if __name__ == "__main__":
    main()
