# CSI experiment record

## Session

| Field | Value |
|---|---|
| Date and local time | |
| Operator | |
| Experiment name | |
| Duration | |
| Requested interval | |
| Requested rate | |
| Phone keep-alive used | yes / no |
| Keep-alive command | `ping -n -i 0.01 CLIENT_IP` / not used |

## AP

| Field | Value |
|---|---|
| Model | AP-755 |
| Serial | |
| LAN MAC | |
| Management IPv4 | |
| Firmware version/build | |
| Radio interface | |
| Netlink ID | |
| SSID | |
| BSSID | |
| Band/channel/width | |
| Tone decimation | 0 |

## Client

| Field | Value |
|---|---|
| Device name/model | |
| MAC shown by AP | |
| IPv4 | |
| Position/orientation | |
| Activity during capture | |

## HPE commands

```text
wl -i RADIO csimon enable
wl -i RADIO csi_deci 0
wl -i RADIO csimon add CLIENT_MAC INTERVAL_MS
/aruba/bin/csimond NETLINK_ID 64 1 > OUTPUT.txt 2>&1 &
```

## Counters

| Counter | Before | After |
|---|---:|---:|
| `null_frm_cnt` | | |
| `xfer_to_ddr_cnt` | | |
| `ack_fail_cnt` | | |
| `rec_ovfl_cnt` | | |
| `xfer_to_ddr_fail_cnt` | | |

## Files and parser result

| Field | Value |
|---|---|
| Native text filename | |
| Native byte count | |
| Native MD5 | |
| Native SHA-256 | |
| `CSI record:` marker count | |
| Parsed JSON filename | |
| HPE parser record count | |
| Configured active tones | |
| Actual `csi_data` lengths | |
| RX/TX streams | |
| Ping packets transmitted/replied | |
| Ping packet loss | |
| Ping mean RTT | |
| Ping elapsed time | |

## Notes
