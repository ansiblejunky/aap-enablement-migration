"""Decision coverage for the migration wizard."""

from __future__ import annotations

import unittest

from wizard.advise import AdviseError, advise


def facts(**overrides):
    base = {
        "controller_version": "4.5.1",
        "api_style": "v2",
        "control_plane_nodes": 1,
        "execution_nodes": 0,
        "installer": "rpm",
        "rhel_major": 9,
        "hub": False,
        "eda": False,
        "lab_org": True,
        "lab_project": True,
        "job_template_count": 12,
        "execution_environment_count": 2,
        "auth": {"ldap": False, "saml": False, "oidc": False},
    }
    base.update(overrides)
    return base


def by_id(result, target_id):
    matches = [item for item in result["targets"] if item["id"] == target_id]
    assert len(matches) == 1, target_id
    return matches[0]


class AdviseTests(unittest.TestCase):
    def test_rpm_rhel9_single_node_recommends_growth_in_place(self):
        result = advise(facts(execution_nodes=3))
        self.assertTrue(result["source"]["is_lab_source"])
        self.assertEqual(result["source"]["topology"], "growth")
        self.assertEqual(result["source"]["execution_nodes"], 3)
        recommended = by_id(result, result["recommended_id"])
        self.assertEqual(recommended["id"], "rpm-2.6")
        self.assertEqual(recommended["status"], "supported")
        self.assertTrue(recommended["direct"])
        self.assertIn("growth", recommended["title"].lower())
        self.assertNotIn("enterprise", recommended["title"].lower())

    def test_hub_does_not_change_a_single_control_plane(self):
        result = advise(facts(hub=True, execution_nodes=2))
        self.assertEqual(result["source"]["topology"], "growth")
        recommended = by_id(result, result["recommended_id"])
        self.assertIn("growth", recommended["title"].lower())
        self.assertIn("hub", recommended["title"].lower())

    def test_rhel8_restores_onto_rhel9_before_upgrade(self):
        result = advise(facts(rhel_major=8))
        inplace = by_id(result, "rpm-2.6-inplace")
        self.assertEqual(inplace["status"], "unsupported")
        self.assertTrue(inplace["direct"])
        recommended = by_id(result, result["recommended_id"])
        self.assertEqual(recommended["status"], "supported_with_steps")
        self.assertFalse(recommended["direct"])
        text = " ".join(recommended["steps"]).lower()
        self.assertIn("rhel 9", text)
        self.assertTrue("backup" in text or "back up" in text)
        self.assertIn("restore", text)

    def test_containerized_24_upgrade_is_unsupported(self):
        result = advise(facts(installer="containerized", rhel_major=9))
        direct = [
            item
            for item in result["targets"]
            if item["direct"] and "2.6" in item["title"]
        ]
        self.assertTrue(direct)
        self.assertTrue(all(item["status"] == "unsupported" for item in direct))
        self.assertIsNone(result["recommended_id"])

    def test_operator_multi_node_with_hub_is_enterprise(self):
        result = advise(
            facts(
                installer="operator",
                rhel_major=None,
                hub=True,
                control_plane_nodes=3,
                execution_nodes=4,
            )
        )
        self.assertEqual(result["source"]["topology"], "enterprise")
        recommended = by_id(result, result["recommended_id"])
        self.assertIn("enterprise", recommended["title"].lower())
        self.assertIn("operator", recommended["title"].lower())
        self.assertEqual(recommended["status"], "supported")
        self.assertTrue(recommended["direct"])

    def test_operator_ignores_a_rhel8_answer(self):
        result = advise(facts(installer="operator", rhel_major=8))
        recommended = by_id(result, result["recommended_id"])
        self.assertTrue(recommended["direct"])
        self.assertNotIn("restore", " ".join(recommended["steps"]).lower())

    def test_eda_24_needs_a_new_26_instance(self):
        result = advise(facts(eda=True))
        self.assertIsNotNone(result["eda"])
        self.assertFalse(result["eda"]["in_place_supported"])
        summary = result["eda"]["summary"].lower()
        self.assertIn("new", summary)
        self.assertIn("2.6", summary)
        self.assertEqual(result["recommended_id"], "rpm-2.6")

    def test_direct_27_is_blocked_until_26_and_off_rpm(self):
        result = advise(facts())
        target = by_id(result, "aap-2.7")
        self.assertFalse(target["direct"])
        blob = (target["why"] + " " + " ".join(target["steps"])).lower()
        self.assertIn("2.6", blob)
        self.assertIn("rpm", blob)
        self.assertIn("not supported", target["why"].lower())
        self.assertIn("openshift", blob)

    def test_controller_outside_44_and_45_is_not_the_lab_source(self):
        for version in ("4.6.3", "4.3.0", "4.6"):
            result = advise(facts(controller_version=version))
            self.assertFalse(result["source"]["is_lab_source"], version)
            self.assertIsNone(result["recommended_id"])
            self.assertEqual(result["targets"], [])
        included = advise(facts(controller_version="4.4.0"))
        self.assertTrue(included["source"]["is_lab_source"])

    def test_gateway_url_is_not_the_lab_source(self):
        result = advise(facts(api_style="gateway", controller_version="4.5.0"))
        self.assertFalse(result["source"]["is_lab_source"])
        self.assertIn("/api/controller/v2/", result["source"]["message"])

    def test_lab_notes_mention_installer_and_validation(self):
        result = advise(facts(lab_org=False, lab_project=True))
        blob = " ".join(result["lab_notes"]).lower()
        self.assertIn("install-apd.yml", blob)
        self.assertIn("project sync", blob)
        self.assertIn("config-drift", blob)
        self.assertIn("install-apd.yml", result["lab_notes"][0])

    def test_rpm_without_rhel_is_rejected(self):
        with self.assertRaises(AdviseError):
            advise(facts(rhel_major=None))


if __name__ == "__main__":
    unittest.main()
