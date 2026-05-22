from gpiozero import OutputDevice
from time import sleep

EN_PIN = 22
DIR_PIN = 17
STEP_PIN = 27

en = OutputDevice(EN_PIN)
dir = OutputDevice(DIR_PIN)
step = OutputDevice(STEP_PIN)

# DRV8825: EN jest aktywne stanem LOW
en.off()

# Kierunek
dir.on()

try:
    while True:
        step.on()
        sleep(0.002)
        step.off()
        sleep(0.002)

except KeyboardInterrupt:
    en.on()
    print("Stop silnika")