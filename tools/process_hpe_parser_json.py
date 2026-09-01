#!/usr/bin/env python3
"""Merge HPE parser JSON parts and create aligned NPZ and CSV outputs."""

from __future__ import annotations

import argparse
import csv
import json
import re
from pathlib import Path
from typing import Any

import numpy as np


PART_RE = re.compile(
    r"\.part-(?P<part>\d+)\.records-(?P<start>\d+)-(?P<end>\d+)-parsed\.json$"
)
IQ_SCALE = 64


def extract_records(document: Any) -> list[dict[str, Any]]:
    if isinstance(document, list):
        records = document
    elif isinstance(document, dict):
        records = None
        for key in ("records", "data", "csi_records"):
            value = document.get(key)
            if isinstance(value, list):
                records = value
                break
        if records is None and all(
            key in document for key in ("header", "config", "csi_data")
        ):
            records = [document]
        if records is None:
            raise ValueError("unsupported HPE parser JSON object")
    else:
        raise ValueError("JSON root must be an object or list")

    if not records or not all(isinstance(record, dict) for record in records):
        raise ValueError("JSON contains no valid CSI records")
    return records


def input_metadata(path: Path) -> tuple[int, int, int]:
    match = PART_RE.search(path.name)
    if not match:
        raise ValueError(f"input filename has no part/range metadata: {path.name}")
    return tuple(int(match.group(key)) for key in ("part", "start", "end"))


def mac(value: Any) -> str:
    return str(value or "").lower()


def fixed_iq(value: float) -> int:
    scaled = round(value * IQ_SCALE)
    if abs(value - scaled / IQ_SCALE) > 1e-7:
        raise ValueError(f"I/Q value {value} is not on the 1/{IQ_SCALE} grid")
    if not -32768 <= scaled <= 32767:
        raise ValueError(f"scaled I/Q value {scaled} is outside int16")
    return int(scaled)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input_json", nargs="+", type=Path)
    parser.add_argument(
        "--output-stem",
        required=True,
        type=Path,
        help="path used for OUTPUT.json, OUTPUT.npz, and OUTPUT.csv",
    )
    args = parser.parse_args()

    inputs = sorted(
        ((input_metadata(path), path) for path in args.input_json),
        key=lambda item: item[0][0],
    )
    if len({metadata[0] for metadata, _ in inputs}) != len(inputs):
        raise ValueError("duplicate part number")

    merged_records: list[dict[str, Any]] = []
    source_indices: list[int] = []
    source_parts: list[int] = []
    source_chunk_records: list[int] = []
    expected_start = 0

    for (part, start, end), path in inputs:
        if start != expected_start:
            raise ValueError(
                f"part {part} starts at {start}; expected source record {expected_start}"
            )
        records = extract_records(json.loads(path.read_text()))
        expected_count = end - start + 1
        if len(records) != expected_count:
            raise ValueError(
                f"part {part} contains {len(records)} records; expected {expected_count}"
            )

        for chunk_offset, record in enumerate(records):
            global_index = start + chunk_offset
            merged = dict(record)
            merged["source_chunk_part"] = part
            merged["source_chunk_record_number"] = record.get("record_number")
            merged["source_record_index"] = global_index
            merged["record_number"] = global_index + 1
            merged_records.append(merged)
            source_indices.append(global_index)
            source_parts.append(part)
            source_chunk_records.append(int(record.get("record_number", chunk_offset + 1)))
        expected_start = end + 1

    if not merged_records:
        raise ValueError("no records were merged")

    tone_counts = [len(record.get("csi_data") or []) for record in merged_records]
    max_tones = max(tone_counts)
    reference_tones = next(
        record["csi_data"]
        for record in merged_records
        if len(record.get("csi_data") or []) == max_tones
    )
    tone_index = np.asarray(
        [int(tone.get("tone_index", index)) for index, tone in enumerate(reference_tones)],
        dtype=np.int32,
    )
    first_rx = reference_tones[0].get("rx_data")
    if not isinstance(first_rx, list) or not first_rx:
        raise ValueError("first full tone has no receive-stream data")
    streams = len(first_rx)
    count = len(merged_records)

    csi = np.full((count, max_tones, streams), np.complex64(np.nan + 1j * np.nan))
    valid_tone = np.zeros((count, max_tones), dtype=np.bool_)
    actual_tone_count = np.asarray(tone_counts, dtype=np.uint16)
    report_timestamp_us = np.empty(count, dtype=np.uint64)
    association_timestamp_us = np.empty(count, dtype=np.uint64)
    client_mac = np.empty(count, dtype="U17")
    bssid = np.empty(count, dtype="U17")
    rssi_dbm = np.empty((count, streams), dtype=np.int16)
    chanspec = np.empty(count, dtype=np.uint16)
    configured_active_tones = np.empty(count, dtype=np.uint16)
    tx_streams = np.empty(count, dtype=np.uint8)
    rx_streams = np.empty(count, dtype=np.uint8)

    for record_index, record in enumerate(merged_records):
        header = record.get("header")
        config = record.get("config") or {}
        tones = record.get("csi_data")
        if not isinstance(header, dict) or not isinstance(tones, list):
            raise ValueError(f"record {record_index} has invalid header or CSI data")

        indices = [
            int(tone.get("tone_index", index)) for index, tone in enumerate(tones)
        ]
        if indices != tone_index[: len(tones)].tolist():
            raise ValueError(f"record {record_index} has inconsistent tone indices")

        for tone_number, tone in enumerate(tones):
            rx_data = tone.get("rx_data")
            if not isinstance(rx_data, list) or len(rx_data) != streams:
                raise ValueError(
                    f"record {record_index}, tone {tone_number} has inconsistent streams"
                )
            for stream, sample in enumerate(rx_data):
                if not isinstance(sample, dict) or "I" not in sample or "Q" not in sample:
                    raise ValueError(
                        f"record {record_index}, tone {tone_number}, stream {stream} "
                        "has no I/Q value"
                    )
                csi[record_index, tone_number, stream] = complex(
                    float(sample["I"]), float(sample["Q"])
                )
        valid_tone[record_index, : len(tones)] = True

        report_timestamp_us[record_index] = int(
            header.get("report_timestamp_us", header.get("report_timestamp"))
        )
        association_timestamp_us[record_index] = int(
            header.get("assoc_timestamp_us", header.get("assoc_timestamp", 0))
        )
        client_mac[record_index] = mac(header.get("client_mac"))
        bssid[record_index] = mac(header.get("bss_mac", header.get("bssid")))
        rssi = header.get("rssi")
        if not isinstance(rssi, list) or len(rssi) != streams:
            raise ValueError(f"record {record_index} has inconsistent RSSI")
        rssi_dbm[record_index] = [int(value) for value in rssi]
        chanspec[record_index] = int(header.get("chanspec", 0))
        configured_active_tones[record_index] = int(
            config.get("num_active_tones", len(tones))
        )
        tx_streams[record_index] = int(header.get("txstreams", 0))
        rx_streams[record_index] = int(header.get("rxstreams", streams))

    json_path = Path(f"{args.output_stem}.json")
    npz_path = Path(f"{args.output_stem}.npz")
    csv_path = Path(f"{args.output_stem}.csv")
    json_path.parent.mkdir(parents=True, exist_ok=True)

    json_path.write_text(json.dumps(merged_records, indent=2) + "\n")
    np.savez_compressed(
        npz_path,
        csi=csi,
        valid_tone=valid_tone,
        actual_tone_count=actual_tone_count,
        tone_index=tone_index,
        report_timestamp_us=report_timestamp_us,
        association_timestamp_us=association_timestamp_us,
        client_mac=client_mac,
        bssid=bssid,
        rssi_dbm=rssi_dbm,
        chanspec=chanspec,
        configured_active_tones=configured_active_tones,
        tx_streams=tx_streams,
        rx_streams=rx_streams,
        source_record_index=np.asarray(source_indices, dtype=np.uint32),
        source_chunk_part=np.asarray(source_parts, dtype=np.uint16),
        source_chunk_record_number=np.asarray(source_chunk_records, dtype=np.uint16),
        iq_scale=np.asarray(IQ_SCALE, dtype=np.uint16),
    )

    with csv_path.open("w", newline="") as output:
        writer = csv.writer(output, lineterminator="\n")
        columns = [
            "record_index",
            "source_record_index",
            "source_chunk_part",
            "source_chunk_record_number",
            "report_timestamp_us",
            "association_timestamp_us",
            "client_mac",
            "bssid",
            "chanspec",
            "tx_streams",
            "rx_streams",
            "configured_active_tones",
            "actual_tone_count",
            "iq_scale",
        ]
        columns.extend(f"rssi_rx{stream}_dbm" for stream in range(streams))
        for tone in tone_index:
            for stream in range(streams):
                columns.append(f"tone{int(tone):03d}_rx{stream}_I_x64")
                columns.append(f"tone{int(tone):03d}_rx{stream}_Q_x64")
        writer.writerow(columns)

        for record_index in range(count):
            row: list[str | int] = [
                record_index,
                source_indices[record_index],
                source_parts[record_index],
                source_chunk_records[record_index],
                int(report_timestamp_us[record_index]),
                int(association_timestamp_us[record_index]),
                str(client_mac[record_index]),
                str(bssid[record_index]),
                int(chanspec[record_index]),
                int(tx_streams[record_index]),
                int(rx_streams[record_index]),
                int(configured_active_tones[record_index]),
                int(actual_tone_count[record_index]),
                IQ_SCALE,
            ]
            row.extend(int(value) for value in rssi_dbm[record_index])
            for tone_number in range(max_tones):
                for stream in range(streams):
                    if valid_tone[record_index, tone_number]:
                        sample = csi[record_index, tone_number, stream]
                        row.append(fixed_iq(float(sample.real)))
                        row.append(fixed_iq(float(sample.imag)))
                    else:
                        row.extend(("", ""))
            writer.writerow(row)

    print(f"merged records: {count}")
    print(f"tone counts: {dict(sorted((value, tone_counts.count(value)) for value in set(tone_counts)))}")
    print(f"NPZ CSI shape: {csi.shape}")
    print(f"wrote: {json_path}")
    print(f"wrote: {npz_path}")
    print(f"wrote: {csv_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
