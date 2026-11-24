"""Pre-check coverage for installer preflight and version-specific ports."""

from __future__ import annotations

import unittest

from wizard.precheck import PrecheckError, precheck


def host(name, role, **overrides):
    base = {
        "name": name,
        "role": role,
        "rhel": "9.7",
        "cpu": 4,
        "memory_gb": 16,
        "disk_gb": 100,
        "noexec": [],
        "localhost_hostname": False,
        "registered": True,
        "open_ports": [22, 80, 443, 5432, 8443, 16379],
    }
    if role == "automationcontroller":
        base["custom_venvs"] = False
        base["schema_ok"] = True
    base.update(overrides)
    return base


def growth_hosts():
    return [
        host("gateway.lab", "automationgateway"),
        host("controller.lab", "automationcontroller"),
        host("hub.lab", "automationhub"),
        host("database.lab", "database"),
    ]


def by_id(result, check_id):
    matches = [item for item in result["checks"] if item["id"] == check_id]
    assert len(matches) == 1, check_id
    return matches[0]


class PrecheckTests(unittest.TestCase):
    def test_rhel_95_blocks_aap_26_and_passes_aap_24(self):
        hosts = [host("controller.lab", "automationcontroller", rhel="9.5")]
        blocked = precheck({
            "target": "rpm-2.6-growth",
            "controller_version": "4.5.8",
            "hub": False,
            "eda": False,
            "execution_nodes": 0,
            "hosts": hosts,
        })
        os_check = by_id(blocked, "os:controller.lab")
        self.assertEqual(blocked["status"], "blocked")
        self.assertEqual(os_check["status"], "blocked")
        self.assertEqual(os_check["found"], "9.5")
        self.assertIn("9.6", os_check["required"])

        older = precheck({
            "target": "rpm-2.4",
            "controller_version": "4.5.8",
            "hub": False,
            "eda": False,
            "execution_nodes": 0,
            "hosts": hosts,
        })
        self.assertEqual(by_id(older, "os:controller.lab")["status"], "ready")

    def test_controller_older_than_45_blocks_the_26_installer(self):
        result = precheck({
            "target": "rpm-2.6-growth",
            "controller_version": "4.4.2",
            "hosts": [],
        })
        check = by_id(result, "controller-version")
        self.assertEqual(check["status"], "blocked")
        self.assertIn("4.5", check["required"])

    def test_noexec_and_closed_database_port_block(self):
        result = precheck({
            "target": "rpm-2.6-growth",
            "controller_version": "4.5.8",
            "hub": True,
            "eda": False,
            "execution_nodes": 0,
            "hosts": [
                host("controller.lab", "automationcontroller", noexec=["/tmp"]),
                host("database.lab", "database", open_ports=[22]),
            ],
        })
        self.assertEqual(by_id(result, "noexec:controller.lab")["status"], "blocked")
        firewall = by_id(result, "firewall:database.lab")
        self.assertEqual(firewall["status"], "blocked")
        self.assertIn("5432/tcp", firewall["found"])

    def test_measured_growth_hosts_are_ready(self):
        result = precheck({
            "target": "rpm-2.6-growth",
            "controller_version": "4.5.8",
            "hub": True,
            "eda": False,
            "execution_nodes": 0,
            "hosts": growth_hosts(),
        })
        self.assertEqual(result["status"], "ready")

    def test_port_lists_differ_by_version(self):
        growth = precheck({"target": "rpm-2.6-growth", "hosts": []})
        enterprise = precheck({"target": "rpm-2.6-enterprise", "hosts": []})
        current = precheck({"target": "rpm-2.4", "hosts": []})
        growth_sources = {item["source"] for item in growth["ports"]}
        current_sources = {item["source"] for item in current["ports"]}
        self.assertIn("Platform gateway", growth_sources)
        self.assertNotIn("Platform gateway", current_sources)
        enterprise_gateway = [
            item for item in enterprise["ports"]
            if item["port"] == 8443 and item["required"] and item["destination"] == "Platform gateway"
        ]
        growth_gateway = [
            item for item in growth["ports"]
            if item["port"] == 8443 and item["required"] and item["destination"] == "Platform gateway"
        ]
        self.assertTrue(enterprise_gateway)
        self.assertFalse(growth_gateway)

    def test_unknown_target_is_rejected(self):
        with self.assertRaises(PrecheckError):
            precheck({"target": "container-2.6"})


if __name__ == "__main__":
    unittest.main()
