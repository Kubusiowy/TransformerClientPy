#!/bin/sh

set -eu

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
. "$SCRIPT_DIR/drv8825_common.sh"

DIRECTION=${1:-forward}
TEST_STEPS=${2:-300}

case "$DIRECTION" in
  forward|reverse)
    ;;
  *)
    echo "Uzycie: $0 [forward|reverse] [liczba_krokow]" >&2
    exit 1
    ;;
esac

case "$TEST_STEPS" in
  ''|*[!0-9]*)
    echo "Liczba krokow musi byc dodatnia liczba calkowita." >&2
    exit 1
    ;;
esac

if [ "$TEST_STEPS" -le 0 ]; then
  echo "Liczba krokow musi byc wieksza od 0." >&2
  exit 1
fi

cleanup() {
  disable_driver
}

ensure_pinctrl
trap cleanup INT TERM EXIT
stop_worker
BURST_STEPS=$TEST_STEPS
run_burst "$DIRECTION"
