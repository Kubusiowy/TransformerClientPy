#!/bin/sh

set -eu

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
. "$SCRIPT_DIR/drv8825_common.sh"

cleanup() {
  disable_driver
}

ensure_pinctrl
stop_worker
init_pins
pinctrl set "$DIR_PIN" op dh
enable_driver

trap cleanup INT TERM EXIT

while :; do
  single_step
done
