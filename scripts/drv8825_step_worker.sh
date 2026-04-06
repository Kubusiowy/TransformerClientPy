#!/bin/sh

set -eu

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
. "$SCRIPT_DIR/drv8825_common.sh"

direction=${1:-}
if [ "$direction" != "forward" ] && [ "$direction" != "reverse" ]; then
  echo "Uzycie: $0 forward|reverse" >&2
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

trap 'disable_driver; rm -f "$PID_FILE"; exit 0' INT TERM EXIT

for ramp_delay in $RAMP_STEP_DELAYS; do
  count=0
  while [ "$count" -lt "$RAMP_STEPS_PER_STAGE" ]; do
    pinctrl set "$STEP_PIN" op dh
    sleep "$ramp_delay"
    pinctrl set "$STEP_PIN" op dl
    sleep "$ramp_delay"
    count=$((count + 1))
  done
done

while :; do
  pinctrl set "$STEP_PIN" op dh
  sleep "$STEP_DELAY_SEC"
  pinctrl set "$STEP_PIN" op dl
  sleep "$STEP_DELAY_SEC"
done
