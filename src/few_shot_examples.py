"""Ejemplos breves y respaldados usados para guiar el formato RAG."""

FEW_SHOT_EXAMPLES = [
    {
        "pregunta": "Mi hijo hace una rabieta cuando apago la pantalla. ¿Qué hago?",
        "evidencia": (
            "Conviene anticipar el límite, validar la emoción y mantener la "
            "decisión con calma. Una frase útil es: 'Entiendo que estás "
            "enojado; la pantalla se apaga ahora'."
        ),
        "respuesta_json": {
            "resumen_breve": (
                "Puedes sostener el límite con calma y reconocer su frustración."
            ),
            "estrategias": [
                "Avisa antes de apagar la pantalla.",
                "Nombra la emoción y mantén la decisión con calma.",
            ],
            "senal_alerta": None,
            "derivar_a_profesional": False,
        },
    },
    {
        "pregunta": "¿Qué actividad sensorial específica debo usar para dormir?",
        "evidencia": (
            "La guía recuperada solo recomienda mantener horarios previsibles; "
            "no describe actividades sensoriales para dormir."
        ),
        "respuesta_json": {
            "resumen_breve": (
                "La guía no incluye una recomendación específica sobre "
                "actividades sensoriales para dormir."
            ),
            "estrategias": [
                "Puedes mantener una rutina previsible; para una recomendación "
                "individual, consulta a un profesional."
            ],
            "senal_alerta": None,
            "derivar_a_profesional": False,
        },
    },
]
