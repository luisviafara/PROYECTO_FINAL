#!/usr/bin/env python3
# -- coding: utf-8 --
"""
Termostato activado por aplausos con registro de datos en MySQL.
Compatible con Raspberry Pi 3 + Python 3.5.3 + GrovePi.

    1 aplauso  -> Mide temperatura/humedad durante 10s y guarda el promedio
                  en la base de datos.
    2 aplausos -> Muestra la ultima medida en el LCD (cian) e imprime el
                  historial completo en la consola (orden cronologico).
    3 aplausos -> Borra todos los registros de la base de datos, pita muy
                  largo y muestra "Datos Borrados" en rojo.

Nota: la base de datos MySQL vive en tu PC, no en la Raspberry Pi. La Pi
se conecta a ella por la red local usando la libreria "pymysql".
"""

import math
import time
import pymysql
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

TIEMPO_DEBOUNCE = 0.3
VENTANA_CONTEO = 1.5

TEMP_MIN, TEMP_MAX = -10, 60
HUM_MIN, HUM_MAX = 0, 100

# Datos de conexion a MySQL
DB_HOST = "192.168.1.12"       # <--- Tu IP correcta
DB_PORT = 3306
DB_USER = "grovepi_user"
DB_PASSWORD = "1234"           # <--- Tu contraseña corregida
DB_NAME = "datos_clima"

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


def conectar_bd():
    """Abre una conexion a MySQL y garantiza que la tabla 'mediciones'
    exista. Se llama una vez por operacion."""
    conexion = pymysql.connect(
        host=DB_HOST,
        port=DB_PORT,
        user=DB_USER,
        password=DB_PASSWORD,
        database=DB_NAME,
    )
    cursor = conexion.cursor()
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS mediciones (
            id INT AUTO_INCREMENT PRIMARY KEY,
            fecha_hora VARCHAR(19) NOT NULL,
            temperatura_c FLOAT NOT NULL,
            humedad_porc FLOAT NOT NULL
        )
        """
    )
    conexion.commit()
    cursor.close()
    return conexion


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
    """1 aplauso: mide 10s (5 lecturas cada 2s) y guarda el promedio en la BD."""
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

    prom_t = round(sum(temperaturas) / len(temperaturas), 1)
    prom_h = round(sum(humedades) / len(humedades), 1)
    pitido(0.4)

    fecha_hora = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    try:
        conexion = conectar_bd()
        cursor = conexion.cursor()
        cursor.execute(
            "INSERT INTO mediciones (fecha_hora, temperatura_c, humedad_porc) VALUES (%s, %s, %s)",
            (fecha_hora, prom_t, prom_h),
        )
        conexion.commit()
        cursor.close()
        conexion.close()
        print("-> Medidas guardadas exitosamente en la base de datos.")
        lcd_mostrar("Guardado!", "T:{:.1f}C H:{:.1f}%".format(prom_t, prom_h), (0, 255, 0))
    except pymysql.MySQLError as e:
        print("-> Error al guardar en MySQL: {}".format(e))
        lcd_mostrar("Error BD", "Sin conexion", (255, 0, 0))

    time.sleep(3)
    lcd_apagar()


def mostrar_mediciones():
    """2 aplausos: imprime el historial completo y muestra la ultima medida."""
    print("\n[2 aplausos] Mostrando mediciones guardadas...")

    try:
        conexion = conectar_bd()
        cursor = conexion.cursor()
        cursor.execute(
            "SELECT fecha_hora, temperatura_c, humedad_porc FROM mediciones ORDER BY id ASC"
        )
        filas = cursor.fetchall()
        cursor.close()
        conexion.close()
    except pymysql.MySQLError as e:
        print("-> Error al leer de MySQL: {}".format(e))
        lcd_mostrar("Error BD", "Sin conexion", (255, 0, 0))
        time.sleep(3)
        lcd_apagar()
        return

    if not filas:
        lcd_mostrar("Sin datos", "Base vacia", (255, 255, 0))
        time.sleep(3)
        lcd_apagar()
        return

    print("--- HISTORIAL DE MEDIDAS (orden cronologico) ---")
    for fecha, temp, hum in filas:
        print("[{}] Temp: {} C | Hum: {} %".format(fecha, temp, hum))

    _, ultima_temp, ultima_hum = filas[-1]
    lcd_mostrar(
        "Ultima: T:{} C".format(ultima_temp),
        "Humedad: {} %".format(ultima_hum),
        (0, 255, 255),
    )
    time.sleep(5)
    lcd_apagar()


def borrar_mediciones():
    """3 aplausos: borra todos los registros, pita largo y muestra 'Datos Borrados' en rojo."""
    print("\n[3 aplausos] Borrando todo el historial...")
    try:
        conexion = conectar_bd()
        cursor = conexion.cursor()
        cursor.execute("DELETE FROM mediciones")
        conexion.commit()
        cursor.close()
        conexion.close()
        print("-> Todos los registros fueron eliminados de la base de datos.")
    except pymysql.MySQLError as e:
        print("-> Error al borrar en MySQL: {}".format(e))

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