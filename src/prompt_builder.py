# -*- coding: utf-8 -*-
"""
prompt_builder.py
-------------------
Construye el prompt completo que se enviaría a un LLM, combinando:

    1) System Prompt          (system_prompt.py)
    2) Ejemplos Few-Shot      (few_shot_examples.py)
    3) Contexto del usuario   (delimitado con XML tags y triple comillas)
    4) Pregunta del usuario   (delimitada)

IMPORTANTE: Este proyecto NO se conecta a ningún modelo de lenguaje. La
función `build_prompt` solo ensambla y devuelve el texto del prompt, tal
como quedaría estructurado antes de enviarse a un LLM. Esto cumple el
alcance del ejercicio: diseño de prompts, few-shot prompting y
estrategias de delimitadores.
"""

import json
from src.system_prompt import SYSTEM_PROMPT
from src.few_shot_examples import FEW_SHOT_EXAMPLES


def _formatear_ejemplo(ejemplo: dict, numero: int) -> str:
    """Convierte un ejemplo few-shot en texto con delimitadores XML."""
    pregunta = ejemplo["pregunta"].strip()
    respuesta_json = json.dumps(
        ejemplo["respuesta_json"], ensure_ascii=False, indent=2
    )
    return (
        f"<ejemplo numero=\"{numero}\">\n"
        f"  <pregunta_usuario>\n"
        f"  \"\"\"{pregunta}\"\"\"\n"
        f"  </pregunta_usuario>\n"
        f"  <respuesta_esperada formato=\"json\">\n"
        f"{respuesta_json}\n"
        f"  </respuesta_esperada>\n"
        f"</ejemplo>"
    )


def build_prompt(contexto_usuario: str, pregunta_usuario: str) -> str:
    """
    Ensambla el prompt final.

    Parameters
    ----------
    contexto_usuario : str
        Antecedentes/datos que aporta quien consulta (p. ej. edad del
        niño/a, situación previa). Puede ir vacío.
    pregunta_usuario : str
        La pregunta o situación puntual que se quiere resolver.

    Returns
    -------
    str
        El prompt completo, listo para ser enviado a un LLM (o, en este
        proyecto, para ser inspeccionado/impreso como evidencia del
        diseño de prompt).
    """
    ejemplos_texto = "\n\n".join(
        _formatear_ejemplo(ej, i + 1) for i, ej in enumerate(FEW_SHOT_EXAMPLES)
    )

    prompt_final = f"""{SYSTEM_PROMPT.strip()}

<ejemplos_few_shot>
Estos ejemplos ilustran el formato de salida esperado. Imita EXACTAMENTE
la estructura JSON, no el contenido literal.

{ejemplos_texto}
</ejemplos_few_shot>

<contexto>
\"\"\"{contexto_usuario.strip()}\"\"\"
</contexto>

<pregunta_usuario>
\"\"\"{pregunta_usuario.strip()}\"\"\"
</pregunta_usuario>

<instruccion_final>
Usando únicamente la información dentro de <contexto> y <pregunta_usuario>,
responde siguiendo ESTRICTAMENTE el formato definido en <formato_salida>
del system prompt. No expliques tu razonamiento, entrega solo el JSON.
</instruccion_final>
"""
    return prompt_final
