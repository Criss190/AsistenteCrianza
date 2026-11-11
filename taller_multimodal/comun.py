"""Piezas compartidas por los scripts del taller: modelos, imágenes y resultados."""
import base64
import json
import mimetypes
import os
from pathlib import Path

from dotenv import load_dotenv
from langchain_groq import ChatGroq

CARPETA = Path(__file__).parent
CARPETA_IMAGENES = CARPETA / "imagenes"
CARPETA_AUDIOS = CARPETA / "audios"
CARPETA_RESULTADOS = CARPETA / "resultados"

load_dotenv(CARPETA / ".env")
load_dotenv()  # también vale un .env en la carpeta desde la que se ejecuta

MODELO_VISION = os.getenv("VISION_MODEL", "qwen/qwen3.8-27b")
MODELO_TEXTO = os.getenv("LLM_MODEL", "openai/gpt-oss-20b")
MODELO_AUDIO = os.getenv("AUDIO_MODEL", "whisper-large-v3-turbo")


def comprobar_clave():
    if not os.getenv("GROQ_API_KEY"):
        raise SystemExit("Falta GROQ_API_KEY. Copia .env.example como .env y pon tu clave.")


def cargar_llm_vision():
    """Modelo con visión (el mismo de multimodal.py de clase)."""
    comprobar_clave()
    return ChatGroq(model=MODELO_VISION, temperature=0, max_tokens=4096, reasoning_effort="low")


def cargar_llm_texto():
    """Modelo de solo texto, para responder a las transcripciones."""
    comprobar_clave()
    return ChatGroq(model=MODELO_TEXTO, temperature=0)


def bloque_imagen(ruta, mime_type=None):
    """Convierte una imagen local en el bloque base64 que espera el modelo."""
    ruta = Path(ruta)
    return {
        "type": "image",
        "base64": base64.b64encode(ruta.read_bytes()).decode("utf-8"),
        "mime_type": mime_type or mimetypes.guess_type(ruta.name)[0] or "image/png",
    }


def texto_de(respuesta):
    """Devuelve el texto de una respuesta, venga como cadena o como lista de bloques."""
    contenido = respuesta.content
    if isinstance(contenido, str):
        return contenido
    return "".join(b.get("text", "") for b in contenido if isinstance(b, dict))


def guardar_resultado(nombre, datos):
    """Guarda la salida de un script en resultados/ para usarla en el informe."""
    CARPETA_RESULTADOS.mkdir(exist_ok=True)
    ruta = CARPETA_RESULTADOS / f"{nombre}.json"
    ruta.write_text(json.dumps(datos, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n[Resultado guardado en {ruta.relative_to(CARPETA)}]")
