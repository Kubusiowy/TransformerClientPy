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

while :; do
  single_step
done
