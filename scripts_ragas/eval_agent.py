"""Evalúa el agente (Avance 3) con las mismas métricas de Ragas y el mismo
conjunto de evaluación de `eval_ragas.py` (Avance 2), para poder comparar
pipeline fijo vs. agente en una sola tabla. También registra costo (llamadas
al LLM, tokens y latencia) por pregunta, igual que exige la rúbrica.

Los `retrieved_contexts` del agente son los fragmentos que de verdad
devolvió `buscar_en_base` en cada pregunta (no una recuperación aparte).
"""

from __future__ import annotations

import json
import math
import os
from pathlib import Path
import sys
import time
from typing import Any

SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

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

from scripts_ragas.eval_ragas import DATASET_PATH, _clasificar_dominio, _entero_entorno, cargar_dataset
from src.agent import AgenteCrianza, MENSAJE_SIN_EVIDENCIA


def _es_abstencion(respuesta: str) -> bool:
    """La abstención correcta puede llegar como mode="no_evidence" (se
    agotaron las iteraciones) o como un JSON válido cuya única estrategia es
    la frase fija (el agente sí llamó tools, pero ninguna encontró nada)."""
    return MENSAJE_SIN_EVIDENCIA.rstrip(".") in respuesta

load_dotenv(PROJECT_ROOT / ".env")
RESULTS_PATH = Path(
    os.getenv("RAGAS_AGENT_RESULTS_PATH", str(SCRIPT_DIR / "results" / "ragas_agent.json"))
).resolve()
METRIC_NAMES = (
    "faithfulness",
    "answer_relevancy",
    "context_precision",
    "context_recall",
)


def recolectar_evidencia(
    datos: list[dict[str, str]], agente: AgenteCrianza
) -> list[dict[str, Any]]:
    """Ejecuta el agente y reúne las columnas de Ragas más el costo por turno."""
    if not agente.api_key:
        print("Aviso: GROQ_API_KEY no está configurada; el agente no puede responder.")
    espera = _entero_entorno("RAGAS_GROQ_DELAY_SEGUNDOS", 20, 0)
    evaluacion: list[dict[str, Any]] = []
    for indice, fila in enumerate(datos):
        if indice and agente.api_key and espera:
            time.sleep(espera)
        resultado = agente.responder(fila["question"])
        evaluacion.append(
            {
                "question": fila["question"],
                "contexts": resultado["contexts"],
                "answer": resultado["answer"],
                "ground_truth": fila["ground_truth"],
                "domain": _clasificar_dominio(fila),
                "mode": resultado["mode"],
                "tool_calls": resultado["tool_calls"],
                "llm_calls": resultado["llm_calls"],
                "tokens": resultado["tokens"],
                "latencia_ms": resultado["latencia_ms"],
            }
        )
    return evaluacion


def main() -> None:
    """Ejecuta Ragas sobre el agente y guarda resultados + costo por pregunta."""
    if not os.getenv("GOOGLE_API_KEY", "").strip():
        raise RuntimeError("Configura GOOGLE_API_KEY en el entorno para ejecutar el juez Ragas.")

    datos = cargar_dataset(DATASET_PATH)
    registros = recolectar_evidencia(datos, AgenteCrianza())
    registros_en_dominio = [r for r in registros if r["domain"] == "in_domain"]
    registros_fuera_dominio = [r for r in registros if r["domain"] == "out_of_domain"]

    conjunto = Dataset.from_list(
        [
            {campo: r[campo] for campo in ("question", "contexts", "answer", "ground_truth")}
            for r in registros_en_dominio
        ]
    )
    juez = ChatGoogleGenerativeAI(
        model=os.getenv("RAGAS_LLM_MODEL", "gemini-3.8-flash"),
        temperature=0,
        max_retries=6,
        timeout=120,
    )
    embeddings = LangchainEmbeddingsWrapper(
        GoogleGenerativeAIEmbeddings(
            model=os.getenv("RAGAS_EMBEDDING_MODEL", "models/gemini-embedding-001"),
            max_retries=6,
        )
    )
    juez_ragas = LangchainLLMWrapper(juez)
    puntajes_anteriores = [
        faithfulness.llm,
        answer_relevancy.llm,
        context_precision.llm,
        context_recall.llm,
    ]
    for metrica in (faithfulness, answer_relevancy, context_precision, context_recall):
        metrica.llm = juez_ragas
    try:
        resultado = evaluate(
            conjunto,
            metrics=[faithfulness, answer_relevancy, context_precision, context_recall],
            llm=juez_ragas,
            embeddings=embeddings,
            run_config=RunConfig(timeout=300, max_retries=6, max_workers=1),
            raise_exceptions=False,
        )
    finally:
        for metrica, llm_anterior in zip(
            (faithfulness, answer_relevancy, context_precision, context_recall),
            puntajes_anteriores,
        ):
            metrica.llm = llm_anterior

    if len(resultado.scores) != len(registros_en_dominio):
        raise RuntimeError(
            "Ragas no produjo una puntuación para cada pregunta; "
            "revisa las credenciales, cuota y compatibilidad del entorno."
        )
    puntuaciones_por_pregunta = {
        r["question"]: puntuaciones for r, puntuaciones in zip(registros_en_dominio, resultado.scores)
    }
    tabla = pd.DataFrame(
        [{**r, **puntuaciones_por_pregunta.get(r["question"], {})} for r in registros]
    )
    for metrica in METRIC_NAMES:
        if metrica not in tabla:
            tabla[metrica] = float("nan")
    print(tabla[["question", "domain", "llm_calls", "tokens", "latencia_ms", *METRIC_NAMES]].to_string(index=False))

    resumen = tabla[list(METRIC_NAMES)].mean(numeric_only=True)
    print("\nPromedio de métricas Ragas (agente):")
    print(resumen.to_frame("score").to_string())

    costo = tabla[["llm_calls", "tokens", "latencia_ms"]].mean(numeric_only=True)
    print("\nCosto promedio por pregunta (agente):")
    print(costo.to_frame("promedio").to_string())

    abstenciones_correctas = sum(_es_abstencion(r["answer"]) for r in registros_fuera_dominio)
    tasa_abstencion = (
        abstenciones_correctas / len(registros_fuera_dominio) if registros_fuera_dominio else float("nan")
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
            "answer": fila["answer"],
            "tool_calls": fila["tool_calls"],
            "llm_calls": fila["llm_calls"],
            "tokens": fila["tokens"],
            "latencia_ms": fila["latencia_ms"],
            "correct_abstention": (
                _es_abstencion(fila["answer"]) if fila["domain"] == "out_of_domain" else None
            ),
        }
        for metrica in METRIC_NAMES:
            valor = fila.get(metrica)
            salida[metrica] = float(valor) if valor is not None and math.isfinite(float(valor)) else None
        filas_salida.append(salida)

    RESULTS_PATH.parent.mkdir(parents=True, exist_ok=True)
    RESULTS_PATH.write_text(
        json.dumps(
            {
                "evaluation": {
                    "in_domain_count": len(registros_en_dominio),
                    "out_of_domain_count": len(registros_fuera_dominio),
                    "correct_abstentions": abstenciones_correctas,
                    "out_of_domain_abstention_rate": tasa_abstencion,
                },
                "metrics": {
                    metrica: (
                        float(resumen[metrica]) if math.isfinite(float(resumen[metrica])) else None
                    )
                    for metrica in METRIC_NAMES
                },
                "cost": {
                    "avg_llm_calls": float(costo["llm_calls"]),
                    "avg_tokens": float(costo["tokens"]),
                    "avg_latency_ms": float(costo["latencia_ms"]),
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
