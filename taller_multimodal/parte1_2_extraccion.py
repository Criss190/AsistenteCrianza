"""Parte 1.2 — Extracción estructurada: de una ficha de Niveles de Respuesta TBRI a un JSON validado."""
import json
from typing import Literal

from langchain_core.messages import HumanMessage
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from comun import CARPETA_IMAGENES, MODELO_VISION, bloque_imagen, cargar_llm_vision, guardar_resultado, texto_de


class FichaNivelRespuesta(BaseModel):
    """Esquema de los datos que se extraen de cada ficha."""
    model_config = ConfigDict(extra="forbid")  # un campo inventado también es un error

    nivel: int = Field(ge=1, le=4, description="Número del Nivel de Respuesta (entero de 1 a 4)")
    nombre: str = Field(description="Nombre del nivel, por ejemplo 'Interacción divertida'")
    principio: Literal["Conexión", "Empoderamiento", "Corrección"] = Field(description="Principio de TBRI al que pertenece")
    tono: str = Field(description="Tono de voz recomendado para el adulto")
    volumen: str = Field(description="Volumen de voz recomendado")
    cadencia: str = Field(description="Cadencia o ritmo recomendado al hablar")
    tiempo_resolucion: str = Field(description="Tiempo de resolución, tal como aparece en la ficha")
    pagina_fuente: int = Field(description="Número de página de la fuente citada al pie (entero)")


CAMPOS = list(FichaNivelRespuesta.model_fields)

INSTRUCCION = (
    "Extrae los datos de esta ficha de crianza sobre los Niveles de Respuesta de TBRI. "
    "Responde SOLO con un objeto JSON, sin texto adicional, con exactamente estos campos:\n"
    + "\n".join(f'- "{nombre}": {campo.description}' for nombre, campo in FichaNivelRespuesta.model_fields.items())
    + '\nValores permitidos: "principio" es "Conexión", "Empoderamiento" o "Corrección"; '
    '"nivel" y "pagina_fuente" son números enteros, no texto.'
)


def validar_json(texto):
    """Valida la salida del modelo contra el esquema.

    Devuelve (datos, None) si es válida o (None, mensaje_de_error) si no lo es.
    Nunca lanza una excepción: el programa informa del problema y sigue.
    """
    texto = texto.strip()
    inicio, fin = texto.find("{"), texto.rfind("}")
    if inicio == -1 or fin == -1:
        return None, "La respuesta no contiene un objeto JSON."
    try:
        datos = json.loads(texto[inicio:fin + 1])  # ignora ```json ... ``` y texto alrededor
    except json.JSONDecodeError as e:
        return None, f"JSON mal formado: {e}"
    try:
        return FichaNivelRespuesta.model_validate(datos).model_dump(), None
    except ValidationError as e:
        errores = "; ".join(f"{'.'.join(map(str, err['loc']))}: {err['msg']}" for err in e.errors())
        return None, f"El JSON no cumple el esquema: {errores}"


def normalizar(valor):
    """Comparación sin distinguir mayúsculas, espacios ni punto final."""
    return None if valor is None else str(valor).strip().rstrip(".").casefold()


def comparar(real, extraido):
    """Compara campo por campo. Si no hubo JSON válido, todos los campos cuentan como fallo."""
    filas = []
    for campo in CAMPOS:
        valor = extraido.get(campo) if extraido else None
        correcto = extraido is not None and normalizar(real[campo]) == normalizar(valor)
        filas.append({"campo": campo, "real": real[campo], "extraido": valor, "correcto": correcto})
    return filas


if __name__ == "__main__":
    valores_reales = json.loads((CARPETA_IMAGENES / "valores_reales.json").read_text(encoding="utf-8"))
    llm = cargar_llm_vision()
    resultados, aciertos, total = [], 0, 0

    for nombre, real in valores_reales.items():
        print(f"\n=== {nombre} ===")
        respuesta = llm.invoke([HumanMessage(content=[
            {"type": "text", "text": INSTRUCCION},
            bloque_imagen(CARPETA_IMAGENES / nombre),
        ])])
        salida = texto_de(respuesta)
        print(f"Salida del modelo:\n{salida}\n")

        extraido, error = validar_json(salida)
        print(f"Validación: {'JSON válido' if error is None else 'NO VÁLIDO → ' + error}")

        filas = comparar(real, extraido)
        print(f"{'Campo':<18} {'Valor real':<30} {'Valor extraído':<30} ¿Correcto?")
        for f in filas:
            print(f"{f['campo']:<18} {str(f['real']):<30} {str(f['extraido']):<30} {'Sí' if f['correcto'] else 'No'}")
        aciertos += sum(f["correcto"] for f in filas)
        total += len(filas)
        resultados.append({"imagen": nombre, "salida_modelo": salida, "error_validacion": error, "campos": filas})

    porcentaje = 100 * aciertos / total
    print(f"\nPorcentaje de aciertos: {aciertos} de {total} campos = {porcentaje:.1f} %")
    guardar_resultado("parte1_2", {
        "modelo": MODELO_VISION, "instruccion": INSTRUCCION,
        "aciertos": aciertos, "total": total, "porcentaje": round(porcentaje, 1), "imagenes": resultados,
    })
