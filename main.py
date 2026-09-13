# -*- coding: utf-8 -*-
"""
main.py
--------
Punto de entrada de la demo de "CrianzApp".

Este script NO se conecta a ningún LLM (Gemini, GPT, etc.). Su objetivo es
demostrar, de forma local, las tres técnicas de Prompt Engineering
pedidas en el alcance del ejercicio:

    1. Diseño de Prompts (System Prompt)      -> src/system_prompt.py
    2. Few-Shot Prompting                     -> src/few_shot_examples.py
    3. Estrategias de Delimitadores           -> src/prompt_builder.py
                                                  (triple comillas + XML tags)

Flujo de ejecución:
    entrada del usuario -> build_prompt() arma el prompt completo
                         -> se imprime el prompt (lo que se enviaría a un LLM)
                                 -> generar_respuesta_local() recupera evidencia y
                                     produce la salida JSON exigida
                         -> validar_formato() confirma que cumple el contrato
"""

import json
from src.knowledge_base import BaseConocimientoLocal
from src.prompt_builder import build_prompt
from src.output_formatter import generar_respuesta_local, validar_formato

SEPARADOR = "=" * 70


def ejecutar_caso(
    contexto: str,
    pregunta: str,
    titulo: str,
    base_conocimiento: BaseConocimientoLocal,
) -> None:
    print(SEPARADOR)
    print(f"CASO: {titulo}")
    print(SEPARADOR)

    # 1) Construcción del prompt estructurado (system + few-shot + contexto)
    fragmentos = base_conocimiento.buscar(f"{contexto} {pregunta}")
    conocimiento = "\n\n".join(
        f"[Fuente local: {fragmento.fuente}]\n{fragmento.texto}"
        for fragmento in fragmentos
    )
    prompt = build_prompt(
        contexto_usuario=contexto,
        pregunta_usuario=pregunta,
        conocimiento_recuperado=conocimiento,
    )
    print("\n--- PROMPT ENVIADO (system + few-shot + contexto delimitado) ---\n")
    print(prompt)

    # 2) Respuesta determinista usando únicamente la base local recuperada.
    respuesta = generar_respuesta_local(
        contexto=contexto,
        pregunta=pregunta,
        fragmentos=fragmentos,
    )
    validar_formato(respuesta)

    print("\n--- FUENTES LOCALES RECUPERADAS ---\n")
    print(
        "\n".join(sorted({fragmento.fuente for fragmento in fragmentos}))
        or "Ninguna"
    )

    print("\n--- RESPUESTA DEL ASISTENTE (formato JSON validado) ---\n")
    print(json.dumps(respuesta, ensure_ascii=False, indent=2))
    print("\n")


def main():
    base_conocimiento = BaseConocimientoLocal.cargar("docs/base_conocimiento")

    # Caso 1: situación cotidiana de crianza (no requiere alerta)
    ejecutar_caso(
        contexto="El niño tiene 4 años y va a preescolar.",
        pregunta=(
            "Cada vez que le digo que apague la tele hace una rabieta "
            "enorme, grita y se tira al piso. No sé si ceder o no."
        ),
        titulo="Rabieta por límite de pantallas (situación cotidiana)",
        base_conocimiento=base_conocimiento,
    )

    # Caso 2: señal de alerta (debe derivar a profesional)
    ejecutar_caso(
        contexto="La niña tiene 7 años.",
        pregunta=(
            "Mi hija me contó que un familiar la toca de una forma que "
            "la incomoda. No sé qué hacer."
        ),
        titulo="Posible situación de riesgo (debe derivar a profesional)",
        base_conocimiento=base_conocimiento,
    )


if __name__ == "__main__":
    main()
