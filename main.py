# -*- coding: utf-8 -*-
"""Aplicación web CrianzApp: chat RAG con conocimiento local y Groq opcional."""

from pathlib import Path

from dotenv import load_dotenv
from flask import Flask, Response, jsonify, render_template, request

from src.agent import AgenteCrianza


load_dotenv(Path(__file__).resolve().parent / ".env")

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 16 * 1024
# El chat desplegado usa el agente (Avance 3): el LLM decide qué tool llamar.
# El pipeline fijo de Avance 2 (`src/rag_chat.ChatRAG`) se conserva en el
# código y se instancia aparte solo para comparación en
# scripts_ragas/eval_ragas.py; cargarlo aquí también duplicaría el índice en
# memoria sin servir ninguna ruta.
agente = AgenteCrianza()


@app.get("/")
def inicio() -> str:
    """Sirve la interfaz web del asistente."""
    return render_template("index.html")


@app.get("/api/health")
def health() -> Response:
    """Estado mínimo para comprobaciones de disponibilidad de Render."""
    return jsonify(agente.estado())


@app.post("/chat")
@app.post("/api/chat")
def chat() -> Response | tuple[Response, int]:
    """Recibe mensaje e historial y devuelve respuesta y fuentes citadas."""
    datos = request.get_json(silent=True)
    if not isinstance(datos, dict):
        return jsonify(error="Envía los datos del chat como JSON."), 400

    mensaje = datos.get("message")
    if not isinstance(mensaje, str) or not mensaje.strip():
        return jsonify(error="Escribe una pregunta para continuar."), 400
    if len(mensaje) > 2000:
        return jsonify(error="El mensaje debe tener 2.000 caracteres o menos."), 400

    historial = datos.get("history", [])
    if (
        not isinstance(historial, list)
        or len(historial) > 12
        or any(
            not isinstance(turno, dict)
            or turno.get("role") not in {"user", "assistant"}
            or not isinstance(turno.get("content"), str)
            or len(turno.get("content", "")) > 4000
            for turno in historial
        )
    ):
        return jsonify(error="El historial debe contener turnos válidos."), 400

    try:
        resultado = agente.responder(mensaje.strip(), historial=historial)
    except Exception:
        app.logger.exception("Error procesando la consulta del agente")
        return jsonify(
            error="Ocurrió un problema al procesar tu consulta. Inténtalo de nuevo."
        ), 500

    return jsonify(
        respuesta=resultado["respuesta"],
        fuentes=resultado["fuentes"],
        answer=resultado["answer"],
        sources=resultado["sources"],
        mode=resultado["mode"],
        notice=resultado["notice"],
        tool_calls=resultado["tool_calls"],
        llm_calls=resultado["llm_calls"],
    )


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=False)
