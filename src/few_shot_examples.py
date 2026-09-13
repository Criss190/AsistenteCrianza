# -*- coding: utf-8 -*-
"""
few_shot_examples.py
---------------------
Ejemplos "few-shot" que se insertan en el prompt para que el modelo
aprenda, por imitación, el formato de salida esperado (JSON con claves
fijas). Cada ejemplo sigue la estructura:

    Pregunta del usuario (delimitada) -> Respuesta ideal (JSON)

Estos ejemplos son estáticos: no llaman a ningún LLM, solo se usan como
piezas de texto que se concatenan al prompt final (ver prompt_builder.py).
"""

FEW_SHOT_EXAMPLES = [
    {
        "pregunta": """Mi hijo de 4 años hace rabietas enormes cuando le
        digo que ya no puede ver más televisión. Grita, llora y a veces
        se tira al piso. No sé si debo cederle o mantenerme firme.""",
        "respuesta_json": {
            "resumen_breve": "Es muy común que a los 4 años los límites "
                              "generen frustración intensa; no significa "
                              "que algo esté mal en tu crianza.",
            "estrategias": [
                "Anticipa el límite antes de que llegue el momento: "
                "'Cuando termine este capítulo, apagamos la tele'.",
                "Valida la emoción sin ceder el límite: "
                "'Entiendo que te frustra, y aun así ya es hora de apagarla'.",
                "Mantente firme y en calma; ceder ante el llanto enseña "
                "que la rabieta funciona para cambiar la decisión.",
                "Ofrece una alternativa de conexión inmediata después: "
                "leer un cuento o jugar algo breve juntos."
            ],
            "senal_alerta": None,
            "derivar_a_profesional": False
        }
    },
    {
        "pregunta": """Mi hija de 7 años me contó que un familiar la toca
        de una forma que la incomoda. No sé qué hacer.""",
        "respuesta_json": {
            "resumen_breve": "Gracias por confiar esta situación; lo que "
                              "describes requiere atención inmediata y "
                              "especializada.",
            "estrategias": [
                "Cree en lo que tu hija te contó y agradécele por hablarlo.",
                "No la confrontes con el familiar ni la expongas a repetir "
                "la historia varias veces.",
                "Comunícate cuanto antes con una entidad especializada en "
                "protección infantil (en Colombia: ICBF, línea 141)."
            ],
            "senal_alerta": "Posible abuso o vulneración hacia la menor: "
                             "requiere intervención profesional y legal, "
                             "no orientación general de crianza.",
            "derivar_a_profesional": True
        }
    }
]
