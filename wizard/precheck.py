"""Pre-checks that can run before an upgrade plan.

Scores measurements the operator collected against the AAP RPM installer
preflight and the published port tables. Port requirements differ by AAP
version. This module does not connect to the hosts and does not change them.

https://docs.redhat.com/en/documentation/red_hat_ansible_automation_platform/2.6/plan-ref_rpm_a_env_a
https://docs.redhat.com/en/documentation/red_hat_ansible_automation_platform/2.6/plan-assembly_network_ports_protocols
https://docs.redhat.com/en/documentation/red_hat_ansible_automation_platform/2.6/plan-ref_rpm_b_env_a
"""

from __future__ import annotations

import re

DOC_GROWTH = (
    "https://docs.redhat.com/en/documentation/red_hat_ansible_automation_platform/"
    "2.6/plan-ref_rpm_a_env_a"
)
DOC_PORTS = (
    "https://docs.redhat.com/en/documentation/red_hat_ansible_automation_platform/"
    "2.6/plan-assembly_network_ports_protocols"
)
DOC_ENTERPRISE = (
    "https://docs.redhat.com/en/documentation/red_hat_ansible_automation_platform/"
    "2.6/plan-ref_rpm_b_env_a"
)
DOC_24 = (
    "https://docs.redhat.com/en/documentation/red_hat_ansible_automation_platform/"
    "2.4/html/red_hat_ansible_automation_platform_installation_guide/"
    "assembly-platform-install-scenario"
)

_NOEXEC = ("/tmp", "/var", "/var/tmp")
_ROLES = {
    "automationgateway": "Platform gateway",
    "automationcontroller": "Automation controller",
    "automationhub": "Automation hub",
    "database": "Database",
    "execution": "Execution node",
    "automationedacontroller": "Event-Driven Ansible",
}
_CAPACITY = {
    "automationgateway": (4, 16, 60),
    "automationcontroller": (4, 16, 80),
    "automationhub": (4, 16, 60),
    "database": (4, 16, 100),
    "execution": (4, 16, 60),
    "automationedacontroller": (4, 16, 60),
}


class PrecheckError(ValueError):
    """The page sent a pre-check the wizard cannot score."""


def precheck(facts: dict) -> dict:
    """Score one target's preflight and port requirements."""
    parsed = _parse(facts)
    profile = _PROFILES[parsed["target"]]
    checks = []
    checks.append(_controller_check(parsed, profile))
    if not parsed["hosts"]:
        checks.append(_unknown(
            "hosts",
            "Host measurements",
            "No hosts have been entered.",
            "Enter each host that will run this target, including its RHEL version.",
        ))
        checks.append(_unknown(
            "firewall",
            "Firewall ports",
            "Ports have not been measured.",
            "Compare each host with the port list for this AAP version.",
        ))
    else:
        for host in parsed["hosts"]:
            checks.extend(_host_checks(host, profile, parsed))
    status = _overall(checks)
    return {
        "target": {
            "id": profile["id"],
            "title": profile["title"],
            "version": profile["version"],
            "installer": "rpm",
        },
        "status": status,
        "summary": _summary(status, profile),
        "checks": checks,
        "ports": [dict(item) for item in profile["ports"]],
        "docs": [dict(item) for item in profile["docs"]],
    }


def _flow(port, service, source, destination, source_role, destination_role, applies="always", required=True):
    return {
        "port": port,
        "protocol": "tcp",
        "service": service,
        "source": source,
        "destination": destination,
        "source_role": source_role,
        "destination_role": destination_role,
        "applies": applies,
        "required": required,
    }


def _ssh(role, destination):
    return _flow(22, "SSH", "Installer node", destination, "installer", role)


def _https(source, destination, source_role, destination_role, applies="always"):
    return _flow(443, "HTTPS", source, destination, source_role, destination_role, applies)


def _postgres(source, source_role, applies="always"):
    return _flow(5432, "PostgreSQL", source, "Database", source_role, "database", applies)


_GROWTH_PORTS = [
    _ssh("automationgateway", "Platform gateway"),
    _ssh("automationcontroller", "Automation controller"),
    _ssh("automationhub", "Automation hub", ),
    _ssh("database", "Database"),
    _ssh("execution", "Execution node"),
    _ssh("automationedacontroller", "Event-Driven Ansible"),
    _https("Platform gateway", "Automation controller", "automationgateway", "automationcontroller"),
    _https("Platform gateway", "Automation hub", "automationgateway", "automationhub", "hub"),
    _https("Platform gateway", "Event-Driven Ansible", "automationgateway", "automationedacontroller", "eda"),
    _https("Automation controller", "Automation hub", "automationcontroller", "automationhub", "hub"),
    _https("Execution node", "Platform gateway", "execution", "automationgateway", "execution"),
    _https("Event-Driven Ansible", "Automation controller", "automationedacontroller", "automationcontroller", "eda"),
    _postgres("Platform gateway", "automationgateway"),
    _postgres("Automation controller", "automationcontroller"),
    _postgres("Automation hub", "automationhub", "hub"),
    _postgres("Event-Driven Ansible", "automationedacontroller", "eda"),
    _flow(
        27199, "Receptor", "Automation controller", "Execution node",
        "automationcontroller", "execution", "execution",
    ),
    _flow(
        80, "HTTP", "Platform gateway", "Automation controller",
        "automationgateway", "automationcontroller", required=False,
    ),
    _flow(
        6379, "Redis", "Platform gateway", "Redis on the gateway",
        "automationgateway", "automationgateway", required=False,
    ),
    _flow(
        8443, "HTTPS", "Platform gateway", "Automation controller",
        "automationgateway", "automationcontroller", required=False,
    ),
]

_ENTERPRISE_EXTRA = [
    _flow(443, "HTTPS", "Load balancer", "Platform gateway", "loadbalancer", "automationgateway"),
    _flow(8443, "HTTPS", "Platform gateway", "Platform gateway", "automationgateway", "automationgateway"),
    _flow(16379, "Redis", "Platform gateway", "Platform gateway", "automationgateway", "automationgateway"),
]

_PORTS_24 = [
    _ssh("automationcontroller", "Automation controller"),
    _ssh("automationhub", "Automation hub"),
    _ssh("database", "Database"),
    _ssh("execution", "Execution node"),
    _https("Clients and controller nodes", "Automation controller", "client", "automationcontroller"),
    _https("Automation controller", "Automation hub", "automationcontroller", "automationhub", "hub"),
    _postgres("Automation controller", "automationcontroller"),
    _postgres("Automation hub", "automationhub", "hub"),
    _flow(
        27199, "Receptor", "Execution node", "Automation controller",
        "execution", "automationcontroller", "execution",
    ),
    _flow(
        27199, "Receptor", "Automation controller", "Execution node",
        "automationcontroller", "execution", "execution",
    ),
]

_PROFILES = {
    "rpm-2.6-growth": {
        "id": "rpm-2.6-growth",
        "title": "AAP 2.6 RPM growth",
        "version": "2.6",
        "os": "rhel-9.6",
        "controller_min": (4, 5),
        "ports": _GROWTH_PORTS,
        "docs": [
            {"title": "AAP 2.6 RPM growth topology", "url": DOC_GROWTH},
            {"title": "AAP 2.6 network ports and protocols", "url": DOC_PORTS},
        ],
    },
    "rpm-2.6-enterprise": {
        "id": "rpm-2.6-enterprise",
        "title": "AAP 2.6 RPM enterprise",
        "version": "2.6",
        "os": "rhel-9.6",
        "controller_min": (4, 5),
        "ports": _GROWTH_PORTS + _ENTERPRISE_EXTRA,
        "docs": [
            {"title": "AAP 2.6 RPM enterprise topology", "url": DOC_ENTERPRISE},
            {"title": "AAP 2.6 network ports and protocols", "url": DOC_PORTS},
        ],
    },
    "rpm-2.4": {
        "id": "rpm-2.4",
        "title": "AAP 2.4 RPM",
        "version": "2.4",
        "os": "rhel-2.4",
        "controller_min": None,
        "ports": _PORTS_24,
        "docs": [
            {"title": "AAP 2.4 installation guide", "url": DOC_24},
        ],
    },
}


def _parse(facts: dict) -> dict:
    if not isinstance(facts, dict):
        raise PrecheckError("Pre-check facts must be a JSON object.")
    target = facts.get("target")
    if target not in _PROFILES:
        raise PrecheckError("target must be rpm-2.6-growth, rpm-2.6-enterprise, or rpm-2.4.")
    version = facts.get("controller_version")
    if version is not None and (not isinstance(version, str) or not version.strip()):
        raise PrecheckError("controller_version must be a string.")
    hosts = facts.get("hosts", [])
    if not isinstance(hosts, list):
        raise PrecheckError("hosts must be a list.")
    return {
        "target": target,
        "controller_version": None if version is None else version.strip(),
        "hub": _optional_bool(facts, "hub"),
        "eda": _optional_bool(facts, "eda"),
        "execution_nodes": _optional_count(facts, "execution_nodes"),
        "hosts": [_parse_host(item) for item in hosts],
    }


def _parse_host(item) -> dict:
    if not isinstance(item, dict):
        raise PrecheckError("Each host must be an object.")
    name = item.get("name")
    if not isinstance(name, str) or not name.strip():
        raise PrecheckError("Each host needs a name.")
    role = item.get("role")
    if role not in _ROLES:
        raise PrecheckError("Host role is not one of the RPM topology roles.")
    return {
        "name": name.strip(),
        "role": role,
        "rhel": _optional_rhel(item.get("rhel")),
        "cpu": _optional_number(item, "cpu"),
        "memory_gb": _optional_number(item, "memory_gb"),
        "disk_gb": _optional_number(item, "disk_gb"),
        "noexec": _optional_paths(item.get("noexec")),
        "localhost_hostname": _optional_bool(item, "localhost_hostname"),
        "registered": _optional_bool(item, "registered"),
        "custom_venvs": _optional_bool(item, "custom_venvs"),
        "schema_ok": _optional_bool(item, "schema_ok"),
        "open_ports": _optional_ports(item.get("open_ports")),
    }


def _optional_bool(facts: dict, key: str):
    if key not in facts or facts[key] is None:
        return None
    if not isinstance(facts[key], bool):
        raise PrecheckError(f"{key} must be true, false, or null.")
    return facts[key]


def _optional_count(facts: dict, key: str):
    if key not in facts or facts[key] is None:
        return None
    value = facts[key]
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise PrecheckError(f"{key} must be zero or a positive integer.")
    return value


def _optional_number(item: dict, key: str):
    if key not in item or item[key] is None:
        return None
    value = item[key]
    if isinstance(value, bool) or not isinstance(value, (int, float)) or value < 0:
        raise PrecheckError(f"{key} must be a number.")
    return value


def _optional_rhel(value):
    if value is None or value == "":
        return None
    if isinstance(value, bool):
        raise PrecheckError("rhel must be a version such as 9.5.")
    match = re.match(r"^\s*(\d+)(?:\.(\d+))?", str(value))
    if not match:
        raise PrecheckError("rhel must be a version such as 9.5.")
    minor = int(match.group(2)) if match.group(2) is not None else None
    return (int(match.group(1)), minor)


def _optional_paths(value):
    if value is None:
        return None
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise PrecheckError("noexec must be a list of mount paths.")
    return [item.strip().rstrip("/") or "/" for item in value]


def _optional_ports(value):
    if value is None:
        return None
    if not isinstance(value, list):
        raise PrecheckError("open_ports must be a list of port numbers.")
    ports = []
    for item in value:
        if isinstance(item, bool) or not isinstance(item, int) or not 1 <= item <= 65535:
            raise PrecheckError("open_ports must be a list of port numbers.")
        ports.append(item)
    return ports


def _controller_check(parsed, profile) -> dict:
    version = parsed["controller_version"]
    if version is None:
        return _unknown(
            "controller-version",
            "Automation controller version",
            "The controller version was not provided.",
            "Read the version from the controller before the upgrade.",
        )
    parsed_version = _version_tuple(version)
    if profile["version"] == "2.4":
        ok = parsed_version is not None and (4, 4) <= parsed_version[:2] < (4, 6)
        required = "Automation controller 4.4 or 4.5"
        detail = "AAP 2.4 RPM uses automation controller 4.4 or 4.5."
    else:
        minimum = profile["controller_min"]
        ok = parsed_version is not None and parsed_version[:2] >= minimum
        required = "Automation controller 4.5 or newer"
        detail = (
            "This 2.6 RPM installer preflight stops when the automation controller "
            "is older than 4.5."
        )
    return _check(
        "controller-version",
        "Automation controller version",
        "ready" if ok else "blocked",
        version,
        required,
        detail,
    )


def _host_checks(host, profile, parsed) -> list[dict]:
    checks = [
        _os_check(host, profile),
        _capacity_check(host),
        _noexec_check(host),
        _hostname_check(host),
        _registered_check(host),
        _firewall_check(host, profile, parsed),
    ]
    if host["role"] == "automationcontroller":
        checks.append(_venv_check(host))
        checks.append(_schema_check(host))
    return [item for item in checks if item is not None]


def _os_check(host, profile) -> dict:
    name = host["name"]
    found = _format_rhel(host["rhel"])
    if profile["os"] == "rhel-9.6":
        required = "Red Hat Enterprise Linux 9.6 or later"
        detail = "The 2.6 RPM installer rejects RHEL 9.5 and any earlier minor."
        ok = _meets_rhel96(host["rhel"])
    else:
        required = "Red Hat Enterprise Linux 8.4 or later, or RHEL 9"
        detail = "AAP 2.4 RPM runs on RHEL 8.4 or later, and on RHEL 9."
        ok = _meets_rhel24(host["rhel"])
    if host["rhel"] is None:
        return _unknown(
            f"os:{name}",
            f"RHEL version on {name}",
            "Not measured.",
            required,
        )
    return _check(
        f"os:{name}",
        f"RHEL version on {name}",
        "ready" if ok else "blocked",
        found,
        required,
        detail,
    )


def _capacity_check(host) -> dict:
    name = host["name"]
    cpu_min, memory_min, disk_min = _CAPACITY[host["role"]]
    required = f"{cpu_min} CPU, {memory_min} GB RAM, {disk_min} GB disk"
    measured = {
        "cpu": host["cpu"],
        "memory_gb": host["memory_gb"],
        "disk_gb": host["disk_gb"],
    }
    if all(value is None for value in measured.values()):
        return _unknown(
            f"capacity:{name}",
            f"Capacity of {name}",
            "CPU, memory, and disk were not measured.",
            required,
        )
    short = []
    if host["cpu"] is not None and host["cpu"] < cpu_min:
        short.append(f"{host['cpu']} CPU")
    if host["memory_gb"] is not None and host["memory_gb"] < memory_min:
        short.append(f"{host['memory_gb']} GB RAM")
    if host["disk_gb"] is not None and host["disk_gb"] < disk_min:
        short.append(f"{host['disk_gb']} GB disk")
    missing = [key for key, value in measured.items() if value is None]
    if short:
        return _check(
            f"capacity:{name}",
            f"Capacity of {name}",
            "blocked",
            ", ".join(short),
            required,
            "The host is below the tested minimum for this role.",
        )
    if missing:
        return _unknown(
            f"capacity:{name}",
            f"Capacity of {name}",
            "Measured values meet the minimum. " + ", ".join(missing) + " was not measured.",
            required,
        )
    return _check(
        f"capacity:{name}",
        f"Capacity of {name}",
        "ready",
        required,
        required,
        "CPU, memory, and disk meet the tested minimum for this role.",
    )


def _noexec_check(host) -> dict:
    name = host["name"]
    required = "noexec is absent from /tmp, /var, and /var/tmp"
    if host["noexec"] is None:
        return _unknown(
            f"noexec:{name}",
            f"noexec mounts on {name}",
            "Not measured.",
            required,
        )
    found = [path for path in host["noexec"] if path in _NOEXEC]
    if found:
        return _check(
            f"noexec:{name}",
            f"noexec mounts on {name}",
            "blocked",
            ", ".join(found),
            required,
            "The installer preflight stops when these paths are mounted noexec.",
        )
    return _check(
        f"noexec:{name}",
        f"noexec mounts on {name}",
        "ready",
        "none",
        required,
        "The installer preflight accepts these mounts.",
    )


def _hostname_check(host) -> dict:
    name = host["name"]
    required = "Hostname is not localhost"
    if host["localhost_hostname"] is None:
        return _unknown(
            f"hostname:{name}",
            f"Hostname of {name}",
            "Not measured.",
            required,
        )
    if host["localhost_hostname"]:
        return _check(
            f"hostname:{name}",
            f"Hostname of {name}",
            "blocked",
            "localhost",
            required,
            "Receptor preflight stops when a node hostname is localhost.",
        )
    return _check(
        f"hostname:{name}",
        f"Hostname of {name}",
        "ready",
        name,
        required,
        "The hostname is not localhost.",
    )


def _registered_check(host) -> dict:
    name = host["name"]
    required = "Registered with subscription-manager"
    if host["registered"] is None:
        return _unknown(
            f"subscription:{name}",
            f"Subscription on {name}",
            "Not measured.",
            required,
        )
    if not host["registered"]:
        return _check(
            f"subscription:{name}",
            f"Subscription on {name}",
            "blocked",
            "Not registered",
            required,
            "The installer reads subscription-manager identity before it installs packages.",
        )
    return _check(
        f"subscription:{name}",
        f"Subscription on {name}",
        "ready",
        "Registered",
        required,
        "subscription-manager identity succeeded.",
    )


def _venv_check(host) -> dict:
    name = host["name"]
    required = "No custom virtual environments"
    if host["custom_venvs"] is None:
        return _unknown(
            f"venv:{name}",
            f"Custom virtual environments on {name}",
            "Not measured.",
            required,
        )
    if host["custom_venvs"]:
        return _check(
            f"venv:{name}",
            f"Custom virtual environments on {name}",
            "blocked",
            "Present",
            required,
            "The 2.6 installer preflight stops when custom virtual environments are present.",
        )
    return _check(
        f"venv:{name}",
        f"Custom virtual environments on {name}",
        "ready",
        "None",
        required,
        "No custom virtual environments were reported.",
    )


def _schema_check(host) -> dict:
    name = host["name"]
    required = "awx-manage migrate --check passes"
    if host["schema_ok"] is None:
        return _unknown(
            f"schema:{name}",
            f"Controller schema on {name}",
            "Not measured.",
            required,
        )
    if not host["schema_ok"]:
        return _check(
            f"schema:{name}",
            f"Controller schema on {name}",
            "blocked",
            "migrate --check failed",
            required,
            "A partial migration or an unhealthy schema stops the installer.",
        )
    return _check(
        f"schema:{name}",
        f"Controller schema on {name}",
        "ready",
        "migrate --check passed",
        required,
        "The controller schema is ready for the installer.",
    )


def _firewall_check(host, profile, parsed) -> dict:
    name = host["name"]
    needed = _inbound_ports(host["role"], profile, parsed)
    required = _format_ports(needed) if needed else "No extra inbound ports for this role"
    if host["open_ports"] is None:
        return _unknown(
            f"firewall:{name}",
            f"Firewall ports on {name}",
            "Not measured.",
            required,
        )
    missing = sorted(port for port in needed if port not in host["open_ports"])
    if missing:
        return _check(
            f"firewall:{name}",
            f"Firewall ports on {name}",
            "blocked",
            "Closed: " + _format_ports(missing),
            required,
            "These destination ports are required for this AAP version and are not open.",
        )
    return _check(
        f"firewall:{name}",
        f"Firewall ports on {name}",
        "ready",
        required,
        required,
        "The required inbound ports for this role are open.",
    )


def _inbound_ports(role, profile, parsed) -> set[int]:
    needed = set()
    for flow in profile["ports"]:
        if not flow["required"] or flow["destination_role"] != role:
            continue
        if not _flow_applies(flow, parsed):
            continue
        needed.add(flow["port"])
    return needed


def _role_present(parsed, role) -> bool:
    return any(host["role"] == role for host in parsed["hosts"])


def _flow_applies(flow, parsed) -> bool:
    applies = flow["applies"]
    if applies == "hub":
        if parsed["hub"] is False:
            return False
        if parsed["hub"] is True:
            return True
        return _role_present(parsed, "automationhub")
    if applies == "eda":
        if parsed["eda"] is False:
            return False
        if parsed["eda"] is True:
            return True
        return _role_present(parsed, "automationedacontroller")
    if applies == "execution":
        if _role_present(parsed, "execution"):
            return True
        nodes = parsed["execution_nodes"]
        return nodes is not None and nodes > 0
    return True


def _meets_rhel96(rhel) -> bool:
    if rhel is None:
        return False
    major, minor = rhel
    if major != 9 or minor is None:
        return False
    return minor >= 6


def _meets_rhel24(rhel) -> bool:
    if rhel is None:
        return False
    major, minor = rhel
    if major == 9:
        return True
    if major == 8 and minor is not None:
        return minor >= 4
    return False


def _format_rhel(rhel) -> str:
    if rhel is None:
        return "Not measured"
    major, minor = rhel
    if minor is None:
        return str(major)
    return f"{major}.{minor}"


def _format_ports(ports) -> str:
    return ", ".join(f"{port}/tcp" for port in sorted(ports))


def _version_tuple(value: str):
    parts = []
    for piece in value.split("."):
        digits = ""
        for char in piece:
            if char.isdigit():
                digits += char
            else:
                break
        if not digits:
            break
        parts.append(int(digits))
    return tuple(parts) if parts else None


def _overall(checks) -> str:
    statuses = [item["status"] for item in checks]
    if "blocked" in statuses:
        return "blocked"
    if "unknown" in statuses:
        return "incomplete"
    return "ready"


def _summary(status, profile) -> str:
    title = profile["title"]
    if status == "ready":
        return f"The measured hosts meet the preflight and port requirements for {title}."
    if status == "blocked":
        return f"A preflight check for {title} failed. Fix the blocked items before the upgrade."
    return f"Preflight for {title} is incomplete. Measure the remaining hosts before the upgrade."


def _check(check_id, title, status, found, required, detail) -> dict:
    return {
        "id": check_id,
        "title": title,
        "status": status,
        "found": found,
        "required": required,
        "detail": detail,
    }


def _unknown(check_id, title, found, required) -> dict:
    return _check(check_id, title, "unknown", found, required, "This check has not been measured yet.")
