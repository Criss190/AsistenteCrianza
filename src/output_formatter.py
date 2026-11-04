# -*- coding: utf-8 -*-
"""Contrato y validación de la salida JSON del modelo."""

import re

CLAVES_ESPERADAS = {
    "validacion": str,
    "lectura_conducta": (str, type(None)),
    "estrategias": list,
    "limite_de_la_guia": (str, type(None)),
    "senal_alerta": (str, type(None)),
    "derivar_a_profesional": bool,
}
LIMITE_VALIDACION = 450
LIMITE_LECTURA = 550
LIMITE_ESTRATEGIA = 500
LIMITE_NOTA = 400
MIN_ESTRATEGIAS = 1
MAX_ESTRATEGIAS = 4


def limpiar_texto_modelo(texto: str) -> str:
    """Quita del final preguntas de seguimiento ("¿Quieres que...?").

    El prompt pide no hacerlas; si el modelo se le escapa una, se elimina en
    lugar de descartar toda la respuesta.
    """
    texto = texto.strip()
    return re.sub(r"\s*¿[^?¿]*\?\s*$", "", texto).strip()


def validar_formato(respuesta: dict) -> bool:
    """
    Valida claves, tipos y límites de longitud del contrato JSON.

    Lanza ValueError si faltan claves, el contenido es excesivo o está vacío.
    """
    if not isinstance(respuesta, dict):
        raise ValueError("La respuesta debe ser un objeto JSON.")

    claves_respuesta = set(respuesta.keys())
    claves_definidas = set(CLAVES_ESPERADAS.keys())

    if claves_respuesta != claves_definidas:
        faltantes = claves_definidas - claves_respuesta
        sobrantes = claves_respuesta - claves_definidas
        raise ValueError(
            f"Formato inválido. Faltan claves: {faltantes or 'ninguna'} | "
            f"Claves no permitidas: {sobrantes or 'ninguna'}"
        )

    for clave, tipo_esperado in CLAVES_ESPERADAS.items():
        if not isinstance(respuesta[clave], tipo_esperado):
            raise ValueError(
                f"La clave '{clave}' debe ser de tipo {tipo_esperado}, "
                f"llegó {type(respuesta[clave])}."
            )

    validacion = respuesta["validacion"].strip()
    if not validacion or len(validacion) > LIMITE_VALIDACION:
        raise ValueError(
            f"'validacion' debe tener entre 1 y {LIMITE_VALIDACION} caracteres."
        )

    estrategias = respuesta["estrategias"]
    if not MIN_ESTRATEGIAS <= len(estrategias) <= MAX_ESTRATEGIAS:
        raise ValueError(
            f"Debe haber entre {MIN_ESTRATEGIAS} y {MAX_ESTRATEGIAS} estrategias."
        )
    if any(
        not isinstance(item, str)
        or not item.strip()
        or len(item) > LIMITE_ESTRATEGIA
        for item in estrategias
    ):
        raise ValueError(
            f"Cada estrategia debe ser texto no vacío de hasta {LIMITE_ESTRATEGIA} caracteres."
        )

    for clave, limite in (
        ("lectura_conducta", LIMITE_LECTURA),
        ("limite_de_la_guia", LIMITE_NOTA),
        ("senal_alerta", LIMITE_NOTA),
    ):
        valor = respuesta[clave]
        if isinstance(valor, str) and (not valor.strip() or len(valor) > limite):
            raise ValueError(
                f"'{clave}' debe ser null o texto de hasta {limite} caracteres."
            )
    return True
