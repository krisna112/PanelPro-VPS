"""Exercise the generated vhosts with a real Nginx on Linux CI."""

import http.client
import shutil
import socket
import ssl
import subprocess
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from panelpro.core.certs import generate_selfsigned
from panelpro.services.webservers import NginxAdapter, write_vhost

NGINX = shutil.which("nginx")
pytestmark = pytest.mark.skipif(sys.platform != "linux" or not NGINX, reason="requires Linux Nginx")


def free_port():
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        return listener.getsockname()[1]


def request(port, host, path, *, tls=False):
    if tls:
        conn = http.client.HTTPSConnection("127.0.0.1", port, context=ssl._create_unverified_context(), timeout=2)
    else:
        conn = http.client.HTTPConnection("127.0.0.1", port, timeout=2)
    try:
        conn.request("GET", path, headers={"Host": host})
        response = conn.getresponse()
        return response.status, response.read(), response.getheader("location")
    finally:
        conn.close()


def test_generated_vhosts_serve_static_proxy_and_acme(tmp_path):
    class Backend(BaseHTTPRequestHandler):
        def do_GET(self):
            self.send_response(200)
            self.end_headers()
            self.wfile.write(self.path.encode())

    with ThreadingHTTPServer(("127.0.0.1", 0), Backend) as upstream:
        worker = threading.Thread(target=upstream.serve_forever, daemon=True)
        worker.start()
        try:
            check_vhosts(tmp_path, upstream.server_port)
        finally:
            upstream.shutdown()
            worker.join(timeout=5)


def check_vhosts(tmp_path, backend_port):
    http_port, tls_port = free_port(), free_port()
    while tls_port == http_port:
        tls_port = free_port()

    adapter = NginxAdapter()
    adapter.conf_dir = tmp_path / "sites"
    adapter.conf_dir.mkdir()
    adapter.log_dir = tmp_path

    root = tmp_path / "public"
    acme = root / ".well-known" / "acme-challenge"
    acme.mkdir(parents=True)
    (acme / "test-token").write_text("challenge", encoding="utf-8")
    (root / "index.html").write_text("site build", encoding="utf-8")
    (root / "index.php").write_text("private PHP source", encoding="utf-8")

    cert, key = generate_selfsigned("static.example")
    cert_file, key_file = tmp_path / "cert.pem", tmp_path / "key.pem"
    cert_file.write_text(cert, encoding="utf-8")
    key_file.write_text(key, encoding="utf-8")

    write_vhost(adapter, "static.example", ["www.static.example"], str(root),
                None, None, True, str(cert_file), str(key_file))
    write_vhost(adapter, "proxy.example", [], str(root),
                None, f"http://127.0.0.1:{backend_port}", False, None, None)
    write_vhost(adapter, "php.example", [], str(root), "8.3", None, False, None, None)
    shutil.copyfile("/etc/nginx/fastcgi_params", tmp_path / "fastcgi_params")

    for file in adapter.conf_dir.glob("*.conf"):
        config = file.read_text(encoding="utf-8")
        config = config.replace("    listen 80;", f"    listen 127.0.0.1:{http_port};")
        config = config.replace("    listen 443 ssl;", f"    listen 127.0.0.1:{tls_port} ssl;")
        config = "\n".join(line for line in config.splitlines() if "listen [::]" not in line)
        file.write_text(config, encoding="utf-8")

    conf = tmp_path / "nginx.conf"
    conf.write_text(
        f"pid {tmp_path / 'nginx.pid'};\n"
        "events {}\n"
        "http {\n"
        "    client_body_temp_path client-body;\n"
        "    proxy_temp_path proxy-temp;\n"
        "    fastcgi_temp_path fastcgi-temp;\n"
        "    uwsgi_temp_path uwsgi-temp;\n"
        "    scgi_temp_path scgi-temp;\n"
        f"    include {adapter.conf_dir}/*.conf;\n"
        "}\n",
        encoding="utf-8",
    )
    args = [NGINX, "-p", str(tmp_path), "-c", str(conf), "-e", "stderr"]
    subprocess.run([*args, "-t"], check=True, capture_output=True, text=True)
    with subprocess.Popen([*args, "-g", "daemon off;"], stderr=subprocess.PIPE) as nginx:
        try:
            deadline = time.monotonic() + 5
            while True:
                try:
                    with socket.create_connection(("127.0.0.1", http_port), timeout=1):
                        break
                except OSError:
                    if nginx.poll() is not None:
                        pytest.fail(nginx.stderr.read().decode())
                    if time.monotonic() >= deadline:
                        pytest.fail("Nginx did not accept connections")
                    time.sleep(0.05)

            assert request(http_port, "static.example", "/")[2] == "https://static.example/"
            assert request(tls_port, "www.static.example", "/", tls=True)[:2] == (200, b"site build")
            assert request(tls_port, "static.example", "/index.php", tls=True)[0] == 404
            for host in ("static.example", "proxy.example"):
                assert request(http_port, host, "/.well-known/acme-challenge/test-token")[:2] == (200, b"challenge")
            assert request(http_port, "proxy.example", "/health?probe=1")[:2] == (200, b"/health?probe=1")
        finally:
            if nginx.poll() is None:
                nginx.terminate()
                try:
                    nginx.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    nginx.kill()
