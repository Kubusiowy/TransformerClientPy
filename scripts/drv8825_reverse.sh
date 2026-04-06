#!/bin/sh

set -eu

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
. "$SCRIPT_DIR/drv8825_common.sh"

ensure_pinctrl
stop_worker
init_pins
nohup sh "$SCRIPT_DIR/drv8825_step_worker.sh" reverse >"$LOG_FILE" 2>&1 &
echo $! > "$PID_FILE"
