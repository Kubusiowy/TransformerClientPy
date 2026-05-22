import RPi.GPIO as GPIO
import time

# PINY
EN_PIN = 22
DIR_PIN = 17
STEP_PIN = 27

# Ustawienie numeracji BCM
GPIO.setmode(GPIO.BCM)

# Konfiguracja pinów
GPIO.setup(EN_PIN, GPIO.OUT)
GPIO.setup(DIR_PIN, GPIO.OUT)
GPIO.setup(STEP_PIN, GPIO.OUT)

# Włączenie sterownika
# EN w DRV8825 jest aktywne LOW
GPIO.output(EN_PIN, GPIO.LOW)

# Kierunek obrotu
GPIO.output(DIR_PIN, GPIO.HIGH)

try:
    while True:

        # Jeden krok
        GPIO.output(STEP_PIN, GPIO.HIGH)
        time.sleep(0.001)

        GPIO.output(STEP_PIN, GPIO.LOW)
        time.sleep(0.001)

except KeyboardInterrupt:
    print("Stop")

finally:
    GPIO.cleanup()