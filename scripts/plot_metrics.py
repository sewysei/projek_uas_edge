import csv
from datetime import datetime
import os
import statistics
import sys

import matplotlib
matplotlib.use("Agg")
import matplotlib.dates as mdates
import matplotlib.pyplot as plt


CSV_FILE = "metrics_log.csv"
TEMP_THRESHOLD = 30.0
OUT_PLOT_1 = "grafik_1_adaptif_sampling.png"
OUT_PLOT_2 = "grafik_2_distribusi_latensi.png"


def load_metrics(csv_path):
    """Membaca data telemetri dan metrik keputusan dari metrics_log.csv."""
    if not os.path.exists(csv_path):
        print(f"Error: File '{csv_path}' tidak ditemukan. Salin dulu dari pod koordinator.")
        sys.exit(1)

    by_agent = {}
    latencies = []

    with open(csv_path, "r", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            agent = row["agent_id"]
            ts = datetime.fromisoformat(row["ts_iso"])
            temp = float(row["temp"])
            latency = float(row["decision_latency_ms"])
            action = row["action_taken"]
            interval = 1.0 if action == "ADAPT_FAST_1S" else 5.0

            if agent not in by_agent:
                by_agent[agent] = {"ts": [], "temp": [], "interval": []}
            by_agent[agent]["ts"].append(ts)
            by_agent[agent]["temp"].append(temp)
            by_agent[agent]["interval"].append(interval)
            latencies.append(latency)

    if not latencies:
        print(f"Error: File '{csv_path}' kosong.")
        sys.exit(1)

    return by_agent, latencies


def plot_adaptive_sampling(by_agent, out_path):
    """Membuat grafik suhu dan perubahan interval sampling adaptif."""
    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(11, 7), sharex=True)

    for agent, data in sorted(by_agent.items()):
        ax1.plot(data["ts"], data["temp"], marker="o", markersize=3, linewidth=1.5, label=agent)
        ax2.step(data["ts"], data["interval"], where="post", linewidth=1.8, label=agent)

    ax1.axhline(
        TEMP_THRESHOLD,
        color="red",
        linestyle="--",
        linewidth=1.2,
        label=f"Ambang Anomali ({TEMP_THRESHOLD}°C)",
    )
    ax1.set_title("Grafik 1: Adaptasi Frekuensi Sampling terhadap Perubahan Suhu")
    ax1.set_ylabel("Suhu (°C)")
    ax1.grid(True, linestyle=":", alpha=0.6)
    ax1.legend(loc="upper right")

    ax2.set_ylabel("Interval Sampling (detik)")
    ax2.set_xlabel("Waktu (UTC)")
    ax2.set_yticks([1.0, 5.0])
    ax2.set_yticklabels(["1s (ADAPT_FAST_1S)", "5s (NORMAL_5S)"])
    ax2.set_ylim(0.5, 5.8)
    ax2.grid(True, linestyle=":", alpha=0.6)
    ax2.legend(loc="upper right")
    ax2.xaxis.set_major_formatter(mdates.DateFormatter("%H:%M:%S"))

    fig.autofmt_xdate()
    plt.tight_layout()
    plt.savefig(out_path, dpi=150)
    plt.close(fig)
    print(f"Tersimpan: {out_path}")


def plot_latency_distribution(latencies, out_path):
    """Membuat histogram distribusi decision latency beserta garis p50 dan p95."""
    sorted_lat = sorted(latencies)
    p50 = statistics.median(sorted_lat)
    p95 = sorted_lat[min(int(len(sorted_lat) * 0.95), len(sorted_lat) - 1)]

    fig, ax = plt.subplots(figsize=(9, 5))
    bins = min(30, max(10, len(sorted_lat) // 5))
    ax.hist(sorted_lat, bins=bins, color="#3b82f6", edgecolor="white", alpha=0.85)

    ax.axvline(p50, color="green", linestyle="--", linewidth=1.8, label=f"p50 (Median) = {p50:.2f} ms")
    ax.axvline(p95, color="red", linestyle="--", linewidth=1.8, label=f"p95 = {p95:.2f} ms")

    ax.set_title(f"Grafik 2: Distribusi Decision Latency (n = {len(sorted_lat)} sampel)")
    ax.set_xlabel("Decision Latency (ms)")
    ax.set_ylabel("Frekuensi")
    ax.grid(True, axis="y", linestyle=":", alpha=0.6)
    ax.legend()

    plt.tight_layout()
    plt.savefig(out_path, dpi=150)
    plt.close(fig)
    print(f"Tersimpan: {out_path}")


def main():
    by_agent, latencies = load_metrics(CSV_FILE)
    plot_adaptive_sampling(by_agent, OUT_PLOT_1)
    plot_latency_distribution(latencies, OUT_PLOT_2)


if __name__ == "__main__":
    main()
