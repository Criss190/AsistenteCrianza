"""Parte 1.4 — Errores provocados a propósito, mostrando el mensaje de la API.

Caso A: 4 imágenes en una solicitud (el modelo de visión admite 3 como máximo).
Caso B: una imagen enviada a un modelo sin visión.
"""
from langchain_core.messages import HumanMessage

from comun import (CARPETA_IMAGENES, MODELO_TEXTO, MODELO_VISION, bloque_imagen,
                   cargar_llm_texto, cargar_llm_vision, guardar_resultado, texto_de)

CUATRO_IMAGENES = ["ficha_nivel_1.png", "ficha_nivel_2.png", "ficha_nivel_3.png", "ficha_nivel_4.png"]


def provocar(titulo, llm, modelo, imagenes, pregunta):
    """Hace la solicitud y devuelve el error de la API en lugar de dejar que el programa falle."""
    print(f"\n=== {titulo} ===")
    print(f"Modelo: {modelo} | Imágenes enviadas: {len(imagenes)}")
    mensaje = HumanMessage(content=[
        {"type": "text", "text": pregunta},
        *[bloque_imagen(CARPETA_IMAGENES / nombre) for nombre in imagenes],
    ])
    try:
        respuesta = llm.invoke([mensaje])
    except Exception as e:  # se captura cualquier error de la API para poder mostrarlo
        print(f"Tipo de error: {type(e).__name__}")
        print(f"Mensaje de la API:\n{e}")
        return {"caso": titulo, "modelo": modelo, "imagenes": imagenes,
                "hubo_error": True, "tipo": type(e).__name__, "mensaje": str(e)}
    print(f"La API NO devolvió error. Respuesta:\n{texto_de(respuesta)}")
    return {"caso": titulo, "modelo": modelo, "imagenes": imagenes,
            "hubo_error": False, "respuesta": texto_de(respuesta)}


if __name__ == "__main__":
    casos = [
        provocar("Caso A: más imágenes de las permitidas", cargar_llm_vision(), MODELO_VISION,
                 CUATRO_IMAGENES, "Resume lo que muestran estas imágenes."),
        provocar("Caso B: modelo sin visión", cargar_llm_texto(), MODELO_TEXTO,
                 ["semaforo_hidratacion.png"], "¿Qué indica cada color de esta gráfica?"),
    ]
    guardar_resultado("parte1_4", {"casos": casos})
