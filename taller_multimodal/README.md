# Taller: entrada multimodal y audio

Dominio: **crianza positiva con TBRI®** (Intervención Relacional Basada en la Confianza), el del asistente CrianzApp. La parte 1 usa un modelo con visión sobre fichas de los Niveles de Respuesta™, un resumen de la Respuesta IDEAL© y un semáforo de hidratación; la parte 2 transcribe preguntas de cuidadores grabadas en audio y se las pasa a un modelo para que responda.

Integrantes: Mariana Alejandra Gordillo Meneses y Julian David Cristancho Niño.

## Preparación

```bash
cd taller_multimodal
```

```bash
python -m venv .venv && source .venv/bin/activate
```

```bash
pip install -r requirements.txt
```

```bash
cp .env.example .env
```

Después se abre `.env` y se pone la clave. Variables de entorno:

| Variable | Obligatoria | Valor por defecto | Uso |
|---|---|---|---|
| `GROQ_API_KEY` | Sí | — | Clave de <https://console.groq.com> |
| `VISION_MODEL` | No | `qwen/qwen3.8-27b` | Modelo con visión (parte 1) |
| `LLM_MODEL` | No | `openai/gpt-oss-20b` | Modelo de texto: responde en la parte 2 y es el "modelo sin visión" de la 1.4 |
| `AUDIO_MODEL` | No | `whisper-large-v3-turbo` | Modelo de transcripción (parte 2) |

El `.env` está en el `.gitignore`: la clave no se sube al repositorio.

## Parte 1. Visión

| Punto | Comando | Qué hace |
|---|---|---|
| 1.1 | `python parte1_1_pregunta_imagen.py` | Envía `semaforo_hidratacion.png` en base64 con una pregunta de una cuidadora sobre la gráfica. |
| 1.2 | `python parte1_2_extraccion.py` | Extrae 8 campos de 3 fichas de Niveles de Respuesta en JSON, valida el JSON con Pydantic y lo compara campo por campo con `imagenes/valores_reales.json`. Imprime el porcentaje de aciertos. |
| 1.3 | `python parte1_3_varias_imagenes.py` | Envía 3 imágenes en un mismo mensaje (Respuesta IDEAL y fichas de los niveles 1 y 4) y pide una comparación y un resumen conjunto. |
| 1.4 | `python parte1_4_error_provocado.py` | Provoca dos errores (4 imágenes en una solicitud; una imagen a un modelo sin visión) y muestra el mensaje de la API. |

Si la salida del modelo en la 1.2 no es JSON o no cumple el esquema, el programa lo informa (`NO VÁLIDO → motivo`), cuenta esos campos como fallos y continúa con la siguiente imagen.

Las 6 imágenes de `imagenes/` son de elaboración propia: se generaron con `python crear_imagenes.py` a partir del contenido de los libros de trabajo de TBRI® (Corrección y Empoderamiento) que forman la base de conocimiento de CrianzApp. El mismo script escribe los valores reales.

## Parte 2. Audio

Los audios van en `audios/` con los nombres `audio_1.mp3` … `audio_4.mp3` (el script acepta también m4a, wav, ogg y webm). El texto de cada uno está en [audios/GUION.md](audios/GUION.md) y en `audios/guion.json`, junto con el hablante y la condición (con o sin ruido).

```bash
python parte2_audio.py
```

Para cada audio muestra la duración, lo que se dijo, la transcripción de Whisper, el error de palabras (WER) frente al guion y la respuesta del modelo a la transcripción.

## Resultados

Cada script guarda su salida en `resultados/` (`parte1_1.json`, `parte1_2.json`, …) para pasarla al informe.

## Límites de la API (Groq)

- Visión con `qwen/qwen3.8-27b`: máximo 3 imágenes y 20 MB por solicitud; cada imagen cuenta como 2.048 tokens de entrada.
- Audio: archivos de hasta 25 MB en el plan gratuito; cada solicitud se cobra como mínimo por 10 segundos.

## Informe

[Informe_Taller_multimodal_y_audio.docx](Informe_Taller_multimodal_y_audio.docx) sigue la plantilla de entrega, con las capturas de la ejecución y el análisis de cada punto.
