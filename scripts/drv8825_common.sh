#!/bin/sh

EN_PIN=24
STEP_PIN=23
DIR_PIN=22
STEP_DELAY_SEC=${MOTOR_STEP_DELAY_SEC:-0.008}
BURST_STEPS=${MOTOR_BURST_STEPS:-6}

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

disable_driver() {
  pinctrl set "$EN_PIN" op dh
  pinctrl set "$STEP_PIN" op dl
}

enable_driver() {
  pinctrl set "$EN_PIN" op dl
}

single_step() {
  pinctrl set "$STEP_PIN" op dh
  sleep "$STEP_DELAY_SEC"
  pinctrl set "$STEP_PIN" op dl
  sleep "$STEP_DELAY_SEC"
}

run_burst() {
  direction=${1:-}
  if [ "$direction" != "forward" ] && [ "$direction" != "reverse" ]; then
    echo "Uzycie: run_burst forward|reverse" >&2
    exit 1
  fi

  ensure_pinctrl
  init_pins

  if [ "$direction" = "forward" ]; then
    pinctrl set "$DIR_PIN" op dh
  else
    pinctrl set "$DIR_PIN" op dl
  fi

  enable_driver
  count=0
  while [ "$count" -lt "$BURST_STEPS" ]; do
    single_step
    count=$((count + 1))
  done
  disable_driver
}
