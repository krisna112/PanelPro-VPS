"""Config template rendering tests (original templates)."""

from panelpro.services.webservers import ApacheAdapter, NginxAdapter


def _ctx(**overrides):
    base = {
        "domain": "example.com",
        "aliases": ["www.example.com"],
        "root": "/www/wwwroot/example.com",
        "php_version": "8.2",
        "php_socket": "/run/php/php8.2-fpm.sock",
        "proxy_target": None,
        "force_https": False,
        "ssl_cert": None,
        "ssl_key": None,
        "access_log": "/var/log/nginx/example.com.access.log",
        "error_log": "/var/log/nginx/example.com.error.log",
        "server": "nginx",
    }
    base.update(overrides)
    return base


def test_nginx_php_site():
    conf = NginxAdapter().render("nginx_site.conf.j2", _ctx())
    assert "server_name example.com www.example.com" in conf
    assert "fastcgi_pass  unix:/run/php/php8.2-fpm.sock" in conf
    assert "root  /www/wwwroot/example.com" in conf


def test_nginx_ssl_and_redirect():
    conf = NginxAdapter().render(
        "nginx_site.conf.j2",
        _ctx(force_https=True, ssl_cert="/etc/le/cert.pem", ssl_key="/etc/le/key.pem"),
    )
    assert "listen 443 ssl" in conf
    assert "ssl_certificate     /etc/le/cert.pem" in conf
    assert "return 301 https://$host$request_uri" in conf


def test_nginx_proxy_mode():
    conf = NginxAdapter().render(
        "nginx_site.conf.j2", _ctx(php_version=None, proxy_target="http://127.0.0.1:3000")
    )
    assert "proxy_pass         http://127.0.0.1:3000;" in conf
    assert "fastcgi_pass" not in conf


def test_apache_php_site():
    conf = ApacheAdapter().render("apache_site.conf.j2", _ctx(server="apache"))
    assert "ServerName example.com" in conf
    assert "proxy:unix:/run/php/php8.2-fpm.sock|fcgi://localhost" in conf


def test_apache_ssl():
    conf = ApacheAdapter().render(
        "apache_site.conf.j2",
        _ctx(server="apache", force_https=True, ssl_cert="/c.pem", ssl_key="/k.pem"),
    )
    assert "<VirtualHost *:443>" in conf
    assert "SSLCertificateFile    /c.pem" in conf
