# Edge Agent dengan MQTT dan k3s

Panduan deployment dan pengujian sistem edge agent pada Raspberry Pi menggunakan
Docker, k3s, dan broker MQTT Mosquitto.

## 12 Langkah Deployment dan Pengujian

### 1. Siapkan perangkat dan prasyarat

Pastikan Raspberry Pi sudah memiliki:

- Docker
- k3s
- Python 3
- Akses `sudo`
- Koneksi jaringan yang stabil

Jalankan seluruh perintah berikut dari root proyek, yaitu folder yang berisi
`agents/`, `k8s/`, dan `scripts/`.

### 2. Hubungkan sensor DHT11

Hubungkan pin DHT11 ke Raspberry Pi sebagai berikut:

| Pin DHT11 | Raspberry Pi |

| VCC | 3.3V, pin fisik 1 |
| GND | GND, pin fisik 6 |
| DATA | GPIO 4 / BCM 4, pin fisik 7 |

Sensor fisik digunakan oleh `agent-sensor-1`, `agent-sensor-2` menggunakan
mode virtual sehingga tidak membutuhkan sensor tambahan.

### 3. Ambil source code proyek

git clone https://github.com/sewysei/projek_uas_edge.git
cd projek_uas_edge

### 4. Build image Docker

Build image agen dengan tag yang digunakan oleh manifest Kubernetes:

docker build -t local/edge-agent:1.0 ./agents

### 5. Impor image ke containerd k3s

Image lokal perlu diimpor ke containerd milik k3s karena deployment memakai
`imagePullPolicy: Never`.

docker save local/edge-agent:1.0 | sudo k3s ctr images import -

### 6. Deploy broker Mosquitto

Manifest ini membuat broker MQTT, konfigurasi autentikasi, ACL, dan service
internal `mosquitto-svc`.

sudo k3s kubectl apply -f k8s/01-mosquitto.yaml

### 7. Deploy seluruh edge agent

Perintah berikut menjalankan dua sensor dan satu koordinator:

- `agent-sensor-1`: sensor DHT11 fisik pada GPIO 4
- `agent-sensor-2`: sensor virtual
- `agent-coordinator`: pemantau telemetri dan pencatat metrik

sudo k3s kubectl apply -f k8s/02-agents.yaml

### 8. Verifikasi pod dan image

Pastikan seluruh pod berstatus `Running` dan menggunakan image versi `1.0`:

sudo k3s kubectl get pods -o wide
sudo k3s kubectl describe pods

Jika pod tidak berjalan, periksa log pod yang bermasalah:

sudo k3s kubectl logs <nama-pod>

### 9. Pantau telemetri dan heartbeat

Buka terminal baru, lalu subscribe ke seluruh topic pada kelompok `kel01`:

sudo k3s kubectl exec -it deploy/mosquitto-broker -- \
 mosquitto_sub -u coorduser -P coordpass123 -t 'edge/kel01/#' -v

Heartbeat agent dikirim setiap 1 detik. Telemetri normal dikirim setiap 5 detik
dan dapat berubah menjadi 1 detik ketika suhu mencapai ambang `30.0°C`.

### 10. Uji gangguan broker dan buffering

Matikan broker selama 60 detik:

sudo k3s kubectl scale deploy/mosquitto-broker --replicas=0
sudo k3s kubectl logs -f deploy/agent-sensor-1

Selama broker mati, sensor harus masuk ke mode otonomi lokal dan menyimpan data
ke buffer. Nyalakan kembali broker:

sudo k3s kubectl scale deploy/mosquitto-broker --replicas=1
sudo k3s kubectl logs -f deploy/agent-sensor-1

Cari event `BUFFER_FLUSH` untuk memastikan data buffer dikirim ulang.

### 11. Uji auto-healing dan hitung MTTR

Hapus pod sensor tanpa menghentikan deployment:

sudo k3s kubectl delete pod -l app=agent-sensor-1
sudo k3s kubectl logs -f deploy/agent-coordinator

Kubernetes seharusnya membuat pod pengganti secara otomatis. Koordinator akan
mencatat status LWT `offline` dan event pemulihan beserta nilai `mttr_sec`.

### 12. Salin dan evaluasi metrik

Salin file metrik dari pod koordinator ke host Raspberry Pi:

COORD_POD=$(sudo k3s kubectl get pod \
 -l app=agent-coordinator \
 -o jsonpath="{.items[0].metadata.name}")

sudo k3s kubectl cp "$COORD_POD:/tmp/metrics_log.csv" ./metrics_log.csv

Hitung decision latency p50/p95, packet loss, dan task success rate:

python3 scripts/evaluate_metrics.py

Hasil evaluasi akan ditampilkan di terminal sebagai ringkasan metrik pengujian.

## Struktur Proyek

.
├── agents/
│ ├── coordinator_agent.py
│ ├── requirements.txt
│ └── sensor_agent.py
├── k8s/
│ ├── 01-mosquitto.yaml
│ └── 02-agents.yaml
├── scripts/
│ └── evaluate_metrics.py
└── README.md

## Catatan Keamanan

Username dan password pada manifest Kubernetes digunakan untuk keperluan
demonstrasi lokal. Untuk deployment nyata, simpan kredensial MQTT di Kubernetes
Secret dan jangan memasukkannya langsung ke dalam repository.
