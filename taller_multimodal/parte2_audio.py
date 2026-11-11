"""Parte 2 — Audio: transcripción desde archivo (2.1) y respuesta del modelo (2.2).

Flujo: archivo de audio → Whisper (voz a texto) → transcripción → LLM → respuesta.
Lee los audios de audios/ (audio_1.m4a, audio_2.wav, ...) y lo que se dijo de audios/guion.json.
"""
import json
import re

from groq import Groq
from langchain_core.messages import HumanMessage, SystemMessage

from comun import CARPETA_AUDIOS, MODELO_AUDIO, MODELO_TEXTO, cargar_llm_texto, guardar_resultado, texto_de

FORMATOS = {".wav", ".mp3", ".m4a", ".ogg", ".webm", ".flac", ".mp4"}
LIMITE_BYTES = 25 * 1024 * 1024  # 25 MB en el plan gratuito de Groq

ASISTENTE = (
    "Eres CrianzApp, un asistente de orientación sobre crianza positiva para madres, padres y "
    "cuidadores de niños de 0 a 12 años, basado en TBRI (Intervención Relacional Basada en la "
    "Confianza). Respondes en español, de forma breve, cálida y concreta, con pasos que se puedan "
    "aplicar hoy. No diagnosticas ni reemplazas a un profesional y nunca recomiendas castigos "
    "físicos ni humillación. La pregunta viene de una transcripción de voz: si un término técnico "
    "parece mal transcrito, interpreta el más probable y dilo."
)


def palabras(texto):
    return re.findall(r"\w+", texto.casefold())


def tasa_error_palabras(referencia, hipotesis):
    """WER: palabras sustituidas, omitidas o añadidas, sobre el total de palabras dichas."""
    ref, hip = palabras(referencia), palabras(hipotesis)
    fila = list(range(len(hip) + 1))
    for i, r in enumerate(ref, start=1):
        anterior, fila[0] = fila[0], i
        for j, h in enumerate(hip, start=1):
            anterior, fila[j] = fila[j], min(fila[j] + 1, fila[j - 1] + 1, anterior + (r != h))
    return fila[-1] / max(len(ref), 1)


def transcribir(cliente, ruta):
    """Envía el archivo a Whisper y devuelve (texto, duración en segundos)."""
    t = cliente.audio.transcriptions.create(
        file=(ruta.name, ruta.read_bytes()),
        model=MODELO_AUDIO,
        language="es",
        temperature=0,
        response_format="verbose_json",  # incluye la duración del audio
    )
    return t.text.strip(), getattr(t, "duration", None)


if __name__ == "__main__":
    guion = json.loads((CARPETA_AUDIOS / "guion.json").read_text(encoding="utf-8"))
    audios = sorted(a for a in CARPETA_AUDIOS.iterdir() if a.suffix.lower() in FORMATOS)
    if not audios:
        raise SystemExit(f"No hay audios en {CARPETA_AUDIOS}. Grábalos siguiendo audios/GUION.md.")

    llm = cargar_llm_texto()  # también comprueba que exista GROQ_API_KEY
    cliente = Groq()
    resultados = []

    for ruta in audios:
        info = guion.get(ruta.stem, {})
        print(f"\n=== {ruta.name} | {info.get('hablante', '?')} | {info.get('condicion', '?')} ===")
        if ruta.stat().st_size > LIMITE_BYTES:
            print("Omitido: supera los 25 MB que admite la API.")
            continue

        # 2.1 Transcripción desde archivo
        transcripcion, duracion = transcribir(cliente, ruta)
        dicho = info.get("texto", "")
        wer = tasa_error_palabras(dicho, transcripcion) if dicho else None
        print(f"Duración:      {f'{duracion:.1f} s' if duracion else '?'}")
        print(f"Lo que se dijo: {dicho or '(no está en guion.json)'}")
        print(f"Transcripción:  {transcripcion}")
        if wer is not None:
            print(f"Error de palabras (WER): {100 * wer:.1f} %")

        # 2.2 Respuesta a partir de la transcripción
        respuesta = texto_de(llm.invoke([SystemMessage(ASISTENTE), HumanMessage(transcripcion)]))
        print(f"\nRespuesta del modelo:\n{respuesta}")

        resultados.append({
            "audio": ruta.name, "hablante": info.get("hablante"), "condicion": info.get("condicion"),
            "duracion_s": round(duracion, 1) if duracion else None,
            "lo_que_se_dijo": dicho, "transcripcion": transcripcion,
            "wer_porcentaje": round(100 * wer, 1) if wer is not None else None,
            "respuesta": respuesta,
        })

    guardar_resultado("parte2", {"modelo_audio": MODELO_AUDIO, "modelo_texto": MODELO_TEXTO, "audios": resultados})
