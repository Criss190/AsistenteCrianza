# Flujo completo del sistema RAG — CrianzApp

Este documento recoge, en un solo lugar, cada decisión técnica del pipeline
RAG de extremo a extremo (Avance 2) y los resultados de su evaluación con
Ragas. El código referenciado vive en `src/` y `eval_ragas.py`; el README
resume la puesta en marcha.

## 1. Selección de documentos

El corpus son cinco documentos en `docs/base_conocimiento/` (y sus PDF
originales en `docs/fuentes_originales/`):

| Documento | Tipo de evidencia que aporta |
|---|---|
| TBRI® — Principios de Conexión (participante) | Apego, contacto saludable, calidad de la voz, interacción divertida |
| TBRI® — Principios de Corrección (participante) | Niveles de Respuesta, Respuesta IDEAL©, disciplina no punitiva |
| TBRI® — Principios de Empoderamiento (participante) | Regulación del cuerpo: hidratación, glucemia, sentidos, rutinas/rituales |
| Gómez Muzzio et al. (2008) | Marco teórico de apego y sensibilidad parental (Ainsworth/Bowlby), psicoterapias basadas en evidencia |
| Lin-Lewry et al. (2024) | Revisión sistemática de intervenciones digitales de crianza postparto |

**Pertinencia frente al dominio:** CrianzApp orienta a madres, padres y
cuidadores en crianza positiva y regulación emocional infantil. TBRI es el
marco operativo (qué hacer en el momento), y los dos artículos académicos
dan respaldo teórico y de evidencia empírica a esas prácticas, sin
duplicarse entre sí. Se excluyó deliberadamente una guía Markdown
provisional (`guia_crianza.md`) que no pasó por el mismo control de fuente
que los PDF originales (ver `FUENTES_EXCLUIDAS` en
[src/knowledge_base.py](../src/knowledge_base.py)).

## 2. Ingesta

[src/knowledge_base.py](../src/knowledge_base.py) extrae texto y metadatos de
ubicación según el formato (`_leer_texto`):

- **PDF**: una entrada por página (`pypdf`), con `page` en los metadatos —
  así cada cita puede señalar la página exacta del PDF original.
- **DOCX**: se segmenta por encabezados de Word (`python-docx`); las tablas
  se extraen aparte como filas `celda | celda`.
- **HTML/HTM**: un parser propio (`_ExtractorHTML`) extrae texto visible,
  ignora `<script>/<style>` y usa los `<h1>-<h6>` como `section`.
- **Markdown**: se reconoce el formato `## Página N — Título` que genera
  `scripts/pdf_a_markdown.py`, preservando el número de página del PDF del
  que se derivó.
- **TXT**: se indexa como una sola sección con el nombre del archivo.

## 3. Chunking

Implementado en `_fragmentar`/`_unidades_de_texto`
([src/knowledge_base.py](../src/knowledge_base.py)): **no** es
`RecursiveCharacterTextSplitter` de LangChain, sino un splitter propio que:

1. Agrupa párrafos completos hasta el tamaño máximo.
2. Si un párrafo excede el tamaño, baja a frases (separando en `. ! ? ; :`).
3. Si una frase aún excede el tamaño, baja a palabras.
4. Nunca corta a mitad de oración.
5. Arrastra al inicio del fragmento siguiente las últimas unidades del
   anterior, hasta cubrir el solapamiento configurado, para no perder
   contexto en el límite.

**Parámetros:** por defecto 900 caracteres / 120 de solapamiento
(`TAMANO_FRAGMENTO`/`SOLAPAMIENTO_FRAGMENTO`); el despliegue (`.env` y
Render) los fija en **500/50** vía `RAG_CHUNK_SIZE`/`RAG_CHUNK_OVERLAP`.
Justificación: los documentos TBRI están escritos en párrafos cortos y
viñetas; 500 caracteres mantiene cada fragmento centrado en una sola idea
(una estrategia, un nivel de respuesta) sin mezclar dos secciones distintas,
y el solapamiento de 50 basta para no perder el encabezado de sección que
antecede a cada fragmento. La sección 6 compara esta configuración contra
`top_k` más alto como iteración de mejora.

## 4. Vectorización

Embedding `sentence-transformers/all-MiniLM-L6-v2`
(`MODELO_EMBEDDINGS`), ejecutado localmente por la función predeterminada de
ChromaDB (`DefaultEmbeddingFunction`). Se eligió por ser compacto (~80 MB),
no requerir llamadas remotas ni llaves para vectorizar, y tener latencia
mínima en un plan gratuito de Render. Limitación conocida: no es
multilingüe de forma nativa, lo que se compensa recuperando principalmente
por BM25 en español (sección 5) y usando los vectores solo como señal de
desempate.

## 5. Base de datos vectorial

ChromaDB persistente en `vectorstore/` (`PersistentClient`,
`_preparar_vectores`). La colección guarda, por fragmento:

- `source`, `filename`: documento de origen, para citar la fuente.
- `chunk_id`: identificador estable (hash del archivo + índice de fragmento).
- `page` (PDF) o `section` (DOCX/MD/HTML/TXT): ubicación dentro del
  documento.
- `document_title`: título de documento cuando el formato lo provee.

Esos mismos metadatos se devuelven en cada respuesta del API (`sources`) y
se muestran en la interfaz junto al extracto citado. El índice se
reconstruye automáticamente cuando cambia el hash del corpus o los
parámetros de fragmentación/embedding (`corpus_hash` en los metadatos de la
colección), evitando índices desincronizados tras un cambio de documentos.

## 6. Recuperación

Híbrida, en `BaseConocimientoLocal.buscar`:

- **BM25** (k1=1.5, b=0.75) sobre raíces de palabras en español (stemming +
  sin tildes + lista de stopwords), con expansión de la consulta al
  vocabulario TBRI mediante reglas léxicas (p. ej. "rabieta/berrinche" →
  "autorregulación, niveles de respuesta").
- **Similitud coseno** sobre los embeddings de Chroma, usada como señal
  secundaria.
- **Fusión por rango recíproco (RRF)**: el orden léxico decide, los
  vectores desempatan.
- Un fragmento solo cuenta como evidencia si supera un umbral mínimo de
  BM25 y coincide en al menos dos señales de contenido (evita que una
  palabra suelta compartida con una pregunta ajena al corpus cuente como
  evidencia).
- `top_k` es configurable por entorno (`RAG_TOP_K`, por defecto 4; el
  despliegue usa 3).

**Seguimientos conversacionales:** si la pregunta sola no encuentra
evidencia y existe un turno anterior, el sistema reintenta la búsqueda con
la pregunta reformulada de forma autónoma (ver sección 7) antes de
abstenerse. La clasificación de riesgo de seguridad (abuso, autolesión,
riesgo hacia el niño) depende únicamente del mensaje actual, nunca del
historial, para que una revelación pasada no bloquee ni "contamine" una
pregunta nueva no relacionada.

## 7. Generación

Reutiliza y refina los artefactos del Avance 1:

- **System Prompt** ([src/system_prompt.py](../src/system_prompt.py)):
  define el rol, la estructura TBRI de la respuesta (validación → lectura de
  conducta → estrategias citadas → límite de la guía), las reglas de cita y
  el contrato JSON de salida.
- **Few-shot** ([src/few_shot_examples.py](../src/few_shot_examples.py)):
  dos ejemplos completos (pregunta + evidencia + JSON esperado) que anclan
  el formato antes del turno real.
- **Delimitadores**: `src/prompt_builder.py` serializa pregunta, evidencia y
  (si existe) `contexto_previo` como un único objeto JSON en el rol `user`,
  en vez de interpolarlos en una cadena con comillas — la pregunta/evidencia
  nunca pueden escapar su rol de "dato".
- **Formato de salida**: `src/output_formatter.py` valida claves, tipos y
  límites de longitud del JSON devuelto por el modelo, y reintenta una vez
  (`INTENTOS_GENERACION`) indicando al modelo qué incumplió.

**Memoria conversacional en la generación:** cuando hay un turno anterior,
se construye `contexto_previo` (pregunta y resumen de la respuesta previa,
máx. 300 caracteres cada uno) y se adjunta solo al turno real, nunca a los
ejemplos few-shot. El system prompt indica explícitamente que
`contexto_previo` sirve únicamente para interpretar referencias ("eso", "el
segundo"), no como fuente de hechos citables — los hechos solo pueden venir
de la evidencia numerada de ese turno.

Si no hay `GROQ_API_KEY`, el sistema cae a un modo extractivo local: cita
textualmente las frases de los fragmentos recuperados que comparten al
menos dos señales de contenido con la pregunta (o, en seguimientos, con la
pregunta ya resuelta).

## 8. Evaluación con Ragas

### 8.1 Conjunto de evaluación

`eval_dataset.json`: 15 preguntas con `ground_truth` — 12 en dominio
(cubren los cinco documentos del corpus) y 3 fuera de dominio (satélites de
Marte, impuestos en Colombia, Tratado de Versalles) para medir control de
alucinaciones. Las métricas de Ragas se calculan solo sobre las 12 preguntas
en dominio: `context_recall` no es una medida válida cuando el
`ground_truth` dice explícitamente "la información no está en el corpus"; en
su lugar, para las 3 fuera de dominio se reporta la tasa de abstención
correcta (`eval_ragas.py`).

### 8.2 Resultados

<!-- RESULTADOS_RAGAS -->

### 8.3 Iteración de mejora

<!-- ITERACION_RAGAS -->

## 9. Interfaz y despliegue

Chat Flask (`main.py`, `templates/index.html`, `static/app.js`) con historial
real (sección 6-7), fuentes con documento/página/sección visibles por
respuesta, y abstención explícita cuando no hay evidencia. Despliegue
configurado en [render.yaml](../render.yaml) (Gunicorn, `GROQ_API_KEY` como
secret de Render, nunca en el repo).
