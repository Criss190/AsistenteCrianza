# CrianzApp — Asistente de Crianza Positiva y Responsable

Proyecto académico (Desarrollo de Aplicaciones con IA) que aplica técnicas
de **Prompt Engineering** para diseñar un asistente de psicología enfocado
en **crianza positiva y responsable**.

> **Funcionamiento local:** el proyecto carga una base de conocimiento en
> archivos Markdown, recupera fragmentos relevantes y genera una respuesta
> determinista. **No se conecta a ningún modelo LLM ni envía datos fuera del
> equipo.**

## 1. ¿Qué hace el asistente?

CrianzApp carga la guía ubicada en `docs/base_conocimiento/`, busca
fragmentos relacionados con la consulta y responde usando únicamente esa
evidencia local. También puede ejecutar tareas sencillas como recuperar
orientaciones, resumir el contexto encontrado y señalar cuándo derivar a
ayuda profesional.

## 2. Técnicas de Prompt Engineering aplicadas

### 2.1 Diseño de Prompts (System Prompt)
En [`src/system_prompt.py`](src/system_prompt.py) se define el
comportamiento base del asistente: rol, público objetivo, tono, alcance
(qué puede y qué no puede responder) y el formato de salida obligatorio
(JSON con claves fijas).

### 2.2 Few-Shot Prompting
En [`src/few_shot_examples.py`](src/few_shot_examples.py) se incluyen
ejemplos de pares *pregunta → respuesta ideal* que se insertan en el
prompt para que el modelo imite el formato JSON esperado, incluyendo un
caso cotidiano y un caso de alerta (derivación a profesional).

### 2.3 Estrategias de Delimitadores
En [`src/prompt_builder.py`](src/prompt_builder.py) se combinan dos
estrategias de delimitación para separar instrucciones de datos:

- **Triple comillas** (`"""..."""`) alrededor del contexto y la pregunta
  del usuario, para que el modelo no confunda el texto del usuario con
  instrucciones del sistema.
- **XML tags** (`<rol>`, `<alcance>`, `<formato_salida>`,
  `<ejemplos_few_shot>`, `<contexto>`, `<pregunta_usuario>`, etc.) para
  estructurar y etiquetar cada sección del prompt.

## 3. Formato de salida

Toda respuesta del asistente debe cumplir este contrato (ver
[`src/output_formatter.py`](src/output_formatter.py)):

```json
{
  "resumen_breve": "string",
  "estrategias": ["string", "..."],
  "senal_alerta": "string o null",
  "derivar_a_profesional": true
}
```

`output_formatter.py` incluye:
- `validar_formato()`: valida que una respuesta cumpla exactamente ese
  esquema (claves y tipos).
- `generar_respuesta_local()`: crea la respuesta a partir de fragmentos
  recuperados, sin inferencia remota.

`src/knowledge_base.py` incluye:
- `BaseConocimientoLocal.cargar()`: lee archivos `.md` y `.txt` desde una
  carpeta local.
- `BaseConocimientoLocal.buscar()`: recupera fragmentos por coincidencia
  de términos, sin servicios externos ni dependencias adicionales.

## 4. Estructura del proyecto

```
crianza-positiva-chatbot/
├── main.py                    # Demo: arma el prompt y muestra la salida local
├── requirements.txt
├── README.md
├── docs/
│   ├── ejecucion_prompt.pdf   # Explicación de la ejecución (evidencias)
│   └── base_conocimiento/
│       └── guia_crianza.md    # Fuente local consultada por el asistente
└── src/
    ├── system_prompt.py       # Diseño de prompts (System Prompt)
    ├── few_shot_examples.py   # Ejemplos few-shot
    ├── prompt_builder.py      # Ensamblaje del prompt + delimitadores
    ├── output_formatter.py    # Contrato de salida + respuesta local
    └── knowledge_base.py      # Carga y recuperación local de documentos
```

## 5. Relación con lo visto en clase "en qué nos basamos para hacer este código"

Este proyecto retoma la lógica de carga y estructuración de contexto
usada en los ejemplos de clase (`1_a_csv_loader.py`, `2_pdf_loader.py`,
`6_retriever.py`, donde un `ChatPromptTemplate` combina *contexto +
pregunta* para consultar un LLM sobre una base de conocimiento). Aquí se
aplica esa misma idea de plantilla de prompt, pero el "contexto" es la
situación de crianza que describe el usuario, y la conexión a un LLM
real queda fuera del alcance de este entregable.

## 7. Privacidad y límites técnicos

La búsqueda usa coincidencia léxica local; no es un modelo generativo ni
un sistema RAG semántico. Para ampliar la base, agrega archivos `.md` o
`.txt` dentro de `docs/base_conocimiento/`. Ningún archivo se sube a
Internet y `requirements.txt` no requiere paquetes externos.

## 8. Límites éticos

CrianzApp **no reemplaza** la atención de un psicólogo, psiquiatra
infantil o autoridad de protección de menores. Ante cualquier indicio de
maltrato, abuso o riesgo, el asistente está diseñado para derivar a
ayuda profesional (en Colombia: ICBF, línea 141) en vez de dar
recomendaciones generales.
