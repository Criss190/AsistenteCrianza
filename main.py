# -*- coding: utf-8 -*-
"""Aplicación web CrianzApp: chat RAG con conocimiento local y Groq opcional."""

from flask import Flask, jsonify, render_template, request

from src.rag_chat import ChatRAG


app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 16 * 1024
chat_rag = ChatRAG()


@app.get("/")
def inicio():
    """Sirve la interfaz web del asistente."""
    return render_template("index.html")


@app.get("/api/health")
def health():
    """Estado mínimo para comprobaciones de disponibilidad de Render."""
    return jsonify(chat_rag.estado())


@app.post("/api/chat")
def chat():
    """Recibe un mensaje, recupera evidencia y devuelve respuesta y fuentes."""
    datos = request.get_json(silent=True)
    if not isinstance(datos, dict):
        return jsonify(error="Envía los datos del chat como JSON."), 400

    mensaje = datos.get("message")
    if not isinstance(mensaje, str) or not mensaje.strip():
        return jsonify(error="Escribe una pregunta para continuar."), 400
    if len(mensaje) > 2000:
        return jsonify(error="El mensaje debe tener 2.000 caracteres o menos."), 400

    historial = datos.get("history", [])
    if not isinstance(historial, list):
        historial = []

    try:
        resultado = chat_rag.responder(mensaje.strip(), historial=historial)
    except Exception:
        app.logger.exception("Error procesando la consulta RAG")
        return jsonify(
            error="Ocurrió un problema al procesar tu consulta. Inténtalo de nuevo."
        ), 500

    return jsonify(resultado)


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=False)
