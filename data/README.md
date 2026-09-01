# Measurement data

Two capture sessions from the same AP-755 and the same client, recorded on
2026-09-01. They differ in how the CSI record reached the file, and therefore in
how many of the 208 configured tones survived.

| Field | Value |
|---|---|
| AP | AP-755, `build elferkou_csimond` |
| BSSID | `94:ff:06:26:f3:20` |
| Client | Samsung Galaxy S21 FE, `52:12:a6:cc:bc:1a` |
| Radio | `aruba000`, 5 GHz, 80 MHz |
| Netlink subsystem | `23` |
| Tone decimation | `0` |
| Requested interval | 33 ms |
| Configured active tones | 208 |

## `HPE_ARUBA_2026-09-01_16-52-23_.../`

HPE's `csimond` text path, collected with `csimond 23 64 1`.

The source text holds 294 `CSI record:` markers, of which 293 are complete
2,048-byte displays. `csimond` was terminated mid-block, so the final marker
holds 243 hexadecimal words instead of 512; the parser decoded 55 tones from it
rather than 122. That record is excluded from the merged outputs.

| | |
|---|---:|
| Records in merged outputs | 293 |
| **Tones per record** | **122** of 208 |
| Receive streams | 4 |

Contents: the unchanged `.txt`, the three raw parser downloads in
`parser-chunks-100/` (uploaded separately because the parser rejects the whole
file), the merged `-parsed.json` / `.npz` / `.csv`, plots, the ping log, and
`native-csimond-check.json` with the structural and timing summary.

The raw chunk downloads still contain the incomplete record, so the exclusion
can be reviewed or reversed by re-merging them.

## `Local_Collector__2026-09-01_17-50-23_..._full208/`

The full-record collector, writing complete 8,192-byte payloads.

| | |
|---|---:|
| Records | 294 |
| **Tones per record** | **208** of 208 |
| Receive streams | 4 |

Contents: the raw `.bin`, the locally decoded `.npz`, the same capture uploaded
in 15 chunks with their parser JSON in `hpe-parser-upload-chunks-20/`, the
merged `.hpe-parsed.npz` / `.csv`, plots, logs, `capture-summary.json`, and
`DECODER-COMPARISON.md`.

Both decoders were compared value by value on this capture: 294 of 294 records,
244,608 complex values, zero differences. See `DECODER-COMPARISON.md`.

## The difference between them

| | `csimond` text | full-record collector |
|---|---:|---:|
| Payload bytes per record | 2,048 | 8,192 |
| Tones per record | 122 | **208** |
| Frequency coverage | lower 122 of 208 | full 80 MHz |

Both paths decode the same byte layout and agree on the tones they share. The
tone count follows from how many payload bytes reached the file: the CSI region
starts at byte 96 and each tone occupies 16 bytes, so `(2048 - 96) / 16 = 122`
and `(3424 - 96) / 16 = 208`. See
[the tested configuration](../docs/04_TESTED_CONFIGURATION.md) and
[collecting all 208 tones](../docs/05_FULL_208_TONE_COLLECTION.md).

## Checking integrity

Each dataset directory carries a `SHA256SUMS` covering every file in it:

```bash
cd <dataset directory> && sha256sum -c SHA256SUMS
```
