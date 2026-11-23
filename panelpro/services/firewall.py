"""Firewall adapter: ufw -> firewalld -> iptables, plus IP blocking and
SSH/ping hardening helpers."""

from __future__ import annotations

import ipaddress
from pathlib import Path

from panelpro.core.errors import PanelError
from panelpro.core.syscmd import run, which

ICMP_IGNORE = Path("/proc/sys/net/ipv4/icmp_echo_ignore_all")


def detect_tool() -> str | None:
    for tool in ("ufw", "firewall-cmd", "iptables"):
        if which(tool):
            return tool
    return None


def validate_port(port: int) -> int:
    if not isinstance(port, int) or not (1 <= port <= 65535):
        raise PanelError(f"Invalid port: {port}", 400)
    return port


def validate_proto(proto: str) -> str:
    proto = (proto or "tcp").lower()
    if proto not in ("tcp", "udp"):
        raise PanelError(f"Invalid protocol: {proto}", 400)
    return proto


def validate_ip(ip: str) -> str:
    try:
        return str(ipaddress.ip_address(ip))
    except ValueError as exc:
        raise PanelError(f"Invalid IP address: {ip}", 400) from exc


class Firewall:
    def __init__(self) -> None:
        self.tool = detect_tool()
        if not self.tool:
            raise PanelError(
                "No firewall tool found (install ufw, firewalld or iptables).", 400
            )

    # -- status --------------------------------------------------------------
    def status(self) -> dict:
        if self.tool == "ufw":
            res = run(["ufw", "status", "numbered"], timeout=30)
            return {
                "tool": self.tool,
                "active": res.stdout.startswith("Status: active"),
                "rules": self._parse_ufw(res.stdout),
            }
        if self.tool == "firewalld":
            res = run(["firewall-cmd", "--state"], timeout=30)
            listing = run(
                ["firewall-cmd", "--list-all"], timeout=30
            )
            return {
                "tool": self.tool,
                "active": res.stdout.strip() == "running",
                "rules": [line.strip() for line in listing.stdout.splitlines()],
            }
        res = run(["iptables", "-L", "-n", "--line-numbers"], timeout=30)
        return {
            "tool": self.tool,
            "active": bool(res.stdout.strip()),
            "rules": res.stdout.splitlines()[:200],
        }

    def _parse_ufw(self, text: str) -> list[dict]:
        rules = []
        for line in text.splitlines():
            stripped = line.strip()
            if not stripped or stripped.startswith("Status"):
                continue
            rules.append({"raw": stripped})
        return rules

    # -- ports -----------------------------------------------------------------
    def add_port(self, port: int, proto: str = "tcp") -> dict:
        validate_port(port)
        validate_proto(proto)
        if self.tool == "ufw":
            run(["ufw", "allow", f"{port}/{proto}"], check=True)
        elif self.tool == "firewalld":
            run(["firewall-cmd", "--permanent", "--add-port", f"{port}/{proto}"], check=True)
            run(["firewall-cmd", "--reload"], check=True)
        else:
            run(
                ["iptables", "-A", "INPUT", "-p", proto, "--dport", str(port),
                 "-j", "ACCEPT"],
                check=True,
            )
        return {"port": port, "proto": proto}

    def remove_port(self, port: int, proto: str = "tcp") -> dict:
        validate_port(port)
        validate_proto(proto)
        if self.tool == "ufw":
            run(["ufw", "delete", "allow", f"{port}/{proto}"], check=True)
        elif self.tool == "firewalld":
            run(["firewall-cmd", "--permanent", "--remove-port", f"{port}/{proto}"], check=True)
            run(["firewall-cmd", "--reload"], check=True)
        else:
            run(
                ["iptables", "-D", "INPUT", "-p", proto, "--dport", str(port),
                 "-j", "ACCEPT"],
                check=True,
            )
        return {"port": port, "proto": proto}

    # -- IP blocking -------------------------------------------------------------
    def block_ip(self, ip: str) -> dict:
        ip = validate_ip(ip)
        if self.tool == "ufw":
            run(["ufw", "insert", "1", "deny", "from", ip], check=True)
        elif self.tool == "firewalld":
            run(
                ["firewall-cmd", "--permanent", "--add-rich-rule",
                 f"rule family=ipv4 source address={ip} reject"],
                check=True,
            )
            run(["firewall-cmd", "--reload"], check=True)
        else:
            run(["iptables", "-I", "INPUT", "-s", ip, "-j", "DROP"], check=True)
        return {"ip": ip, "blocked": True}

    def unblock_ip(self, ip: str) -> dict:
        ip = validate_ip(ip)
        if self.tool == "ufw":
            run(["ufw", "delete", "deny", "from", ip], check=True)
        elif self.tool == "firewalld":
            run(
                ["firewall-cmd", "--permanent", "--remove-rich-rule",
                 f"rule family=ipv4 source address={ip} reject"],
                check=True,
            )
            run(["firewall-cmd", "--reload"], check=True)
        else:
            run(["iptables", "-D", "INPUT", "-s", ip, "-j", "DROP"], check=True)
        return {"ip": ip, "blocked": False}

    # -- on/off --------------------------------------------------------------------
    def enable(self) -> None:
        if self.tool == "ufw":
            run(["ufw", "--force", "enable"], check=True)
        elif self.tool == "firewalld":
            run(["systemctl", "enable", "--now", "firewalld"], check=True)
        else:
            raise PanelError("Enable/disable is managed by ufw or firewalld.", 400)

    def disable(self) -> None:
        if self.tool == "ufw":
            run(["ufw", "--force", "disable"], check=True)
        elif self.tool == "firewalld":
            run(["systemctl", "stop", "firewalld"], check=True)
        else:
            raise PanelError("Enable/disable is managed by ufw or firewalld.", 400)

    # -- ping / sysctl ---------------------------------------------------------------
    def ping_blocked(self) -> bool:
        try:
            return ICMP_IGNORE.read_text().strip() == "1"
        except OSError:
            return False

    def set_ping_block(self, blocked: bool) -> dict:
        try:
            ICMP_IGNORE.write_text("1" if blocked else "0")
        except OSError as exc:
            raise PanelError("Cannot write icmp_echo_ignore_all (need root).", 500) from exc
        return {"ping_blocked": blocked}

    # -- SSH port -----------------------------------------------------------------
    def ssh_port(self) -> int:
        res = run(["sshd", "-T"], timeout=15, check=False)
        if res.code != 0:
            res2 = run(["ss", "-tlnp"], timeout=15)
            for line in res2.stdout.splitlines():
                if "sshd" in line:
                    for token in line.split():
                        if token.startswith(":"):
                            try:
                                return int(token[1:])
                            except ValueError:
                                pass
            return 22
        for line in res.stdout.splitlines():
            if line.startswith("port "):
                return int(line.split()[1])
        return 22

    def set_ssh_port(self, port: int) -> dict:
        validate_port(port)
        sshd_config = Path("/etc/ssh/sshd_config")
        if not sshd_config.exists():
            raise PanelError("/etc/ssh/sshd_config not found.", 404)
        text = sshd_config.read_text(encoding="utf-8")
        replaced = False
        lines = []
        for line in text.splitlines():
            if line.strip().startswith("#") is False and line.strip().startswith("Port "):
                lines.append(f"Port {port}")
                replaced = True
            else:
                lines.append(line)
        if not replaced:
            lines.append(f"Port {port}")
        backup = sshd_config.with_suffix(".config.pp-bak")
        backup.write_text(text, encoding="utf-8")
        sshd_config.write_text("\n".join(lines) + "\n", encoding="utf-8")
        run(["systemctl", "restart", "sshd"], timeout=40, check=False)
        return {"port": port, "backup": str(backup),
                "warning": "Keep the new port open in the firewall before closing this session."}


def fail2ban_status() -> dict:
    if not which("fail2ban-client"):
        return {"installed": False}
    res = run(["fail2ban-client", "status"], timeout=15)
    jails = []
    if res.code == 0:
        parts = res.stdout.strip().splitlines()
        if parts and "Jail list" in parts[-1]:
            jails = [j.strip() for j in parts[-1].split(":", 1)[-1].split(",") if j.strip()]
    detail = {}
    for jail in jails:
        r = run(["fail2ban-client", "status", jail], timeout=15)
        detail[jail] = r.stdout[-500:]
    return {"installed": True, "jails": jails, "detail": detail}
