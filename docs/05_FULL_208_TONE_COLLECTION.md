# Collect all 208 active CSI tones

## Why the full-record collector is used

The tested AP used an 80 MHz channel, one client transmit stream, four AP
receive streams, and zero tone decimation. Its CSI configuration header reports
208 active tones. These are the active CSI tones reported by this firmware, not
all 256 FFT bins of an 80 MHz OFDM symbol.

The HPE-native command below displayed 2,048 bytes from each CSI payload:

```sh
/aruba/bin/csimond 23 64 1 > capture.txt 2>&1 &
```

The first 96 bytes are the record header. Each tone then uses 16 bytes in the
tested 1x4 layout:

```text
4 receive streams x (I int16 + Q int16) = 16 bytes per tone
(2,048 - 96) / 16 = 122 complete displayed tones
```

This is why the corresponding HPE parser JSON contained 122 `csi_data` entries
even though `config.num_active_tones` reported 208.

The CSI driver delivers an 8,208-byte netlink message:

```text
16-byte Linux netlink header + 8,192-byte CSI payload
```

`tools/csi_raw_capture.c` binds to the same CSI netlink stream, removes only the
16-byte Linux netlink header, and writes the full 8,192-byte payload unchanged.
It does not modify CSI generation, packet timing, firmware, `csimond`, or I/Q
samples. Retaining the full payload makes all 208 configured active tones
available. The first tone starts at payload byte 96, and the 208-tone 1x4 I/Q
region occupies 3,328 bytes.

## Files added for full-record collection

| File | Purpose |
|---|---|
| `tools/csi_raw_capture.c` | Collector source code |
| `tools/csi_raw_capture.arm` | Statically linked 32-bit ARM AP executable |
| `tools/run_csi_capture_on_ap.sh` | Bounded capture and cleanup script |
| `tools/decode_raw_capture.py` | Validated local format-1 decoder |

The HPE-provided `wl` command still configures and registers CSI clients. The
new collector replaces only the output stage normally handled by `csimond`.

## Build the collector

On an Ubuntu/Debian research PC:

```bash
sudo apt install gcc-arm-linux-gnueabihf
arm-linux-gnueabihf-gcc -O2 -static -Wall -Wextra \
  -o tools/csi_raw_capture.arm tools/csi_raw_capture.c
sha256sum tools/csi_raw_capture.arm
```

The tested binary hash is:

```text
42bb89fb8ce68b3f8afdf7ec01093d538c2884314721fbd4a3662e77ff5a4151
```

## Install the collector in the AP temporary directory

From the `Aruba_Share` directory on the PC, serve the repository over the AP
management network:

```bash
PC_LAN_IP=192.168.10.1
python3 -m http.server 8000 --bind "$PC_LAN_IP"
```

In a separate terminal, SSH to the AP and enter `support`. Then run:

```sh
mkdir -p /tmp/csi_tools
wget -O /tmp/csi_tools/csi_raw_capture \
  http://192.168.10.1:8000/tools/csi_raw_capture.arm
wget -O /tmp/csi_tools/run_csi_capture_on_ap.sh \
  http://192.168.10.1:8000/tools/run_csi_capture_on_ap.sh
chmod 755 /tmp/csi_tools/csi_raw_capture
chmod 755 /tmp/csi_tools/run_csi_capture_on_ap.sh
```

`/tmp` is cleared when the AP reboots, so installation is repeated after a
reboot. Stop the PC HTTP server after both files are copied.

## Record the association before collection

From the normal AP CLI:

```text
show ap association
```

Record the client MAC, BSSID, band, channel width, and current client IP. The
tested 10-second run used:

| Item | Value |
|---|---|
| AP IP | `192.168.10.114` |
| AP radio | `aruba000` |
| Netlink subsystem | `23` |
| Client | Samsung S21 FE |
| Client IP | `192.168.10.79` |
| Client MAC | `52:12:a6:cc:bc:1a` |
| BSSID | `94:ff:06:26:f3:20` |
| Channel width | 80 MHz |
| Requested interval | 33 ms, approximately 30.3 Hz |
| Measured duration | 10 seconds |
| Tone decimation | 0 |

## Start the phone keep-alive traffic

On the PC, create the dataset directory and start 100-Hz ICMP traffic to keep
the phone's Wi-Fi link active:

```bash
DATASET_DIR="$PWD/data/SESSION_NAME"
mkdir -p "$DATASET_DIR"
KEEPALIVE_LOG="$DATASET_DIR/keepalive-ping.log"
ping -n -i 0.01 192.168.10.79 > "$KEEPALIVE_LOG" 2>&1 &
KEEPALIVE_PID=$!
```

The ping rate is only keep-alive traffic. CSI timing is controlled by the
`csimon add` interval and measured from embedded CSI timestamps.

## Run the same 10-second, 33-ms CSI configuration

Enter `support` on the AP, then run:

```sh
CSI_OUTPUT_MODE=binary CSI_DRAIN_ACTIVE_S=3 \
  /tmp/csi_tools/run_csi_capture_on_ap.sh \
  aruba000 23 33 10 \
  /tmp/DATE_TIME_Samsung-S21FE_33ms-30.3Hz_10s_full208.bin \
  52:12:a6:cc:bc:1a
```

The script performs these actions:

1. deletes earlier client registrations and disables CSI;
2. starts an active discard receiver to drain pending records;
3. enables CSI and runs `wl -i aruba000 csi_deci 0`;
4. registers the phone at 33 ms during the drain;
5. switches directly to the measured full-record collector;
6. captures for 10 seconds and prints initial/final driver counters;
7. deletes the registration, disables CSI, stops the collector, and validates
   the binary size.

After capture, stop the keep-alive process on the PC:

```bash
kill -INT "$KEEPALIVE_PID"
wait "$KEEPALIVE_PID" || true
tail -n 5 "$KEEPALIVE_LOG"
```

## Transfer and verify the binary

Start a PC listener:

```bash
nc -l 9005 > "$DATASET_DIR/CAPTURE.bin"
```

Send the AP file from the support shell:

```sh
md5sum /tmp/CAPTURE.bin
/usr/sbin/netcat -w 5 192.168.10.1 9005 < /tmp/CAPTURE.bin
```

Stop the PC listener if it remains open after all bytes arrive. Verify the PC
copy before removing the AP temporary copy:

```bash
wc -c "$DATASET_DIR/CAPTURE.bin"
md5sum "$DATASET_DIR/CAPTURE.bin"
sha256sum "$DATASET_DIR/CAPTURE.bin"
```

The byte count must be nonzero and divisible by 8,192. The AP and PC MD5 values
must match.

## Decode and check all 208 tones

Install local dependencies once:

```bash
python3 -m pip install -r requirements.txt
```

Decode the full binary:

```bash
python3 tools/decode_raw_capture.py \
  "$DATASET_DIR/CAPTURE.bin" \
  "$DATASET_DIR/CAPTURE.npz"
```

Inspect the array shape:

```bash
python3 - <<'PY'
import numpy as np
with np.load("data/SESSION_NAME/CAPTURE.npz") as data:
    print(data["csi"].shape)
    print(data["tone_index"][[0, -1]])
PY
```

For a successful single-client run with 208 tones and four AP receive streams,
the shape is `(records, 208, 4)` and the reported tone indices are 0 through
207.

## Prepare the same records for the HPE CSI Parser

The research binary is a byte-for-byte concatenation of complete 8,192-byte
payloads. This is the lowest-overhead capture format, but a plain binary file
does not provide the HPE website with multi-record boundaries. In testing, a
concatenated binary upload could be accepted while only one record appeared in
the downloaded JSON.

The multi-record path uses the parser's recognized text boundary before every
record:

```text
CSI record:
```

`prepare_hpe_parser_chunks.py` converts the exact captured binary records into
this framing. Every text record contains all 2,048 little-endian words from its
8,192-byte source payload. The tool reconstructs the binary bytes from every
finished text chunk and requires an exact match before marking the part as
verified.

Create small upload parts from the unchanged research binary:

```bash
python3 tools/prepare_hpe_parser_chunks.py \
  "$DATASET_DIR/CAPTURE.bin" \
  "$DATASET_DIR/hpe-parser-chunks-100" \
  --records-per-file 100
```

One hundred full records produce a 2,279,600-byte text part. During the tested
upload, this file received HTTP status 413 before parsing. The 100-record files
remain available as a record-aligned archive. A separate upload set uses 20
records per file, producing a maximum file size of 455,920 bytes:

```bash
python3 tools/prepare_hpe_parser_chunks.py \
  "$DATASET_DIR/CAPTURE.bin" \
  "$DATASET_DIR/hpe-parser-upload-chunks-20" \
  --records-per-file 20
```

Upload each file from `hpe-parser-upload-chunks-20` to
<https://tmelabs.arubanetworks.com/> in part-number order. The parser should
report 20 records for each full part and 14 records for the final part. Each
downloaded record should report:

```text
num_active_tones: 208
rxstreams: 4
tone_decimation: 0
```

Save every downloaded JSON beside its corresponding text part while retaining
the source stem and adding `-parsed.json`. Merge the downloads:

```bash
python3 tools/process_hpe_parser_json.py \
  "$DATASET_DIR"/hpe-parser-upload-chunks-20/*-parsed.json \
  --output-stem "$DATASET_DIR/CAPTURE-hpe-parsed"
```

Compare every HPE-decoded complex value against the local decoding:

```bash
python3 tools/compare_decoded_npz.py \
  "$DATASET_DIR/CAPTURE.npz" \
  "$DATASET_DIR/CAPTURE-hpe-parsed.npz" \
  --output-json "$DATASET_DIR/local-vs-hpe-comparison.json"
```

With matching record counts, the comparison aligns the complete arrays in
source order and requires exact I/Q equality by default.

## Result from the repeated ten-second test

The same phone and CSI configuration used for the 122-tone native test were
repeated with the full-record collector:

| Check | Result |
|---|---:|
| Measured AP transfers | 294 |
| Complete 8,192-byte records | 294 |
| Binary size | 2,408,448 bytes |
| Decoded CSI shape | `(294, 208, 4)` |
| Active tones per retained record | 208 |
| Narrow-band records removed | 0 |
| Duplicate records removed | 0 |
| CSI timestamp span | 9.965710 s |
| Achieved timestamp rate | 29.400815 Hz |
| ACK failures during measurement | 0 |
| Record overflows during measurement | 0 |
| DDR transfer failures during measurement | 0 |

The same 294 raw records were converted into three 100-record archive parts:
two parts contain 100 records and the final part contains 94. Every part passed an
exact text-to-binary round-trip check. The original binary SHA-256 remains
`1d6259a9e16e048dc224e214af8c9ab068e09d6b08479ff3e1112430a05bf52b`.

The first 100-record, 2,279,600-byte text part returned HTTP status 413 during
website upload. The same records were also prepared as fifteen upload parts:
fourteen contain 20 records and the final part contains 14. Every smaller part
also passed exact text-to-binary round-trip verification.

The capture contains only client `52:12:a6:cc:bc:1a` and BSSID
`94:ff:06:26:f3:20`. CSI monitoring was disabled and the client registration
was removed after the capture.
