import os
import sqlite3
import unittest

from national_scheduler import ALL_STATES, approved_states, national_summary, ranked_states, refill_national_queue


class NationalSchedulerTests(unittest.TestCase):
    def setUp(self):
        self.conn = sqlite3.connect(":memory:")
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("""create table ember_state_cursors(
            state text primary key,last_index_id integer default 0,companies_processed integer default 0,
            contacts_found integer default 0,last_run_at text default '',updated_at text default ''
        )""")
        self.old = os.environ.get("EMBER_APPROVED_STATES")
        os.environ["EMBER_APPROVED_STATES"] = "ALL"

    def tearDown(self):
        self.conn.close()
        if self.old is None:
            os.environ.pop("EMBER_APPROVED_STATES", None)
        else:
            os.environ["EMBER_APPROVED_STATES"] = self.old

    def test_all_states_are_enabled(self):
        self.assertEqual(50, len(ALL_STATES))
        self.assertEqual(50, len(approved_states()))
        self.assertEqual(50, len(set(approved_states())))

    def test_never_run_states_rank_before_covered_states(self):
        self.conn.execute("insert into ember_state_cursors(state,last_run_at,companies_processed) values('AL','2026-08-01T00:00:00',10)")
        ranked = ranked_states(self.conn)
        self.assertNotEqual('AL', ranked[0])
        self.assertLess(ranked.index('AK'), ranked.index('AL'))

    def test_refill_is_bounded_and_deduplicated(self):
        first = refill_national_queue(self.conn, target_depth=6)
        second = refill_national_queue(self.conn, target_depth=6)
        self.assertEqual(6, len(first))
        self.assertEqual([], second)
        rows = self.conn.execute("select state from crawl_jobs where status='Queued'").fetchall()
        self.assertEqual(6, len(rows))
        self.assertEqual(6, len({row['state'] for row in rows}))

    def test_summary_is_decision_sized(self):
        refill_national_queue(self.conn, target_depth=4)
        summary = national_summary(self.conn)
        self.assertEqual(50, summary['enabled_states'])
        self.assertEqual(4, summary['active_state_jobs'])
        self.assertLessEqual(len(summary['next_states']), 5)
        self.assertFalse(summary['outreach_enabled'])
        self.assertTrue(summary['human_review_required'])


if __name__ == '__main__':
    unittest.main()
