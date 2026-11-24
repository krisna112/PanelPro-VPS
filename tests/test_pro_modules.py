"""Pro-module pure-function tests (parser, validators, renderers)."""

import pytest

from panelpro.core.errors import PanelError

# --- traffic ---------------------------------------------------------------

def test_parse_combined_log_line():
    from panelpro.services.traffic import parse_line

    line = ('203.0.113.5 - - [23/Nov/2026:08:10:00 +0700] '
            '"GET /index.php?id=1 HTTP/1.1" 200 2326 "https://ref.example" '
            '"Mozilla/5.0 (X11; Linux) Firefox/120.0"')
    item = parse_line(line)
    assert item["ip"] == "203.0.113.5"
    assert item["url"] == "/index.php"
    assert item["status"] == 200
    assert item["bytes"] == 2326
    assert "Firefox" in item["ua"]


def test_parse_line_garbage_returns_none():
    from panelpro.services.traffic import parse_line

    assert parse_line("not a log line") is None
    assert parse_line("") is None


def test_aggregate_counts_pv_uv_spider_errors():
    from panelpro.services.traffic import aggregate

    lines = [
        ('1.1.1.1 - - [23/Nov/2026:08:00:00 +0000] "GET /a HTTP/1.1" 200 100 "-" "Googlebot"'),
        ('1.1.1.1 - - [23/Nov/2026:08:00:01 +0000] "GET /a HTTP/1.1" 200 100 "-" "Googlebot"'),
        ('2.2.2.2 - - [23/Nov/2026:08:00:02 +0000] "GET /b?x=1 HTTP/1.1" 404 0 "-" "curl/8.0"'),
    ]
    days = aggregate(lines)
    assert list(days) == ["2026-11-23"]
    b = days["2026-11-23"]
    assert b["pv"] == 3
    assert b["uv"] == 2  # 1.1.1.1 + 2.2.2.2
    assert b["spiders"] == 3  # Googlebot + curl
    assert b["errors"] == 1
    assert b["top_urls"]["/a"] == 2


# --- waf -------------------------------------------------------------------

def test_waf_validate_profile_data():
    from panelpro.services.waf import validate_profile_data

    data = validate_profile_data(True, 500, ["203.0.113.9"], ["sqlmap"])
    assert data["cc_rpm"] == 500
    assert data["blocked_ips"] == ["203.0.113.9"]

    for bad_ip in ("999.1.1.1", "abc", "1.2.3"):
        with pytest.raises(PanelError):
            validate_profile_data(True, 300, [bad_ip], [])
    for bad_ua in ("sqlmap; deny all;", 'bad" ua', "ua{backtick}", "x" * 121):
        with pytest.raises(PanelError):
            validate_profile_data(True, 300, [], [bad_ua])
    # cc_rpm is clamped into a sane range, not rejected
    assert validate_profile_data(True, 5, [], [])["cc_rpm"] == 10
    assert validate_profile_data(True, 999999, [], [])["cc_rpm"] == 60000


def test_waf_render_site_conf_quotes_ua():
    import shlex

    from panelpro.services.waf import render_site_conf

    class FakeProfile:
        cc_rpm = 300
        blocked_ips = ["203.0.113.9"]
        blocked_uas = ["sqlmap'; deny all;"]

    conf = render_site_conf(FakeProfile(), "site.test")
    assert "deny 203.0.113.9;" in conf
    # the UA pattern must survive as ONE quoted nginx argument — directive
    # injection via ';' must stay inside the quoted regex
    if_line = next(line for line in conf.splitlines() if "http_user_agent" in line)
    tokens = shlex.split(if_line.split("(", 1)[1].split(")", 1)[0])
    assert "sqlmap'; deny all;" in tokens


def test_waf_render_zone_conf():
    from panelpro.services.waf import render_zone_conf

    class FakeProfile:
        cc_rpm = 600

    conf = render_zone_conf(FakeProfile(), "site.test")
    assert "rate=600r/m" in conf
    assert "ppwaf_site.test" in conf


# --- lb --------------------------------------------------------------------

def test_lb_validate_name():
    from panelpro.services.lb import validate_name

    assert validate_name("Backend-01") == "backend-01"
    for bad in ("1abc", "a b", "x" * 80, "", "a;b"):
        with pytest.raises(PanelError):
            validate_name(bad)


def test_lb_validate_servers():
    from panelpro.services.lb import validate_servers

    servers = validate_servers([{"host": "10.0.0.1", "port": 8001, "weight": 2}])
    assert servers == [{"host": "10.0.0.1", "port": 8001, "weight": 2}]
    with pytest.raises(PanelError):
        validate_servers([])  # empty
    with pytest.raises(PanelError):
        validate_servers([{"host": "bad host", "port": 80}])


def test_lb_parse_proxy_target():
    from panelpro.services.lb import parse_proxy_target

    assert parse_proxy_target("upstream:backend") == "upstream:backend"
    assert parse_proxy_target("127.0.0.1:9000") == "127.0.0.1:9000"
    for bad in ("upstream:Bad Name", "http://x; rm", "..", ""):
        with pytest.raises(PanelError):
            parse_proxy_target(bad)


# --- fleet -----------------------------------------------------------------

def test_fleet_validate_base_url():
    from panelpro.services.fleet import validate_base_url

    assert validate_base_url("https://vps.example:21000/") == "https://vps.example:21000"
    assert validate_base_url("http://203.0.113.9") == "http://203.0.113.9"
    for bad in ("ftp://x", "https://host/path", "notaurl", ""):
        with pytest.raises(PanelError):
            validate_base_url(bad)


# --- daemon ----------------------------------------------------------------

def test_daemon_validate_target():
    from panelpro.services.procd import validate_target

    assert validate_target("systemd", "nginx") == "nginx"
    assert validate_target("port", "127.0.0.1:8080") == "127.0.0.1:8080"
    for kind, bad in (("systemd", "bad name"), ("port", "127.0.0.1:0"),
                      ("command", "x\ny"), ("pidfile", "../etc/passwd")):
        with pytest.raises(PanelError):
            validate_target(kind, bad)
    with pytest.raises(PanelError):
        validate_target("carrier", "x")
