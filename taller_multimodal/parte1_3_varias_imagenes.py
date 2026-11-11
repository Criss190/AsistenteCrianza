"""Parte 1.3 — Varias imágenes relacionadas en una misma solicitud."""
from langchain_core.messages import HumanMessage

from comun import CARPETA_IMAGENES, MODELO_VISION, bloque_imagen, cargar_llm_vision, guardar_resultado, texto_de

IMAGENES = [CARPETA_IMAGENES / n for n in ("respuesta_ideal.png", "ficha_nivel_1.png", "ficha_nivel_4.png")]
PREGUNTA = (
    "Estas tres imágenes son material de crianza basado en TBRI: una resume la Respuesta IDEAL "
    "y las otras dos son fichas de Niveles de Respuesta. Compara las dos fichas (tono, volumen, "
    "cadencia, tiempo de resolución y conducta típica) y explica con cuál de las letras de la "
    "Respuesta IDEAL se relaciona el hecho de elegir un nivel u otro. "
    "Termina con un resumen conjunto de tres frases para un cuidador. "
    "Responde en menos de 250 palabras."
)

if __name__ == "__main__":
    llm = cargar_llm_vision()
    respuesta = llm.invoke([HumanMessage(content=[
        {"type": "text", "text": PREGUNTA},
        *[bloque_imagen(ruta) for ruta in IMAGENES],
    ])])

    print(f"Modelo:   {MODELO_VISION}")
    print(f"Imágenes: {', '.join(r.name for r in IMAGENES)}")
    print(f"Pregunta: {PREGUNTA}\n")
    print(f"Respuesta:\n{texto_de(respuesta)}")

    guardar_resultado("parte1_3", {
        "modelo": MODELO_VISION, "imagenes": [r.name for r in IMAGENES],
        "pregunta": PREGUNTA, "respuesta": texto_de(respuesta),
    })
