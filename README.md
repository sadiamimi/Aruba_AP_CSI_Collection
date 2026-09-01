# HPE Aruba AP-755 CSI setup and collection

This folder contains the tested procedure for preparing an HPE Aruba AP-755,
associating a client, collecting CSI, and processing the saved capture. It
documents both the HPE `csimond` text path, which displayed 122 CSI tones in
the tested 1x4 configuration, and a full-record collector that retained all
208 configured active tones. The collector does not edit the firmware,
`csimond`, or CSI values.

## Start here

Follow the documents in this order:

1. [AP setup](docs/01_AP_SETUP.md)
2. [CSI collection](docs/02_CSI_COLLECTION.md)
3. [Parsing and data checks](docs/03_PARSE_AND_CHECK.md)
4. [Tested configuration and findings](docs/04_TESTED_CONFIGURATION.md)
5. [Collect all 208 active tones](docs/05_FULL_208_TONE_COLLECTION.md)

Use [the experiment record template](docs/EXPERIMENT_RECORD_TEMPLATE.md) as a
checklist for each new collection session. General instructions remain under
`docs`; measurement artifacts are stored under [`data`](data/README.md), which
indexes the two capture sessions and states what each one contains. The original
HPE guide is retained unchanged at
[`reference/CSI_User_Guide_Final.docx`](reference/CSI_User_Guide_Final.docx).

## Required components

- HPE Aruba AP-755 with the experimental CSI image
- DC power adapter or a compatible PoE source
- Ethernet network with DHCP
- PC on the AP management network
- Wi-Fi client associated to the AP
- SSH access to the AP
- Linux `ping`, `nc`, `md5sum`, and `sha256sum` on the research PC
- HPE CSI Parser: <https://tmelabs.arubanetworks.com/>
- ARM cross-compiler when rebuilding the included full-record collector

The local command requirements and the policy for adding future helpers are
documented under [`tools`](tools/README.md).

The tested AP image identifies itself as:

```text
AOS-10 (MODEL: 755), Version 10.8.1.0 LSR
This is an experimental build for test purposes
build elferkou_csimond
```

The CSI image must provide these HPE programs:

```text
/bin/wl
/aruba/bin/csimond
```

## Tested signal path

The phone associates to the AP's WPA3 SSID. The HPE `csimon` function schedules
the client measurement exchange, the AP receives the response, and the AP
radio produces CSI records. `csimond` receives those records through the
firmware's netlink interface and writes them as text when payload display is
enabled.

The AP's Ethernet connection carries management traffic and provides the path
to the upstream DHCP network. It is separate from the measured Wi-Fi link.

## Tested command adjustments

The original guide remains the reference. The following values were selected
during the AP-755 test so that the output could be saved and uploaded:

| Item | Guide example | Tested value | Reason for the tested value |
|---|---|---|---|
| 5 GHz netlink ID | `22` | `23` | This image delivered `aruba000` records on netlink subsystem 23. |
| `csimond` record-size argument | `0` | `64` | The tested executable reported an effective 2,048-byte payload display and printed `CSI record:` blocks. |
| `csimond` message-frequency argument | `1000` | `1` | Every received record was displayed during the short test. |
| Output destination | terminal/background | `> capture.txt 2>&1` | The displayed records were saved to a file. |
| Experiment duration | continuous | bounded with `sleep` and `kill` | Each dataset has a defined duration. |
| Tone decimation | automation example `0` | `0` | No tone decimation was requested. |

With `csimond 23 64 1`, each complete displayed record contains the 96-byte
header followed by 122 complete tones for the tested one-transmit/four-receive
stream configuration. The header reports the configured 80 MHz value of 208
active tones. The actual number of decoded values must therefore be checked
with `len(csi_data)` in the downloaded JSON.

The [tested-configuration notes](docs/04_TESTED_CONFIGURATION.md) record the
commands that were tested and what was observed. The full-record procedure and
the reason for using it are documented separately in
[Collect all 208 active tones](docs/05_FULL_208_TONE_COLLECTION.md). Measurement
artifacts are stored under [`data`](data/).
