import csv
import statistics

latencies = []
lost_per_agent = {}
recv_per_agent = {}

with open("metrics_log.csv", "r") as f:
    reader = csv.DictReader(f)
    for row in reader:
        agent = row["agent_id"]
        latencies.append(float(row["decision_latency_ms"]))
        lost_per_agent[agent] = int(row["lost_packets_total"])
        recv_per_agent[agent] = int(row["received_total"])

latencies.sort()
p50 = statistics.median(latencies)
p95 = latencies[int(len(latencies) * 0.95)] if latencies else 0

total_lost = sum(lost_per_agent.values())
total_recv = sum(recv_per_agent.values())
total_expected = total_lost + total_recv
packet_loss_pct = (total_lost / total_expected * 100) if total_expected > 0 else 0.0
success_rate_pct = 100.0 - packet_loss_pct

print("=== HASIL EVALUASI METRIK UAS (BAB 5) ===")
print(f"Total Sampel Telemetri : {total_recv} pesan")
print(f"Decision Latency p50   : {p50:.2f} ms")
print(f"Decision Latency p95   : {p95:.2f} ms")
print(f"Packet Loss (%)        : {packet_loss_pct:.2f}%")
print(f"Task Success Rate (%)  : {success_rate_pct:.2f}%")