"""Evalúa la recuperación y generación del chat con las métricas de Ragas."""

from __future__ import annotations

import json
import math
import os
from pathlib import Path
from typing import Any

from datasets import Dataset
from dotenv import load_dotenv
from langchain_google_genai import (
    ChatGoogleGenerativeAI,
    GoogleGenerativeAIEmbeddings,
)
import pandas as pd
from ragas import evaluate
from ragas.metrics import (
    answer_relevancy,
    context_precision,
    context_recall,
    faithfulness,
)
from ragas.embeddings.base import LangchainEmbeddingsWrapper
from ragas.llms.base import LangchainLLMWrapper
from ragas.run_config import RunConfig

from src.rag_chat import ChatRAG


ROOT = Path(__file__).resolve().parent
load_dotenv(ROOT / ".env")
DATASET_PATH = Path(
    os.getenv("RAGAS_EVAL_DATASET", str(ROOT / "eval_dataset.json"))
)
RESULTS_PATH = Path(
    os.getenv("RAGAS_RESULTS_PATH", str(ROOT / "ragas_results.json"))
).resolve()
METRIC_NAMES = (
    "faithfulness",
    "answer_relevancy",
    "context_precision",
    "context_recall",
)


def _entero_entorno(nombre: str, predeterminado: int, minimo: int) -> int:
    """Carga un parámetro entero opcional y valida el rango."""
    valor = os.getenv(nombre)
    if valor is None:
        return predeterminado
    try:
        entero = int(valor)
    except ValueError as error:
        raise ValueError(f"{nombre} debe ser un número entero.") from error
    if entero < minimo:
        raise ValueError(f"{nombre} debe ser mayor o igual que {minimo}.")
    return entero


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
                "domain": _clasificar_dominio(fila),
                "mode": resultado["mode"],
            }
        )
    return evaluacion


def main() -> None:
    """Ejecuta Ragas, muestra el promedio de métricas y guarda resultados."""
    if not os.getenv("GOOGLE_API_KEY", "").strip():
        raise RuntimeError(
            "Configura GOOGLE_API_KEY en el entorno para ejecutar el juez Ragas."
        )

    datos = cargar_dataset(DATASET_PATH)
    chunk_size = _entero_entorno("RAG_CHUNK_SIZE", 500, 1)
    chunk_overlap = _entero_entorno("RAG_CHUNK_OVERLAP", 50, 0)
    top_k = _entero_entorno("RAG_TOP_K", 3, 1)
    if chunk_overlap >= chunk_size:
        raise ValueError("RAG_CHUNK_OVERLAP debe ser menor que RAG_CHUNK_SIZE.")
    registros = recolectar_evidencia(
        datos,
        ChatRAG(
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap,
            top_k=top_k,
        ),
    )
    registros_en_dominio = [
        registro for registro in registros if registro["domain"] == "in_domain"
    ]
    registros_fuera_dominio = [
        registro for registro in registros if registro["domain"] == "out_of_domain"
    ]
    conjunto = Dataset.from_list(
        [
            {
                campo: registro[campo]
                for campo in ("question", "contexts", "answer", "ground_truth")
            }
            for registro in registros_en_dominio
        ]
    )
    juez = ChatGoogleGenerativeAI(
        model=os.getenv("RAGAS_LLM_MODEL", "gemini-3.8-flash"),
        temperature=0,
        max_retries=0,
        timeout=60,
    )
    embeddings = LangchainEmbeddingsWrapper(
        GoogleGenerativeAIEmbeddings(
            model=os.getenv(
                "RAGAS_EMBEDDING_MODEL", "models/gemini-embedding-001"
            )
        )
    )
    juez_ragas = LangchainLLMWrapper(juez)
    puntajes_anteriores = [
        faithfulness.llm,
        answer_relevancy.llm,
        context_precision.llm,
        context_recall.llm,
    ]
    for metrica in (
        faithfulness,
        answer_relevancy,
        context_precision,
        context_recall,
    ):
        metrica.llm = juez_ragas
    try:
        resultado = evaluate(
            conjunto,
            metrics=[
                faithfulness,
                answer_relevancy,
                context_precision,
                context_recall,
            ],
            llm=juez_ragas,
            embeddings=embeddings,
            run_config=RunConfig(timeout=90, max_retries=0, max_workers=1),
            raise_exceptions=True,
        )
    finally:
        for metrica, llm_anterior in zip(
            (
                faithfulness,
                answer_relevancy,
                context_precision,
                context_recall,
            ),
            puntajes_anteriores,
        ):
            metrica.llm = llm_anterior

    if len(resultado.scores) != len(registros_en_dominio):
        raise RuntimeError(
            "Ragas no produjo una puntuación para cada pregunta; "
            "revisa las credenciales, cuota y compatibilidad del entorno."
        )
    puntuaciones_por_pregunta = {
        registro["question"]: puntuaciones
        for registro, puntuaciones in zip(registros_en_dominio, resultado.scores)
    }
    tabla = pd.DataFrame(
        [
            {
                **registro,
                **puntuaciones_por_pregunta.get(registro["question"], {}),
            }
            for registro in registros
        ]
    )
    for metrica in METRIC_NAMES:
        if metrica not in tabla:
            tabla[metrica] = float("nan")
    print(tabla[["question", "domain", *METRIC_NAMES]].to_string(index=False))
    resumen = tabla[list(METRIC_NAMES)].mean(numeric_only=True)
    print("\nPromedio de métricas Ragas:")
    print(resumen.to_frame("score").to_string())
    abstenciones_correctas = sum(
        registro["mode"] == "no_evidence" for registro in registros_fuera_dominio
    )
    tasa_abstencion = (
        abstenciones_correctas / len(registros_fuera_dominio)
        if registros_fuera_dominio
        else float("nan")
    )
    print(
        "\nControl fuera de dominio: "
        f"{abstenciones_correctas}/{len(registros_fuera_dominio)} "
        f"abstenciones correctas ({tasa_abstencion:.1%})"
    )

    filas_salida = []
    for fila in tabla.to_dict(orient="records"):
        salida = {
            "question": fila["question"],
            "domain": fila["domain"],
            "mode": fila["mode"],
            "correct_abstention": (
                fila["mode"] == "no_evidence"
                if fila["domain"] == "out_of_domain"
                else None
            ),
        }
        for metrica in METRIC_NAMES:
            valor = fila.get(metrica)
            salida[metrica] = (
                float(valor)
                if valor is not None and math.isfinite(float(valor))
                else None
            )
        filas_salida.append(salida)
    RESULTS_PATH.parent.mkdir(parents=True, exist_ok=True)
    RESULTS_PATH.write_text(
        json.dumps(
            {
                "pipeline": {
                    "chunk_size": chunk_size,
                    "chunk_overlap": chunk_overlap,
                    "top_k": top_k,
                    "embedding_model": (
                        "sentence-transformers/all-MiniLM-L6-v2"
                    ),
                },
                "evaluation": {
                    "in_domain_count": len(registros_en_dominio),
                    "out_of_domain_count": len(registros_fuera_dominio),
                    "correct_abstentions": abstenciones_correctas,
                    "out_of_domain_abstention_rate": tasa_abstencion,
                },
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
