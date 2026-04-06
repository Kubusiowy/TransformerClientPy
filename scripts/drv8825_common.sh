#!/bin/sh

EN_PIN=24
STEP_PIN=23
DIR_PIN=22
STEP_DELAY_SEC=${MOTOR_STEP_DELAY_SEC:-0.008}
BURST_STEPS=${MOTOR_BURST_STEPS:-6}
ENABLE_DELAY_SEC=${MOTOR_ENABLE_DELAY_SEC:-0.002}
MICROSTEP_MODE=${MOTOR_MICROSTEP_MODE:-FULL}
M0_PIN=${MOTOR_M0_PIN:-}
M1_PIN=${MOTOR_M1_PIN:-}
M2_PIN=${MOTOR_M2_PIN:-}

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
  configure_microstep_mode
}

disable_driver() {
  pinctrl set "$EN_PIN" op dh
  pinctrl set "$STEP_PIN" op dl
}

enable_driver() {
  pinctrl set "$EN_PIN" op dl
  sleep "$ENABLE_DELAY_SEC"
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

set_pin_level() {
  pin=${1:-}
  level=${2:-dl}
  if [ -n "$pin" ]; then
    pinctrl set "$pin" op "$level"
  fi
}

configure_microstep_mode() {
  case "$MICROSTEP_MODE" in
    FULL)
      set_pin_level "$M0_PIN" dl
      set_pin_level "$M1_PIN" dl
      set_pin_level "$M2_PIN" dl
      ;;
    HALF)
      set_pin_level "$M0_PIN" dh
      set_pin_level "$M1_PIN" dl
      set_pin_level "$M2_PIN" dl
      ;;
    QUARTER)
      set_pin_level "$M0_PIN" dl
      set_pin_level "$M1_PIN" dh
      set_pin_level "$M2_PIN" dl
      ;;
    EIGHTH)
      set_pin_level "$M0_PIN" dh
      set_pin_level "$M1_PIN" dh
      set_pin_level "$M2_PIN" dl
      ;;
    SIXTEENTH)
      set_pin_level "$M0_PIN" dl
      set_pin_level "$M1_PIN" dl
      set_pin_level "$M2_PIN" dh
      ;;
    THIRTY_SECOND)
      set_pin_level "$M0_PIN" dh
      set_pin_level "$M1_PIN" dl
      set_pin_level "$M2_PIN" dh
      ;;
    *)
      set_pin_level "$M0_PIN" dl
      set_pin_level "$M1_PIN" dl
      set_pin_level "$M2_PIN" dl
      ;;
  esac
}
