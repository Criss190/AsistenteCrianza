"""Genera las imágenes del dominio (crianza positiva con TBRI®) y sus valores reales.

El contenido sale de la base de conocimiento de CrianzApp: los libros de trabajo
de TBRI® de Corrección (Respuesta IDEAL©, Niveles de Respuesta™) y de
Empoderamiento (hidratación). Las imágenes ya están en imagenes/; este script
solo hace falta para regenerarlas.
"""
import json
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

CARPETA_IMAGENES = Path(__file__).parent / "imagenes"
FUENTES = "/usr/share/fonts/liberation-sans-fonts/LiberationSans-{}.ttf"

VERDE_OSCURO, GRIS, NEGRO, BLANCO, CREMA = "#2f6b5e", "#5c6670", "#1a1a1a", "#ffffff", "#f6efe2"
COLOR_NIVEL = {1: "#3a9d5d", 2: "#e0a526", 3: "#d9722b", 4: "#b3261e"}


def fuente(tam, estilo="Regular"):
    try:
        return ImageFont.truetype(FUENTES.format(estilo), tam)
    except OSError:
        return ImageFont.load_default(tam)


# Valores reales de cada ficha, con el mismo esquema que extrae parte1_2_extraccion.py.
# "conducta" se dibuja en la ficha pero no forma parte del esquema.
FICHAS = {
    "ficha_nivel_1.png": {
        "nivel": 1, "nombre": "Interacción divertida", "principio": "Corrección",
        "tono": "Acogedor", "volumen": "Moderado", "cadencia": "Rápida, divertida",
        "tiempo_resolucion": "60 segundos o menos", "pagina_fuente": 23,
        "conducta": "Tono exigente, voltear los ojos, interrumpir",
    },
    "ficha_nivel_2.png": {
        "nivel": 2, "nombre": "Interacción estructurada", "principio": "Corrección",
        "tono": "Bajo, firme, pero no severo", "volumen": "Moderado", "cadencia": "Moderada/lenta",
        "tiempo_resolucion": "De 5 a 10 minutos o menos", "pagina_fuente": 24,
        "conducta": "Agitación leve o mal comportamiento prolongado",
    },
    "ficha_nivel_3.png": {
        "nivel": 3, "nombre": "Interacción para calmar", "principio": "Corrección",
        "tono": "Firme", "volumen": "Intenso pero no elevado", "cadencia": "Lenta",
        "tiempo_resolucion": "De 15 a 30 minutos o menos", "pagina_fuente": 25,
        "conducta": "Niño abrumado, levemente agresivo o en riesgo",
    },
    "ficha_nivel_4.png": {
        "nivel": 4, "nombre": "Interacción para proteger", "principio": "Corrección",
        "tono": "Muy firme", "volumen": "Intenso pero no elevado", "cadencia": "Muy lenta",
        "tiempo_resolucion": "De 30 a 60 minutos o menos", "pagina_fuente": 26,
        "conducta": "Amenaza de daño o comportamiento fuera de control",
    },
}
FICHAS_CON_VALOR_REAL = ["ficha_nivel_1.png", "ficha_nivel_2.png", "ficha_nivel_3.png"]


def crear_ficha(nombre, v):
    img = Image.new("RGB", (900, 640), BLANCO)
    d = ImageDraw.Draw(img)
    d.rectangle([0, 0, 900, 90], fill=VERDE_OSCURO)
    d.text((40, 26), "CrianzApp · Niveles de Respuesta TBRI®", font=fuente(32, "Bold"), fill=BLANCO)
    d.rounded_rectangle([40, 120, 220, 220], radius=16, fill=COLOR_NIVEL[v["nivel"]])
    d.text((130, 170), f"Nivel {v['nivel']}", font=fuente(40, "Bold"), fill=BLANCO, anchor="mm")
    d.text((250, 142), v["nombre"], font=fuente(50, "Bold"), fill=NEGRO)

    filas = [
        ("Principio:", v["principio"]),
        ("Tono:", v["tono"]),
        ("Volumen:", v["volumen"]),
        ("Cadencia:", v["cadencia"]),
        ("Tiempo de resolución:", v["tiempo_resolucion"]),
        ("Conducta típica:", v["conducta"]),
    ]
    y = 262
    for etiqueta, valor in filas:
        d.text((40, y), etiqueta, font=fuente(26, "Bold"), fill=GRIS)
        d.text((330, y), valor, font=fuente(26), fill=NEGRO)
        y += 52
    d.rectangle([0, 590, 900, 640], fill=CREMA)
    d.text((40, 602), f"Fuente: TBRI® Principios de Corrección, libro del participante, p. {v['pagina_fuente']}",
           font=fuente(22), fill=GRIS)
    img.save(CARPETA_IMAGENES / nombre)


def crear_respuesta_ideal(nombre):
    letras = [
        ("I", "Inmediata", "Dentro de los 3 segundos del comportamiento"),
        ("D", "Directa", "A la altura del niño, con contacto visual"),
        ("E", "Eficiente", "Solo la estructura que la situación necesita"),
        ("A", "Basada en acciones", "El niño repite la conducta de forma correcta"),
        ("L", "Enfocada al comportamiento", "Se corrige la conducta, no al niño"),
    ]
    img = Image.new("RGB", (900, 660), BLANCO)
    d = ImageDraw.Draw(img)
    d.rectangle([0, 0, 900, 90], fill=VERDE_OSCURO)
    d.text((40, 26), "CrianzApp · La Respuesta IDEAL© de TBRI®", font=fuente(32, "Bold"), fill=BLANCO)
    y = 120
    for letra, titulo, detalle in letras:
        d.rounded_rectangle([40, y, 120, y + 80], radius=14, fill=VERDE_OSCURO)
        d.text((80, y + 40), letra, font=fuente(52, "Bold"), fill=BLANCO, anchor="mm")
        d.text((150, y + 6), titulo, font=fuente(32, "Bold"), fill=NEGRO)
        d.text((150, y + 46), detalle, font=fuente(25), fill=GRIS)
        y += 94
    d.rectangle([0, 610, 900, 660], fill=CREMA)
    d.text((40, 622), "Fuente: TBRI® Principios de Corrección, libro del participante, pp. 19-21",
           font=fuente(22), fill=GRIS)
    img.save(CARPETA_IMAGENES / nombre)


def crear_semaforo(nombre):
    luces = [
        ("#3a9d5d", "VERDE · orina clara", "Bien hidratado: sigue tomando agua"),
        ("#f2c230", "AMARILLO · orina amarilla", "Toma un vaso de agua ahora"),
        ("#b3261e", "ROJO · orina oscura", "Toma agua ya y avísale a un adulto"),
    ]
    img = Image.new("RGB", (900, 640), BLANCO)
    d = ImageDraw.Draw(img)
    d.rectangle([0, 0, 900, 90], fill=VERDE_OSCURO)
    d.text((40, 26), "CrianzApp · Semáforo de hidratación", font=fuente(32, "Bold"), fill=BLANCO)
    d.rounded_rectangle([50, 120, 230, 570], radius=30, fill="#2b2b2b")
    y = 195
    for color, titulo, accion in luces:
        d.ellipse([85, y - 55, 195, y + 55], fill=color)
        d.text((270, y - 36), titulo, font=fuente(32, "Bold"), fill=NEGRO)
        d.text((270, y + 8), accion, font=fuente(26), fill=GRIS)
        y += 150
    d.rectangle([0, 590, 900, 640], fill=CREMA)
    d.text((40, 602), "Elaboración propia a partir de TBRI® Principios de Empoderamiento, p. 15",
           font=fuente(22), fill=GRIS)
    img.save(CARPETA_IMAGENES / nombre)


if __name__ == "__main__":
    CARPETA_IMAGENES.mkdir(exist_ok=True)
    for nombre, valores in FICHAS.items():
        crear_ficha(nombre, valores)
    crear_respuesta_ideal("respuesta_ideal.png")
    crear_semaforo("semaforo_hidratacion.png")

    reales = {n: {c: v for c, v in FICHAS[n].items() if c != "conducta"} for n in FICHAS_CON_VALOR_REAL}
    (CARPETA_IMAGENES / "valores_reales.json").write_text(
        json.dumps(reales, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"Imágenes creadas en {CARPETA_IMAGENES}")
