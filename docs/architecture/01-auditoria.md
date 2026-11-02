# 01. Auditoría técnica del repositorio

## 1. Alcance y método

Inspección estática inicial de archivos fuente, interfaz, configuración, despliegue, pruebas y documentos Markdown; el árbol estaba sin cambios previos a esa inspección. En esa etapa no se ejecutaron pruebas ni se accedió a servicios externos. **Actualización posterior (2 de noviembre de 2026):** se ejecutó `unittest` antes y después de corregir el flujo conversacional; se documentan resultados observados y cambios en las secciones siguientes. No se llamó a Groq/Google ni se midieron tokens/costo. Los hallazgos distinguen evidencia de inferencia y algunas descripciones iniciales se conservan explícitamente como comportamiento anterior.

Se leyeron: `main.py`, `src/*.py`, `templates/index.html`, `static/*`, `requirements.txt`, `.env.example`, `.gitignore`, `render.yaml`, `README.md`, `docs/flujo_completo_rag.md`, `docs/base_conocimiento/guia_crianza.md`, `eval_dataset.json`, `eval_ragas.py` y los archivos de `tests/`. Se inventariaron además PDFs, PNG y notebook, pero no se examinó su contenido. El detalle de límites está al final.

## 2. Árbol observado

```text
main.py                         Flask: rutas y creación del servicio RAG
src/
  rag_chat.py                    coordinación RAG, riesgo por patrones y Groq
  knowledge_base.py              loaders, chunking, Chroma y búsqueda
  prompt_builder.py              construcción de prompt
  system_prompt.py               reglas del modelo
  few_shot_examples.py           ejemplos de prompt
  output_formatter.py            contrato/validación JSON y funciones heredadas
templates/index.html             pantalla única de chat
static/app.js                    conversación cliente y fetch
static/styles.css                estilos responsive
 tests/                          Flask, conocimiento y evaluación
 docs/                           corpus, diseño RAG, entregables y capturas
 eval_dataset.json               15 ejemplos declarados
 eval_ragas.py                   evaluación Ragas
 requirements.txt                runtime y paquetes de evaluación juntos
 render.yaml                     blueprint Render
 .env.example / .gitignore       variables y exclusiones locales
```

No se observaron paquetes de configuración separados, dominio/aplicación/infraestructura, migraciones, repositorios de datos de usuarios, autenticación, scripts CI, lockfile, contenedor, política de retención ni módulo de administración. `venv/` está en el árbol local y se excluye por `.gitignore`; no debe incorporarse al repositorio.

## 3. Ciclo de vida, API y persistencia

### Hechos verificados

- [main.py](../../main.py#L12-L16) carga `.env`, crea Flask, limita el cuerpo a 16 KiB e instancia `ChatRAG` al importar el módulo. La carga del corpus/vectorstore sucede, por tanto, durante creación del servicio y puede afectar arranque, worker y despliegue.
- [main.py](../../main.py#L19-L33) expone `/`, `/api/health`, `/chat` y `/api/chat`. No hay autenticación, autorización ni identidad asociada a las solicitudes en estas rutas.
- [main.py](../../main.py#L35-L52) valida objeto JSON, mensaje no vacío y límite de 2.000 caracteres; valida que cada turno del historial use rol `user`/`assistant` y contenido texto. No valida la autoría de turnos, semántica ni esquema adicional.
- [main.py](../../main.py#L54-L69) captura excepciones generales, registra traceback y devuelve mensaje genérico; la respuesta normal incluye claves duplicadas en español e inglés, modo y aviso.
- [src/knowledge_base.py](../../src/knowledge_base.py#L234-L258) persiste un índice Chroma en `vectorstore/`; [src/knowledge_base.py](../../src/knowledge_base.py#L286-L322) reconstruye colección si cambia la huella. El índice contiene fragmentos/metadatos documentales, no entidades de usuario.
- El historial visual de la demo permanece en la pestaña y no se persiste. Desde la actualización de esta auditoría, la UI tampoco lo envía al backend; el campo legado `history` se acepta y valida, pero `ChatRAG` lo ignora.
- El contrato del endpoint, tal como hoy existe, no debe confundirse con una API estable de producto. Los alias en español/inglés y los dos paths son deuda de compatibilidad a resolver con versionado.

### Riesgos e inferencias

- Los turnos `assistant` los controla el cliente. Un usuario podría modificar el historial antes de enviarlo; el backend no comprueba que sean respuestas previamente producidas por el servidor. El historial llega al prompt, por lo que su integridad importa.
- `ChatRAG` se instancia como global de módulo. En workers múltiples habría una instancia por proceso; en despliegue efímero, Chroma debe poder reconstruirse y no constituye almacenamiento durable de estado operativo.
- No hay limitación de frecuencia/cupo visible en el código. Si el servicio está expuesto, esto puede permitir abuso de CPU o gasto de proveedor; es riesgo, no abuso constatado.

## 4. Chatbot, RAG, contenido e integraciones

### Hechos verificados

- [src/knowledge_base.py](../../src/knowledge_base.py#L21-L30) admite PDF, DOCX, TXT, Markdown y HTML; [src/knowledge_base.py](../../src/knowledge_base.py#L142-L200) implementa extracción de texto y metadatos, y [src/knowledge_base.py](../../src/knowledge_base.py#L220-L245) chunking de 500 caracteres con solapamiento de 50.
- Chroma usa función de embeddings predeterminada, persistencia coseno y filtro por distancia $=0.65 más intersección léxica, devolviendo hasta `top_k`: [src/knowledge_base.py](../../src/knowledge_base.py#L286-L322), [src/knowledge_base.py](../../src/knowledge_base.py#L339-L374). La constante de nombre de modelo se registra como metadata/huella; la concordancia entre etiqueta y embedding resuelto depende de la versión efectiva.
- `ChatRAG` recupera evidencia y evalúa señales de seguridad solo sobre el mensaje actual; no usa historial para retrieval o generación. La generación Groq es opcional, timeout 25s, un reintento, temperatura 0.2, tope de 350 tokens y JSON mode; cualquier fallo de generación cae a extractos locales con aviso.
- [src/prompt_builder.py](../../src/prompt_builder.py) separa roles, serializa consulta/evidencia como JSON y usa ejemplos cortos. Esto reduce ambigüedad, pero no constituye prueba de resistencia a prompt injection.
- [src/output_formatter.py](../../src/output_formatter.py) valida claves, tipos, longitud de resumen/estrategias, máximo de tres pasos y ausencia de preguntas de seguimiento; no comprueba soporte semántico de cada afirmación/cita.
- [docs/flujo_completo_rag.md](../flujo_completo_rag.md#L147-L170) registra métricas Ragas como N/D y reporta timeouts externos. No se presentan aquí scores inventados ni se reejecutó evaluación.
- El corpus local tiene tres documentos de participante TBRI, dos PDFs y una guía Markdown según el árbol; no se verificó su contenido/licencia/aprobación editorial.

### Hallazgos funcionales y de costo reproducidos

La suite se ejecutó antes de los cambios: **15 pruebas pasaron** con `unittest`; `pytest` no está instalado en el entorno configurado. No se midieron tokens ni latencia de Groq, por lo que las reducciones de costo descritas abajo son esperadas, no ahorros cuantificados.

1. **El historial del navegador contamina el turno y la solicitud externa.** La UI enviaba hasta ocho turnos; el backend usaba heurísticas para anteponer hasta dos preguntas anteriores a algunas consultas y enviaba el historial al prompt completo. Esto podía recuperar temas ajenos y elevaba tokens/costo por turno. El historial es manipulable por el cliente, no memoria verificada. Se elimina del request normal y se ignora en el backend por compatibilidad; cada turno queda stateless. Una pregunta de seguimiento ambigua ahora debe reformularse con el tema explícito o abstenerse, nunca inferirse silenciosamente.
2. **Formato y ejemplos se contradicen.** Los ejemplos originales eran largos, uno recomendaba que ceder ante una rabieta “enseña que la rabieta funciona” sin que la fuente lo respaldara; además, el ejemplo de seguridad era redundante porque ese caso se atiende antes del LLM. El prompt pedía de 2 a 4 estrategias y la salida no imponía máximo ni prohibía preguntas de seguimiento. Se sustituyeron por ejemplos breves con evidencia explícita; la respuesta se limita a 1–3 pasos y no puede acabar con preguntas.
3. **Un fallo de formato de Groq terminaba en HTTP 500.** JSON malformado, salida vacía o fallo de validación no entraban en el fallback que solo cubría errores de conexión/estado. Ahora una excepción en el límite de generación deja una respuesta extractiva con fuentes y aviso, en lugar de fallar la petición.
4. **El prompt no separaba roles ni estructuraba entradas.** Pregunta, historial y pasajes se interpolaban en una cadena con etiquetas y comillas, que no son una frontera de instrucciones. Se envían system/user/few-shot en roles diferenciados y los campos de consulta/evidencia se serializan como JSON. Esto mejora legibilidad y reduce ambigüedad, pero **no demuestra** inmunidad a prompt injection.
5. **El presupuesto de salida era innecesariamente alto para la forma solicitada.** Groq admitía 550 tokens por respuesta aunque el contrato pedía un resumen y 2–4 recomendaciones. Se limita a 350 tokens y se acorta la salida objetivo. No se modifica top-k ni el umbral 0.65 sin evaluación, porque son parámetros de recuperación no calibrados y un cambio ciego podría aumentar abstenciones o respuestas sin soporte.

**Calibración pendiente:** comparar modo local y Groq con el mismo conjunto versionado; registrar modelo, prompt/corpus, llamadas por consulta, tokens de entrada/salida, latencia, fallback, calidad de cita y abstención. No activar generación solo porque la clave exista en un despliegue de participantes: la autorización del proveedor y del tratamiento externo sigue siendo un gate independiente.

### Hallazgos de seguridad de IA

1. **Inyección potencial:** delimitadores XML/textuales no aíslan instrucciones. Preguntas, historial y documentos pueden incluir instrucciones hostiles. No se realizó una prueba de ataque.
2. **Señales heurísticas, no triage clínico:** regex sobre palabras clave no comprende contexto, negación, ironía o eufemismos. La regla puede tener falsos positivos y falsos negativos. Además se aplica después de la recuperación y puede leer términos de mensajes anteriores retenidos.
3. **Fallo de proveedor:** solo errores `APIConnectionError`/`APIStatusError` tienen fallback local visible; JSON malformado o errores de esquema derivan a excepción general y HTTP 500.
4. **Gobernanza de corpus ausente en runtime:** no se observa mecanismo de aprobación, fecha de vigencia, versión editorial, licencia, caducidad, rollback ni trazabilidad de quién publicó cada documento.
5. **Respuesta de riesgo estática:** usa texto fijo y números de contacto en [src/rag_chat.py](../../src/rag_chat.py#L20-L39). No se verificaron vigencia/cobertura, horarios, escalamiento institucional ni disponibilidad humana.

## 5. UI, experiencia, responsive y accesibilidad

### Hechos verificados

- [templates/index.html](../../templates/index.html#L2-L10) define idioma español, viewport, descripción y carga estáticos. Tiene `<main>`, etiqueta para textarea y región de conversación `aria-live="polite"`: [templates/index.html](../../templates/index.html#L47-L62), [templates/index.html](../../templates/index.html#L80-L88).
- [static/app.js](../../static/app.js#L14-L22) y [static/app.js](../../static/app.js#L73-L106) renderizan contenido con `textContent`, reduciendo riesgo de XSS por interpolación HTML.
- [static/styles.css](../../static/styles.css#L100-L124) define breakpoints móvil y oculta sidebar bajo 760 px; por ello también oculta allí la nota de privacidad y acceso al ICBF definidos en [templates/index.html](../../templates/index.html#L40-L43).
- Hay indicador de carga, contador, sugerencias, fuentes y modo de respuesta. No hay pantalla de error recuperable diferenciada: errores HTTP/red se traducen a `no_evidence` en [static/app.js](../../static/app.js#L132-L150), pudiendo confundir indisponibilidad con abstención.
- No se observó configuración `prefers-reduced-motion`; los indicadores animados se definen en [static/styles.css](../../static/styles.css#L84-L98). El foco del textarea elimina outline y se apoya en `:focus-within`.

### Evaluación

El diseño actual es una buena base visual de demostrador, no prueba de usabilidad o conformidad. Deben probarse teclado, lector de pantalla, zoom, contraste medido, mensajes largos, estados de error, interacción con teclado virtual y tamaños pequeños. La propuesta debe mantener visible el aviso de privacidad y la vía de ayuda en móvil. WCAG 2.2 AA se usa como objetivo de aceptación futuro; no se declara cumplimiento actual.

## 6. Seguridad, privacidad y configuración

- `.env` y `vectorstore/` aparecen excluidos por [\.gitignore](../../.gitignore#L1-L14), y [\.env.example](../../.env.example#L1-L15) contiene nombres/valores vacíos, sin secretos reales observados.
- Al habilitar Groq se envían la pregunta actual y fragmentos recuperados, no el historial. En una plataforma de investigación esto exige decisión explícita, análisis contractual/de transferencia, minimización y aviso/consentimiento aplicable; el usuario no debe aportar narrativas identificables.
- No se observaron sesiones, cuentas, roles, controles de acceso, consentimiento, DSAR/solicitudes de titulares, cifrado de datos de usuario, política de borrado o registros de auditoría funcional.
- El log de excepción puede incluir trazas técnicas; no se observó logging del cuerpo de mensaje en la ruta, pero no se inspeccionó la configuración del proveedor de hosting ni telemetría de dependencias.
- El health endpoint declara estado, número de chunks y configuración de LLM, pero no secretos: [src/rag_chat.py](../../src/rag_chat.py#L74-L81).

## 7. Dependencias, pruebas y despliegue

- [requirements.txt](../../requirements.txt#L1-L12) agrupa Flask, RAG, Groq, Gunicorn y evaluación. Hay rangos amplios y no se observó lockfile. `eval_ragas.py` importa `pandas`; no aparece como dependencia directa en ese archivo.
- [render.yaml](../../render.yaml#L1-L13) usa plan gratuito, Gunicorn de un worker/timeout 120, health check y variables de Groq; no declara disco persistente. El README advierte sobre almacenamiento efímero y URL pública 404 reportada: [README.md](../../README.md#L126-L137). Estado actual externo pendiente.
- Los tests visibles cubren endpoints básicos, validaciones, RAG, loaders y evaluación: [tests/test_app.py](../../tests/test_app.py#L15-L136), [tests/test_knowledge_base.py](../../tests/test_knowledge_base.py#L16-L67), [tests/test_evaluation.py](../../tests/test_evaluation.py#L18-L112). La documentación menciona 12 pruebas en una sección, pero en el código se observan 15 métodos `test_`; **no se ejecutaron**, así que no se afirma que pasen.
- No se encontraron pruebas de autorización/roles, persistencia, concurrencia, seguridad, retención, consentimientos, prompt injection, disponibilidad del modelo, respuesta JSON malformada, responsive automatizado o accesibilidad.
- Ragas se evalúa con dependencia de Google/Gemini y dataset pequeño (12 consultas en dominio y 3 OOD en [eval_dataset.json](../../eval_dataset.json)); sirve como punto de partida experimental, no como validación estadística o garantía clínica.

## 8. Registro de hallazgos priorizados

Esfuerzo en persona-semanas (PS) aproximado para implementación y verificación; no incluye revisión institucional. Severidad: crítica/alta/media/baja. Prioridad: P0 antes de piloto, P1 MVP, P2 evolución, P3 opcional. **Bloquea producción** significa bloqueo de piloto con datos de participantes, no que impida desplegar una demo sintética.

| ID | Hallazgo/evidencia | Acción/clasificación | Sev. / prioridad | Impacto y esfuerzo | Dependencias | Bloquea piloto |
|---|---|---|---|---|---|---|
| A-01 | Flask tiene API pública sin identidad/roles observables ([main.py](../../main.py#L19-L33)). | Crear identidad, autorización por objeto/alcance y tests deny-by-default. | Crítica / P0 | Exposición de datos; 3–5 PS. | Definición de roles, IdP/secretos, diseño de datos. | Sí |
| A-02 | No hay persistencia de usuario, consentimiento ni operación de estudio; solo Chroma documental. | Crear módulos y esquema relacional, consentimiento versionado, segregación. | Crítica / P0 | Validez y protección de participantes; 4–7 PS. | Protocolo, aprobación ética/jurídica, retención. | Sí |
| A-03 | Pregunta actual/pasajes van a Groq si hay clave configurada. | Mantener modo local por defecto en datos reales y habilitar proveedor solo tras evaluación contractual/de transferencia y aprobación. | Alta / P0 | Divulgación/transferencia; 2–4 PS más gestión institucional. | Evaluación del tercero, bases legales y consentimiento. | Sí |
| A-04 | Respuesta humana/urgencia no tiene SLA/horarios verificados; regex no clasifica contexto. | Refactorizar hacia guiones aprobados, señal revisable y protocolo operativo; no diagnóstico. | Crítica / P0 | Seguridad de participantes; 3–5 PS + validación profesional. | responsables, cobertura, mensajes/alternativas aprobadas. | Sí |
| A-05 | Pregunta y documentos recuperados siguen siendo datos no confiables aunque ahora viajen en roles/campos estructurados. | Conservar corpus curado, aplicar filtro de salida y red-team; no tratar la estructura como frontera de seguridad. | Alta / P0 | Inyección y orientación fuera de corpus; 2–4 PS. | Diseño IA responsable y pruebas adversarias. | Sí para IA generativa; no para FAQ extractiva local. |
| A-06 | No hay administración de corpus, aprobación/versión ni rollback. | Crear flujo editorial versionado. | Alta / P0 | Contenido erróneo o desactualizado; 2–3 PS. | Roles editor/validador, fuentes licenciadas. | Sí |
| A-07 | Chroma local puede ser efímero y se inicializa durante import. | Conservar concepto; refactorizar indexación fuera del arranque y externalizar o reconstruir artefacto reproducible. | Alta / P1 | Disponibilidad/cold-start; 1–3 PS. | Despliegue, persistencia y presupuesto. | Sí si el índice no se garantiza disponible; no para demo local. |
| A-08 | Excepciones Groq no cubren JSON/schema; UI confunde error de red con falta de evidencia ([src/rag_chat.py](../../src/rag_chat.py#L110-L128), [static/app.js](../../static/app.js#L132-L150)). | Refactorizar estados de error, fallback controlado y telemetría sin texto sensible. | Alta / P1 | UX y resiliencia; 1–2 PS. | Contrato API, monitorización. | Sí para piloto si no hay alternativa segura. |
| A-09 | Evaluación Ragas incompleta/documentada N/D; corpus/umbral no calibrados ([docs/flujo_completo_rag.md](../flujo_completo_rag.md#L147-L170)). | Conservar harness tras fijar dataset, evaluación humana y abstención calibrada. | Alta / P0 | Riesgo de respuesta no respaldada; 2–4 PS. | Corpus aprobado, expertos revisores, conjunto de prueba. | Sí para liberar FAQ generativa. |
| A-10 | Breakpoint es responsive pero oculta privacidad/ayuda; no WCAG validada. | Conservar UI, corregir y probar. | Media / P1 | Comprensión y acceso; 1–2 PS. | Diseño y pruebas con usuarios. | Sí para lanzamiento público; no para demo local. |
| A-11 | Dependencias de runtime/evaluación juntas, rangos sin lockfile; `pandas` indirecto/no declarado. | Refactorizar extras/lock reproducible y cadena de suministro. | Media / P1 | reproducibilidad/supply chain; 1–2 PS. | CI, Python soportado. | Sí antes de despliegue mantenido. |
| A-12 | `output_formatter.py` describe que no hay LLM pese a integración real, conserva rutas simuladas. | Corregir comentarios y retirar rutas obsoletas solo tras búsqueda de referencias/pruebas. | Baja / P2 | Confusión de mantenimiento; 0.5 PS. | Confirmar referencias. | No |
| A-13 | Endpoint devuelve alias bilingües y 2 paths. | Refactorizar bajo `/api/v1`, mantener adaptador temporal documentado si hay cliente externo. | Media / P2 | Compatibilidad futura; 0.5–1 PS. | Inventario consumidores. | No |
| A-14 | No existen módulos/canales de notificaciones ni foro. | Crear solo si se aprueba, con consentimiento/preferencias y moderación. | Media / P2–P3 | Retención/seguridad operacional; 2–5 PS por canal/foro. | Viabilidad, operadores, privacidad. | No para MVP |
| A-15 | Avisos ICBF/123 y respuesta de riesgo no validados en este estudio. | Conservar solo tras validación profesional/legal/operativa y prueba de ubicación/actualización. | Crítica / P0 | Consecuencia grave si dato desactualizado. | Fuente oficial y responsable de revisión. | Sí |

## 9. Decisión sobre componentes existentes

| Componente | Clasificación | Qué se conserva / cambia |
|---|---|---|
| Flask y ruta de UI | **Conservar después de corregir** | Mantener como backend inicial. Añadir factory, configuración por entorno, blueprints y límites claros; no afirmar que el código actual es modular. |
| Plantilla HTML, CSS y JS | **Conservar después de corregir** | Reutilizar UI y diseño; accesibilidad, responsive móvil, estados de error, login y vistas nuevas requieren cambios. No migrar por defecto a SPA. |
| `ChatRAG` | **Refactorizar** | Separar retrieval, servicio FAQ, política de riesgo, proveedor LLM y repositorios; cubrir fallos. |
| Loaders/Chroma | **Conservar después de corregir** | Aprovechar extracción y citas. Añadir corpus aprobado/versionado, pruebas de parser, reproducibilidad, calibración, licencias y estrategia de persistencia. |
| Prompt/few-shot | **Conservar después de corregir** | Versionar y validar con profesionales; estructurar instrucciones/datos; few-shot sujeto a evaluación. |
| Respuesta de riesgo por regex | **Reemplazar** | No usar regex como triage ni asignar diagnósticos. Usar guiones seguros, detección de señales limitada y revisable, humano y alternativas; salida no generativa. |
| `output_formatter.py` | **Refactorizar** | Mantener validación del contrato si aporta; eliminar duplicación/deuda solo con pruebas. |
| Chroma persistente del prototipo | **Conservar después de corregir** | Es store de corpus, no DB de participantes; indexar en pipeline, conservar version metadata y garantizar despliegue reproducible. |
| Evaluación Ragas y dataset | **Conservar después de corregir** | Separar deps, aumentar/curar conjunto, incluir evaluación experta/ataques y no confundir score con seguridad clínica. |
| Tests existentes | **Conservar** | Extender; ejecutar y registrar baseline antes de cambios. |
| Render plan gratuito actual | **Reemplazar para producción** | Decidir alojamiento institucional con disco/DB/backups, secretos y acuerdos. Render puede seguir para demo sintética si se acepta limitación. |
| `venv/` del workspace | **Eliminar del versionado, si estuviera versionado** | En estado observado está local e ignorado; no borrar ambiente personal. |
| React/TypeScript | **No adoptar en MVP** | Solo ADR futuro si interacción SPA, offline, estados complejos o equipo justifican costo. |
| Conversaciones completas | **No crear por defecto** | No persistir ni enviar externamente; si protocolo lo exige, aprobación expresa, minimización, cifrado y acceso separado. |

## 10. Comparación: prototipo y objetivo

| Área | Prototipo observado | Solución objetivo |
|---|---|---|
| Actor/identidad | Visitante anónimo en una pantalla. | Participante con acceso seguro y rol/estudio asociado. |
| Datos | Historial temporal de pestaña; índice documental local. | Relacional para cuentas/consentimientos/actividades; claves de estudio separadas de identidad. |
| RAG | Corpus de archivos en carpeta, búsqueda heurística, Groq opcional. | Corpus cerrado aprobado y versionado, recuperación medible, abstención, proveedor opt-in/validado. |
| Riesgo | Regex y respuesta fija. | Guía inmediata preaprobada + señal revisable + escalamiento operativo. |
| Funcionalidad programa | Chat FAQ. | Contenido, prácticas, check-ins, progreso, comunicación, acompañamiento humano. |
| Administración | Sin panel observado. | Roles separados; agregados para técnico; profesional asignado; investigador codificado. |
| Gobernanza | No se ve aprobación de contenido/consentimiento. | Auditoría, versionado, consentimiento, derechos, retención y responsables. |
| Pruebas | Cobertura de prototipo y dataset reducido. | Matriz de pruebas; auth deny tests, seguridad, accesibilidad, RAG/humano y recuperación. |
| Despliegue | Render plan free, almacenamiento sin persistencia declarada. | Infraestructura que respalda datos reales, alta disponibilidad proporcional, RPO/RTO aprobados. |

## 11. Alcance y limitaciones de la inspección

No se leyeron los cinco PDF del corpus ni `docs/entrega_avance2.pdf`; no se revisaron visualmente las capturas PNG. Del notebook `docs/base_conocimiento/flujo_rag_groq.ipynb` solo se conoció que existe, sin leer celdas. No se inspeccionó `.git/`, dependencias instaladas, logs de hosting, consola de Render, políticas de Groq/Google/Render ni configuración DNS. No se validó que las líneas 141/123 sigan vigentes para el contexto operativo. No se hizo evaluación de datos personales con usuarios ni verificación de licencias/autorizaciones del corpus. La referencia legal de Colombia se trata como marco para revisión institucional, no concepto jurídico.

