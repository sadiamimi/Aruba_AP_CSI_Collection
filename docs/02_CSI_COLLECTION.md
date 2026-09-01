# Collect CSI with HPE `csimond`

This procedure uses only the HPE-provided `/bin/wl` and
`/aruba/bin/csimond` programs on the AP. Standard Linux commands on the PC are
listed in [`tools/README.md`](../tools/README.md).

## 1. Record the association

In the normal AP CLI, run:

```text
show ap association
show ap bss-table
```

The tested setup showed:

| Field | Value |
|---|---|
| Client | Samsung S21 FE |
| Client MAC | `52:12:a6:cc:bc:1a` |
| Client IPv4 | `192.168.10.79` |
| AP management IPv4 | `192.168.10.114` |
| BSSID | `94:ff:06:26:f3:20` |
| Radio | `aruba000` |
| Bandwidth | 80 MHz |
| Tested netlink ID | `23` |

Enter the internal shell:

```text
support
```

Confirm the associated MAC directly from the radio:

```sh
wl -i aruba000 assoclist
```

Use the MAC displayed by the AP. A phone can use a private Wi-Fi MAC that is
different from the address printed in its hardware information.

## 2. Prepare a new dataset directory on the PC

Open a terminal in the `Aruba_Share` directory. Create a new directory before
starting traffic or AP commands:

```bash
SESSION=YYYY-MM-DD_HH-MM-SS_TZ_Samsung-S21FE_1000ms-1Hz_10s
DATASET_DIR="$PWD/data/$SESSION"
mkdir -p "$DATASET_DIR"
```

Replace the date and parameters with the planned session. Use
[`EXPERIMENT_RECORD_TEMPLATE.md`](EXPERIMENT_RECORD_TEMPLATE.md) as the general
checklist for the AP, client, channel, interval, duration, and counters. Do not
copy documentation into the data directory.

Confirm that the phone is reachable from the PC:

```bash
CLIENT_IP=192.168.10.79
ping -n -c 5 "$CLIENT_IP"
```

## 3. Start phone keep-alive traffic on the PC

For phone experiments, the tested keep-alive is ICMP traffic sent from the PC
to the phone at a requested 10 ms interval. Start it before registering the
client for CSI:

```bash
KEEPALIVE_LOG="$DATASET_DIR/keepalive-ping.log"
ping -n -i 0.01 "$CLIENT_IP" >"$KEEPALIVE_LOG" 2>&1 &
KEEPALIVE_PID=$!
ps -p "$KEEPALIVE_PID" -o pid=,cmd=
```

This command requests 100 ICMP echo requests per second. It keeps Wi-Fi traffic
active but does not set the CSI collection rate. The CSI rate is requested by
`csimon add CLIENT_MAC INTERVAL_MS`. Use the same keep-alive choice for every
session being compared and record whether it was enabled.

If keep-alive traffic is not part of the experiment, skip this step and write
`not used` in the experiment notes.

Keep this PC terminal open. Its shell variables are used to stop the ping after
the AP capture finishes.

## 4. Set the AP experiment values

In the AP support shell, replace the examples with the values for the new
session:

```sh
IFACE=aruba000
NETLINK_ID=23
CLIENT_MAC=52:12:a6:cc:bc:1a
INTERVAL_MS=1000
DURATION_S=10
OUTPUT=/tmp/DATE_TIME_PHONE_1000ms-1Hz_10s_HPE-native-csimond.txt
```

Use the research PC's synchronized local date and time in the filename. The AP
shell clock and PC clock can differ. CSI header timestamps are radio/firmware
measurement timestamps rather than wall-clock time.

The HPE guide maps 5 GHz to `aruba000` and 6 GHz to `aruba200`. It gives
netlink 22 as a 5 GHz example. Netlink 23 was the active `aruba000` mapping on
the tested image. Use the value assigned to the image being tested.

## 5. Prepare the HPE receiver on the AP

Stop an earlier registration if present. An `Undefined error` from the first
`del` command means that the MAC was not currently registered.

```sh
wl -i "$IFACE" csimon del "$CLIENT_MAC"
wl -i "$IFACE" csimon disable
```

Start HPE `csimond` as a discard receiver, enable the monitor, set zero tone
decimation, and register the associated client. Keeping the HPE receiver active
during preparation clears records already waiting on the netlink path.

```sh
/aruba/bin/csimond "$NETLINK_ID" 0 1 >/dev/null 2>/tmp/csimond-drain.log &
DRAIN_PID=$!

wl -i "$IFACE" csimon enable
wl -i "$IFACE" csi_deci 0
wl -i "$IFACE" csimon add "$CLIENT_MAC" "$INTERVAL_MS"

sleep 3
kill -TERM "$DRAIN_PID"
wait "$DRAIN_PID"
```

## 6. Save HPE native text records

Start `csimond` immediately while the client remains registered:

```sh
/aruba/bin/csimond "$NETLINK_ID" 64 1 >"$OUTPUT" 2>&1 &
CSIMOND_PID=$!

wl -i "$IFACE" csimon state
sleep "$DURATION_S"
```

The changes from the guide's baseline `csimond NETLINK_ID 0 1000 &` are:

- `64` requests the tested executable's largest payload display;
- `1` displays every received record during a short capture;
- redirection saves standard output and standard error in the dataset file.

No HPE executable or firmware file is changed.

## 7. Stop the AP collection and record counters

Read the counters before removing the client:

```sh
wl -i "$IFACE" dump csimon
wl -i "$IFACE" csimon state
```

Record these values in the experiment notes:

- `null_frm_cnt`
- `xfer_to_ddr_cnt`
- `ack_fail_cnt`
- `rec_ovfl_cnt`
- `xfer_to_ddr_fail_cnt`

Stop generation, then stop `csimond` and flush the file:

```sh
wl -i "$IFACE" csimon del "$CLIENT_MAC"
wl -i "$IFACE" csimon disable
sleep 1
kill -TERM "$CSIMOND_PID"
wait "$CSIMOND_PID"
sync
```

Check the AP file:

```sh
ls -l "$OUTPUT"
grep -c '^CSI record:$' "$OUTPUT"
md5sum "$OUTPUT"
```

Record the byte count, record-marker count, and MD5. The
final displayed block can end during a record when the continuously running
daemon is stopped. The HPE parser reports how many tones are actually present
in each parsed JSON record.

## 8. Stop and save the keep-alive result on the PC

After AP collection has stopped, return to the PC terminal that started ping:

```bash
kill -INT "$KEEPALIVE_PID"
wait "$KEEPALIVE_PID" || true
tail -n 5 "$KEEPALIVE_LOG"
```

The log contains the transmitted packets, replies, packet loss, and round-trip
timing. Record those values with the experiment results. Do not leave ping
running between sessions.

When keep-alive was not started, skip these three commands.

## 9. Transfer the file to the PC

In a new PC terminal, set the existing dataset directory and start a listener:

```bash
DATASET_DIR="$PWD/data/SESSION_NAME"
CAPTURE_NAME=DATE_TIME_PHONE_1000ms-1Hz_10s_HPE-native-csimond.txt
nc -l 9005 > "$DATASET_DIR/$CAPTURE_NAME"
```

In the AP support shell, send the file to the PC's Ethernet address:

```sh
/usr/sbin/netcat -w 5 PC_LAN_IP 9005 < "$OUTPUT"
```

Once the AP sender has finished, stop the PC listener with `Ctrl-C` if it is
still waiting. Compare the PC byte count and checksum with the AP values:

```bash
wc -c "$DATASET_DIR/$CAPTURE_NAME"
md5sum "$DATASET_DIR/$CAPTURE_NAME"
sha256sum "$DATASET_DIR/$CAPTURE_NAME" \
  > "$DATASET_DIR/SHA256SUMS"
```

After the PC byte count and MD5 equal the AP values, the temporary AP copy can
be removed:

```sh
rm "$OUTPUT"
```

Keep the PC native text file unchanged. Continue with
[parsing and data checks](03_PARSE_AND_CHECK.md).

Run the included local framing and timestamp checker:

```bash
python3 tools/check_native_csimond.py "$DATASET_DIR/$CAPTURE_NAME" \
  --output-json "$DATASET_DIR/native-csimond-check.json"
```

Compare its marker count with `grep` and the AP transfer-counter change. Check
that its client MAC and BSSID match the association recorded before collection.

## 10. Requested interval and measured rate

`INTERVAL_MS` is the requested measurement interval for the registered client.

| Requested interval | Requested rate |
|---:|---:|
| 1000 ms | 1 Hz |
| 100 ms | 10 Hz |
| 50 ms | 20 Hz |
| 33 ms | about 30.3 Hz |

The tested image accepted 33 ms as its shortest interval. For every research
session, calculate the achieved rate from the CSI timestamps rather than from
the requested value alone.

## 11. More than one client

Register each associated client before starting measured `csimond`:

```sh
wl -i "$IFACE" csimon add CLIENT_MAC_1 "$INTERVAL_MS"
wl -i "$IFACE" csimon add CLIENT_MAC_2 "$INTERVAL_MS"
```

Remove both at the end:

```sh
wl -i "$IFACE" csimon del CLIENT_MAC_1
wl -i "$IFACE" csimon del CLIENT_MAC_2
```

Records from both clients share one output stream. The parsed `client_mac`
field identifies the client for each record. Run one keep-alive process per
phone when the experiment requires keep-alive traffic, and save separate logs.
