"""Parte 1.1 — Una pregunta del dominio sobre una imagen local enviada en base64."""
from langchain_core.messages import HumanMessage

from comun import CARPETA_IMAGENES, MODELO_VISION, bloque_imagen, cargar_llm_vision, guardar_resultado, texto_de

IMAGEN = CARPETA_IMAGENES / "semaforo_hidratacion.png"
PREGUNTA = (
    "Soy mamá de un niño de 6 años y quiero usar esta gráfica en casa. "
    "¿Qué color indica que está bien hidratado y qué debe hacer en cada uno de los otros dos colores? "
    "Explica también por qué la hidratación influye en el comportamiento del niño."
)

if __name__ == "__main__":
    llm = cargar_llm_vision()
    respuesta = llm.invoke([HumanMessage(content=[
        {"type": "text", "text": PREGUNTA},
        bloque_imagen(IMAGEN),
    ])])

    print(f"Modelo:   {MODELO_VISION}")
    print(f"Imagen:   imagenes/{IMAGEN.name}")
    print(f"Pregunta: {PREGUNTA}\n")
    print(f"Respuesta:\n{texto_de(respuesta)}")

    guardar_resultado("parte1_1", {
        "modelo": MODELO_VISION, "imagen": IMAGEN.name,
        "pregunta": PREGUNTA, "respuesta": texto_de(respuesta),
    })
