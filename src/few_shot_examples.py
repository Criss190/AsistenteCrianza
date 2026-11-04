"""Ejemplos breves y respaldados usados para guiar el formato RAG."""

FEW_SHOT_EXAMPLES = [
    {
        "pregunta": (
            "Mi hijo de 5 años hace una rabieta enorme cuando le apago la "
            "pantalla y yo termino gritando. ¿Qué hago?"
        ),
        "evidencia": (
            "[Fuente 1: TBRI — Principios de Corrección, página 25]\n"
            "Nivel 3: Interacción para calmar. Cuando el niño está muy "
            "alterado, el adulto baja el tono y el volumen de la voz, se pone a "
            "su nivel y ofrece un lugar seguro elegido de antemano, como un "
            "rincón con una manta con peso o música relajante.\n\n"
            "[Fuente 2: TBRI — Principios de Corrección, página 28]\n"
            "Los adultos modelan la autorregulación: si el adulto se mantiene "
            "tranquilo y respira profundo, ayuda al niño a calmarse."
        ),
        "respuesta_json": {
            "validacion": (
                "Qué desgastante es llegar al grito cuando tu hijo está en plena "
                "rabieta; no eres la única persona a la que le pasa."
            ),
            "lectura_conducta": (
                "Cuando el niño está tan alterado, lo primero que necesita es "
                "calma y no una lección: la guía propone calmar antes de "
                "corregir [Fuente 1]."
            ),
            "estrategias": [
                "Respira profundo y baja tu voz: tu calma le ayuda a calmarse "
                "[Fuente 2].",
                "Ponte a su nivel y ofrécele un lugar seguro que hayan elegido "
                "juntos, por ejemplo con una manta o música suave [Fuente 1].",
            ],
            "limite_de_la_guia": (
                "La guía no menciona nada específico sobre pantallas."
            ),
            "senal_alerta": None,
            "derivar_a_profesional": False,
        },
    },
    {
        "pregunta": "¿Qué actividad sensorial específica debo usar para dormir?",
        "evidencia": (
            "[Fuente 1: TBRI — Principios de Empoderamiento, página 20]\n"
            "Un ejemplo de rutina a la hora de dormir es tomar un baño, leer un "
            "libro, apagar las luces. Un ejemplo de ritual es que la mamá y el "
            "niño hagan contacto visual y cada uno diga su parte favorita del "
            "día."
        ),
        "respuesta_json": {
            "validacion": (
                "Es muy válido buscar que la hora de dormir sea tranquila."
            ),
            "lectura_conducta": None,
            "estrategias": [
                "Mantén una rutina previsible (baño, un libro, apagar las "
                "luces) y suma un pequeño ritual de conexión, como contar cada "
                "uno su parte favorita del día [Fuente 1]."
            ],
            "limite_de_la_guia": (
                "La guía recuperada no describe actividades sensoriales "
                "específicas para dormir; para una recomendación individual, "
                "consulta a un profesional."
            ),
            "senal_alerta": None,
            "derivar_a_profesional": False,
        },
    },
]
