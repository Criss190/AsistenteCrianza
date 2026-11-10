# CrianzApp — Crianza con calma

Asistente web de orientación general sobre crianza positiva. La interfaz
desplegada usa un **agente con tool calling** (Avance 3,
[docs/agente_avance3.md](docs/agente_avance3.md)): el LLM decide si busca en
la guía local, si genera una referencia APA o si busca en un conjunto fijo
de sitios web oficiales, y responde solo con lo que esas tools devolvieron,
citando la fuente. El pipeline fijo original (Avance 2,
[docs/flujo_completo_rag.md](docs/flujo_completo_rag.md)) se conserva en
`src/rag_chat.py` para comparación en la evaluación Ragas.

## Agente con tool calling (Avance 3)

`src/agent.py` (`AgenteCrianza`) reemplaza la recuperación automática del
Avance 2 por un loop de hasta 4 idas y vueltas con Groq (SDK nativo,
tool calling estilo OpenAI). Tools en [src/tools.py](src/tools.py):

- **`buscar_en_base(consulta)`** — recupera en la guía local (lo mismo que
  usaba el Avance 2). Máximo 4 fragmentos de 600 caracteres, cada uno con
  documento y página/sección, fijo en código.
- **`generar_referencia_apa(documento)`** — tarea de dominio: devuelve la
  cita APA real y fija de uno de los 5 documentos del corpus (nunca inventa
  una referencia).
- **`buscar_en_web(consulta, se_uso_base)`** — búsqueda pública vía Tavily,
  ver política abajo.

### Búsqueda web controlada

La base de conocimiento nunca sale del sistema — solo la *consulta* que el
agente decide enviar a Tavily, y solo bajo esta política:

- **Cuándo se usa**: solo si `buscar_en_base` no encontró evidencia para la
  misma pregunta Y la pregunta trata de información pública o vigente (una
  norma, una definición general, una cifra reciente) — nunca como primera
  opción. La regla está en el docstring de `buscar_en_web` y en el System
  Prompt, y además se refuerza en código: la tool recibe `se_uso_base` y si
  es `False` rechaza la búsqueda sin llegar a llamar a Tavily.
- **Sitios permitidos** (fijos en `DOMINIOS_PERMITIDOS_WEB`, el LLM no los
  puede cambiar): `child.tcu.edu` (Instituto Karyn Purvis, fuente oficial de
  TBRI®), `icbf.gov.co` (protección infantil en Colombia), `who.int`,
  `unicef.org`, `healthychildren.org` (Academia Americana de Pediatría) y
  `cdc.gov`. Se eligieron por ser organismos oficiales o de salud pública
  reconocidos en crianza y protección infantil, no sitios genéricos.
- **Resultados acotados**: máximo 3, cada uno con título, URL y un extracto
  de hasta 300 caracteres, marcado `origen: "web"`.
- **Respuesta separada por origen**: lo que viene de la guía se cita como
  `(Fuente: documento, p.página)`; lo que viene de la web, como
  `[web: URL]`. Nunca se mezclan en una misma cita.

Requiere `TAVILY_API_KEY` (ver [Despliegue](#despliegue)); sin ella,
`buscar_en_web` devuelve un error controlado y el agente sigue funcionando
solo con la base local.

### Registro de uso de tools

Cada respuesta del agente guarda qué tools llamó, con qué argumentos, y
cuántas llamadas al LLM hizo, en `scripts_ragas/results/agent_log.jsonl` y
en la propia respuesta de la API (`tool_calls`, `llm_calls`) — la interfaz
los muestra en una sección desplegable.

## Pipeline fijo (Avance 2) — flujo RAG de referencia

```mermaid
flowchart LR
    A["Corpus seleccionado<br/>docs/base_conocimiento/"] --> B["Extracción<br/>PDF · DOCX · TXT · MD · HTML"]
    B --> C["Fragmentación por párrafo/frase<br/>900 car. · 120 solapados (sin cortar oraciones)"]
    C --> D["Embeddings locales<br/>all-MiniLM-L6-v2"]
    D --> E[("ChromaDB persistente<br/>vectorstore/")]
    F["Pregunta + contexto del turno anterior"] --> H["Híbrido BM25 + coseno (RRF)<br/>top_k configurable"]
    E --> H
    H --> I{"¿Hay evidencia?"}
    I -- No --> J["Abstención explícita"]
    I -- Sí --> K["System Prompt + Few-Shot<br/>delimitadores + evidencia + contexto_previo"]
    K --> L["Groq opcional<br/>JSON validado"]
    L --> M["Respuesta + fuentes<br/>fragmento, archivo, página/sección"]
    J --> M
```

La auditoría y requisitos están en
[docs/architecture/01-auditoria.md](docs/architecture/01-auditoria.md) y
[docs/architecture/02-requisitos-y-casos-de-uso.md](docs/architecture/02-requisitos-y-casos-de-uso.md).
El detalle del pipeline, sus decisiones técnicas y el estado de evaluación
están en [docs/flujo_completo_rag.md](docs/flujo_completo_rag.md).

### Corpus

El corpus definitivo contiene cinco PDF: los tres materiales de participante
TBRI (Conexión, Corrección y Empoderamiento), el artículo de Gómez Muzzio
sobre psicoterapia y apego, y la revisión sistemática de intervenciones
digitales de crianza. El Markdown provisional `guia_crianza.md` fue retirado
y se excluye explícitamente de la ingestión; los PDF originales se conservan.
Los documentos Markdown derivados de esos PDF siguen siendo formatos válidos.

Los formatos aceptados son PDF, DOCX, TXT, Markdown y HTML (`.html`/`.htm`).
PDF usa metadatos de página; DOCX/Markdown/HTML/TXT usan sección o nombre de
archivo. El splitter (`src/knowledge_base.py`) es propio, no
`RecursiveCharacterTextSplitter`: agrupa párrafos completos y, si exceden el
tamaño, baja a frases y luego a palabras, sin cortar nunca a mitad de oración;
arrastra al fragmento siguiente las últimas unidades del anterior hasta el
solapamiento configurado. El tamaño/solapamiento por defecto es 900/120
caracteres, pero `.env`/Render los fijan en 500/50 vía `RAG_CHUNK_SIZE` y
`RAG_CHUNK_OVERLAP` (ver sección de evaluación para la comparación entre
configuraciones). Chroma persiste los textos, metadatos e índices en
`vectorstore/`. El embedding explícito es `sentence-transformers/all-MiniLM-L6-v2`,
ejecutado localmente por la función predeterminada de Chroma; es compacto y no
requiere llaves ni llamadas remotas para vectorizar. Es una limitación conocida
que no sea multilingüe y se documenta como mejora candidata.

La recuperación es híbrida: BM25 sobre raíces de palabras en español (señal
principal, ponderada por coincidencia con la pregunta y su expansión al
vocabulario TBRI) combinada con similitud coseno vía fusión por rango
recíproco (RRF); se conservan hasta `top_k` fragmentos que superen un umbral
mínimo de evidencia léxica. Si la pregunta sola no encuentra nada y hay un
turno anterior, el sistema reintenta la búsqueda con la pregunta reformulada
de forma autónoma (con Groq si hay clave, o por combinación léxica simple en
modo local) para resolver seguimientos elípticos ("¿y el segundo?"). La
clasificación de riesgo de seguridad depende solo del mensaje actual, nunca
del historial. Sin evidencia aceptable, el asistente explica que su
especialidad es la crianza responsable y que no encontró información
suficiente para responder con seguridad.

### Memoria conversacional

El frontend mantiene el historial visual de la conversación (hasta 4
intercambios) y lo envía con cada mensaje. El backend lo usa de dos formas: (1)
como respaldo de recuperación cuando la pregunta actual sola no basta, y (2)
como `contexto_previo` para la generación, exclusivamente para interpretar
referencias ("eso", "el segundo") — nunca como fuente de hechos citables. El
historial se trunca a los últimos turnos y nunca influye en la clasificación de
riesgo, que siempre evalúa solo el mensaje actual.

## Instalación y ejecución

Requiere Python 3.12.8, fijado en `.python-version`.

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
cp .env.example .env
python main.py
```

Completa localmente `GROQ_API_KEY` para habilitar generación con Groq.
`GOOGLE_API_KEY` solo se requiere para ejecutar Ragas. `.env` está ignorado por
Git y se carga desde la raíz; nunca incluyas claves en commits o capturas.
Sin clave de Groq, el backend devuelve los fragmentos relevantes en modo
extractivo. Abre `http://localhost:5000`.

### API

- `GET /`: interfaz de conversación.
- `GET /api/health`: disponibilidad, cantidad de chunks y estado del LLM; no
  devuelve secretos.
- `POST /chat` y alias `POST /api/chat`: JSON `{ "message": "...", "history": [...] }`.
  `history` son los últimos turnos `{role, content}` de la conversación (el
  frontend conserva hasta 4 intercambios); el agente los usa para resolver
  seguimientos elípticos y dar contexto, nunca como fuente de hechos ni para
  decidir riesgo de seguridad. Devuelve `respuesta`, `fuentes` (con `origen:
  "base"|"web"`), `mode`, `notice`, `tool_calls` (qué tool llamó y con qué
  argumentos) y `llm_calls`, además de alias en inglés.

## Evaluación Ragas

`scripts_ragas/questions/eval_dataset.json` contiene 15 preguntas: 12 en dominio y 3 fuera de dominio,
con `ground_truth`. Las cuatro métricas Ragas se calculan solo para las
preguntas en dominio, donde la referencia representa contenido recuperable.
Para las preguntas fuera de dominio se reporta por separado la tasa de
abstención correcta; `context_recall` no es una medida válida para una
referencia que explícitamente dice que el dato no está en el corpus.

```bash
GOOGLE_API_KEY=... python scripts_ragas/eval_ragas.py
```

El script carga `.env`, usa Gemini configurado en `RAGAS_LLM_MODEL` y
`RAGAS_EMBEDDING_MODEL`, imprime promedios y guarda `scripts_ragas/results/ragas_results.json`
(o la ruta indicada en `RAGAS_RESULTS_PATH`). La clave y el modelo de Google
deben tener cuota disponible; el plan gratuito de algunos modelos de Gemini
(p. ej. `gemini-3.8-flash`) limita a 5 solicitudes/minuto, insuficiente para
esta evaluación — `RAGAS_LLM_MODEL=gemini-3.5-flash-lite` (15/min) funciona
de forma confiable.

**Resultados reales** (análisis completo, con atribución por componente, en
[docs/flujo_completo_rag.md](docs/flujo_completo_rag.md#8-evaluación-con-ragas)):

| Métrica | 500/50, top_k=3 ([json](scripts_ragas/results/ragas_baseline.json)) | 900/120, top_k=4 — adoptada ([json](scripts_ragas/results/ragas_900_120_4.json)) |
|---|---|---|
| faithfulness | 0.555 | 0.540 |
| answer_relevancy | 0.693 | 0.614 |
| context_precision | 0.417 | 0.569 |
| context_recall | 0.333 | 0.409 |
| Abstención fuera de dominio | 3/3 (100%) | 3/3 (100%) |

La métrica más baja en ambas corridas es de recuperación
(`context_recall`/`context_precision`), no de generación: varios fragmentos
con la respuesta exacta no entraban en el `top_k`. Subir chunk/overlap/top_k
mejoró ambas métricas de recuperación a costa de una pequeña baja en
`answer_relevancy`/`faithfulness` (fragmentos más grandes traen más texto
no relacionado con la pregunta puntual). El índice se reconstruye solo al
detectar cambios en el corpus o en estos parámetros.

## Despliegue

El blueprint de Render está en `render.yaml`. Conecta el repositorio como
Blueprint y configura `GROQ_API_KEY` y `TAVILY_API_KEY` como secretos;
`GROQ_MODEL` tiene un valor predeterminado. Sin `TAVILY_API_KEY` el agente
sigue funcionando, solo que `buscar_en_web` devuelve un error controlado en
vez de resultados. El comando de inicio es Gunicorn con un worker y crea el
índice al arrancar. El almacenamiento del plan gratuito puede ser efímero,
por lo que el índice se reconstruye en cada despliegue.

- Repositorio: [github.com/Criss190/AsistenteCrianza](https://github.com/Criss190/AsistenteCrianza)
- URL pública: pendiente de verificar. La dirección probada
  `https://crianzapp.onrender.com` respondió HTTP 404; no debe presentarse
  como despliegue funcional hasta confirmar la URL generada por Render.

## Alcance y seguridad

El asistente brinda información general; no diagnostica ni reemplaza atención
profesional. Señales de abuso, violencia o autolesión tienen una respuesta de
seguridad prioritaria, determinística, antes de llegar al agente. En
Colombia se informa la línea ICBF 141 y emergencias 123. Al habilitar Groq,
la pregunta actual y los fragmentos recuperados se envían a ese proveedor; si
el agente usa `buscar_en_web`, la consulta (no la base de conocimiento) se
envía a Tavily. No incluyas datos identificables de niños o niñas.
