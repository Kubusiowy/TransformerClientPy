from __future__ import annotations

import argparse
import shutil
import subprocess
import time


EN_PIN = 22
DIR_PIN = 17
STEP_PIN = 27


def set_pin(pin_number: int, level: str) -> None:
    subprocess.run(
        ["pinctrl", "set", str(pin_number), "op", level],
        check=True,
    )


def init_driver(direction: str) -> None:
    set_pin(EN_PIN, "dh")      # EN HIGH = driver OFF
    set_pin(STEP_PIN, "dl")    # STEP idle LOW
    set_pin(DIR_PIN, "dh" if direction == "forward" else "dl")
    time.sleep(0.05)
    set_pin(EN_PIN, "dl")      # EN LOW = driver ON
    time.sleep(0.05)


def disable_driver() -> None:
    set_pin(STEP_PIN, "dl")
    set_pin(EN_PIN, "dh")


def step_motor(steps: int, delay_sec: float) -> None:
    for index in range(steps):
        set_pin(STEP_PIN, "dh")
        time.sleep(delay_sec)
        set_pin(STEP_PIN, "dl")
        time.sleep(delay_sec)
        if (index + 1) % 100 == 0:
            print(f"Kroki: {index + 1}/{steps}", flush=True)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Test DRV8825/NEMA17 przez pinctrl.")
    parser.add_argument(
        "direction",
        nargs="?",
        choices=("forward", "reverse"),
        default="forward",
        help="Kierunek ruchu.",
    )
    parser.add_argument(
        "steps",
        nargs="?",
        type=int,
        default=1000,
        help="Liczba impulsow STEP.",
    )
    parser.add_argument(
        "--delay",
        type=float,
        default=0.01,
        help="Czas stanu HIGH i LOW impulsu STEP w sekundach.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if args.steps <= 0:
        raise SystemExit("Liczba krokow musi byc wieksza od 0.")
    if args.delay <= 0:
        raise SystemExit("Delay musi byc wiekszy od 0.")
    if shutil.which("pinctrl") is None:
        raise SystemExit("Brak komendy 'pinctrl'. Uruchom na Raspberry Pi z Raspberry Pi OS.")

    print(
        f"Start: EN=GPIO{EN_PIN}, DIR=GPIO{DIR_PIN}, STEP=GPIO{STEP_PIN}, "
        f"kierunek={args.direction}, kroki={args.steps}, delay={args.delay}s",
        flush=True,
    )

    try:
        init_driver(args.direction)
        step_motor(args.steps, args.delay)
    finally:
        disable_driver()
        print("Driver OFF.", flush=True)


if __name__ == "__main__":
    main()
