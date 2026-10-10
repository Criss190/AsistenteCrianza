# -*- coding: utf-8 -*-
"""
prompt_builder.py
-------------------
Construye el prompt completo que se enviaría a un LLM, combinando:

    1) System Prompt          (system_prompt.py)
    2) Ejemplos Few-Shot      (few_shot_examples.py)
    3) Contexto del usuario   (delimitado con XML tags y triple comillas)
    4) Pregunta del usuario   (delimitada)

El prompt conserva los ejemplos few-shot y delimitadores del Avance 1 e
incorpora el historial y la evidencia recuperada antes de la pregunta actual.
"""

import json
from typing import Any

from src.system_prompt import SYSTEM_PROMPT
from src.few_shot_examples import FEW_SHOT_EXAMPLES


def _formatear_ejemplo(ejemplo: dict[str, Any], numero: int) -> str:
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


def build_prompt(
    contexto_usuario: str,
    pregunta_usuario: str,
    conocimiento_recuperado: str = "",
    historial: list[dict[str, str]] | None = None,
) -> str:
    """
    Ensambla el prompt final.

    Parameters
    ----------
    contexto_usuario : str
        Antecedentes/datos que aporta quien consulta (p. ej. edad del
        niño/a, situación previa). Puede ir vacío.
    pregunta_usuario : str
        La pregunta o situación puntual que se quiere resolver.
    conocimiento_recuperado : str
        Fragmentos recuperados desde la base local, si existen.
    historial : list[dict[str, str]] | None
        Turnos anteriores validados, en orden cronológico.

    Returns
    -------
    str
        El prompt completo listo para enviar al modelo.
    """
    ejemplos_texto = "\n\n".join(
        _formatear_ejemplo(ej, i + 1) for i, ej in enumerate(FEW_SHOT_EXAMPLES)
    )
    dialogo_previo = "\n".join(
        f"<turno rol=\"{turno['role']}\">{turno['content']}</turno>"
        for turno in (historial or [])
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

<historial_conversacional>
{dialogo_previo}
</historial_conversacional>

<pregunta_usuario>
\"\"\"{pregunta_usuario.strip()}\"\"\"
</pregunta_usuario>

<base_conocimiento>
\"\"\"{conocimiento_recuperado.strip()}\"\"\"
</base_conocimiento>

<instruccion_final>
Usando únicamente la información dentro de <contexto>, <pregunta_usuario> y
<base_conocimiento>,
responde siguiendo ESTRICTAMENTE el formato definido en <formato_salida>
del system prompt. Usa solo evidencia de <base_conocimiento>. Si no contiene
la respuesta, indica explícitamente que no dispones de esa información en la
base de conocimientos. No expliques tu razonamiento, entrega solo el JSON.
</instruccion_final>
"""
    return prompt_final
