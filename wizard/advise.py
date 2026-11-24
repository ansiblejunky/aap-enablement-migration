"""Support advice for an AAP 2.4 migration-lab controller.

The decision rules follow the published AAP 2.6 upgrade and same-version
migration matrix. Step text here is a short teaching sequence with links
back to those documents, not a copy of them.

https://docs.redhat.com/en/documentation/red_hat_ansible_automation_platform/2.6/upgrade-con_aap_upgrade_overview
https://docs.redhat.com/en/documentation/red_hat_ansible_automation_platform/2.6/upgrade-ref_upgrade_scenarios_rpm
https://docs.redhat.com/en/documentation/red_hat_ansible_automation_platform/2.6/whats_new-aap_26
https://docs.redhat.com/en/documentation/red_hat_ansible_automation_platform/2.6/upgrade-assembly_aap_upgrading_platform
https://docs.redhat.com/en/documentation/red_hat_ansible_automation_platform/2.next/html/ansible_automation_platform_preview_release_notes/supported_upgrade_paths
"""

from __future__ import annotations

DOC_OVERVIEW = (
    "https://docs.redhat.com/en/documentation/red_hat_ansible_automation_platform/"
    "2.6/upgrade-con_aap_upgrade_overview"
)
DOC_RPM = (
    "https://docs.redhat.com/en/documentation/red_hat_ansible_automation_platform/"
    "2.6/upgrade-ref_upgrade_scenarios_rpm"
)
DOC_WHATS_NEW = (
    "https://docs.redhat.com/en/documentation/red_hat_ansible_automation_platform/"
    "2.6/whats_new-aap_26"
)
DOC_UPGRADE = (
    "https://docs.redhat.com/en/documentation/red_hat_ansible_automation_platform/"
    "2.6/upgrade-assembly_aap_upgrading_platform"
)
DOC_27 = (
    "https://docs.redhat.com/en/documentation/red_hat_ansible_automation_platform/"
    "2.next/html/ansible_automation_platform_preview_release_notes/"
    "supported_upgrade_paths"
)

OVERVIEW_DOC = {"title": "Plan your upgrade to AAP 2.6", "url": DOC_OVERVIEW}
RPM_DOC = {"title": "Supported RPM upgrade and migration scenarios", "url": DOC_RPM}
WHATS_NEW_DOC = {"title": "AAP 2.6 upgrade and migration tables", "url": DOC_WHATS_NEW}
UPGRADE_DOC = {"title": "Upgrade Ansible Automation Platform", "url": DOC_UPGRADE}
NEXT_DOC = {"title": "Supported paths through AAP 2.7", "url": DOC_27}

AUTH_STEP = (
    "Reach users through the platform gateway after the upgrade. "
    "LDAP, SAML, and OIDC settings move to the gateway with the 2.6 upgrade."
)
INSTALL_STEP = (
    "Keep install-apd.yml on the 2.4 controller. That playbook talks only to "
    "/api/v2/ and stops when the automation controller version is outside 4.4 and 4.5."
)
VALIDATE_STEP = (
    "Validate the workload on the target. The AAP Migration Lab organization, "
    "its project, and its job templates are present, and a project sync succeeds."
)
CLOSING = [AUTH_STEP, INSTALL_STEP, VALIDATE_STEP]

_INSTALLERS = {"rpm", "operator", "containerized"}
_API_STYLES = {"v2", "gateway"}
_RHEL = {8, 9, 10}


class AdviseError(ValueError):
    """The page sent facts the wizard cannot score."""


def advise(facts: dict) -> dict:
    """Return supported targets and teaching steps for one source."""
    parsed = _parse_facts(facts)
    source = _source(parsed)
    eda = _eda(parsed)
    notes = _lab_notes(parsed)
    if not source["is_lab_source"]:
        return {
            "source": source,
            "targets": [],
            "recommended_id": None,
            "eda": eda,
            "lab_notes": notes,
        }
    targets = _targets(parsed, source["topology"])
    recommended = next((item["id"] for item in targets if item["recommended"]), None)
    return {
        "source": source,
        "targets": targets,
        "recommended_id": recommended,
        "eda": eda,
        "lab_notes": notes,
    }


def _parse_facts(facts: dict) -> dict:
    if not isinstance(facts, dict):
        raise AdviseError("Facts must be a JSON object.")
    version = _require(facts, "controller_version")
    if not isinstance(version, str) or not version.strip():
        raise AdviseError("controller_version must be a string.")
    api_style = _require(facts, "api_style")
    if api_style not in _API_STYLES:
        raise AdviseError("api_style must be v2 or gateway.")
    installer = _require(facts, "installer")
    if installer not in _INSTALLERS:
        raise AdviseError("installer must be rpm, operator, or containerized.")
    rhel_major = _parse_rhel(facts, installer)
    return {
        "controller_version": version.strip(),
        "version_tuple": _parse_version(version),
        "api_style": api_style,
        "control_plane_nodes": _parse_count(facts, "control_plane_nodes"),
        "execution_nodes": _parse_count(facts, "execution_nodes"),
        "installer": installer,
        "rhel_major": rhel_major,
        "hub": _parse_bool(facts, "hub"),
        "eda": _parse_bool(facts, "eda"),
        "lab_org": _parse_optional_bool(facts, "lab_org"),
        "lab_project": _parse_optional_bool(facts, "lab_project"),
        "job_template_count": _parse_optional_count(facts, "job_template_count"),
        "execution_environment_count": _parse_optional_count(
            facts, "execution_environment_count"
        ),
        "auth": _parse_auth(facts.get("auth")),
    }


def _require(facts: dict, key: str):
    if key not in facts:
        raise AdviseError(f"Missing {key}.")
    return facts[key]


def _parse_bool(facts: dict, key: str) -> bool:
    value = _require(facts, key)
    if not isinstance(value, bool):
        raise AdviseError(f"{key} must be true or false.")
    return value


def _parse_optional_bool(facts: dict, key: str):
    if key not in facts or facts[key] is None:
        return None
    if not isinstance(facts[key], bool):
        raise AdviseError(f"{key} must be true, false, or null.")
    return facts[key]


def _parse_count(facts: dict, key: str) -> int:
    value = _require(facts, key)
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise AdviseError(f"{key} must be zero or a positive integer.")
    return value


def _parse_optional_count(facts: dict, key: str):
    if key not in facts or facts[key] is None:
        return None
    value = facts[key]
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise AdviseError(f"{key} must be zero or a positive integer.")
    return value


def _parse_rhel(facts: dict, installer: str):
    if "rhel_major" not in facts or facts["rhel_major"] is None:
        if installer == "rpm":
            raise AdviseError("RPM sources need a RHEL major version: 8, 9, or 10.")
        return None
    value = facts["rhel_major"]
    if isinstance(value, bool) or value not in _RHEL:
        raise AdviseError("rhel_major must be 8, 9, 10, or null.")
    if installer == "operator":
        return None
    return value


def _parse_auth(value) -> dict:
    blank = {"ldap": None, "saml": None, "oidc": None}
    if value is None:
        return blank
    if not isinstance(value, dict):
        raise AdviseError("auth must be an object.")
    parsed = {}
    for key in ("ldap", "saml", "oidc"):
        item = value.get(key)
        if item is not None and not isinstance(item, bool):
            raise AdviseError(f"auth.{key} must be true, false, or null.")
        parsed[key] = item
    return parsed


def _parse_version(value: str):
    parts = []
    for piece in value.strip().split("."):
        digits = ""
        for char in piece:
            if char.isdigit():
                digits += char
            else:
                break
        if not digits:
            return None
        parts.append(int(digits))
    return tuple(parts) if parts else None


def _is_aap_24(version) -> bool:
    if not version or len(version) < 2:
        return False
    major_minor = version[:2]
    return (4, 4) <= major_minor < (4, 6)


def _topology(control_plane_nodes: int):
    if control_plane_nodes == 1:
        return "growth"
    if control_plane_nodes > 1:
        return "enterprise"
    return None


def _shape(topology: str, hub: bool) -> str:
    label = "growth" if topology == "growth" else "enterprise"
    if hub:
        return f"{label} with automation hub"
    return label


def _source(parsed: dict) -> dict:
    version = parsed["version_tuple"]
    aap = "2.4" if _is_aap_24(version) else None
    lab = parsed["api_style"] == "v2" and aap == "2.4"
    topology = _topology(parsed["control_plane_nodes"]) if lab else None
    detected = [name for name, enabled in parsed["auth"].items() if enabled is True]
    unreadable = [name for name, enabled in parsed["auth"].items() if enabled is None]
    return {
        "controller_version": parsed["controller_version"],
        "aap_version": aap if lab else None,
        "api_style": parsed["api_style"],
        "is_lab_source": lab,
        "topology": topology,
        "installer": parsed["installer"],
        "rhel_major": parsed["rhel_major"],
        "hub": parsed["hub"],
        "control_plane_nodes": parsed["control_plane_nodes"],
        "execution_nodes": parsed["execution_nodes"],
        "auth_detected": detected,
        "auth_unreadable": unreadable,
        "message": _source_message(parsed, aap, lab, topology),
    }


def _source_message(parsed, aap, lab, topology) -> str:
    shown = parsed["controller_version"]
    if parsed["api_style"] == "gateway":
        return (
            f"This URL answered on /api/controller/v2/ with automation controller "
            f"{shown}. The AAP 2.4 lab uses /api/v2/ on the controller."
        )
    if aap != "2.4":
        return (
            f"Automation controller {shown} is outside the 4.4 and 4.5 releases "
            f"this lab installs on."
        )
    if topology is None:
        return (
            f"Automation controller {shown} is AAP 2.4. The ping response listed "
            f"no control or hybrid nodes, so growth or enterprise is still unknown."
        )
    kind = "growth" if topology == "growth" else "enterprise"
    plane = parsed["control_plane_nodes"]
    execs = parsed["execution_nodes"]
    plane_noun = "node" if plane == 1 else "nodes"
    exec_noun = "node" if execs == 1 else "nodes"
    return (
        f"Automation controller {shown} is AAP 2.4, with {plane} control-plane "
        f"{plane_noun} and {execs} execution {exec_noun}. That control plane maps "
        f"to a 2.6 {kind} topology."
    )


def _eda(parsed: dict):
    if not parsed["eda"]:
        return None
    return {
        "in_place_supported": False,
        "summary": (
            "Event-Driven Ansible 2.4 needs a new 2.6 EDA deployment. "
            "An in-place upgrade of that EDA controller is not supported."
        ),
    }


def _lab_notes(parsed: dict) -> list[str]:
    notes = [
        (
            "install-apd.yml on this branch only talks to automation controller "
            "/api/v2/ on AAP 2.4."
        ),
        (
            "The config-drift EDA activation in this lab still expects a later "
            "platform gateway, an AAP 2.7 decision environment, and an "
            "/api/controller credential host."
        ),
        (
            "Validation means the AAP Migration Lab organization, its project, "
            "and its job templates are present, and a project sync succeeds."
        ),
    ]
    if parsed["lab_org"] is False or parsed["lab_project"] is False:
        notes.insert(
            0,
            (
                "The live check did not find the AAP Migration Lab organization and "
                "project together. Run install-apd.yml on this 2.4 controller before "
                "treating it as the migration source."
            ),
        )
    return notes


def _targets(parsed: dict, topology) -> list[dict]:
    if topology is None:
        return [
            _target(
                id="topology-unknown",
                title="Growth or enterprise",
                status="unsupported",
                direct=False,
                summary="Ping listed no control or hybrid nodes.",
                why=(
                    "Point the wizard at a control node. /api/v2/ping/ lists "
                    "hybrid, control, and execution nodes, and omits hop nodes. "
                    "One control-plane node maps to growth. More than one control "
                    "or hybrid node maps to enterprise."
                ),
                steps=[],
                docs=[OVERVIEW_DOC],
            )
        ]
    installer = parsed["installer"]
    if installer == "containerized":
        return _containerized_targets()
    if installer == "operator":
        return _operator_targets(parsed, topology)
    return _rpm_targets(parsed, topology)


def _containerized_targets() -> list[dict]:
    return [
        _target(
            id="container-2.6",
            title="AAP 2.6 containerized upgrade",
            status="unsupported",
            direct=True,
            summary="A 2.4 containerized deployment has no supported in-place upgrade to 2.6.",
            why="An upgrade from a 2.4 containerized deployment to 2.6 is not supported.",
            steps=[],
            docs=[OVERVIEW_DOC, WHATS_NEW_DOC],
        ),
        _target(
            id="aap-2.7",
            title="AAP 2.7",
            status="unsupported",
            direct=False,
            summary="A direct jump from this 2.4 containerized deployment to 2.7 is unsupported.",
            why=(
                "A direct upgrade from 2.4 to 2.7 is not supported. A 2.4 "
                "containerized deployment also has no supported in-place upgrade to 2.6."
            ),
            steps=[],
            docs=[NEXT_DOC, OVERVIEW_DOC],
        ),
    ]


def _operator_targets(parsed: dict, topology: str) -> list[dict]:
    shape = _shape(topology, parsed["hub"])
    why = _topology_why(parsed, topology)
    upgrade = [
        "Back up the AAP 2.4 operator deployment.",
        f"Upgrade the operator deployment to AAP 2.6 {shape}.",
    ]
    targets = [
        _target(
            id="operator-2.6",
            title=f"AAP 2.6 operator {shape}",
            status="supported",
            direct=True,
            recommended=True,
            summary=f"Upgrade this operator deployment in place to AAP 2.6 {shape}.",
            why=why,
            steps=upgrade + CLOSING,
            docs=[OVERVIEW_DOC, UPGRADE_DOC, WHATS_NEW_DOC],
        ),
        _target(
            id="aap-2.7",
            title="AAP 2.7 operator",
            status="supported_with_steps",
            direct=False,
            summary="Reach AAP 2.6 on the operator, then upgrade that deployment to 2.7.",
            why="A direct upgrade from 2.4 or 2.5 to 2.7 is not supported.",
            steps=[
                "Upgrade the operator deployment from 2.4 to 2.6.",
                "Upgrade that 2.6 operator deployment to 2.7.",
                VALIDATE_STEP,
            ],
            docs=[NEXT_DOC, OVERVIEW_DOC],
        ),
    ]
    return targets


def _rpm_targets(parsed: dict, topology: str) -> list[dict]:
    if parsed["rhel_major"] == 10:
        return _rpm_rhel10_targets()
    shape = _shape(topology, parsed["hub"])
    reach = _reach_rpm_26(parsed, shape)
    rhel8 = parsed["rhel_major"] == 8
    recommended = _target(
        id="rpm-2.6",
        title=f"AAP 2.6 RPM {shape}",
        status="supported_with_steps" if rhel8 else "supported",
        direct=not rhel8,
        recommended=True,
        summary=(
            f"Restore this deployment onto RHEL 9, then upgrade to AAP 2.6 RPM {shape}."
            if rhel8
            else f"Upgrade this RHEL 9 RPM deployment in place to AAP 2.6 RPM {shape}."
        ),
        why=_rpm_why(parsed, topology, rhel8),
        steps=reach + CLOSING,
        docs=[RPM_DOC, OVERVIEW_DOC, UPGRADE_DOC],
    )
    later = _rpm_follow_on_targets(reach, shape)
    targets = [recommended, *later]
    if rhel8:
        targets.append(
            _target(
                id="rpm-2.6-inplace",
                title="AAP 2.6 RPM in place on RHEL 8",
                status="unsupported",
                direct=True,
                summary="RPM-based AAP 2.6 requires RHEL 9.",
                why=(
                    "RPM-based AAP 2.6 requires RHEL 9. An in-place upgrade of this "
                    "RHEL 8 host to RHEL 9 is outside the supported path. Restore "
                    "the deployment onto new RHEL 9 hosts, then upgrade."
                ),
                steps=[],
                docs=[RPM_DOC, OVERVIEW_DOC],
            )
        )
    return targets


def _rpm_rhel10_targets() -> list[dict]:
    return [
        _target(
            id="rpm-2.6",
            title="AAP 2.6 RPM",
            status="unsupported",
            direct=True,
            summary="Documented RPM upgrades to 2.6 start from RHEL 8 or RHEL 9.",
            why=(
                "The documented RPM upgrades to AAP 2.6 start from RHEL 8 or RHEL 9. "
                "This source is RHEL 10."
            ),
            steps=[],
            docs=[RPM_DOC, OVERVIEW_DOC],
        ),
        _target(
            id="aap-2.7",
            title="AAP 2.7",
            status="unsupported",
            direct=False,
            summary="A direct jump from AAP 2.4 to 2.7 is unsupported.",
            why=(
                "A direct upgrade from 2.4 or 2.5 to 2.7 is not supported. "
                "AAP 2.6 is the last release published for RPM installations."
            ),
            steps=[],
            docs=[NEXT_DOC, RPM_DOC],
        ),
    ]


def _reach_rpm_26(parsed: dict, shape: str) -> list[str]:
    inventory = (
        f"Prepare a 2.6 {shape} RPM inventory, including the platform gateway "
        f"hosts AAP 2.6 adds."
    )
    if parsed["rhel_major"] == 8:
        return [
            "Back up the AAP 2.4 RPM deployment.",
            "Restore that backup onto new RHEL 9 hosts. RPM-based AAP 2.6 requires RHEL 9.",
            inventory,
            f"Upgrade the restored deployment to AAP 2.6 RPM {shape}.",
        ]
    return [
        "Back up the automation controller and private automation hub.",
        inventory,
        f"Upgrade this RHEL 9 RPM deployment in place to AAP 2.6 RPM {shape}.",
    ]


def _rpm_follow_on_targets(reach: list[str], shape: str) -> list[dict]:
    container_rhel9 = (
        "Migrate the AAP 2.6 RPM deployment to containerized AAP 2.6 on RHEL 9. "
        "A deployment-type change is supported when both sides are the same AAP version."
    )
    return [
        _target(
            id="container-2.6-rhel9",
            title="Containerized AAP 2.6 on RHEL 9",
            status="supported_with_steps",
            direct=False,
            summary="Reach AAP 2.6 RPM, then migrate to containerized AAP 2.6 on RHEL 9.",
            why=(
                "Changing from RPM to containerized AAP is a same-version migration. "
                "Complete the 2.6 RPM upgrade first."
            ),
            steps=reach + [container_rhel9, VALIDATE_STEP],
            docs=[RPM_DOC, WHATS_NEW_DOC],
        ),
        _target(
            id="container-2.6-rhel10",
            title="Containerized AAP 2.6 on RHEL 10",
            status="supported_with_steps",
            direct=False,
            summary=(
                "Reach containerized AAP 2.6 on RHEL 9, then restore that backup "
                "onto RHEL 10."
            ),
            why=(
                "The documented path onto containerized AAP 2.6 on RHEL 10 restores "
                "a containerized 2.6 backup from RHEL 9."
            ),
            steps=reach
            + [
                container_rhel9,
                (
                    "Back up the containerized AAP 2.6 deployment on RHEL 9 and "
                    "restore it onto a fresh containerized AAP 2.6 installation on RHEL 10."
                ),
                VALIDATE_STEP,
            ],
            docs=[RPM_DOC],
        ),
        _target(
            id="openshift-2.6",
            title="AAP 2.6 on OpenShift",
            status="supported_with_steps",
            direct=False,
            summary="Reach AAP 2.6 RPM, then migrate to OpenShift with aap_snapshot.",
            why=(
                "RPM to OpenShift is a same-version migration. Complete the 2.6 RPM "
                f"upgrade to {shape} first."
            ),
            steps=reach
            + [
                (
                    "Migrate the AAP 2.6 RPM deployment to AAP 2.6 on OpenShift "
                    "with the aap_snapshot collection."
                ),
                VALIDATE_STEP,
            ],
            docs=[RPM_DOC, WHATS_NEW_DOC],
        ),
        _target(
            id="managed-2.6",
            title="Managed AAP 2.6",
            status="supported_with_steps",
            direct=False,
            summary="Reach AAP 2.6 RPM, then migrate to managed AAP at the same version.",
            why=(
                "RPM to managed AAP is a same-version migration. Complete the 2.6 "
                "RPM upgrade first."
            ),
            steps=reach
            + [
                (
                    "Migrate the AAP 2.6 RPM deployment to managed AAP 2.6. "
                    "A deployment-type change is supported when both sides are "
                    "the same AAP version."
                ),
                VALIDATE_STEP,
            ],
            docs=[WHATS_NEW_DOC, RPM_DOC],
        ),
        _target(
            id="aap-2.7",
            title="AAP 2.7",
            status="supported_with_steps",
            direct=False,
            summary=(
                "Reach AAP 2.6, leave RPM for containerized or OpenShift, then upgrade to 2.7."
            ),
            why=(
                "A direct upgrade from 2.4 or 2.5 to 2.7 is not supported. "
                "AAP 2.6 is the last release published for RPM installations."
            ),
            steps=reach
            + [
                (
                    "Migrate that AAP 2.6 RPM deployment to containerized AAP 2.6 "
                    "or to AAP 2.6 on OpenShift."
                ),
                "Upgrade the containerized or OpenShift deployment from 2.6 to 2.7.",
                VALIDATE_STEP,
            ],
            docs=[NEXT_DOC, RPM_DOC, WHATS_NEW_DOC],
        ),
    ]


def _topology_why(parsed: dict, topology: str) -> str:
    kind = "growth" if topology == "growth" else "enterprise"
    if parsed["control_plane_nodes"] == 1:
        plane = "One control-plane node maps to a 2.6 growth topology."
    else:
        plane = (
            "More than one control or hybrid node maps to a 2.6 enterprise topology."
        )
    execution = " Execution nodes do not change that result."
    if parsed["hub"]:
        hub = (
            f" Private automation hub keeps this source on the same {kind} result."
        )
    else:
        hub = ""
    return plane + execution + hub


def _rpm_why(parsed: dict, topology: str, rhel8: bool) -> str:
    base = _topology_why(parsed, topology)
    if rhel8:
        return (
            base
            + " RPM-based AAP 2.6 requires RHEL 9, so the upgrade starts with a "
            "backup restored onto new RHEL 9 hosts."
        )
    return base + " This RHEL 9 RPM deployment can upgrade in place to AAP 2.6."


def _target(
    *,
    id: str,
    title: str,
    status: str,
    direct: bool,
    summary: str,
    why: str,
    steps: list[str],
    docs: list[dict],
    recommended: bool = False,
) -> dict:
    return {
        "id": id,
        "title": title,
        "status": status,
        "direct": direct,
        "recommended": recommended,
        "summary": summary,
        "why": why,
        "steps": list(steps),
        "docs": [dict(item) for item in docs],
    }
