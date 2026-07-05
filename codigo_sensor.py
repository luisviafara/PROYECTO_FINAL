from gpiozero import DistanceSensor, LED
from time import sleep

sensor = DistanceSensor(echo=24, trigger=23)
led = LED(18)

while True:

    distancia = sensor.distance * 100

    print(f"Distancia: {distancia:.2f} cm")

    if distancia < 20:
        led.on()
        print("Objeto Detectado")
    else:
        led.off()

    sleep(0.2)
    