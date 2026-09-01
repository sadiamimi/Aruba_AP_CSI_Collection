# Local tools

The HPE-native 122-tone text procedure uses the HPE-provided `wl` and
`/aruba/bin/csimond` programs. The 208-tone procedure additionally uses the
included full-record collector, AP run script, and validated local decoder.
The following standard Linux commands are used on the research PC:

```text
ssh
ping
nc
ps
mkdir
cp
wc
tail
md5sum
sha256sum
```

Check their availability with:

```bash
command -v ssh ping nc ps mkdir cp wc tail md5sum sha256sum
```

The AP support shell uses the HPE `wl` and `csimond` programs together with
its built-in `sleep`, `kill`, `wait`, `grep`, `ls`, `sync`, `rm`, `md5sum`, and
`netcat` commands. These are invoked directly in the collection instructions;
the full-record collector is the only additional AP executable stored here.

Any local helper introduced for a future collection or processing step must be
stored in this directory. Its README entry must state:

- what it does;
- its exact command line;
- its inputs and outputs;
- why the HPE guide commands alone do not perform that step;
- how its output was checked.

## `csi_raw_capture.c` and `csi_raw_capture.arm`

`csi_raw_capture.c` is the source of the AP-side full-record collector. The
included `csi_raw_capture.arm` is its statically linked 32-bit ARM build. The
collector binds to the selected CSI netlink subsystem and multicast group 2,
removes the 16-byte Linux netlink header, and saves each 8,192-byte CSI payload
without changing it. Binary mode is used for research capture; `--hpe-text`
can represent a short full record using the HPE parser's `CSI record:` text
framing.

Build on an Ubuntu/Debian PC:

```bash
sudo apt install gcc-arm-linux-gnueabihf
arm-linux-gnueabihf-gcc -O2 -static -Wall -Wextra \
  -o tools/csi_raw_capture.arm tools/csi_raw_capture.c
```

The tested ARM binary has SHA-256
`42bb89fb8ce68b3f8afdf7ec01093d538c2884314721fbd4a3662e77ff5a4151`.
The source and binary are included because `csimond 23 64 1` displayed 2,048
payload bytes, enough for 122 tones in the tested 1x4 layout, while the driver
delivered an 8,192-byte payload containing all 208 active tones.

## `run_csi_capture_on_ap.sh`

This script runs in the AP support shell. It drains pending netlink records,
sets `csi_deci 0`, continuously registers the selected client, captures for a
bounded duration, records driver counters, stops CSI, and validates that binary
output is a multiple of 8,192 bytes.

```sh
/tmp/csi_tools/run_csi_capture_on_ap.sh \
  RADIO NETLINK_ID INTERVAL_MS DURATION_S OUTPUT.bin CLIENT_MAC
```

The tested 10-second command is shown in
[`docs/05_FULL_208_TONE_COLLECTION.md`](../docs/05_FULL_208_TONE_COLLECTION.md).

## `decode_raw_capture.py`

This decoder reads complete 8,192-byte format-1 records from the tested AP-755
80 MHz, 1 TX/4 RX layout and writes a compressed NPZ. It decodes 208 tones,
preserves source record indices and timestamps, and reports narrow-band client
frames or byte-identical re-deliveries instead of treating them as independent
full-band measurements.

```bash
python3 tools/decode_raw_capture.py CAPTURE.bin CAPTURE.npz
```

The implementation was checked sample-for-sample against HPE parser output for
a complete 208-tone record. The new ten-second capture decoded to shape
`(294, 208, 4)` with no narrow-band or duplicate records removed.

## `prepare_hpe_parser_chunks.py`

This tool converts the unchanged full-record binary into HPE multi-record text
files. It places `CSI record:` before every 8,192-byte payload, writes all 2,048
little-endian words, and splits the result into small upload parts. Each text
part is parsed back to bytes and compared exactly with its source range. A JSON
manifest records ranges, sizes, hashes, and the round-trip result.

```bash
python3 tools/prepare_hpe_parser_chunks.py CAPTURE.bin OUTPUT_DIR \
  --records-per-file 100
```

This derived format is used because the HPE website recognizes multi-record
text boundaries, while a plain concatenation of binary payloads does not carry
website-level record framing.

The default remains 100 records per file. In the tested full-record dataset,
that produced a 2,279,600-byte file and the website returned HTTP status 413.
Use `--records-per-file 20` for the 455,920-byte upload set while retaining the
100-record archive.

## `compare_decoded_npz.py`

After HPE parser JSON parts are merged with `process_hpe_parser_json.py`, this
tool compares the HPE-decoded CSI array and metadata with the local full-record
decode. Equal-length datasets are compared in source order. The default
absolute tolerance is zero.

```bash
python3 tools/compare_decoded_npz.py LOCAL.npz HPE.npz \
  --output-json local-vs-hpe-comparison.json
```

## `check_native_csimond.py`

This local checker reads a finished HPE native text capture. It counts
`CSI record:` blocks, checks their displayed byte lengths, reads identity and
timing fields from the record headers, and calculates the achieved timestamp
rate. It does not receive CSI from the AP and does not decode I/Q values.

Run it from the `Aruba_Share` directory:

```bash
python3 tools/check_native_csimond.py data/SESSION/CAPTURE.txt \
  --output-json data/SESSION/native-csimond-check.json
```

Input: the unchanged `.txt` file written by HPE `csimond`.

Outputs: a terminal summary and an optional JSON check report. This check is
local because the HPE web parser supplies decoded CSI but does not create a
local source-file framing and timing report. The checker result is compared
with the AP's marker count, association MAC/BSSID, requested duration, and
driver transfer counters.

## `split_native_csimond.py`

This local tool splits an unchanged HPE native text capture only at
`CSI record:` boundaries. It repeats the original `csimond` startup prefix in
each output file, keeps every record block byte-for-byte, and creates a JSON
manifest containing source record ranges, sizes, and SHA-256 hashes.

Create files containing at most 100 records:

```bash
python3 tools/split_native_csimond.py data/SESSION/CAPTURE.txt \
  data/SESSION/parser-chunks-100 --records-per-file 100
```

Input: the unchanged HPE native `.txt` capture.

Outputs: numbered `.txt` chunks and `manifest.json`. The HPE parser upload
returned HTTP 413 for the complete 1.6 MB test capture, so smaller
record-aligned files are used for upload. The tool verifies internally that the
chunk record blocks reconstruct the original source byte-for-byte.

## `process_hpe_parser_json.py`

This tool orders HPE parser JSON parts by their part/range filenames, validates
that the ranges are continuous, merges every record, and writes matching JSON,
NPZ, and CSV files. Install NumPy first:

```bash
python3 -m pip install -r requirements.txt
```

Run from `Aruba_Share`:

```bash
python3 tools/process_hpe_parser_json.py \
  data/SESSION/parser-chunks-100/*-parsed.json \
  --output-stem data/SESSION/CAPTURE-parsed
```

The merged JSON retains all parser records and assigns global record numbers
and source indices. The NPZ uses `csi[record, tone, receive_stream]` and keeps
all records. Unavailable tones in a partial record are complex NaN and are
identified by `valid_tone` and `actual_tone_count`. The CSV uses fixed-point
I/Q columns scaled by 64 and leaves unavailable final-record cells blank.

## `plot_hpe_csi.py`

This tool creates a channel-frequency-response figure and a CSI magnitude-
deviation figure from the merged NPZ. It automatically excludes partial
records, sorts by embedded CSI timestamp, and uses only the client present in
the selected data.

```bash
python3 tools/plot_hpe_csi.py data/SESSION/CAPTURE-parsed.npz \
  data/SESSION/plots
```

The frequency-response figure uses the raw HPE I/Q magnitude and phase relative
to RX stream 0. Its x-axis is the HPE-reported, frequency-ordered tone index;
an absolute frequency is not inferred without a verified tone-to-frequency
mapping. The deviation plot removes per-packet gain, centres each tone on its
time mean, and breaks traces when an interval exceeds three times the median.
