#!/bin/sh

set -eu

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
. "$SCRIPT_DIR/drv8825_common.sh"

ensure_pinctrl
init_pins
disable_driver
