import subprocess
import time

EN = 24    # GPIO24
DIR = 22   # GPIO22
STEP = 23  # GPIO23

DELAY = 0.01  # 10 ms


def pin(pin_number, state):
    subprocess.run(
        ["pinctrl", "set", str(pin_number), "op", state],
        check=True
    )


print("Start...")

# 1. włącz driver
pin(EN, "dl")   # EN LOW = ON

# 2. ustaw kierunek
pin(DIR, "dh")  # DIR HIGH

time.sleep(0.01)

# 3. kroki
for i in range(300):
    pin(STEP, "dh")
    time.sleep(DELAY)
    pin(STEP, "dl")
    time.sleep(DELAY)

# 4. wyłącz driver
pin(EN, "dh")   # EN HIGH = OFF

print("Koniec.")