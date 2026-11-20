import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from epicbyte.engine import Limits, WorkflowEngine
from epicbyte.provider import QuotaExhausted, is_quota_error, quota_retry_at
from epicbyte.storage import Store

MSG = "You've hit your usage limit. Upgrade to Pro or try again at 3:32 AM."


class QuotaParsingTests(unittest.TestCase):
    def test_reads_reset_time(self):
        tz = timezone(timedelta(hours=-3))
        now = datetime(2026, 11, 20, 1, 0, tzinfo=tz)
        self.assertEqual(quota_retry_at(MSG, now), datetime(2026, 11, 20, 3, 34, tzinfo=tz))
        late = datetime(2026, 11, 20, 4, 0, tzinfo=tz)   # já passou hoje: é amanhã
        self.assertEqual(quota_retry_at(MSG, late).day, 21)
        self.assertEqual(quota_retry_at('try again at 3:15 PM', now).hour, 15)
        self.assertTrue(is_quota_error(MSG))
        self.assertFalse(is_quota_error('Erro de sintaxe'))


class QuotaProvider:
    def execute(self, prompt, workspace, timeout=180, write=False, cancelled=lambda: False):
        raise QuotaExhausted('Limite de uso do provedor: ' + MSG, datetime.now().astimezone() + timedelta(hours=1))


class QuotaEngineTests(unittest.TestCase):
    def test_pauses_without_consuming_attempt(self):
        with tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parents[1]) as d:
            store = Store(str(Path(d) / 'f.db'))
            ws = Path(d) / 'ws'
            ws.mkdir()
            store.create('m', '# missão', ws)
            store.save_plan('m', {'tasks': [{'id': 'T1', 'agent': 'developer', 'mode': 'read-only', 'description': 'ler',
                                             'acceptance_criteria': ['ok'], 'dependencies': []}]})
            WorkflowEngine(store, QuotaProvider(), Path(__file__).resolve().parents[1] / 'agents', Limits()).run('m')
            self.assertEqual(store.mission('m')['state'], 'PAUSED')
            self.assertEqual(store.tasks('m')[0]['attempts'], 0)
            row = store.db.execute("SELECT data FROM events WHERE type='QUOTA_EXHAUSTED'").fetchone()
            self.assertIn('retry_at', row[0])
            store.db.close()


if __name__ == '__main__':
    unittest.main()
