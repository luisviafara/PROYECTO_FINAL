#!/usr/bin/env python3
# -- coding: utf-8 --
"""
Termostato activado por aplausos con registro de datos en CSV.
Compatible con Raspberry Pi 3 + Python 3.5.3 + GrovePi.

    1 aplauso  -> Mide temperatura/humedad durante 10s y la guarda en el CSV.
    2 aplausos -> Muestra la ultima medida en el LCD (cian) e imprime el
                  historial completo en la consola (orden cronologico).
    3 aplausos -> Borra el archivo de historial, pita muy largo y muestra
                  "Datos Borrados" en rojo.
"""

import os
import csv
import math
import time
import grovepi
from datetime import datetime

try:
    import grove_rgb_lcd
    LCD_DISPONIBLE = True
except ImportError:
    LCD_DISPONIBLE = False


# ------------------------------- Configuracion ------------------------------
PUERTO_DHT = 4
TIPO_DHT = 0
PUERTO_SONIDO = 0
PUERTO_BUZZER = 7

UMBRAL_SONIDO = 650
ARCHIVO_DATOS = "datos_clima.csv"

TIEMPO_DEBOUNCE = 0.3
VENTANA_CONTEO = 1.5

TEMP_MIN, TEMP_MAX = -10, 60
HUM_MIN, HUM_MAX = 0, 100


# ------------------------------ Capa de hardware -----------------------------
def configurar_hardware():
    """Configura el buzzer como salida. Reintenta porque el I2C de GrovePi
    a veces falla justo al encender la Raspberry Pi."""
    for _ in range(5):
        try:
            grovepi.pinMode(PUERTO_BUZZER, "OUTPUT")
            time.sleep(0.2)
            grovepi.digitalWrite(PUERTO_BUZZER, 0)
            return True
        except IOError:
            time.sleep(0.3)
    print("Aviso: no se pudo inicializar el buzzer tras varios intentos.")
    return False


def lcd_mostrar(linea1, linea2="", color=(255, 255, 255)):
    if not LCD_DISPONIBLE:
        return
    try:
        texto = linea1 + ("\n" + linea2 if linea2 else "")
        grove_rgb_lcd.setText(texto)
        grove_rgb_lcd.setRGB(*color)
    except Exception:
        pass


def lcd_apagar():
    if not LCD_DISPONIBLE:
        return
    try:
        grove_rgb_lcd.setText("")
        grove_rgb_lcd.setRGB(0, 0, 0)
    except Exception:
        pass


def pitido(duracion=0.1):
    try:
        grovepi.digitalWrite(PUERTO_BUZZER, 1)
        time.sleep(duracion)
        grovepi.digitalWrite(PUERTO_BUZZER, 0)
    except IOError:
        pass


def leer_sonido():
    """Devuelve el nivel de sonido, o None si el sensor no responde."""
    try:
        return grovepi.analogRead(PUERTO_SONIDO)
    except IOError:
        return None


def leer_dht():
    """Devuelve (temperatura, humedad) validas, o (None, None) si la
    lectura fallo, no es numerica, es 'nan' o esta fuera de rango."""
    try:
        t, h = grovepi.dht(PUERTO_DHT, TIPO_DHT)
    except (IOError, TypeError, ValueError):
        return None, None

    if not isinstance(t, (int, float)) or not isinstance(h, (int, float)):
        return None, None
    if math.isnan(t) or math.isnan(h):
        return None, None
    if not (TEMP_MIN <= t <= TEMP_MAX) or not (HUM_MIN <= h <= HUM_MAX):
        return None, None

    return t, h


# -------------------------------- Acciones ----------------------------------
def ejecutar_medicion_10s():
    """1 aplauso: mide 10s (5 lecturas cada 2s) y guarda el promedio en el CSV."""
    print("\n[1 aplauso] Midiendo temperatura durante 10 segundos...")
    lcd_mostrar("Midiendo...", "Espere 10s", (0, 128, 255))

    temperaturas, humedades = [], []
    for i in range(5):
        time.sleep(2)
        t, h = leer_dht()
        if t is not None:
            temperaturas.append(t)
            humedades.append(h)
            print("  Muestra {}: {} C | {} %".format(i + 1, t, h))
        else:
            print("  Muestra {}: lectura invalida, se descarta.".format(i + 1))

    if not temperaturas:
        print("-> Error: ninguna lectura valida.")
        lcd_mostrar("Error", "Sin lecturas", (255, 0, 0))
        time.sleep(3)
        lcd_apagar()
        return

    prom_t = sum(temperaturas) / len(temperaturas)
    prom_h = sum(humedades) / len(humedades)
    pitido(0.4)

    nueva_fila = [
        datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "{:.1f}".format(prom_t),
        "{:.1f}".format(prom_h),
    ]
    necesita_encabezado = (
        not os.path.exists(ARCHIVO_DATOS) or os.path.getsize(ARCHIVO_DATOS) == 0
    )
    with open(ARCHIVO_DATOS, "a", newline="") as f:
        escritor = csv.writer(f)
        if necesita_encabezado:
            escritor.writerow(["fecha_hora", "temperatura_c", "humedad_porc"])
        escritor.writerow(nueva_fila)

    print("-> Medidas guardadas exitosamente.")
    lcd_mostrar("Guardado!", "T:{:.1f}C H:{:.1f}%".format(prom_t, prom_h), (0, 255, 0))
    time.sleep(3)
    lcd_apagar()


def mostrar_mediciones():
    """2 aplausos: imprime el historial completo y muestra la ultima medida."""
    print("\n[2 aplausos] Mostrando mediciones guardadas...")

    if not os.path.exists(ARCHIVO_DATOS) or os.path.getsize(ARCHIVO_DATOS) == 0:
        lcd_mostrar("Sin datos", "Archivo vacio", (255, 255, 0))
        time.sleep(3)
        lcd_apagar()
        return

    with open(ARCHIVO_DATOS, "r", newline="") as f:
        filas = list(csv.reader(f))

    if len(filas) <= 1:
        lcd_mostrar("Sin datos", "Archivo vacio", (255, 255, 0))
        time.sleep(3)
        lcd_apagar()
        return

    print("--- HISTORIAL DE MEDIDAS (orden cronologico) ---")
    for fila in filas[1:]:
        print("[{}] Temp: {} C | Hum: {} %".format(fila[0], fila[1], fila[2]))

    ultima = filas[-1]
    lcd_mostrar(
        "Ultima: T:{} C".format(ultima[1]),
        "Humedad: {} %".format(ultima[2]),
        (0, 255, 255),
    )
    time.sleep(5)
    lcd_apagar()


def borrar_mediciones():
    """3 aplausos: borra el CSV, pita largo y muestra 'Datos Borrados' en rojo."""
    print("\n[3 aplausos] Borrando todo el historial...")
    if os.path.exists(ARCHIVO_DATOS):
        os.remove(ARCHIVO_DATOS)
        print("-> Archivo {} eliminado.".format(ARCHIVO_DATOS))
    else:
        print("-> El archivo ya estaba vacio.")

    lcd_mostrar("Datos", "Borrados", (255, 0, 0))
    pitido(1.0)
    time.sleep(2)
    lcd_apagar()


ACCIONES = {
    1: ejecutar_medicion_10s,
    2: mostrar_mediciones,
}


def ejecutar_accion(aplausos):
    """Elige que accion correr segun el numero de aplausos contados."""
    if aplausos >= 3:
        borrar_mediciones()
    else:
        ACCIONES.get(aplausos, lambda: None)()


# ------------------------------ Deteccion de aplausos ------------------------
def contar_aplausos():
    """Ya se detecto un primer aplauso. Pita, espera, y sigue contando
    mientras sigan llegando aplausos dentro de la ventana de tiempo."""
    aplausos = 1
    pitido(0.05)
    time.sleep(TIEMPO_DEBOUNCE)

    inicio_ventana = time.time()
    while time.time() - inicio_ventana < VENTANA_CONTEO:
        ruido = leer_sonido()
        if ruido is not None and ruido > UMBRAL_SONIDO:
            aplausos += 1
            pitido(0.05)
            time.sleep(TIEMPO_DEBOUNCE)

    return aplausos


def mostrar_instrucciones():
    print("=========================================")
    print("SISTEMA CONTROLADO POR APLAUSOS INICIADO")
    print("=========================================")
    print("1 Aplauso  -> Medir 10s y guardar")
    print("2 Aplausos -> Mostrar ultima medida")
    print("3 Aplausos -> Borrar todo el historial")
    print("Presiona CTRL+C para salir.\n")


def main():
    configurar_hardware()
    lcd_apagar()
    mostrar_instrucciones()

    try:
        while True:
            nivel = leer_sonido()
            if nivel is not None and nivel > UMBRAL_SONIDO:
                aplausos = contar_aplausos()
                print("\n---> Fin de secuencia: ¡Se detectaron {} aplauso(s)!".format(aplausos))
                ejecutar_accion(aplausos)
                print("\nEsperando nuevos aplausos...")
            time.sleep(0.05)

    except KeyboardInterrupt:
        try:
            grovepi.digitalWrite(PUERTO_BUZZER, 0)
        except IOError:
            pass
        lcd_apagar()
        print("\nPrograma terminado por el usuario.")


if _name_ == "_main_":
    main()