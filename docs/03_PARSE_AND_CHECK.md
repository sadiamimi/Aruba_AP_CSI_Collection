# Parse and check the CSI data

## 1. Preserve the native file

Keep the text file transferred from the AP unchanged. Record its byte count and
checksum in the experiment notes:

```bash
wc -c capture.txt
md5sum capture.txt
sha256sum capture.txt
grep -c '^CSI record:$' capture.txt
```

Run the local framing and timestamp check before upload:

```bash
python3 tools/check_native_csimond.py capture.txt \
  --output-json native-csimond-check.json
```

This checker does not decode I/Q. It confirms that the saved file contains the
expected client, BSSID, HPE text blocks, and timestamp rate.

## 2. Upload to the HPE CSI Parser

Open:

<https://tmelabs.arubanetworks.com/>

If the complete native text file returns HTTP status 413, create
record-aligned chunks containing at most 100 records:

```bash
python3 tools/split_native_csimond.py capture.txt parser-chunks-100 \
  --records-per-file 100
```

Upload the numbered chunk files in part order. `manifest.json` records the
source record range, byte count, and SHA-256 hash of every upload file. Keep the
unchanged complete source capture; chunks are derived upload artifacts.

Save each downloaded JSON beside its corresponding chunk using the same stem
plus `-parsed.json`. Verify that parts 001 and 002 each produce 100 records.
The final part contains the remaining source records; if collection stopped
during its last displayed block, that last parsed record can contain fewer
tones than the other records.

Merge all downloaded parts and create analysis files:

```bash
python3 -m pip install -r requirements.txt
python3 tools/process_hpe_parser_json.py \
  parser-chunks-100/*-parsed.json \
  --output-stem CAPTURE-parsed
```

This creates `CAPTURE-parsed.json`, `CAPTURE-parsed.npz`, and
`CAPTURE-parsed.csv` with the same record order. The merged JSON keeps every
record. NPZ uses complex NaN and CSV uses blank I/Q cells only where a partial
final parser record did not contain those tones; `actual_tone_count` records
the number available in each row.

Create the channel-frequency-response and CSI-deviation plots:

```bash
python3 tools/plot_hpe_csi.py CAPTURE-parsed.npz plots
```

Only complete records are plotted. The channel-frequency response uses raw HPE
I/Q magnitude and relative phase versus reported tone index. The deviation
plot removes per-packet gain and each tone's time mean, then uses embedded CSI
timestamps for the horizontal axis.

Upload the native `.txt` capture and wait for the parse summary. Download the
parsed JSON directly into the same new dataset directory, using the source
filename plus `-parsed.json`:

```text
capture.txt
capture-parsed.json
```

The page's detected-record count should be compared with the number of
`CSI record:` markers in the source text.

## 3. Check the downloaded JSON

For each parsed record, check:

- `client_mac` matches an associated client;
- `bssid` matches the experiment BSSID;
- `rxstreams` and `txstreams` match the tested radio exchange;
- `config.tone_decimation` is zero;
- `config.num_active_tones` reports the configured tone count;
- the number of entries actually present in `csi_data` is recorded separately;
- `report_timestamp` or `timestamp_s` advances through the selected session.

For the tested 5 GHz/80 MHz/one-transmit/four-receive-stream configuration,
the header reports 208 active tones. HPE native text produced by
`csimond NETLINK_ID 64 1` displays 2,048 payload bytes. After its 96-byte
header, that is 122 complete tones:

```text
(2048 - 96) / (4 receive streams x I/Q x 2 bytes) = 122 tones
```

The parser summary can therefore show 208 from the record configuration while
the downloaded `csi_data` array contains 122 entries. Use the JSON array length
when reporting how many tone values were available for analysis.

To retain all 208 configured active tones rather than the 122 tones present in
this text display, follow
[Collect all 208 active tones](05_FULL_208_TONE_COLLECTION.md).

## 4. Interpret the I/Q values

Each `csi_data` entry represents one tone and contains the I/Q values for the
receive streams decoded by the HPE parser. For one complex value:

```text
H = I + jQ
amplitude = sqrt(I^2 + Q^2)
phase = atan2(Q, I)
```

Retain the downloaded JSON as the HPE-decoded result. Keep the original native
text and JSON together under one dataset directory with the experiment notes
and checksums.

After downloading the JSON, refresh the dataset checksums from inside its
directory:

```bash
sha256sum *.txt *.json keepalive-ping.log > SHA256SUMS
sha256sum -c SHA256SUMS
```

If keep-alive was not used, omit `keepalive-ping.log` from the first command.

## 5. Dataset naming

Use a filename containing the collection time and essential parameters:

```text
YYYY-MM-DD_HH-MM-SS_TZ_PHONE_INTERVAL-RATE_DURATION_
HPE-native-csimond_clientIP-CLIENT_IP_APIP-AP_IP.txt
```

Example:

```text
2026-09-01_16-34-00_EDT_Samsung-S21FE_1000ms-1Hz_10s_
HPE-native-csimond_clientIP-192.168.10.79_APIP-192.168.10.114.txt
```

Use the same stem for the downloaded JSON.

## 6. Final session contents

A complete new dataset directory contains:

```text
keepalive-ping.log                 # when keep-alive was used
...HPE-native-csimond.txt          # unchanged AP output
native-csimond-check.json          # local framing/timing report
parser-chunks-100/                 # upload chunks and downloaded part JSON
...HPE-native-csimond-parsed.json  # merged HPE parser records
...HPE-native-csimond-parsed.npz   # complex CSI array and metadata
...HPE-native-csimond-parsed.csv   # fixed-point wide table
SHA256SUMS
```

General commands, instructions, and experiment templates remain under `docs`.
Check that no file from another session is present before sharing the dataset.
