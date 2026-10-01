# CrianzApp — Crianza con calma

Chat web de orientación general sobre crianza positiva y responsable. Recupera evidencia de la guía local en Markdown y, si se configura `GROQ_API_KEY`, usa Groq para redactar respuestas conversacionales basadas en esos fragmentos. Está preparado para ejecutarse localmente o desplegarse en Render.

## Cómo funciona el RAG

1. **Carga:** lee los archivos `.md` y `.txt` de `docs/base_conocimiento/` al iniciar.
2. **Recuperación:** `BaseConocimientoLocal.buscar()` selecciona hasta cuatro fragmentos por coincidencia léxica. No descarga modelos ni necesita una base vectorial, para mantener bajo el consumo de memoria de Render.
3. **Aumento:** `build_prompt()` añade la pregunta, los fragmentos recuperados, los ejemplos few-shot y las instrucciones de crianza responsable.
4. **Generación:** con una clave de Groq, genera y valida una respuesta estructurada. Sin clave o si Groq no está disponible, muestra directamente la evidencia local.
5. **Seguridad:** consultas con señales de violencia, abuso o autolesión reciben orientación prioritaria y canales de ayuda, sin enviarse al LLM.

La interfaz muestra las fuentes consultadas y distingue respuesta generativa, respuesta local y orientación de seguridad. El historial se conserva solo en la pestaña durante la conversación.

## Ejecutar localmente

Requiere Python 3.12 o posterior.

1. Instala dependencias: `pip install -r requirements.txt`.
2. (Opcional) Configura `GROQ_API_KEY` y `GROQ_MODEL` en las variables de entorno. La clave se obtiene en la consola de Groq; no se debe subir al repositorio.
3. Inicia la aplicación: `python main.py`.
4. Abre `http://localhost:5000`.

Sin `GROQ_API_KEY`, el chat sigue disponible en modo local extractivo. El archivo `.env.example` documenta las variables de entorno, pero no se carga automáticamente.

## Desplegar en Render

1. Sube este repositorio a GitHub.
2. En Render, selecciona **New → Blueprint** y conecta el repositorio. Render usará `render.yaml`.
3. Añade el valor secreto de `GROQ_API_KEY` cuando Render lo solicite. `GROQ_MODEL` ya tiene un valor por defecto y se puede cambiar en la configuración del servicio.
4. Despliega y verifica `/api/health`.

También se puede crear un **Web Service** manual con entorno Python, build command `pip install -r requirements.txt` y start command `gunicorn main:app --bind 0.0.0.0:$PORT --workers 2 --timeout 60`.

## API

- `GET /` — interfaz del chat.
- `GET /api/health` — estado del servicio, fragmentos disponibles y si Groq está configurado (nunca expone la clave).
- `POST /api/chat` — recibe JSON con `message` y un `history` opcional; devuelve `answer`, `sources`, `mode` y `notice`.

## Contenido y alcance

Amplía la base añadiendo archivos `.md` o `.txt` en `docs/base_conocimiento/`. La recuperación actual es léxica, no usa embeddings, ChromaDB ni búsqueda semántica. La notebook `docs/base_conocimiento/flujo_rag_groq.ipynb` conserva el ejemplo educativo de embeddings y ChromaDB; esta app web usa una arquitectura ligera más adecuada para el despliegue elegido.

CrianzApp ofrece orientación general: no diagnostica ni reemplaza a psicología, pediatría o servicios de protección infantil. Ante indicios de abuso o riesgo, prioriza ayuda humana; en Colombia, ICBF línea 141 y emergencias 123. Evita compartir información que identifique a niños o niñas. Cuando Groq está habilitado, el mensaje y los fragmentos recuperados se envían a ese proveedor para generar la respuesta.
