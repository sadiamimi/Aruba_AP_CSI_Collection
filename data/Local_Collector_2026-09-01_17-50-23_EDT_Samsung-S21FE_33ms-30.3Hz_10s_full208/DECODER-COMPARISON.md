# HPE parser and local decoder, compared

Both decoders were run on the same 10-second, 294-record, 208-tone capture and
their outputs compared value by value.

## Sources

| | File | Origin |
|---|---|---|
| Local | `....npz` | decoded from `....bin` on this PC |
| HPE | `....hpe-parsed.npz` | 15 parser JSON files merged in part order |

The capture was uploaded in 15 chunks of 20 records because the parser front end
rejects larger uploads. Parts 1 to 14 hold 20 records each and part 15 holds 14,
totalling 294 — the same count the local decoder produced.

```bash
python3 ../../tools/parsed_json_to_npz.py \
  $(ls hpe-parser-upload-chunks-20/*-parsed.json | sort) BASE.hpe-parsed.npz
python3 ../../tools/npz_to_csv.py BASE.hpe-parsed.npz BASE.hpe-parsed.csv
```

## Result

| | |
|---|---:|
| Records compared | 294 of 294 |
| Complex values compared | **244,608** |
| Header field differences | **0** |
| I/Q differences | **0** |
| Largest absolute error | **0.0** |

Matching by embedded report timestamp gave 294 of 294 with none unmatched, and
the two arrays are also bit-identical element by element in capture order:

```text
record order identical (timestamps elementwise): True
csi arrays bit-identical                       : True
client_mac, bssid, rssi_dbm, tone_index        : True
```

Both decoders return 294 records of 208 tones and 4 receive streams, so the
full tone grid is present in each.

## Files

| File | Contents |
|---|---|
| `....hpe-parsed.npz` | 294 x 208 x 4 complex64, merged from the 15 parser JSONs |
| `....hpe-parsed.csv` | 294 rows x 1,674 columns |

The CSV carries `record_index`, `source_record_index`, `report_timestamp_us`,
`client_mac`, `bssid`, `iq_scale`, four RSSI columns, then
`tone000_rx0_I_x64` through `tone207_rx3_Q_x64`. Divide the integer columns by
`iq_scale` (64) to recover the I/Q values.
