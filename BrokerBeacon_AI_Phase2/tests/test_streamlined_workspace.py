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


if __name__ == "__main__":
    unittest.main()
