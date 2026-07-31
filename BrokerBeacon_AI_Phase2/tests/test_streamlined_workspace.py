import unittest
from pathlib import Path


SOURCE = Path(__file__).resolve().parents[1].joinpath("app.py").read_text(encoding="utf-8")


class StreamlinedWorkspaceTests(unittest.TestCase):
    def test_dashboard_has_one_primary_start_action(self):
        self.assertEqual(SOURCE.count('id="startMyDayBtn"'), 1)
        self.assertIn('Focus on the next best action.', SOURCE)
        self.assertIn('class="workspace-shortcuts"', SOURCE)

    def test_advanced_agent_workflow_is_preserved_but_collapsed(self):
        self.assertIn('<details class="streamlined-details">', SOURCE)
        self.assertEqual(SOURCE.count('id="runAgentTeamBtn"'), 1)
        self.assertEqual(SOURCE.count('id="agentPlan"'), 1)

    def test_secondary_insights_use_progressive_disclosure(self):
        self.assertIn('<details class="workspace-more">', SOURCE)
        self.assertIn("if(v==='dashboard')return", SOURCE)

    def test_platform_controls_are_separated_from_prospects(self):
        self.assertIn('id="platformadmin"', SOURCE)
        self.assertIn("const page=$('#platformAdminContent')", SOURCE)
        self.assertNotIn("const page=$('#prospects')", SOURCE)

    def test_platform_navigation_initializes_account_context_on_startup(self):
        self.assertIn("loadSaasAccount().catch(e=>msg(e.message||'Unable to load account context'));load();", SOURCE)

    def test_platform_admin_has_clickable_state_discovery(self):
        self.assertIn('id="runScoutBtn"', SOURCE)
        self.assertIn('id="scoutMetro"', SOURCE)
        self.assertIn("selectScoutState(code,focusSearch=false)", SOURCE)
        self.assertIn("filterScoutStatus(status)", SOURCE)
        self.assertIn("admin-clickable", SOURCE)

    def test_dashboard_metrics_have_workflow_destinations(self):
        self.assertIn('title="Open Opportunity Engine"', SOURCE)
        self.assertIn('title="Open Daily Plan"', SOURCE)
        self.assertIn('title="Open Pipeline"', SOURCE)

    def test_platform_navigation_requires_owner_context(self):
        self.assertIn("ownerOnly:true", SOURCE)
        self.assertIn("v==='platformadmin'&&!SaaSContext?.user?.is_platform_owner", SOURCE)
        self.assertIn("adminButton.onclick=()=>show('platformadmin')", SOURCE)


if __name__ == "__main__":
    unittest.main()
