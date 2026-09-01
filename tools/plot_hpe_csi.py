#!/usr/bin/env python3
"""Plot channel frequency response and CSI deviation from processed HPE CSI."""

from __future__ import annotations

import argparse
from pathlib import Path

import matplotlib
import numpy as np

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.cm import ScalarMappable  # noqa: E402
from matplotlib.collections import LineCollection  # noqa: E402
from matplotlib.colors import Normalize  # noqa: E402


STREAM_COLOURS = ("#1769aa", "#00897b", "#ef6c00", "#8e24aa")


def complete_record_mask(data: np.lib.npyio.NpzFile, csi: np.ndarray) -> np.ndarray:
    keep = np.isfinite(csi.real).all(axis=(1, 2)) & np.isfinite(csi.imag).all(
        axis=(1, 2)
    )
    if "actual_tone_count" in data.files:
        keep &= data["actual_tone_count"] == csi.shape[1]
    if "valid_tone" in data.files:
        keep &= data["valid_tone"].all(axis=1)
    return keep


def save_frequency_response(
    csi: np.ndarray,
    tone_index: np.ndarray,
    client: str,
    configured_tones: int,
    output: Path,
    dpi: int,
) -> None:
    magnitude = np.abs(csi).astype(np.float64)
    positive = magnitude[magnitude > 0]
    floor = positive.min() if positive.size else 1e-12
    magnitude_db = 20.0 * np.log10(np.maximum(magnitude, floor))
    magnitude_median = np.median(magnitude_db, axis=0)
    magnitude_low, magnitude_high = np.percentile(magnitude_db, [10, 90], axis=0)

    relative_phase = np.angle(csi * np.conj(csi[:, :, [0]]))
    phase_centre = np.angle(np.mean(np.exp(1j * relative_phase), axis=0))
    phase_residual = np.angle(
        np.exp(1j * (relative_phase - phase_centre[np.newaxis, :, :]))
    )
    phase_low, phase_high = np.percentile(phase_residual, [10, 90], axis=0)
    phase_centre = np.unwrap(phase_centre, axis=0)

    streams = csi.shape[2]
    figure, axes = plt.subplots(
        streams, 2, figsize=(13.5, 2.45 * streams + 1.6), sharex=True
    )
    axes = np.atleast_2d(axes)

    for stream in range(streams):
        colour = STREAM_COLOURS[stream % len(STREAM_COLOURS)]
        magnitude_axis, phase_axis = axes[stream]
        magnitude_axis.fill_between(
            tone_index,
            magnitude_low[:, stream],
            magnitude_high[:, stream],
            color=colour,
            alpha=0.20,
            linewidth=0,
        )
        magnitude_axis.plot(
            tone_index, magnitude_median[:, stream], color=colour, linewidth=1.5
        )
        magnitude_axis.set_ylabel("20 log10 |H|\n(HPE units)", fontsize=9)
        magnitude_axis.set_title(
            f"RX stream {stream}: raw magnitude, median and 10th–90th percentile",
            fontsize=9.5,
        )

        if stream == 0:
            phase_axis.axhline(0, color=colour, linewidth=1.5)
            phase_axis.set_ylim(-np.pi, np.pi)
            phase_axis.text(
                float(np.mean(tone_index)),
                0.35,
                "0 rad by definition",
                color=colour,
                fontsize=9,
                ha="center",
            )
            phase_axis.set_title("RX stream 0: phase reference", fontsize=9.5)
        else:
            phase_axis.fill_between(
                tone_index,
                phase_centre[:, stream] + phase_low[:, stream],
                phase_centre[:, stream] + phase_high[:, stream],
                color=colour,
                alpha=0.20,
                linewidth=0,
            )
            phase_axis.plot(
                tone_index, phase_centre[:, stream], color=colour, linewidth=1.5
            )
            phase_axis.set_title(
                f"RX stream {stream}: phase relative to RX stream 0", fontsize=9.5
            )
        phase_axis.set_ylabel("phase (rad)", fontsize=9)

        for axis in (magnitude_axis, phase_axis):
            axis.grid(True, linewidth=0.4, alpha=0.35)
            axis.set_axisbelow(True)
            axis.tick_params(labelsize=8)
            axis.spines[["top", "right"]].set_visible(False)

    for axis in axes[-1]:
        axis.set_xlabel("reported CSI tone index (frequency ordered)", fontsize=9)

    figure.suptitle(
        "Channel frequency response from decoded CSI\n"
        f"{csi.shape[0]} complete records, {csi.shape[1]} displayed tones of "
        f"{configured_tones} configured, {streams} RX streams — client {client}",
        fontsize=11.5,
        y=0.995,
    )
    figure.tight_layout(rect=(0, 0, 1, 0.955))
    output.parent.mkdir(parents=True, exist_ok=True)
    figure.savefig(output, dpi=dpi, bbox_inches="tight")
    plt.close(figure)


def save_deviation(
    csi: np.ndarray,
    timestamps_us: np.ndarray,
    tone_index: np.ndarray,
    client: str,
    output: Path,
    dpi: int,
) -> tuple[float, float, int]:
    order = np.argsort(timestamps_us)
    csi = csi[order]
    timestamps_us = timestamps_us[order]
    seconds = (timestamps_us - timestamps_us[0]).astype(np.float64) / 1e6
    intervals = np.diff(seconds)
    gap_threshold = 3.0 * np.median(intervals)
    gap_positions = np.nonzero(intervals > gap_threshold)[0] + 1

    magnitude = np.abs(csi).astype(np.float64)
    norms = np.sqrt(np.sum(magnitude**2, axis=(1, 2), keepdims=True))
    norms[norms == 0] = 1.0
    magnitude /= norms
    positive = magnitude[magnitude > 0]
    floor = positive.min() if positive.size else 1e-12
    magnitude_db = 20.0 * np.log10(np.maximum(magnitude, floor))
    deviation = magnitude_db - np.mean(magnitude_db, axis=0, keepdims=True)

    time_for_plot = np.insert(seconds, gap_positions, np.nan)
    deviation_for_plot = np.insert(deviation, gap_positions, np.nan, axis=0)
    centred_tones = tone_index - np.mean(tone_index)
    colour_norm = Normalize(vmin=float(centred_tones[0]), vmax=float(centred_tones[-1]))
    colours = plt.cm.viridis(colour_norm(centred_tones))
    streams = csi.shape[2]

    figure, axes = plt.subplots(
        streams, 1, figsize=(13.5, 2.55 * streams + 1.8), sharex=True, sharey=True
    )
    axes = np.atleast_1d(axes)
    limit = float(np.nanpercentile(np.abs(deviation), 99.0))

    for stream, axis in enumerate(axes):
        values = deviation_for_plot[:, :, stream]
        segments = [
            np.column_stack((time_for_plot, values[:, tone]))
            for tone in range(csi.shape[1])
        ]
        axis.add_collection(
            LineCollection(segments, colors=colours, linewidths=0.38, rasterized=True)
        )
        axis.set_xlim(seconds[0], seconds[-1])
        axis.set_ylim(-limit, limit)
        axis.set_ylabel("|H| deviation\n(dB)", fontsize=9)
        axis.set_title(
            f"RX stream {stream}: all {csi.shape[1]} displayed tones", fontsize=9.5
        )
        axis.grid(True, linewidth=0.4, alpha=0.35)
        axis.set_axisbelow(True)
        axis.tick_params(labelsize=8)
        axis.spines[["top", "right"]].set_visible(False)

    axes[-1].set_xlabel("CSI timestamp relative to first complete record (s)", fontsize=9)
    span = seconds[-1] - seconds[0]
    rate = (len(seconds) - 1) / span if span else float("nan")
    figure.suptitle(
        "CSI magnitude deviation over time\n"
        "per-packet L2 gain removal and per-tone time-mean removal — "
        f"{len(seconds)} complete records, {span:.3f} s, {rate:.3f} Hz — "
        f"client {client}",
        fontsize=11.5,
        y=0.992,
    )
    figure.subplots_adjust(left=0.075, right=0.89, top=0.925, bottom=0.06, hspace=0.30)
    colour_bar = figure.colorbar(
        ScalarMappable(norm=colour_norm, cmap=plt.cm.viridis),
        cax=figure.add_axes([0.91, 0.06, 0.015, 0.865]),
    )
    colour_bar.set_label("reported tone index relative to displayed-tone centre", fontsize=9)
    colour_bar.ax.tick_params(labelsize=8)
    output.parent.mkdir(parents=True, exist_ok=True)
    figure.savefig(output, dpi=dpi, bbox_inches="tight")
    plt.close(figure)
    return span, rate, len(gap_positions)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input_npz", type=Path)
    parser.add_argument("output_dir", type=Path)
    parser.add_argument("--dpi", type=int, default=160)
    args = parser.parse_args()

    with np.load(args.input_npz, allow_pickle=False) as data:
        csi_all = data["csi"]
        keep = complete_record_mask(data, csi_all)
        csi = csi_all[keep]
        timestamps_us = data["report_timestamp_us"][keep]
        clients = sorted({str(value) for value in data["client_mac"][keep]})
        if len(clients) != 1:
            raise ValueError(f"expected one client; found {clients}")
        client = clients[0]
        tone_index = data["tone_index"].astype(np.int32)
        configured_tones = (
            int(data["configured_active_tones"][keep][0])
            if "configured_active_tones" in data.files
            else csi.shape[1]
        )

    if csi.shape[0] < 2:
        raise ValueError("fewer than two complete records are available")

    prefix = args.input_npz.stem
    response_path = args.output_dir / f"{prefix}-channel-frequency-response.png"
    deviation_path = args.output_dir / f"{prefix}-csi-deviation.png"
    save_frequency_response(
        csi, tone_index, client, configured_tones, response_path, args.dpi
    )
    span, rate, gaps = save_deviation(
        csi, timestamps_us, tone_index, client, deviation_path, args.dpi
    )
    print(f"complete records plotted: {csi.shape[0]} of {csi_all.shape[0]}")
    print(f"displayed/configured tones: {csi.shape[1]}/{configured_tones}")
    print(f"timestamp span/rate: {span:.6f} s / {rate:.6f} Hz")
    print(f"trace breaks above 3x median interval: {gaps}")
    print(f"wrote: {response_path}")
    print(f"wrote: {deviation_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
