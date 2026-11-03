# Flujo completo del sistema RAG

## 1. Propósito y corpus

CrianzApp brinda orientación general sobre crianza positiva a cuidadores de
niños y niñas de 0 a 12 años en Colombia. El índice incorpora solo documentos
de `docs/base_conocimiento/` que tratan explícitamente de desarrollo, apego,
relación cuidador-niño, disciplina, corregulación y apoyo parental:

| Archivo | Pertinencia para el dominio |
|---|---|
| `02. (español) TBRI Conexion participante.pdf` | Material de conexión y relación adulto-niño. |
| `03. (español) TBRI Correccion participante.pdf` | Orientación sobre corrección de conductas y límites. |
| `04. (español) TBRI Empoderamiento participante.pdf` | Regulación, necesidades y preparación del niño. |
| `34. Gomez Muzzio.pdf` | Artículo sobre psicoterapia infantil, apego y sensibilidad parental. |
| `39.pdf` | Revisión sistemática sobre intervenciones digitales de apoyo parental. |

El archivo provisional `guia_crianza.md` fue retirado del corpus y está
excluido explícitamente por el cargador. El cargador mantiene soporte para
PDF, DOCX, TXT, Markdown y HTML (`.html`/`.htm`), incluidos los Markdown que
se generen como derivados de los PDF. Formatos no admitidos y la fuente
provisional se ignoran.

## 2. Pipeline

Pipeline durante el arranque:

1. Enumerar recursivamente archivos admitidos y extraer texto.
2. Añadir metadatos de procedencia y ubicación a cada documento extraído.
3. Crear fragmentos recursivos y embeddings; persistir documentos, vectores y
   metadatos en la colección `crianzapp_conocimiento` de Chroma.
4. Reutilizar el índice persistido mientras la huella de corpus y de
   configuración de chunking/embedding no cambie; reconstruirlo en otro caso.

Pipeline por turno:

1. Validar el JSON de la pregunta actual. El cliente puede enviar `history`
   por compatibilidad, pero el backend lo ignora; cada turno es stateless.
2. Recuperar evidencia usando exclusivamente el mensaje actual. Para un
   seguimiento, la persona debe repetir el tema relevante; no se arrastran
   preguntas anteriores ni se transmiten al proveedor.
3. Buscar similitud coseno en Chroma y reranquear los fragmentos con una
   combinación de similitud semántica y BM25. Aplicar el umbral de distancia
   máxima `0.65`, verificar soporte léxico y devolver hasta tres fragmentos.
4. Ante señales de abuso, violencia o autolesión, priorizar orientación de
   seguridad. Sin fragmentos aceptables, abstenerse explícitamente.
5. Con evidencia y `GROQ_API_KEY`, enviar mensajes por roles con consulta y
   evidencia serializadas como JSON, generar hasta 350 tokens y validar el
   contrato. Si el proveedor falla o la salida no valida, presentar extractos
   locales con un aviso; sin clave, no hay llamada externa.
6. Devolver respuesta, extractos y metadatos de citas a Flask; la interfaz
   conserva visualmente la conversación en la pestaña, sin enviar los turnos
   anteriores al servidor, y presenta las fuentes debajo de cada respuesta.

## 3. Decisiones técnicas

### Extracción y metadatos

- **PDF:** `pypdf` obtiene el texto página por página. Se guarda `page` desde 1.
- **Estado verificado del corpus actual:** los cinco PDF contienen texto
  seleccionable; las 107 páginas entregan texto con `pypdf` y no se detectaron
  caracteres de reemplazo en la extracción. No se requiere OCR para estos
  originales. La extracción conserva texto y página, pero tablas y parte del
  orden visual se representan como texto lineal, por lo que la estructura debe
  revisarse para los pasajes que dependan de tablas.
- **DOCX:** `python-docx` extrae párrafos, títulos y tablas; se conserva
  `section`.
- **HTML:** `HTMLParser` obtiene texto visible, excluye `head`, `script`,
  `style`, `noscript` y `svg`, y asocia el texto con el encabezado HTML
  precedente.
- **TXT y Markdown:** lectura UTF-8; Markdown segmenta por encabezados.
- Cada chunk recibe `source`, `filename`, `chunk_id` y `section` o `page`.
  Estos metadatos se usan para construir las citas que ve el usuario.
- Los PDFs escaneados sin capa de texto extraíble requieren OCR, que no está
  implementado.

### Chunking

Se fija `chunk_size=500` y `chunk_overlap=50` caracteres. Un fragmento de 500
caracteres mantiene pasajes cortos, fáciles de recuperar y citar, y evita
entregar demasiado contexto irrelevante al modelo. El solapamiento del 10 %
reduce la pérdida de una definición o recomendación que cruza la frontera.
`RecursiveCharacterTextSplitter` intenta separar por párrafo (`\n\n`), línea
(`\n`), espacio y, como último recurso, carácter; esto conserva límites
textuales más naturales que cortar a una longitud fija sin criterio.

No se convirtieron los PDF a Markdown: todos tienen capa de texto y `pypdf`
extrae las 107 páginas con metadatos de página. Una conversión no aporta una
mejora demostrada y podría aplanar tablas u orden visual; los originales se
mantienen como fuentes canónicas. Si una revisión posterior genera Markdown,
el cargador lo admite y lo identifica como documento derivado.

### Vectorización e índice

Chroma aplica explícitamente su `DefaultEmbeddingFunction`, cuyo modelo por
defecto es `sentence-transformers/all-MiniLM-L6-v2`. Se eligió por ser un
modelo compacto, local y sin costo por llamada ni credenciales para indexar y
consultar; esto facilita la demo y un modo extractivo privado. La colección
usa distancia coseno y persistencia local en `vectorstore/`. El índice registra
la huella de archivos, tamaño/solapamiento y modelo de embeddings; cambiar el
corpus o el chunking produce una reconstrucción.

**Limitación a considerar:** `all-MiniLM-L6-v2` no es un modelo especializado
multilingüe. Aunque el filtro léxico añade una señal en español, conviene
evaluar un embedding multilingüe como una iteración futura y comparar su
calidad y costo antes de adoptarlo. Las embeddings de Google usadas para
calcular métricas Ragas no son las embeddings del índice Chroma.

### Recuperación y abstención

La búsqueda consulta el índice completo para no perder pasajes pertinentes
que quedan fuera de los primeros resultados vectoriales. El orden final combina
la similitud coseno (`0.4`) con BM25 normalizado (`0.6`); los sinónimos
controlados se normalizan a un término común. Para el artículo en inglés sobre
intervenciones digitales se añade una consulta léxica breve en inglés cuando
la pregunta contiene al menos dos conceptos con traducción conocida. Se usa la
menor distancia entre la consulta original y la expansión; el filtro léxico
siempre usa la pregunta original.

Se conservan `top_k=3` y la distancia máxima `0.65`. Un fragmento que comparte
un solo término requiere además distancia `<=0.57` y BM25 `>=8.0`; esto evita
aceptar coincidencias aisladas como “tratado” en la pregunta sobre Versalles,
pero permite recuperar la rutina de sueño usando el término normalizado
“sueño/dormir”. Los fragmentos con líderes de puntos, típicos de índices,
reciben una penalización pequeña en el orden. Estos valores son heurísticos y
se verifican con regresiones, no son una calibración estadística.

### Prompt y generación

`prompt_builder.py` separa `system`, ejemplos `user/assistant` y la consulta
actual. Pregunta y evidencia se codifican como JSON, no se interpolan en
delimitadores textuales. Los ejemplos son breves, citan la evidencia de
entrada y no recomiendan acciones sin respaldo. El system prompt pide una
respuesta directa sin preguntas de seguimiento, de 1–3 pasos concretos.
Groq (`GROQ_MODEL`, predeterminado `openai/gpt-oss-120b`) redacta con
temperatura `0.2`, JSON mode y límite de 350 tokens; `output_formatter.py`
valida claves, longitudes, cantidad de pasos y ausencia de preguntas. Si falla
la generación, el modo extractivo usa la evidencia ya recuperada.

## 4. Consultas observadas y análisis

| Consulta | Comportamiento observado | Análisis |
|---|---|---|
| “Mi hijo hace rabietas cuando apago la televisión” | La respuesta documentada anteriormente provenía de `guia_crianza.md`, ya retirado. | Es evidencia del corpus anterior; no se considera validación del corpus actual de cinco PDF. |
| “¿Cuáles son las tres reglas para las relaciones utilizadas en el grupo de cuidado según TBRI?” | Se recupera evidencia de `03. (español) TBRI Correccion participante.pdf`, página 12. | El reranking posiciona los fragmentos de respuesta de esa página antes que el fragmento tipo índice. |
| “¿Cómo puedo ayudar a un niño a conciliar el sueño?” | La búsqueda híbrida devuelve el ejemplo de rutina para dormir de `04. (español) TBRI Empoderamiento participante.pdf`, página 20. | Cuatro paráfrasis de sueño recuperan la página 20 y excluyen los fragmentos de horarios que contienen alimentos/hidratación. |
| “¿Y qué puedo hacer después para calmarlo?” sin repetir el tema | El sistema se abstiene y no muestra fuentes. | Se evita adivinar el tema a partir del historial del cliente; la pregunta debe incluir el asunto (por ejemplo, “durante una rabieta”). |
| “¿Cuál es la velocidad orbital de satélites alrededor de Marte?” | El sistema se abstiene y no muestra fuentes. | La consulta OOD no hereda términos de crianza ni recibe citas irrelevantes. |

El historial se retiró del camino de recuperación porque la heurística de
seguimiento no puede distinguir de forma fiable una referencia ambigua y
alarga cada prompt. Las pruebas verifican que el historial de un tema sensible
no modifica una pregunta nueva y que un seguimiento ambiguo abstiene.

La regresión de recuperación incluye las 12 preguntas in-domain y las tres
preguntas OOD de `eval_dataset.json`, además de cuatro paráfrasis sobre sueño.
El conjunto actual recupera una ubicación pertinente para cada pregunta
in-domain; las cuatro paráfrasis de sueño incluyen la página 20 y no devuelven
pasajes de comida, y las tres consultas OOD devuelven cero fragmentos. Esto
valida la recuperación local, no una mejora de métricas Ragas ni la calidad
final de respuestas generadas por el modelo.

Páginas con evidencia entre los tres resultados, en el orden de las preguntas
in-domain de `eval_dataset.json`:

| Pregunta | Fuente y páginas recuperadas |
|---|---|
| 1–3 | Corrección: p. 12; p. 19; p. 27 |
| 4–6 | Empoderamiento: p. 8; p. 10; p. 16 |
| 7–8 | Conexión: p. 9 y 7; p. 17 |
| 9–10 | Gómez Muzzio: p. 5; p. 7 |
| 11–12 | `39.pdf`: p. 6, 2 y 7; p. 5 y 1 |

## 5. Evaluación con Ragas

`eval_dataset.json` tiene 15 casos (12 in-domain y 3 out-of-domain), con
`question` y `ground_truth`. El script recoge pregunta, contextos, respuesta,
referencia y modo. Calcula `faithfulness`, `answer_relevancy`,
`context_precision` y `context_recall` para los 12 casos in-domain. Para OOD
calcula aparte la tasa de abstención correcta: incluir una referencia del tipo
“no está en la base” en `context_recall` confundiría falta deliberada de
contexto con mala recuperación. La evaluación usa un juez Gemini
(`RAGAS_LLM_MODEL`) y embeddings Google (`RAGAS_EMBEDDING_MODEL`).

### Estado de resultados reproducibles

| Métrica | Antes | Después | Estado |
|---|---:|---:|---|
| faithfulness | N/D | N/D | No hay ejecución Ragas completa. |
| answer_relevancy | N/D | N/D | No hay ejecución Ragas completa. |
| context_precision | N/D | N/D | No hay ejecución Ragas completa. |
| context_recall | N/D | N/D | No hay ejecución Ragas completa. |
| Abstención OOD | 3/3 preguntas OOD del dataset, sin contexto recuperado | 3/3 preguntas OOD del conjunto vuelven a producir cero fragmentos en las regresiones | Prueba funcional, no puntuación Ragas. |

Las ejecuciones previas del evaluador terminaron con `504 Deadline Exceeded`
del servicio de Google; por tanto no existe una tabla numérica antes/después
ni se puede afirmar cuál métrica quedó más baja. El código exporta resultados
solo después de que Ragas evalúe todas las preguntas y lo documenta en
`ragas_results.json`. No se deben sustituir estos N/D por estimaciones.

### Iteración incorporada y protocolo para medirla

La prueba de conversación mostró que la heurística de historial no daba una
resolución fiable de seguimientos. El componente se actualizó a requests
stateless: una pregunta OOD no hereda contexto de crianza y un seguimiento
ambiguo abstiene en vez de adivinar. La integración con un juez Ragas y las
métricas antes/después siguen pendientes por el timeout externo.

Para producir la comparación cuantitativa cuando Google responda, ejecutar
desde la raíz, con Python 3.12.8 y `GOOGLE_API_KEY` en `.env`:

```bash
RAG_CHUNK_SIZE=500 RAG_CHUNK_OVERLAP=50 RAG_TOP_K=3 \
RAGAS_RESULTS_PATH=ragas_baseline.json ./.venv312/bin/python eval_ragas.py

RAG_CHUNK_SIZE=500 RAG_CHUNK_OVERLAP=50 RAG_TOP_K=4 \
RAGAS_RESULTS_PATH=ragas_topk4.json ./.venv312/bin/python eval_ragas.py
```

La segunda ejecución aumenta únicamente `top_k`; la huella del índice
reconstruye automáticamente si cambia el chunking. Comparar los cuatro
promedios in-domain y la tasa de abstención OOD. Adoptar el cambio solo si
mejora la precisión/context recall sin degradar fidelidad o abstención. Esta
iteración de ajuste está instrumentada, pero la comparación Ragas aún debe
ejecutarse para cerrar el requisito cuantitativo.

## 6. Interfaz y despliegue

La UI Flask mantiene la conversación solo para visualización local y envía a
`POST /chat` únicamente el mensaje actual; renderiza las fuentes por respuesta.
La prueba visual de este documento es local, no demuestra disponibilidad
pública.

Repositorio GitHub:
[Criss190/AsistenteCrianza](https://github.com/Criss190/AsistenteCrianza).
La URL pública debe ser la que Render muestre para el servicio desplegado. La
dirección `https://crianzapp.onrender.com` verificada durante esta revisión
respondió `404 Not Found`; se requiere confirmar/corregir el servicio antes de
presentarla como pública y capturar allí la interfaz.

Render carga secretos del panel del servicio. Para la demo conversacional,
configura `GROQ_API_KEY`; no es necesario subir `.env`. El blueprint persiste
el índice solo durante la vida del disco del servicio; en alojamiento
efímero, se reconstruye al arrancar.

## 7. Verificación del repositorio

La Fase 2 pasó las 20 pruebas de `unittest discover -s tests -v`. El índice
local limpio contiene 620 chunks de los cinco PDF: 96 de Conexión, 129 de
Corrección, 108 de Empoderamiento, 144 de Gómez Muzzio y 143 de `39.pdf`.
No contiene metadatos de `guia_crianza.md` ni registros huérfanos. El test de
evaluación usa respuestas simuladas y no equivale a ejecutar Ragas. No se llamó
a Groq ni a un juez externo; las métricas de calidad siguen pendientes.
