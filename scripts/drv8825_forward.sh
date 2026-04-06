#!/bin/sh

set -eu

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
. "$SCRIPT_DIR/drv8825_common.sh"

stop_worker
nohup sh "$SCRIPT_DIR/drv8825_step_worker.sh" forward >"$LOG_FILE" 2>&1 &
echo $! > "$PID_FILE"
