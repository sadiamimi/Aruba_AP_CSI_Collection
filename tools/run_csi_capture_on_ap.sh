#!/bin/sh
# Run on the AP's support shell after csi_raw_capture has been copied to /tmp.

set -eu

usage() {
    echo "Usage: $0 RADIO NETLINK INTERVAL_MS DURATION_S OUTPUT CLIENT_MAC [CLIENT_MAC ...]" >&2
    echo "Example: $0 aruba000 23 50 60 /tmp/trial.bin aa:bb:cc:dd:ee:ff" >&2
    exit 2
}

[ "$#" -ge 6 ] || usage

CSI_RADIO=$1
CSI_NETLINK=$2
CSI_INTERVAL_MS=$3
CSI_DURATION_S=$4
CSI_OUTPUT=$5
shift 5
CSI_CLIENTS="$*"

CSI_COLLECTOR=${CSI_COLLECTOR:-/tmp/csi_tools/csi_raw_capture}
CSI_OUTPUT_MODE=${CSI_OUTPUT_MODE:-binary}
CSI_LOG=${CSI_LOG:-${CSI_OUTPUT}.collector.log}
CSI_DRAIN_LOG=${CSI_DRAIN_LOG:-/tmp/csi-drain.log}
CSI_DRAIN_ACTIVE_S=${CSI_DRAIN_ACTIVE_S:-3}
CSI_COLLECTOR_PID=
CSI_DRAIN_PID=
CSI_CLEANED=0

if [ ! -x "$CSI_COLLECTOR" ]; then
    echo "Collector is missing or not executable: $CSI_COLLECTOR" >&2
    exit 1
fi
case "$CSI_OUTPUT_MODE" in
    binary|hpe-text) ;;
    *)
        echo "Invalid CSI_OUTPUT_MODE: $CSI_OUTPUT_MODE (use binary or hpe-text)" >&2
        exit 2
        ;;
esac

cleanup() {
    [ "$CSI_CLEANED" -eq 0 ] || return
    CSI_CLEANED=1

    for CSI_CLIENT in $CSI_CLIENTS; do
        wl -i "$CSI_RADIO" csimon del "$CSI_CLIENT" >/dev/null 2>&1 || true
    done
    wl -i "$CSI_RADIO" csimon disable >/dev/null 2>&1 || true
    sleep 2

    if [ -n "$CSI_DRAIN_PID" ]; then
        kill -TERM "$CSI_DRAIN_PID" >/dev/null 2>&1 || true
        wait "$CSI_DRAIN_PID" >/dev/null 2>&1 || true
    fi
    if [ -n "$CSI_COLLECTOR_PID" ]; then
        kill -TERM "$CSI_COLLECTOR_PID" >/dev/null 2>&1 || true
        wait "$CSI_COLLECTOR_PID" >/dev/null 2>&1 || true
    fi
}

trap 'cleanup; exit 130' HUP INT TERM
trap 'cleanup' EXIT

echo "Disabling CSI and draining stale netlink records"
for CSI_CLIENT in $CSI_CLIENTS; do
    wl -i "$CSI_RADIO" csimon del "$CSI_CLIENT" >/dev/null 2>&1 || true
done
wl -i "$CSI_RADIO" csimon disable
"$CSI_COLLECTOR" "$CSI_NETLINK" 0 /dev/null \
    >/dev/null 2>"$CSI_DRAIN_LOG" &
CSI_DRAIN_PID=$!
wl -i "$CSI_RADIO" csimon enable
wl -i "$CSI_RADIO" csi_deci 0
for CSI_CLIENT in $CSI_CLIENTS; do
    echo "Drain-registering $CSI_CLIENT at ${CSI_INTERVAL_MS} ms"
    wl -i "$CSI_RADIO" csimon add "$CSI_CLIENT" "$CSI_INTERVAL_MS"
done
sleep "$CSI_DRAIN_ACTIVE_S"
kill -TERM "$CSI_DRAIN_PID" >/dev/null 2>&1 || true
wait "$CSI_DRAIN_PID" >/dev/null 2>&1 || true
CSI_DRAIN_PID=
echo "Drain collector result"
tail -n 2 "$CSI_DRAIN_LOG" || true

echo "Starting full-record capture: $CSI_OUTPUT (mode=$CSI_OUTPUT_MODE)"
if [ "$CSI_OUTPUT_MODE" = hpe-text ]; then
    "$CSI_COLLECTOR" --hpe-text "$CSI_NETLINK" 0 "$CSI_OUTPUT" \
        >/dev/null 2>"$CSI_LOG" &
else
    "$CSI_COLLECTOR" "$CSI_NETLINK" 0 "$CSI_OUTPUT" \
        >/dev/null 2>"$CSI_LOG" &
fi
CSI_COLLECTOR_PID=$!

for CSI_CLIENT in $CSI_CLIENTS; do
    echo "Keeping drain-registered client $CSI_CLIENT at ${CSI_INTERVAL_MS} ms"
done

echo "Initial driver counters"
wl -i "$CSI_RADIO" dump csimon
echo "Collecting for ${CSI_DURATION_S} seconds"
sleep "$CSI_DURATION_S"
echo "Final driver counters"
wl -i "$CSI_RADIO" dump csimon

cleanup
trap - EXIT HUP INT TERM

echo "Capture complete"
ls -l "$CSI_OUTPUT" "$CSI_LOG"
CSI_BYTES=$(wc -c < "$CSI_OUTPUT")
if [ "$CSI_OUTPUT_MODE" = hpe-text ]; then
    CSI_RECORDS=$(grep -c '^CSI record:$' "$CSI_OUTPUT" || true)
    if [ "$CSI_BYTES" -eq 0 ] || [ "$CSI_RECORDS" -eq 0 ]; then
        echo "Invalid HPE text capture: $CSI_BYTES bytes, $CSI_RECORDS records" >&2
        exit 1
    fi
    echo "Validated $CSI_BYTES bytes ($CSI_RECORDS complete HPE text records)"
else
    if [ "$CSI_BYTES" -eq 0 ] || [ $((CSI_BYTES % 8192)) -ne 0 ]; then
        echo "Invalid capture size: $CSI_BYTES bytes; expected a nonzero multiple of 8192" >&2
        exit 1
    fi
    echo "Validated $CSI_BYTES bytes ($((CSI_BYTES / 8192)) complete records)"
fi
