# CrianzApp — Crianza con calma

Chat web de orientación general sobre crianza positiva y responsable. Recupera evidencia de documentos locales PDF, DOCX, Markdown y texto; si se configura `GROQ_API_KEY`, usa Groq para redactar respuestas conversacionales basadas en esos fragmentos. Está preparado para ejecutarse localmente o desplegarse en Render.

## Cómo funciona el RAG

1. **Carga y fragmentación:** al iniciar, `knowledge_base.py` admite `.pdf`, `.docx`, `.txt` y `.md`; usa `RecursiveCharacterTextSplitter` con fragmentos de 500 caracteres y solapamiento de 50.
2. **Indexación y recuperación:** ChromaDB persiste los embeddings y metadatos en `vectorstore/`; el retriever usa similitud semántica y devuelve hasta tres fragmentos.
3. **Aumento:** `build_prompt()` combina evidencia delimitada, historial conversacional, ejemplos few-shot y las instrucciones responsables del Avance 1.
4. **Generación:** con `GROQ_API_KEY`, Groq redacta y valida la respuesta estructurada. Sin clave o cuando el servicio falla, el chat muestra directamente la evidencia recuperada.
5. **Abstención y seguridad:** sin evidencia suficiente se indica expresamente que la información no está disponible en la base. Las señales de violencia, abuso o autolesión reciben orientación prioritaria y canales de ayuda.

La interfaz muestra las fuentes consultadas y distingue respuesta generativa, respuesta local y orientación de seguridad. El historial se conserva solo en la pestaña durante la conversación.

## Ejecutar localmente

Requiere Python 3.12 o posterior.

1. Usa Python 3.12.8 (versión fijada en `.python-version`) e instala dependencias: `python -m pip install -r requirements.txt`.
2. (Opcional) Configura `GROQ_API_KEY` y `GROQ_MODEL` en las variables de entorno para generación con Groq. Las claves no se deben subir al repositorio.
3. Inicia la aplicación: `python main.py`.
4. Abre `http://localhost:5000`.

Sin `GROQ_API_KEY`, el chat sigue disponible en modo local extractivo. Copia `.env.example` como `.env` para completar tus claves localmente. El archivo `.env` no se carga automáticamente; configura las variables en tu entorno antes de iniciar la aplicación.

Para ejecutar la evaluación dentro del entorno Python 3.12.8, configura `GOOGLE_API_KEY` en `.env` y ejecuta desde la raíz `./.venv312/bin/python -m dotenv run -- ./.venv312/bin/python eval_ragas.py`. El script usa Gemini para puntuar preguntas y fragmentos recuperados y crea `ragas_results.json`. Puedes cambiar el modelo con `RAGAS_LLM_MODEL`; el valor predeterminado es `gemini-3.8-flash`. El dataset con 15 preguntas está en `eval_dataset.json`.

## Desplegar en Render

1. Sube este repositorio a GitHub.
2. En Render, selecciona **New → Blueprint** y conecta el repositorio. Render usará `render.yaml`.
3. Añade el valor secreto de `GROQ_API_KEY` cuando Render lo solicite. `GROQ_MODEL` ya tiene un valor por defecto y se puede cambiar en la configuración del servicio.
4. Despliega y verifica `/api/health`.

También se puede crear un **Web Service** manual con entorno Python, build command `pip install -r requirements.txt` y start command `gunicorn main:app --bind 0.0.0.0:$PORT --workers 1 --timeout 120`.

## API

- `GET /` — interfaz del chat.
- `GET /api/health` — estado del servicio, fragmentos disponibles y si Groq está configurado (nunca expone la clave).
- `POST /chat` (alias compatible: `/api/chat`) — recibe JSON con `message` y `history`; devuelve `respuesta` y `fuentes` junto con los alias `answer` y `sources`, además de `mode` y `notice`.

## Contenido y alcance

Amplía la base añadiendo archivos PDF, DOCX, Markdown o texto a `docs/base_conocimiento/`; al cambiar su contenido, el índice Chroma se reconstruye al iniciar. En despliegues con disco efímero el índice también es efímero y se vuelve a crear durante el arranque.

CrianzApp ofrece orientación general: no diagnostica ni reemplaza a psicología, pediatría o servicios de protección infantil. Ante indicios de abuso o riesgo, prioriza ayuda humana; en Colombia, ICBF línea 141 y emergencias 123. Evita compartir información que identifique a niños o niñas. Cuando Groq está habilitado, el mensaje y los fragmentos recuperados se envían a ese proveedor para generar la respuesta.
