# Tested configuration and findings

This document records the commands that were tested and what was observed. No
capture or parsed data from tests performed before creation of `Aruba_Share` is
stored here. A newly collected session is stored under `data`.

## Tested AP and client

| Field | Tested value |
|---|---|
| AP model | HPE Aruba AP-755 |
| AP serial | `USVGM590QB` |
| AP LAN MAC | `94:ff:06:ca:6f:31` |
| AP management IPv4 | `192.168.10.114` |
| Firmware | AOS-10 10.8.1.0 LSR experimental build |
| Build label | `elferkou_csimond` |
| Client | Samsung S21 FE |
| Client MAC reported by AP | `52:12:a6:cc:bc:1a` |
| Client IPv4 | `192.168.10.79` |
| SSID | `wpa3` |
| BSSID | `94:ff:06:26:f3:20` |
| Band/radio | 5 GHz / `aruba000` |
| Channel width | 80 MHz |
| Netlink subsystem | 23 |

The association was checked with:

```text
show ap association
show ap bss-table
support
wl -i aruba000 assoclist
```

## Test 1: guide baseline

The HPE guide's AP-client sequence was tested with a 1,000 ms client interval:

```sh
wl -i aruba000 csimon enable
wl -i aruba000 csi_deci 0
wl -i aruba000 assoclist
wl -i aruba000 csimon add 52:12:a6:cc:bc:1a 1000
/aruba/bin/csimond 23 0 1000 &
wl -i aruba000 csimon state
```

During a ten-second test, the AP counter showed 12 transferred CSI records.
The `csimond` record-size value of zero produced receipt reporting rather than
CSI payload text. The 1,000-message display threshold was not reached during
the short test.

## Test 2: saved native payload text

The same HPE components were tested with:

```sh
/aruba/bin/csimond 23 64 1 > CAPTURE.txt 2>&1 &
```

The executable reported:

```text
CSIMOND application started with record size 2048 and message frequency 0
using nl subsystem 23
```

The observed result was:

- native output contained multiple `CSI record:` blocks;
- the HPE web parser recognized the native text blocks as separate records;
- each complete displayed block contained 2,048 payload bytes;
- complete parsed records contained 122 `csi_data` tone entries;
- each retained tone contained four receive-stream I/Q pairs;
- the configuration header reported 208 active tones for 80 MHz and zero
  decimation;
- a final block can contain fewer entries when `csimond` is stopped while that
  block is being displayed.

For this 1x4 stream layout, the observed 122 complete tones follow directly
from the displayed byte count:

```text
(2048 displayed bytes - 96 header bytes) /
(4 receive streams x I/Q x 2 bytes) = 122 tones
```

## Test 3: phone keep-alive

The PC keep-alive command used during the Samsung high-rate phone test was:

```bash
ping -n -i 0.01 192.168.10.79 > keepalive-ping.log 2>&1 &
```

It started before CSI client registration and stopped after the AP capture.
The command requested 100 ICMP packets per second and kept the phone's Wi-Fi
link active. CSI timing continued to be read from CSI record timestamps; the
ping interval was not treated as the CSI interval.

## Values carried into the new procedure

For this AP image, the reproducible HPE-native collection command is:

```sh
/aruba/bin/csimond 23 64 1 > CAPTURE.txt 2>&1 &
```

The new procedure records both values for every parsed record set:

- configured tone count from `config.num_active_tones`;
- actual decoded tone count from the length of `csi_data`.

## New ten-second collection result

The documented procedure was run again with a 33 ms requested interval and a
ten-second measured duration. The PC used this keep-alive command:

```bash
ping -n -i 0.01 192.168.10.79 > keepalive-ping.log 2>&1 &
```

The measured result was:

| Item | Result |
|---|---:|
| Requested CSI rate | 30.303 Hz |
| CSI timestamp span | 9.996229 s |
| Achieved CSI timestamp rate | 29.311053 Hz |
| Measured AP transfers | 294 |
| Native `CSI record:` markers | 294 |
| Complete 2,048-byte displays | 293 |
| Final partial display | 1 |
| Client ACK failures | 0 |
| Record overflows | 0 |
| DDR transfer failures | 0 |

The native file contains only client `52:12:a6:cc:bc:1a` and BSSID
`94:ff:06:26:f3:20`. The AP and PC copies matched at 1,675,264 bytes with MD5
`becf2068abdba10fa2adc8cfc40ac9c5`. The local header/timestamp check reported
minimum, mean, and maximum intervals of 17.250, 34.117, and 85.564 ms.

The new measurement artifacts are stored under:

```text
data/2026-09-01_16-52-23_EDT_Samsung-S21FE_33ms-30.3Hz_10s/
```

## Parser chunk and merge result

The complete 1,675,264-byte native file returned HTTP status 413 during HPE
parser upload. It was split at native `CSI record:` boundaries into:

| Part | Source records | Record count | Bytes |
|---|---|---:|---:|
| 001 | 0–99 | 100 | 570,896 |
| 002 | 100–199 | 100 | 570,896 |
| 003 | 200–293 | 94 | 533,664 |

The HPE parser returned 100, 100, and 94 JSON records respectively. The three
downloads are retained unchanged in `parser-chunks-100/`.

`csimond` was terminated mid-block, so the final source record is incomplete:
its displayed block holds 243 hexadecimal words against the 512 of a complete
display, and the parser decoded 55 tones from it rather than 122. That record
is excluded from the merged outputs, which therefore contain 293 records:

- every record contains 122 decoded tones and four receive streams;
- the merged NPZ has shape `(293, 122, 4)`;
- `actual_tone_count` is 122 throughout and `valid_tone` is true throughout,
  so the array contains no NaN;
- all 143,048 complex I/Q samples were compared between merged JSON and NPZ
  with exact equality.

The raw chunk downloads still contain the incomplete record, so the exclusion
can be reviewed or reversed by re-merging them.

## Channel-response plot result

The plots use the merged NPZ, which contains 293 complete records of 122
displayed tones and four receive streams over a 9.962146-second timestamp
span. The achieved rate over those
complete records was 29.310954 records per second.

The channel-frequency-response plot shows raw CSI magnitude and phase relative
to receive stream 0. The deviation plot removes each packet's overall complex
gain and then removes the time mean for each tone. No timestamp gap exceeded
three times the median interval. The x-axis uses the HPE parser's ordered CSI
tone indices 0 through 121; absolute tone frequencies were not assigned because
the exact mapping from these 122 displayed tones to RF frequencies was not
verified for this build.
