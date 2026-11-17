import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from agent_evidence.fixtures import fixture
from agent_evidence.runner import run_checks
from agent_evidence.serialization import EvidenceError


class Receipts(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.base = Path(self.tmp.name).resolve()
        self.source = self.base / 'input'
        fixture(str(self.source))
        self.output = self.base / 'output'

    def run_case(self):
        return run_checks(str(self.source),'manifest.json',str(self.output))

    def change_policy(self, **changes):
        path = self.source / 'policy.json'
        value = json.loads(path.read_text())
        value['domains']['demo'].update(changes)
        path.write_text(json.dumps(value))

    def test_actual_children_and_receipt_readback(self):
        report = self.run_case()
        self.assertEqual(report['check_verdict'],'PASS')
        self.assertFalse(report['complete'])
        self.assertFalse(report['certified_healthy'])
        self.assertEqual(json.loads((self.output/'report.json').read_text()),report)
        self.assertEqual(len(list(self.output.glob('check-*.json'))),2)
        self.assertTrue(all((p.stat().st_mode & 0o777) == 0o600 for p in self.output.iterdir()))

    def test_policy_denial_never_creates_target_worker(self):
        self.change_policy(enabled=False)
        (self.source/'sample.json').unlink()
        os.mkfifo(self.source/'sample.json')
        with patch('agent_evidence.runner.observe_check',side_effect=AssertionError('worker forbidden')):
            report = self.run_case()
        self.assertEqual(report['check_verdict'],'NOT_APPLICABLE')
        self.assertEqual(len(report['checks']),2)
        self.assertTrue(all(r['required'] for r in report['checks']))
        self.assertFalse(list(self.output.glob('check-*.json')))

    def test_missing_policy_no_worker_no_creation(self):
        (self.source/'policy.json').unlink()
        with patch('agent_evidence.runner.observe_check',side_effect=AssertionError('worker forbidden')):
            report = self.run_case()
        self.assertEqual(report['check_verdict'],'UNKNOWN')
        self.assertFalse((self.source/'policy.json').exists())

    def test_missing_lock_not_created(self):
        (self.source/'policy.lock').unlink()
        report = self.run_case()
        self.assertEqual(report['check_verdict'],'UNKNOWN')
        self.assertFalse((self.source/'policy.lock').exists())

    def test_strict_json_real_child_negatives(self):
        for index, body in enumerate((b'{"x":1,"x":2}',b'[]',b'{"x":NaN}',b'{"x":1e999}',b'\xff')):
            with self.subTest(body=body):
                (self.source/'sample.json').write_bytes(body)
                self.output = self.base / f'out-{index}'
                report = self.run_case()
                self.assertEqual(report['checks'][0]['verdict'],'PASS')
                self.assertEqual(report['checks'][1]['verdict'],'FAIL')

    def test_source_changed_between_children(self):
        from agent_evidence import checks
        original = checks.call
        count = 0
        def call(request,budget):
            nonlocal count
            value = original(request,budget); count += 1
            if count == 1:
                (self.source/'sample.json').write_bytes(b'{"changed":true}')
            return value
        with patch.object(checks,'call',call):
            report = self.run_case()
        self.assertEqual(report['checks'][0]['reason_code'],'source_drift')

    def test_receipt_changed_before_independent_read(self):
        from agent_evidence import checks
        original = checks.publish
        def publish(fd,name,raw):
            original(fd,name,raw)
            (self.output/name).write_bytes(b'{"tampered":true}')
        with patch.object(checks,'publish',publish):
            report = self.run_case()
        self.assertTrue(all(r['reason_code']=='receipt_drift' for r in report['checks']))

    def test_policy_drift_final_invalidates_all_rows(self):
        from agent_evidence import runner
        original = runner.observe_check
        def observe(*args):
            value = original(*args)
            self.change_policy(epoch=2)
            return value
        with patch.object(runner,'observe_check',observe):
            report = self.run_case()
        self.assertEqual(report['check_verdict'],'UNKNOWN')
        self.assertIsNone(report['policy_consistency']['control_sha256'])
        self.assertTrue(report['policy_consistency']['final_observation_started'])

    def test_secret_body_not_emitted(self):
        marker = 'PRIVATE_BODY_DO_NOT_EMIT'
        (self.source/'sample.json').write_text(json.dumps({'secret':marker}))
        report = self.run_case()
        self.assertNotIn(marker,json.dumps(report))
        for path in self.output.iterdir():
            self.assertNotIn(marker,path.read_text())
            self.assertNotIn(str(self.base),path.read_text())

    def test_shared_target_denied_by_other_consumer(self):
        path = self.source/'manifest.json'; value=json.loads(path.read_text())
        value['checks'][1]['domains']=['unknown']
        path.write_text(json.dumps(value))
        with patch('agent_evidence.runner.observe_check',side_effect=AssertionError('worker forbidden')):
            report = self.run_case()
        self.assertTrue(all(r['reason_code']=='policy_unknown_domain' for r in report['checks']))

    def test_duplicate_output_preserves_winner(self):
        self.run_case(); before=(self.output/'report.json').read_bytes()
        with self.assertRaises(FileExistsError):
            self.run_case()
        self.assertEqual((self.output/'report.json').read_bytes(),before)
