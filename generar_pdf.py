# -*- coding: utf-8 -*-
"""
generar_pdf.py
----------------
Genera docs/ejecucion_prompt.pdf: la explicación (texto) de cómo se
diseñó y ejecutó el prompt de CrianzApp. Las capturas de pantalla de la
ejecución las agrega el estudiante después, en los espacios señalados.
"""

from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import cm
from reportlab.lib import colors
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, ListFlowable, ListItem,
    Table, TableStyle, PageBreak
)

OUT_PATH = "ejecucion_prompt.pdf"

styles = getSampleStyleSheet()
styles.add(ParagraphStyle(
    name="TituloPortada", parent=styles["Title"], fontSize=22, spaceAfter=6
))
styles.add(ParagraphStyle(
    name="Subtitulo", parent=styles["Heading2"], textColor=colors.HexColor("#2E4057"),
    spaceBefore=14, spaceAfter=8
))
styles.add(ParagraphStyle(
    name="SubSub", parent=styles["Heading3"], textColor=colors.HexColor("#4A6572"),
    spaceBefore=10, spaceAfter=6
))
styles.add(ParagraphStyle(
    name="Cuerpo", parent=styles["Normal"], fontSize=10.5, leading=15,
    spaceAfter=8, alignment=4  # justify
))
styles.add(ParagraphStyle(
    name="Codigo", parent=styles["Code"], fontSize=8.3, leading=10.5,
    backColor=colors.HexColor("#F4F4F4"), borderPadding=6,
    fontName="Courier"
))
styles.add(ParagraphStyle(
    name="Nota", parent=styles["Normal"], fontSize=9.5, leading=13,
    textColor=colors.HexColor("#7A5C00"), backColor=colors.HexColor("#FFF6DA"),
    borderPadding=8, spaceAfter=10
))

story = []

# ------------------------------------------------------------------ #
# Portada
# ------------------------------------------------------------------ #
story.append(Spacer(1, 4 * cm))
story.append(Paragraph("CrianzApp", styles["TituloPortada"]))
story.append(Paragraph(
    "Asistente de Psicología para Crianza Positiva y Responsable",
    styles["Heading2"]
))
story.append(Spacer(1, 0.6 * cm))
story.append(Paragraph(
    "Explicación de la ejecución del prompt — Diseño de Prompts, "
    "Few-Shot Prompting y Estrategias de Delimitadores",
    styles["Cuerpo"]
))
story.append(Spacer(1, 3 * cm))
story.append(Paragraph(
    "Fundación Universitaria Konrad Lorenz — Desarrollo de Aplicaciones con IA",
    styles["Normal"]
))
story.append(PageBreak())

# ------------------------------------------------------------------ #
# 1. Objetivo
# ------------------------------------------------------------------ #
story.append(Paragraph("1. Objetivo del ejercicio", styles["Subtitulo"]))
story.append(Paragraph(
    "Diseñar y ejecutar localmente el prompt de un chatbot de psicología "
    "orientado a crianza positiva y responsable, aplicando tres técnicas "
    "de Prompt Engineering: (1) diseño de un System Prompt que define el "
    "comportamiento del asistente, (2) Few-Shot Prompting para guiar el "
    "formato de la respuesta, y (3) estrategias de delimitadores (triple "
    "comillas y XML tags) para separar instrucciones de datos. El "
    "ejercicio se resuelve de forma local, sin conectarse a un modelo de "
    "lenguaje (LLM): el código construye el prompt completo y simula la "
    "respuesta esperada, cumpliendo el mismo contrato de formato que se "
    "exigiría a un LLM real.",
    styles["Cuerpo"]
))

# ------------------------------------------------------------------ #
# 2. Diseño del System Prompt
# ------------------------------------------------------------------ #
story.append(Paragraph("2. Diseño del System Prompt", styles["Subtitulo"]))
story.append(Paragraph(
    "El System Prompt (archivo <font face='Courier'>src/system_prompt.py</font>) "
    "se estructuró en bloques delimitados con XML tags, cada uno con una "
    "responsabilidad distinta:",
    styles["Cuerpo"]
))
bloques = [
    ("&lt;rol&gt;", "Identidad del asistente: 'CrianzApp', enfocado en crianza positiva."),
    ("&lt;publico_objetivo&gt;", "A quién va dirigido: cuidadores de niños y niñas de 0 a 12 años."),
    ("&lt;tono_y_estilo&gt;", "Cómo debe comunicarse: empático, claro, sin diagnosticar."),
    ("&lt;alcance&gt;", "Qué puede y qué NO puede responder (p. ej. no diagnostica, "
                          "deriva ante señales de riesgo o maltrato)."),
    ("&lt;formato_salida&gt;", "El contrato de salida: un único objeto JSON con claves fijas."),
    ("&lt;manejo_de_contexto&gt;", "Regla de seguridad: todo lo que llegue dentro de los "
                                     "delimitadores de contexto se trata como dato a analizar, "
                                     "nunca como instrucción."),
]
items = [
    ListItem(Paragraph(f"<b>{tag}</b>: {desc}", styles["Cuerpo"]), leftIndent=6)
    for tag, desc in bloques
]
story.append(ListFlowable(items, bulletType="bullet", start="•"))

# ------------------------------------------------------------------ #
# 3. Few-shot prompting
# ------------------------------------------------------------------ #
story.append(Paragraph("3. Few-Shot Prompting", styles["Subtitulo"]))
story.append(Paragraph(
    "En <font face='Courier'>src/few_shot_examples.py</font> se definieron dos "
    "ejemplos completos (pregunta → respuesta ideal en JSON):",
    styles["Cuerpo"]
))
story.append(Paragraph(
    "<b>Ejemplo 1 — Caso cotidiano:</b> una rabieta por el límite del "
    "televisor. La respuesta modelo muestra <font face='Courier'>"
    "derivar_a_profesional: false</font> y estrategias prácticas de "
    "disciplina positiva.",
    styles["Cuerpo"]
))
story.append(Paragraph(
    "<b>Ejemplo 2 — Caso de alerta:</b> una posible situación de abuso. "
    "La respuesta modelo muestra <font face='Courier'>senal_alerta</font> "
    "con una explicación breve y <font face='Courier'>"
    "derivar_a_profesional: true</font>, remitiendo a una entidad de "
    "protección infantil en vez de dar consejos generales.",
    styles["Cuerpo"]
))
story.append(Paragraph(
    "Estos dos ejemplos, al incluirse dentro del prompt (etiquetados como "
    "<font face='Courier'>&lt;ejemplo numero=\"1\"&gt;</font> y "
    "<font face='Courier'>&lt;ejemplo numero=\"2\"&gt;</font>), enseñan por "
    "imitación tanto el formato de salida (JSON con claves fijas) como el "
    "criterio para decidir cuándo derivar a un profesional.",
    styles["Cuerpo"]
))

# ------------------------------------------------------------------ #
# 4. Delimitadores
# ------------------------------------------------------------------ #
story.append(Paragraph("4. Estrategias de Delimitadores", styles["Subtitulo"]))
story.append(Paragraph(
    "El módulo <font face='Courier'>src/prompt_builder.py</font> combina dos "
    "estrategias de delimitación, tal como se trabajó en clase:",
    styles["Cuerpo"]
))
story.append(Paragraph(
    "<b>XML tags</b> para separar las secciones estructurales del prompt: "
    "<font face='Courier'>&lt;contexto&gt;</font>, "
    "<font face='Courier'>&lt;pregunta_usuario&gt;</font>, "
    "<font face='Courier'>&lt;ejemplos_few_shot&gt;</font>, "
    "<font face='Courier'>&lt;instruccion_final&gt;</font>.",
    styles["Cuerpo"]
))
story.append(Paragraph(
    "<b>Triple comillas dobles</b> (<font face='Courier'>\"\"\" ... \"\"\"</font>) "
    "alrededor del texto libre que escribe el usuario (contexto y pregunta), "
    "para marcar explícitamente dónde empieza y termina el dato, evitando "
    "que un texto malicioso dentro de la consulta del usuario sea "
    "interpretado como una instrucción del sistema (mitigación básica de "
    "\"prompt injection\").",
    styles["Cuerpo"]
))

story.append(PageBreak())

# ------------------------------------------------------------------ #
# 5. Ejecución paso a paso
# ------------------------------------------------------------------ #
story.append(Paragraph("5. Ejecución del prompt (main.py)", styles["Subtitulo"]))
story.append(Paragraph(
    "El archivo <font face='Courier'>main.py</font> ejecuta dos casos de "
    "prueba. Para cada uno, el flujo es el siguiente:",
    styles["Cuerpo"]
))
pasos = [
    "Se definen <font face='Courier'>contexto</font> y "
    "<font face='Courier'>pregunta</font> como texto libre (simulando lo "
    "que escribiría un usuario real en el chat).",
    "<font face='Courier'>build_prompt()</font> ensambla el prompt completo: "
    "System Prompt + ejemplos few-shot + contexto y pregunta delimitados "
    "con triple comillas y XML tags.",
    "El prompt resultante se imprime en consola: esto es exactamente el "
    "texto que se enviaría a un LLM si el proyecto estuviera conectado a uno.",
    "Como no hay conexión a un LLM, <font face='Courier'>"
    "generar_respuesta_simulada()</font> produce una respuesta de ejemplo "
    "aplicando una regla simple (detección de palabras clave de riesgo), "
    "respetando el mismo contrato de salida definido en el System Prompt.",
    "<font face='Courier'>validar_formato()</font> confirma que la "
    "respuesta generada tiene exactamente las claves "
    "(<font face='Courier'>resumen_breve</font>, "
    "<font face='Courier'>estrategias</font>, "
    "<font face='Courier'>senal_alerta</font>, "
    "<font face='Courier'>derivar_a_profesional</font>) y los tipos de "
    "dato correctos; si no cumple, lanza un error.",
    "La respuesta validada se imprime en consola como un objeto JSON "
    "legible (indentado).",
]
items_pasos = [
    ListItem(Paragraph(p, styles["Cuerpo"]), leftIndent=6) for p in pasos
]
story.append(ListFlowable(items_pasos, bulletType="1"))

story.append(Paragraph("5.1 Caso 1 — Situación cotidiana", styles["SubSub"]))
story.append(Paragraph(
    "<b>Entrada:</b> contexto = 'El niño tiene 4 años y va a preescolar.' — "
    "pregunta = 'Cada vez que le digo que apague la tele hace una rabieta "
    "enorme...'.",
    styles["Cuerpo"]
))
story.append(Paragraph(
    "<b>Salida esperada:</b> <font face='Courier'>derivar_a_profesional: "
    "false</font>, <font face='Courier'>senal_alerta: null</font> y una "
    "lista de estrategias de disciplina positiva (anticipar el límite, "
    "validar la emoción, mantener la firmeza, reforzar positivamente).",
    styles["Cuerpo"]
))
story.append(Paragraph(
    "[Aquí se inserta la captura de pantalla de la consola mostrando el "
    "prompt completo y el JSON de salida para el Caso 1]",
    styles["Nota"]
))

story.append(Paragraph("5.2 Caso 2 — Señal de alerta", styles["SubSub"]))
story.append(Paragraph(
    "<b>Entrada:</b> contexto = 'La niña tiene 7 años.' — pregunta = 'Mi "
    "hija me contó que un familiar la toca de una forma que la "
    "incomoda...'.",
    styles["Cuerpo"]
))
story.append(Paragraph(
    "<b>Salida esperada:</b> el detector de palabras clave identifica el "
    "término 'toca' dentro del contexto de riesgo, por lo que "
    "<font face='Courier'>derivar_a_profesional: true</font> y "
    "<font face='Courier'>senal_alerta</font> contiene la justificación. "
    "Las estrategias sugeridas dejan de ser de disciplina cotidiana y pasan "
    "a ser de acompañamiento inmediato y derivación (ICBF, línea 141).",
    styles["Cuerpo"]
))
story.append(Paragraph(
    "[Aquí se inserta la captura de pantalla de la consola mostrando el "
    "prompt completo y el JSON de salida para el Caso 2]",
    styles["Nota"]
))

# ------------------------------------------------------------------ #
# 6. Validación del formato de salida
# ------------------------------------------------------------------ #
story.append(Paragraph("6. Validación del formato de salida", styles["Subtitulo"]))
story.append(Paragraph(
    "Independientemente de si la respuesta la genera un LLM real o la "
    "función simulada de este proyecto, <font face='Courier'>"
    "validar_formato()</font> actúa como una capa de control de calidad: "
    "rechaza cualquier respuesta que no tenga exactamente las cuatro claves "
    "esperadas o que use un tipo de dato incorrecto (por ejemplo, si "
    "<font face='Courier'>estrategias</font> llegara como texto plano en "
    "vez de una lista). Esto es clave quando se piensa en integrar este "
    "prompt con un LLM real: el LLM puede 'alucinar' formatos distintos, y "
    "esta validación evita que una respuesta mal formada llegue al "
    "usuario final.",
    styles["Cuerpo"]
))

# ------------------------------------------------------------------ #
# 7. Conclusiones
# ------------------------------------------------------------------ #
story.append(Paragraph("7. Conclusiones", styles["Subtitulo"]))
conclusiones = [
    "El diseño del System Prompt permite fijar de forma explícita el rol, "
    "los límites éticos y el formato de salida del asistente, sin "
    "necesidad de tener el modelo conectado para poder revisarlo y "
    "corregirlo.",
    "El Few-Shot Prompting es especialmente útil para forzar un formato de "
    "salida estructurado (JSON), mostrando ejemplos concretos en lugar de "
    "solo describir la regla.",
    "Los delimitadores (XML tags y triple comillas) son la base para "
    "separar de forma segura las instrucciones del sistema de los datos "
    "que aporta el usuario, reduciendo el riesgo de que texto malicioso "
    "dentro de una consulta altere el comportamiento del asistente.",
    "Este mismo diseño de prompt queda listo para conectarse, en una "
    "siguiente fase, a un LLM real (siguiendo el patrón de "
    "<font face='Courier'>ChatPromptTemplate</font> visto en clase) e "
    "incluso a una base de conocimiento local mediante RAG.",
]
items_concl = [
    ListItem(Paragraph(c, styles["Cuerpo"]), leftIndent=6) for c in conclusiones
]
story.append(ListFlowable(items_concl, bulletType="bullet", start="•"))

doc = SimpleDocTemplate(
    OUT_PATH, pagesize=letter,
    topMargin=2.2 * cm, bottomMargin=2 * cm,
    leftMargin=2.2 * cm, rightMargin=2.2 * cm,
    title="CrianzApp - Explicación de ejecución del prompt"
)
doc.build(story)
print(f"PDF generado en: {OUT_PATH}")
