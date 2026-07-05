#!/usr/bin/env python3
# -- coding: utf-8 --
"""Sistema de medicion de distancia con GrovePi, LED y pantalla LCD RGB."""

import os
import csv
import grovepi
from datetime import datetime
from time import sleep

try:
    import grove_rgb_lcd
    LCD_DISPONIBLE = True
except ImportError:
    LCD_DISPONIBLE = False

PUERTO_ULTRASONICO = 4
PUERTO_LED = 7
UMBRAL_CM = 20
INTERVALO_SEGUNDOS = 2
SEGUNDOS_PREPARACION = 3
CARPETA_DATOS = "mediciones"

grovepi.pinMode(PUERTO_LED, "OUTPUT")


def lcd_mostrar(linea1, linea2="", color=(255, 255, 255)):
    if not LCD_DISPONIBLE:
        return
    try:
        texto = linea1
        if linea2:
            texto += "\n" + linea2
        grove_rgb_lcd.setText(texto)
        grove_rgb_lcd.setRGB(color[0], color[1], color[2])
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


def nombre_valido(nombre):
    return 1 <= len(nombre) <= 4 and nombre.isalnum()


def ruta_archivo(nombre):
    if not os.path.exists(CARPETA_DATOS):
        os.makedirs(CARPETA_DATOS)
    return os.path.join(CARPETA_DATOS, nombre.upper() + ".csv")


def listar_mediciones():
    if not os.path.exists(CARPETA_DATOS):
        return []
    return sorted(f[:-4] for f in os.listdir(CARPETA_DATOS) if f.endswith(".csv"))


def iniciar_medicion():
    print("\n--- NUEVA MEDICION ---")
    nombre = input("Nombre para esta medicion (max 4 letras/numeros): ").strip()

    if not nombre_valido(nombre):
        print("Nombre invalido. Debe tener entre 1 y 4 letras o numeros.\n")
        return

    archivo = ruta_archivo(nombre)
    if os.path.exists(archivo):
        resp = input("Ya existe una medicion '{}'. Sobreescribir? (s/n): ".format(nombre.upper()))
        if resp.strip().lower() != "s":
            print("Medicion cancelada.\n")
            return

    print("\nPreparando el sensor...")
    lcd_mostrar("Preparando...", "ID: {}".format(nombre.upper()), (0, 0, 255))
    for restante in range(SEGUNDOS_PREPARACION, 0, -1):
        print("  Iniciando en {}...".format(restante))
        sleep(1)

    print("\nIniciando lecturas cada {} segundos. Presiona CTRL+C para detener y guardar.\n".format(INTERVALO_SEGUNDOS))
    lecturas = []

    try:
        while True:
            try:
                distancia = grovepi.ultrasonicRead(PUERTO_ULTRASONICO)
            except IOError:
                print("Error de comunicacion con la placa, reintentando...")
                sleep(INTERVALO_SEGUNDOS)
                continue

            momento = datetime.now().strftime("%H:%M:%S")
            print("[{}] Distancia: {} cm".format(momento, distancia))
            lecturas.append({"hora": momento, "distancia_cm": distancia})

            if distancia == 0:
                grovepi.digitalWrite(PUERTO_LED, 0)
                lcd_mostrar("Sin lectura", "valida", (128, 128, 0))
            elif distancia <= UMBRAL_CM:
                print(">>> OBJETO DETECTADO <<<")
                grovepi.digitalWrite(PUERTO_LED, 1)
                lcd_mostrar("Dist: {} cm".format(distancia), "OBJETO CERCA", (255, 0, 0))
            else:
                grovepi.digitalWrite(PUERTO_LED, 0)
                lcd_mostrar("Dist: {} cm".format(distancia), "Libre", (0, 255, 0))

            sleep(INTERVALO_SEGUNDOS)

    except KeyboardInterrupt:
        grovepi.digitalWrite(PUERTO_LED, 0)
        print("\nMedicion detenida.")

    if lecturas:
        with open(archivo, "w", newline="") as f:
            escritor = csv.DictWriter(f, fieldnames=["hora", "distancia_cm"])
            escritor.writeheader()
            escritor.writerows(lecturas)
        print("Se guardaron {} lecturas en '{}'.\n".format(len(lecturas), archivo))
        lcd_mostrar("Guardado:", nombre.upper(), (0, 128, 255))
        sleep(2)
    else:
        print("No se registro ninguna lectura.\n")

    lcd_apagar()


def ver_mediciones():
    print("\n--- MEDICIONES GUARDADAS ---")
    mediciones = listar_mediciones()

    if not mediciones:
        print("No hay mediciones guardadas.\n")
        return

    for i, nombre in enumerate(mediciones, start=1):
        print("{}) {}".format(i, nombre))

    seleccion = input("\nEscribe el nombre para ver detalles (o Enter para volver): ").strip().upper()
    if not seleccion:
        return

    archivo = ruta_archivo(seleccion)
    if not os.path.exists(archivo):
        print("No se encontro esa medicion.\n")
        return

    with open(archivo, "r") as f:
        filas = list(csv.DictReader(f))

    if not filas:
        print("El archivo esta vacio.\n")
        return

    distancias = [float(fila["distancia_cm"]) for fila in filas]
    print("\nMedicion '{}': {} lecturas".format(seleccion, len(filas)))
    print("Minima: {:.2f} cm | Maxima: {:.2f} cm | Promedio: {:.2f} cm".format(
        min(distancias), max(distancias), sum(distancias) / len(distancias)
    ))

    if input("Ver todas las lecturas? (s/n): ").strip().lower() == "s":
        for fila in filas:
            print("  [{}] {} cm".format(fila["hora"], fila["distancia_cm"]))
    print("")


def borrar_medicion():
    print("\n--- BORRAR MEDICION ---")
    mediciones = listar_mediciones()

    if not mediciones:
        print("No hay mediciones guardadas.\n")
        return

    for i, nombre in enumerate(mediciones, start=1):
        print("{}) {}".format(i, nombre))

    seleccion = input("\nEscribe el nombre a borrar (o Enter para cancelar): ").strip().upper()
    if not seleccion:
        return

    archivo = ruta_archivo(seleccion)
    if not os.path.exists(archivo):
        print("No se encontro esa medicion.\n")
        return

    if input("Seguro que deseas borrar '{}'? (s/n): ".format(seleccion)).strip().lower() == "s":
        os.remove(archivo)
        print("Medicion '{}' borrada.\n".format(seleccion))
    else:
        print("Cancelado.\n")


def menu_principal():
    while True:
        print("=====================================")
        print(" SISTEMA DE MEDICION - GROVEPI + LCD")
        print("=====================================")
        print("1) Iniciar nueva medicion")
        print("2) Ver mediciones guardadas")
        print("3) Borrar una medicion")
        print("4) Salir")
        opcion = input("Elige una opcion: ").strip()

        if opcion == "1":
            iniciar_medicion()
        elif opcion == "2":
            ver_mediciones()
        elif opcion == "3":
            borrar_medicion()
        elif opcion == "4":
            print("Saliendo del programa. Hasta luego!")
            lcd_apagar()
            grovepi.digitalWrite(PUERTO_LED, 0)
            break
        else:
            print("Opcion invalida.\n")


if _name_ == "_main_":
    if not LCD_DISPONIBLE:
        print("Aviso: no se pudo importar 'grove_rgb_lcd'. El programa funcionara sin pantalla LCD.\n")
    menu_principal()