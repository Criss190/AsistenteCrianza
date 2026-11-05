# Flujo completo del sistema RAG — CrianzApp

Este documento recoge, en un solo lugar, cada decisión técnica del pipeline
RAG de extremo a extremo (Avance 2) y los resultados de su evaluación con
Ragas. El código referenciado vive en `src/` y `scripts_ragas/eval_ragas.py`; el README
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

**Parámetros adoptados: 900 caracteres / 120 de solapamiento**
(`TAMANO_FRAGMENTO`/`SOLAPAMIENTO_FRAGMENTO` en
[src/knowledge_base.py](../src/knowledge_base.py)). Render no sobreescribe
`RAG_CHUNK_SIZE`/`RAG_CHUNK_OVERLAP`, así que el despliegue usa estos valores
por defecto; `.env` los fija explícitamente para que el entorno local
coincida. La sección 8 documenta que se probó primero 500/50 (chunks más
pequeños, centrados en una sola idea) y se adoptó 900/120 tras comparar
métricas reales de Ragas: el recuperador encontraba evidencia incompleta
porque algunas respuestas (p. ej. las "tres modalidades de psicoterapia" de
Gómez Muzzio) quedan repartidas entre fragmentos consecutivos a 500
caracteres, y chunks más grandes con más solapamiento las mantienen juntas.

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
- `top_k` es configurable por entorno (`RAG_TOP_K`); el valor adoptado y
  usado en despliegue es 4 (ver sección 8).

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

`scripts_ragas/questions/eval_dataset.json`: 15 preguntas con `ground_truth` — 12 en dominio
(cubren los cinco documentos del corpus) y 3 fuera de dominio (satélites de
Marte, impuestos en Colombia, Tratado de Versalles) para medir control de
alucinaciones. Las métricas de Ragas se calculan solo sobre las 12 preguntas
en dominio: `context_recall` no es una medida válida cuando el
`ground_truth` dice explícitamente "la información no está en el corpus"; en
su lugar, para las 3 fuera de dominio se reporta la tasa de abstención
correcta (`scripts_ragas/eval_ragas.py`).

### 8.2 Resultados — configuración exploratoria inicial (chunk 500/50, top_k=3)

Ejecutado con generación real de Groq (modelo `openai/gpt-oss-120b`) y juez
Ragas `gemini-3.5-flash-lite` (resultado completo en
[`ragas_baseline.json`](../scripts_ragas/results/ragas_baseline.json)):

| Métrica | Valor |
|---|---|
| faithfulness | 0.555 |
| answer_relevancy | 0.693 |
| context_precision | 0.417 |
| context_recall | 0.333 |

Control de alucinaciones: **3/3 (100%)** de las preguntas fuera de dominio
(satélites de Marte, impuestos en Colombia, Tratado de Versalles) se
abstuvieron correctamente, sin inventar una respuesta.

**Análisis — la métrica más baja es `context_recall` (0.33), seguida de
`context_precision` (0.42).** Ambas son de **recuperación**, no de
generación: en varias preguntas (p. ej. *"¿Qué conductas presentan los
bebés con un estilo de apego evitativo según Bowlby/TBRI?"*,
*"¿Qué tres modalidades de psicoterapia... Gómez Muzzio?"*) `context_precision`
y `context_recall` caen a 0.0 porque el fragmento con la respuesta exacta no
quedó entre los `top_k=3` recuperados, aunque Groq igual generó una
respuesta razonable apoyándose parcialmente en conocimiento general — lo que
también explica por qué `faithfulness` (0.56) es mediocre en esas mismas
filas: el modelo no tenía la evidencia correcta para anclar la respuesta.
`answer_relevancy` (0.69) es la más sana: las respuestas sí contestan lo que
se pregunta, el problema es que no siempre están respaldadas por el
fragmento correcto.

**Causa atribuida:** chunking/recuperación, no el prompt de generación. Con
chunks de 500 caracteres algunas respuestas completas (como los "tres
modalidades de psicoterapia") quedan repartidas entre dos fragmentos
consecutivos, y `top_k=3` a veces no alcanza a traer ambos. La mejora
candidata más directa es subir `top_k` (sección 8.3); si no fuera
suficiente, el siguiente paso sería revisar el solapamiento o el criterio de
corte para esos documentos académicos (que tienen prosa más larga que los
documentos TBRI).

### 8.3 Iteración de mejora — chunk 900/120, top_k=4 (configuración adoptada)

A partir del diagnóstico de 8.2 (recuperación incompleta), se cambiaron dos
parámetros relacionados — tamaño/solapamiento de chunk y `top_k` — y se
volvió a correr la evaluación completa (resultado en
[`ragas_900_120_4.json`](../scripts_ragas/results/ragas_900_120_4.json)):

| Métrica | Antes (500/50, top_k=3) | Después (900/120, top_k=4) | Δ |
|---|---|---|---|
| faithfulness | 0.555 | 0.540 | −0.015 |
| answer_relevancy | 0.693 | 0.614 | −0.079 |
| context_precision | 0.417 | 0.569 | **+0.153** |
| context_recall | 0.333 | 0.409 | **+0.076** |
| Abstención fuera de dominio | 3/3 (100%) | 3/3 (100%) | sin cambio |

**Lectura del resultado — mejora real pero con un costo, no una victoria
limpia.** Chunks más grandes con más solapamiento sí ayudaron al objetivo
buscado: `context_precision` y `context_recall` suben, porque fragmentos más
grandes capturan respuestas completas que antes quedaban cortadas (p. ej. la
pregunta de "apego evitativo" pasó de `context_recall=0.0` a tener evidencia
relevante en varias filas). Pero `answer_relevancy` y `faithfulness` bajan
un poco: fragmentos más grandes también traen más texto no relacionado con
la pregunta puntual, lo que le da a Groq más oportunidad de desviarse del
tema exacto o de mezclar ideas de la misma sección. El caso más claro es la
fila de "tres modalidades de psicoterapia" (Gómez Muzzio): en ambas
configuraciones el recuperador sigue sin traer el fragmento correcto
(`context_precision=0`), por lo que ese fallo concreto no se debe al tamaño
de chunk sino a que ese documento tiene prosa densa y poco repetitiva —
candidato a una tercera iteración enfocada en ese documento específico
(fragmentos aún más pequeños solo para los PDF académicos, o un chunking por
oración en vez de por tamaño fijo).

**Decisión:** se adoptó 900/120/top_k=4 porque el objetivo prioritario de
esta iteración era el cuello de botella identificado en 8.2 (recuperación,
no generación), y ambas métricas de recuperación mejoran de forma
consistente sin afectar el control de alucinaciones (la abstención fuera de
dominio se mantiene en 100%). La caída en `answer_relevancy`/`faithfulness`
queda documentada como mejora pendiente para una siguiente iteración sobre
el prompt o el chunking específico de los artículos académicos.

## 9. Interfaz y despliegue

Chat Flask (`main.py`, `templates/index.html`, `static/app.js`) con historial
real (sección 6-7), fuentes con documento/página/sección visibles por
respuesta, y abstención explícita cuando no hay evidencia. Despliegue
configurado en [render.yaml](../render.yaml) (Gunicorn, `GROQ_API_KEY` como
secret de Render, nunca en el repo).
