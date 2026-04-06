#!/bin/sh

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
PID_FILE="$SCRIPT_DIR/.drv8825_step.pid"
LOG_FILE="$SCRIPT_DIR/.drv8825_step.log"

EN_PIN=24
STEP_PIN=23
DIR_PIN=22
STEP_DELAY_SEC=0.002

ensure_pinctrl() {
  if ! command -v pinctrl >/dev/null 2>&1; then
    echo "Brak komendy 'pinctrl'." >&2
    exit 1
  fi
}

init_pins() {
  pinctrl set "$EN_PIN" op dh
  pinctrl set "$STEP_PIN" op dl
  pinctrl set "$DIR_PIN" op dl
}

stop_worker() {
  if [ -f "$PID_FILE" ]; then
    pid=$(cat "$PID_FILE")
    if [ -n "$pid" ] && kill -0 "$pid" 2>/dev/null; then
      kill "$pid" 2>/dev/null || true
      wait "$pid" 2>/dev/null || true
    fi
    rm -f "$PID_FILE"
  fi
}

disable_driver() {
  pinctrl set "$EN_PIN" op dh
  pinctrl set "$STEP_PIN" op dl
}

enable_driver() {
  pinctrl set "$EN_PIN" op dl
}
