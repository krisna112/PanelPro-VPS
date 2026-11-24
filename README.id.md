# PanelPro (Bahasa Indonesia)

**PanelPro** adalah control panel server Linux open-source — kelola website,
database, file, SSL, cron, firewall, Docker, dan lainnya dari satu antarmuka
web yang bersih.

> Project ini **ditulis 100% dari nol** sebagai karya orisinal. Mirip dalam
> *kategori produk* dengan panel hosting lain (manajemen web/db/SSL/FTP adalah
> kategori umum), tetapi seluruh kode, arsitektur, desain UI, template, dan
> dokumentasi adalah karya asli repo ini. Lisensi MIT.

## ✨ Ringkasan Fitur

| Modul | Isi |
| --- | --- |
| 🌐 **Websites** | vhost nginx **dan** Apache, alias domain, reverse proxy, PHP per situs, editor vhost, log per situs, paksa HTTPS |
| 🗄️ **Database** | MySQL/MariaDB, PostgreSQL, Redis, MongoDB — kelola DB & user, grant, password root terenkripsi |
| 🐘 **PHP** | multi-versi, ekstensi, editor php.ini, tuning pool FPM |
| 📂 **Files** | file manager lengkap: editor, upload/download, zip/tar.gz, chmod/chown, trash aman, pencarian |
| 🔒 **SSL** | Let's Encrypt (certbot), self-signed, upload custom (dengan cek kecocokan key), monitor kadaluarsa + auto-renew, deploy 1 klik |
| 🛡️ **Keamanan** | adapter ufw/firewalld/iptables, blokir IP, toggle ping, ganti port SSH, status fail2ban, entry path rahasia, rate limit, 2FA |
| ⏰ **Cron** | mesin crontab ber-marker, tugas shell/URL/script, jalankan sekarang, log per tugas |
| 📈 **Monitor** | psutil realtime + riwayat 7 hari (CPU/mem/disk/net/load), proses teratas, alert threshold |
| 🐳 **Docker** | containers, images, volumes, networks, stats, exec, logs, compose |
| 🛍️ **App Store** | installer 1 klik: WordPress, phpMyAdmin, Nextcloud, Portainer, Uptime Kuma, n8n, Redis Commander, Grafana |
| 💾 **Backup** | job terjadwal (situs + dump DB → tar.gz), retensi, target lokal/SFTP/rclone, restore aman |
| ⌨️ **Terminal** | WebSocket SSH (paramiko) + xterm.js |
| 🔔 **Notifikasi** | webhook, Telegram, SMTP; event login gagal, disk/CPU tinggi, SSL kadaluarsa, backup |
| 👥 **Users** | multi-user dengan role (admin/operator/viewer) + API key |
| 🧩 **Plugins** | plugin FastAPI drop-in + contoh + dokumentasi |

## 🚀 Mulai Cepat (server Linux)

```bash
git clone https://github.com/krisna112/PanelPro-VPS.git
cd PanelPro-VPS
sudo bash scripts/install.sh
```

Jalankan di VPS Ubuntu atau Debian setelah DNS subdomain panel mengarah ke IP
VPS dan port 80 serta 443 bisa diakses. Isi subdomain panel, email Let's Encrypt,
dan pilihan stack di terminal. Pilih stack PHP jika situs membutuhkan PHP-FPM
dan MariaDB. Buka URL login HTTPS yang dicetak installer saat selesai.
Untuk instalasi baru, buat username dan password admin saat diminta.
Installer menyembunyikan password saat diketik dan meminta konfirmasi.

Jalankan `sudo panelpro menu` di VPS untuk melihat URL login, mengelola
layanan, mengganti port atau path login, mereset password, dan mengatur domain.

Buka **Websites → Tambah Website**, lalu pilih **Website statis**, **PHP-FPM**,
atau **Reverse proxy**. Setelah DNS mengarah ke VPS, gunakan menu **SSL / HTTPS**
di baris website untuk menerbitkan sertifikat Let's Encrypt.

Mode development (OS apa pun):

```bash
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
PANELPRO_HOME=./runtime PANELPRO_WWW_ROOT=./runtime/www python -m panelpro start --dev
```

## 🧭 Dokumentasi

* [docs/INSTALL.md](docs/INSTALL.md) — instalasi, update, CLI
* [docs/API.md](docs/API.md) — ringkasan REST API
* [docs/SECURITY.md](docs/SECURITY.md) — model ancaman & checklist hardening
* [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) — struktur backend/frontend
* [docs/PLUGINS.md](docs/PLUGINS.md) — menulis plugin

## ⚖️ Orisinalitas & Lisensi

Tidak ada bagian dari repo ini yang disalin dari control panel lain.
Kategori fiturnya generik; implementasi, penamaan, desain, dan teks semuanya
orisinal. Dependensi pihak ketiga dipakai sesuai lisensi open-source-nya
masing-masing.

Dirilis di bawah [MIT License](LICENSE).
