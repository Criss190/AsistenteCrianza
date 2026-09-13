# CrianzApp — Asistente de Crianza Positiva y Responsable

Proyecto académico (Desarrollo de Aplicaciones con IA) que aplica técnicas
de **Prompt Engineering** para diseñar un asistente de psicología enfocado
en **crianza positiva y responsable**.

> **Alcance de este entregable:** diseño de prompts, few-shot prompting y
> estrategias de delimitadores. **No se conecta a ningún modelo LLM**: el
> proyecto construye y muestra el prompt tal como quedaría estructurado,
> y simula localmente la respuesta en el formato de salida definido.

## 1. ¿Qué hace el asistente?

CrianzApp está pensado para acompañar a madres, padres y cuidadores con
dudas frecuentes de crianza (rabietas, límites, comunicación, rutinas,
manejo emocional), y para detectar cuándo una consulta debe derivarse a
un profesional (por ejemplo, ante señales de maltrato o riesgo).

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
- `generar_respuesta_simulada()`: como el proyecto no llama a ningún
  LLM, esta función simula la salida (con reglas simples por palabras
  clave) para poder mostrar el flujo completo entrada → prompt → salida.

## 4. Estructura del proyecto

```
crianza-positiva-chatbot/
├── main.py                    # Demo: arma el prompt y muestra la salida simulada
├── requirements.txt
├── README.md
├── docs/
│   └── ejecucion_prompt.pdf   # Explicación de la ejecución (evidencias)
└── src/
    ├── system_prompt.py       # Diseño de prompts (System Prompt)
    ├── few_shot_examples.py   # Ejemplos few-shot
    ├── prompt_builder.py      # Ensamblaje del prompt + delimitadores
    └── output_formatter.py    # Contrato de salida + validación + simulación
```

## 5. Cómo ejecutarlo (entorno virtual)

```bash
# 1. Crear el entorno virtual
python3 -m venv venv

# 2. Activarlo
source venv/bin/activate        # Linux / Mac
venv\Scripts\activate           # Windows

# 3. Instalar dependencias (no hay dependencias externas por ahora)
pip install -r requirements.txt

# 4. Ejecutar la demo
python3 main.py
```

La salida en consola muestra, para dos casos de ejemplo:
1. El **prompt completo** que se enviaría a un LLM (system prompt +
   ejemplos few-shot + contexto delimitado).
2. La **respuesta simulada** en formato JSON, ya validada contra el
   esquema definido.

## 6. Relación con lo visto en clase

Este proyecto retoma la lógica de carga y estructuración de contexto
usada en los ejemplos de clase (`1_a_csv_loader.py`, `2_pdf_loader.py`,
`6_retriever.py`, donde un `ChatPromptTemplate` combina *contexto +
pregunta* para consultar un LLM sobre una base de conocimiento). Aquí se
aplica esa misma idea de plantilla de prompt, pero el "contexto" es la
situación de crianza que describe el usuario, y la conexión a un LLM
real queda fuera del alcance de este entregable.

## 7. Próximos pasos (fuera de alcance actual)

- Conectar `build_prompt()` a un LLM real (por ejemplo, siguiendo el
  patrón de `6_retriever.py` con `langchain` + un proveedor de LLM).
- Indexar una base de conocimiento (guías de crianza, artículos de
  psicología) con `RecursiveCharacterTextSplitter` + `Chroma`, para dar
  contexto verificado al modelo (RAG), preservando la privacidad al
  correr todo localmente.

## 8. Límites éticos

CrianzApp **no reemplaza** la atención de un psicólogo, psiquiatra
infantil o autoridad de protección de menores. Ante cualquier indicio de
maltrato, abuso o riesgo, el asistente está diseñado para derivar a
ayuda profesional (en Colombia: ICBF, línea 141) en vez de dar
recomendaciones generales.
