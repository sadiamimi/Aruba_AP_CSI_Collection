#!/usr/bin/env python3
"""Decode validated AP-755 format-1, 80 MHz CSI records into NumPy arrays."""

from __future__ import annotations

import argparse
import hashlib
import struct
from pathlib import Path

import numpy as np


RECORD_BYTES = 8192
FORMAT_ID = 1
CSI_OFFSET = 96
ACTIVE_TONES = 208
RX_STREAMS = 4
IQ_SCALE = 64.0
IQ_VALUES = ACTIVE_TONES * RX_STREAMS * 2

# Configuration word at byte 64. Only the three field positions below were
# cross-checked against HPE's parser output; the remaining bits are not
# interpreted here. PACKET_BW_80 is the value HPE's parser reports as "80 MHz".
CONFIG_OFFSET = 64
PACKET_BW_80 = 2


def mac_address(raw: bytes) -> str:
    return ":".join(f"{byte:02x}" for byte in raw)


def packet_bandwidths(record: bytes) -> tuple[int, int]:
    """Return (sta_packet_bw, ap_packet_bw) from the byte-64 configuration word.

    ap_packet_bw follows the AP's own radio configuration. sta_packet_bw is the
    client's per-frame transmit bandwidth, which its rate adaptation may narrow
    on an individual uplink frame even when the BSS stays at 80 MHz.

    The record buffer is always 8,192 bytes with room for ACTIVE_TONES tones,
    but the driver only writes the tones the received frame actually carried.
    The rest of the buffer retains the previous record's contents, which may
    belong to a different client, so a narrow record silently mixes two
    clients' channel estimates into one apparently well-formed record.
    """
    config = struct.unpack_from("<I", record, CONFIG_OFFSET)[0]
    return (config >> 2) & 0x7, (config >> 5) & 0x7


def decode(
    capture_path: Path, output_path: Path, strict: bool = False
) -> tuple[tuple[int, int, int], list[int]]:
    total_bytes = capture_path.stat().st_size
    remainder = total_bytes % RECORD_BYTES
    if remainder:
        raise ValueError(
            f"{capture_path}: {total_bytes} bytes is not a whole number of "
            f"{RECORD_BYTES}-byte records (remainder {remainder})"
        )
    record_count = total_bytes // RECORD_BYTES
    if record_count == 0:
        raise ValueError("capture contains no records")

    csi = np.empty((record_count, ACTIVE_TONES, RX_STREAMS), dtype=np.complex64)
    report_timestamp_us = np.empty(record_count, dtype=np.uint64)
    assoc_timestamp_us = np.empty(record_count, dtype=np.uint64)
    client_mac = np.empty(record_count, dtype="U17")
    bssid = np.empty(record_count, dtype="U17")
    rssi_dbm = np.empty((record_count, RX_STREAMS), dtype=np.int16)
    chanspec = np.empty(record_count, dtype=np.uint16)
    cfo = np.empty(record_count, dtype=np.uint32)
    source_record_index = np.empty(record_count, dtype=np.uint32)
    source_sha256 = hashlib.sha256()
    narrow_records: list[int] = []
    duplicate_records: list[int] = []
    # The driver occasionally re-delivers a record it has already sent. The
    # repeat is byte-identical, timestamp included, so it is a second copy of
    # one measurement rather than a second measurement.
    seen_digests: set[bytes] = set()
    kept = 0

    with capture_path.open("rb") as source:
        for record_number in range(record_count):
            record = source.read(RECORD_BYTES)
            if len(record) != RECORD_BYTES:
                raise ValueError(f"short read at record {record_number}")
            source_sha256.update(record)

            format_id = struct.unpack_from("<I", record, 0)[0]
            tx_streams = record[18]
            rx_streams = record[19]
            if format_id != FORMAT_ID:
                raise ValueError(
                    f"record {record_number}: format ID {format_id}; expected {FORMAT_ID}"
                )
            if tx_streams != 1 or rx_streams != RX_STREAMS:
                raise ValueError(
                    f"record {record_number}: {tx_streams} TX/{rx_streams} RX streams; "
                    f"decoder is validated for 1 TX/{RX_STREAMS} RX"
                )

            sta_packet_bw, ap_packet_bw = packet_bandwidths(record)
            if ap_packet_bw != PACKET_BW_80:
                raise ValueError(
                    f"record {record_number}: AP packet bandwidth code {ap_packet_bw}; "
                    f"decoder is validated for 80 MHz (code {PACKET_BW_80})"
                )
            if sta_packet_bw != PACKET_BW_80:
                # Only the low tones were measured; the upper tones are a stale
                # copy of an earlier record, possibly another client's. Never
                # emit that as CSI.
                narrow_records.append(record_number)
                if strict:
                    raise ValueError(
                        f"record {record_number}: client packet bandwidth code "
                        f"{sta_packet_bw}, not 80 MHz (code {PACKET_BW_80}); "
                        "its upper tones are stale data from an earlier record"
                    )
                continue

            digest = hashlib.sha256(record).digest()
            if digest in seen_digests:
                duplicate_records.append(record_number)
                if strict:
                    raise ValueError(
                        f"record {record_number} is byte-identical to an earlier "
                        "record; it is a re-delivery of one measurement"
                    )
                continue
            seen_digests.add(digest)

            iq = np.frombuffer(
                record,
                dtype="<i2",
                count=IQ_VALUES,
                offset=CSI_OFFSET,
            ).reshape(ACTIVE_TONES, RX_STREAMS, 2)
            csi[kept].real = iq[:, :, 0] / IQ_SCALE
            csi[kept].imag = iq[:, :, 1] / IQ_SCALE

            client_mac[kept] = mac_address(record[4:10])
            bssid[kept] = mac_address(record[10:16])
            chanspec[kept] = struct.unpack_from("<H", record, 16)[0]
            report_timestamp_us[kept] = struct.unpack_from("<I", record, 20)[0]
            assoc_timestamp_us[kept] = struct.unpack_from("<I", record, 24)[0]
            rssi_dbm[kept, :] = struct.unpack_from("<4b", record, 28)
            cfo[kept] = struct.unpack_from("<I", record, 32)[0]
            source_record_index[kept] = record_number
            kept += 1

    if kept == 0:
        raise ValueError("capture contains no usable 80 MHz client records")

    csi = csi[:kept]
    report_timestamp_us = report_timestamp_us[:kept]
    assoc_timestamp_us = assoc_timestamp_us[:kept]
    client_mac = client_mac[:kept]
    bssid = bssid[:kept]
    rssi_dbm = rssi_dbm[:kept]
    chanspec = chanspec[:kept]
    cfo = cfo[:kept]
    source_record_index = source_record_index[:kept]

    output_path.parent.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(
        output_path,
        csi=csi,
        tone_index=np.arange(ACTIVE_TONES, dtype=np.int32),
        report_timestamp_us=report_timestamp_us,
        assoc_timestamp_us=assoc_timestamp_us,
        client_mac=client_mac,
        bssid=bssid,
        rssi_dbm=rssi_dbm,
        chanspec=chanspec,
        cfo=cfo,
        source_record_index=source_record_index,
        source_record_count=np.array(record_count, dtype=np.uint32),
        dropped_narrow_bandwidth_index=np.array(narrow_records, dtype=np.uint32),
        dropped_duplicate_index=np.array(duplicate_records, dtype=np.uint32),
        source_sha256=np.array(source_sha256.hexdigest()),
        record_bytes=np.array(RECORD_BYTES, dtype=np.uint32),
        csi_offset=np.array(CSI_OFFSET, dtype=np.uint32),
        iq_scale=np.array(IQ_SCALE, dtype=np.float32),
        packet_bandwidth_mhz=np.array(80, dtype=np.uint16),
    )
    return csi.shape, narrow_records, duplicate_records


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("capture", type=Path, help="raw full-record CSI capture")
    parser.add_argument("output_npz", type=Path, help="output compressed NumPy file")
    parser.add_argument(
        "--strict",
        action="store_true",
        help="fail instead of dropping narrow-bandwidth or duplicated records",
    )
    args = parser.parse_args()
    shape, narrow_records, duplicate_records = decode(
        args.capture, args.output_npz, args.strict
    )

    def report(indices: list[int], reason: str) -> None:
        if not indices:
            return
        preview = ", ".join(str(index) for index in indices[:10])
        if len(indices) > 10:
            preview += ", ..."
        print(f"Dropped {len(indices)} record(s) {reason}: {preview}")

    report(narrow_records, "whose client transmitted below 80 MHz")
    report(duplicate_records, "byte-identical to an earlier record")
    print(f"Saved {args.output_npz}: csi shape={shape}, dtype=complex64")


if __name__ == "__main__":
    main()
