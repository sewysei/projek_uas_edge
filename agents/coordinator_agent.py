import os, time, json, csv, threading
from datetime import datetime, timezone
import paho.mqtt.client as mqtt

GROUP_ID = os.getenv("GROUP_ID", "kel01")
AGENT_ID = os.getenv("AGENT_ID", "coordinator")
MQTT_HOST = os.getenv("MQTT_HOST", "mosquitto-svc")
MQTT_PORT = int(os.getenv("MQTT_PORT", "1883"))
MQTT_USER = os.getenv("MQTT_USER", "coorduser")
MQTT_PASS = os.getenv("MQTT_PASS", "coordpass123")
TEMP_THRESHOLD = float(os.getenv("TEMP_THRESHOLD", "30.0"))
CSV_PATH = os.getenv("CSV_PATH", "/tmp/metrics_log.csv")

TOPIC_SUB_TELEMETRY = f"edge/{GROUP_ID}/+/telemetry"
TOPIC_SUB_STATUS = f"edge/{GROUP_ID}/+/status"
TOPIC_MY_STATUS = f"edge/{GROUP_ID}/{AGENT_ID}/status"

seq_cmd = 0
seq_status = 0
last_seq_per_agent = {}
lost_packets_per_agent = {}
received_packets_per_agent = {}
agent_offline_ts = {}

# Siapkan file CSV untuk evaluasi Bab 5
with open(CSV_PATH, "w", newline="") as f:
    writer = csv.writer(f)
    writer.writerow(["ts_iso", "agent_id", "seq", "temp", "decision_latency_ms", "lost_packets_total", "received_total", "action_taken"])

def log_event(event_type, msg, extra=None):
    entry = {"ts_iso": datetime.now(timezone.utc).isoformat(), "agent": AGENT_ID, "type": event_type, "msg": msg}
    if extra: entry.update(extra)
    print(json.dumps(entry), flush=True)

def touch_health_file():
    with open("/tmp/healthy", "w") as f:
        f.write(str(time.time()))

def send_cmd(client, target_agent, interval, reason):
    global seq_cmd
    seq_cmd += 1
    cmd_topic = f"edge/{GROUP_ID}/{target_agent}/cmd"
    payload = {"ts": time.time(), "seq": seq_cmd, "cmd": "SET_INTERVAL", "interval": interval, "reason": reason}
    client.publish(cmd_topic, json.dumps(payload), qos=1)

def on_connect(client, userdata, flags, rc):
    if rc == 0:
        client.subscribe([(TOPIC_SUB_TELEMETRY, 1), (TOPIC_SUB_STATUS, 1)])
        log_event("COORD_CONNECTED", "Koordinator siap memantau seluruh agen")

def on_message(client, userdata, msg):
    now = time.time()
    parts = msg.topic.split("/")
    if len(parts) < 4: return
    sender_id, msg_type = parts[2], parts[3]
    if sender_id == AGENT_ID: return

    # 1. Hitung MTTR dari perubahan LWT status offline -> online
    if msg_type == "status":
        raw = msg.payload.decode()
        if raw == "offline":
            agent_offline_ts[sender_id] = now
            log_event("AGENT_DOWN_DETECTED", f"Agen {sender_id} LWT OFFLINE!")
        else:
            if sender_id in agent_offline_ts:
                mttr_sec = round(now - agent_offline_ts.pop(sender_id), 2)
                log_event("MTTR_RECORDED", f"Agen {sender_id} pulih kembali!", {"mttr_sec": mttr_sec})
        return

    # 2. Proses Telemetri & Evaluasi Policy Spasial
    if msg_type == "telemetry":
        try:
            data = json.loads(msg.payload.decode())
            seq = int(data["seq"])
            temp = float(data["temp"])
            ts_sent = float(data["ts"])

            # Hitung Packet Loss berdasarkan gap sequence number
            received_packets_per_agent[sender_id] = received_packets_per_agent.get(sender_id, 0) + 1
            if sender_id in last_seq_per_agent and seq > last_seq_per_agent[sender_id] + 1:
                gap = seq - last_seq_per_agent[sender_id] - 1
                lost_packets_per_agent[sender_id] = lost_packets_per_agent.get(sender_id, 0) + gap
            last_seq_per_agent[sender_id] = seq

            # Decision Process (Sense -> Think -> Act)
            if temp >= TEMP_THRESHOLD:
                action = "ADAPT_FAST_1S"
                send_cmd(client, sender_id, 1.0, f"ANOMALY_AT_{sender_id}")
                # Adaptasi Spasial: jika sensor-1 (fisik) panas, instruksikan sensor-2 waspada (2.0s)
                if sender_id == "sensor-1":
                    send_cmd(client, "sensor-2", 2.0, "SPATIAL_NEIGHBOR_ALERT_FROM_S1")
            else:
                action = "NORMAL_5S"
                if float(data.get("interval", 5.0)) != 5.0:
                    send_cmd(client, sender_id, 5.0, "TEMP_NORMALIZED")

            decision_latency_ms = round((time.time() - ts_sent) * 1000, 3)

            with open(CSV_PATH, "a", newline="") as f:
                csv.writer(f).writerow([
                    datetime.now(timezone.utc).isoformat(), sender_id, seq, temp,
                    decision_latency_ms, lost_packets_per_agent.get(sender_id, 0),
                    received_packets_per_agent[sender_id], action
                ])

            log_event("DECISION_MADE", f"Evaluasi {sender_id}: T={temp}C -> {action}",
                      {"latency_ms": decision_latency_ms, "seq": seq})
        except Exception as e:
            log_event("TELEMETRY_ERR", str(e))

def heartbeat_loop(client):
    global seq_status
    while True:
        touch_health_file()
        seq_status += 1
        payload = {"ts": time.time(), "seq": seq_status, "agent_id": AGENT_ID, "status": "online"}
        client.publish(TOPIC_MY_STATUS, json.dumps(payload), qos=1, retain=True)
        time.sleep(1.0)

def main():
    client = mqtt.Client(client_id=f"{GROUP_ID}-{AGENT_ID}")
    client.username_pw_set(MQTT_USER, MQTT_PASS)
    client.will_set(TOPIC_MY_STATUS, payload="offline", qos=1, retain=True)
    client.on_connect = on_connect
    client.on_message = on_message

    client.connect_async(MQTT_HOST, MQTT_PORT, keepalive=10)
    client.loop_start()
    threading.Thread(target=heartbeat_loop, args=(client,), daemon=True).start()

    while True:
        time.sleep(5)

if __name__ == "__main__":
    main()