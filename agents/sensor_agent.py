import os, time, json, random, threading, collections
from datetime import datetime, timezone
import paho.mqtt.client as mqtt

# Konfigurasi dari Environment Variables (ConfigMap/Deployment)
GROUP_ID = os.getenv("GROUP_ID", "kel01")
AGENT_ID = os.getenv("AGENT_ID", "sensor-1")
SENSOR_MODE = os.getenv("SENSOR_MODE", "physical")  # "physical" atau "virtual"
GPIO_PIN = int(os.getenv("GPIO_PIN", "4"))          # Pin BCM 4 (Pin Fisik 7)
MQTT_HOST = os.getenv("MQTT_HOST", "mosquitto-svc")
MQTT_PORT = int(os.getenv("MQTT_PORT", "1883"))
MQTT_USER = os.getenv("MQTT_USER", "edgeuser")
MQTT_PASS = os.getenv("MQTT_PASS", "edgepass123")
TEMP_THRESHOLD = float(os.getenv("TEMP_THRESHOLD", "30.0"))

TOPIC_TELEMETRY = f"edge/{GROUP_ID}/{AGENT_ID}/telemetry"
TOPIC_STATUS = f"edge/{GROUP_ID}/{AGENT_ID}/status"
TOPIC_CMD = f"edge/{GROUP_ID}/{AGENT_ID}/cmd"

# State Agen
sampling_interval = 5.0
seq_telemetry = 0
seq_status = 0
broker_connected = False
offline_buffer = collections.deque(maxlen=500)
last_valid_temp, last_valid_hum = 27.5, 65.0

# Inisialisasi Sensor DHT11 jika mode physical
dht_device = None
if SENSOR_MODE == "physical":
    try:
        import board
        import adafruit_dht
        pin_map = {4: board.D4, 17: board.D17, 27: board.D27, 22: board.D22}
        dht_device = adafruit_dht.DHT11(pin_map.get(GPIO_PIN, board.D4), use_pulseio=False)
    except Exception as e:
        print(f"[{datetime.now(timezone.utc).isoformat()}] [WARN] Gagal init GPIO DHT11, fallback ke simulasi: {e}")

def log_event(event_type, msg, extra=None):
     entry = {"ts_iso": datetime.now(timezone.utc).isoformat(), "agent": AGENT_ID, "type": event_type, "msg": msg}
     if extra: entry.update(extra)
     print(json.dumps(entry), flush=True)

def touch_health_file():
    with open("/tmp/healthy", "w") as f:
        f.write(str(time.time()))

def read_sensor():
    global last_valid_temp, last_valid_hum
    if SENSOR_MODE == "physical" and dht_device is not None:
        try:
            t = dht_device.temperature
            h = dht_device.humidity
            if t is not None and h is not None:
                last_valid_temp, last_valid_hum = float(t), float(h)
                return last_valid_temp, last_valid_hum
        except RuntimeError as e:
            # DHT11 sering mengalami checksum/timeout di Linux; gunakan nilai valid terakhir
            log_event("DHT_RETRY", f"Transient read error: {e}")
        except Exception as e:
            log_event("DHT_ERR", f"Hardware error: {e}")
        return last_valid_temp, last_valid_hum
    else:
        # Mode Virtual: simulasi fluktuasi + 15% peluang lonjakan anomali suhu
        if random.random() < 0.15:
            last_valid_temp = round(random.uniform(30.5, 34.0), 1)
        else:
            last_valid_temp = round(random.uniform(26.0, 29.2), 1)
        last_valid_hum = round(random.uniform(55.0, 75.0), 1)
        return last_valid_temp, last_valid_hum

def on_connect(client, userdata, flags, rc):
    global broker_connected
    if rc == 0:
        broker_connected = True
        client.subscribe(TOPIC_CMD, qos=1)
        log_event("MQTT_CONNECTED", f"Terhubung ke broker {MQTT_HOST}")
        # Kirim data yang sempat disimpan saat broker mati (Fail-safe Flush)
        while offline_buffer:
            cached_payload = offline_buffer.popleft()
            client.publish(TOPIC_TELEMETRY, json.dumps(cached_payload), qos=1)
            log_event("BUFFER_FLUSH", f"Mengirim ulang seq={cached_payload['seq']}")
    else:
        log_event("MQTT_CONN_FAIL", f"Gagal konek rc={rc}")

def on_disconnect(client, userdata, rc):
    global broker_connected
    broker_connected = False
    log_event("MQTT_DISCONNECTED", f"Terputus dari broker (rc={rc}). Mode Otonom Lokal Aktif!")

def on_message(client, userdata, msg):
    global sampling_interval
    try:
        data = json.loads(msg.payload.decode())
        if data.get("cmd") == "SET_INTERVAL":
            new_int = float(data["interval"])
            if new_int != sampling_interval:
                old_int = sampling_interval
                sampling_interval = new_int
                log_event("ACT_CMD_APPLIED", f"Interval diubah {old_int}s -> {sampling_interval}s",
                          {"reason": data.get("reason"), "cmd_seq": data.get("seq"),
                           "cmd_latency_ms": round((time.time() - data.get("ts", time.time())) * 1000, 2)})
    except Exception as e:
        log_event("CMD_ERROR", str(e))

def heartbeat_loop(client):
    """Wajib >= 1 Hz di topic status (retained)"""
    global seq_status
    while True:
        touch_health_file()
        if broker_connected:
            seq_status += 1
            payload = {"ts": time.time(), "seq": seq_status, "agent_id": AGENT_ID, "status": "online"}
            client.publish(TOPIC_STATUS, json.dumps(payload), qos=1, retain=True)
        time.sleep(1.0)

def main():
    global sampling_interval, seq_telemetry
    client = mqtt.Client(client_id=f"{GROUP_ID}-{AGENT_ID}")
    client.username_pw_set(MQTT_USER, MQTT_PASS)
    # Wajib LWT = offline (retained)
    client.will_set(TOPIC_STATUS, payload="offline", qos=1, retain=True)
    client.on_connect = on_connect
    client.on_disconnect = on_disconnect
    client.on_message = on_message

    client.connect_async(MQTT_HOST, MQTT_PORT, keepalive=10)
    client.loop_start()

    threading.Thread(target=heartbeat_loop, args=(client,), daemon=True).start()
    log_event("AGENT_START", f"Agen {AGENT_ID} berjalan dalam mode {SENSOR_MODE}")

    while True:
        temp, hum = read_sensor()
        seq_telemetry += 1
        now = time.time()

        # THINK & ACT LOKAL (Fail-safe saat broker mati atau anomali kritis lokal)
        if not broker_connected:
            sampling_interval = 1.0 if temp >= TEMP_THRESHOLD else 5.0
            log_event("LOCAL_AUTONOMY", f"Broker offline. Keputusan lokal interval={sampling_interval}s")

        payload = {
            "ts": now,
            "seq": seq_telemetry,
            "agent_id": AGENT_ID,
            "temp": temp,
            "hum": hum,
            "interval": sampling_interval,
            "mode": SENSOR_MODE
        }

        if broker_connected:
            client.publish(TOPIC_TELEMETRY, json.dumps(payload), qos=1)
            log_event("SENSE_PUB", f"T={temp}C H={hum}% int={sampling_interval}s", {"seq": seq_telemetry})
        else:
            offline_buffer.append(payload)
            log_event("SENSE_BUFFERED", f"Data disimpan di buffer lokal (size={len(offline_buffer)})", {"seq": seq_telemetry})

        time.sleep(sampling_interval)

if __name__ == "__main__":
    main()