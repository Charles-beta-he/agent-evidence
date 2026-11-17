import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from agent_evidence_integration import cli


class JsonAcceptance(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.base = Path(tmp.name).resolve()
        self.project = self.base / 'project'
        self.project.mkdir()
        self.target = self.project / 'config.json'
        self.index = 0

    def run_check(self, body, expected='2', field='version'):
        if body is not None:
            self.target.write_text(body)
        self.index += 1
        out = self.base / f'out{self.index}'
        result = cli.check(str(self.project), str(out),
                           expectations=[['config.json', field, expected]])
        self.assertEqual(json.loads((out / 'integration.json').read_text()), result)
        self.assertFalse(result['complete'])
        self.assertFalse(result['certified_healthy'])
        self.assertEqual(result['task_verdict'], 'UNKNOWN')
        return result

    def test_correct_and_wrong(self):
        for value, verdict in [(2, 'PASS'), (1, 'FAIL')]:
            result = self.run_check(json.dumps({'version': value}))
            self.assertEqual(result['observation_verdict'], 'PASS')
            self.assertEqual(result['acceptance_verdict'], verdict)
            row = result['acceptance'][0]
            self.assertEqual(row['observed_sha256'], result['checks'][0]['observed_sha256'])
            self.assertEqual(row['expected'], 2)
            self.assertEqual(len(row['assertion_sha256']), 64)

    def test_unavailable_is_unknown(self):
        for body in [None, '{}', '{"version":{}}', 'not json']:
            with self.subTest(body=body):
                self.assertEqual(self.run_check(body, field='version.child')['acceptance_verdict'], 'UNKNOWN')

    def test_typed_scalars(self):
        for body, expected, verdict in [('{"version":true}', '1', 'FAIL'),
                ('{"version":1}', 'true', 'FAIL'), ('{"version":2.0}', '2', 'FAIL'),
                ('{"version":"2"}', '2', 'FAIL'), ('{"version":null}', 'null', 'PASS'),
                ('{"version":false}', 'false', 'PASS'), ('{"version":2.0}', '2.0', 'PASS'),
                ('{"version":"two"}', '"two"', 'PASS')]:
            with self.subTest(body=body):
                self.assertEqual(self.run_check(body, expected)['acceptance_verdict'], verdict)

    def test_nested_object(self):
        self.assertEqual(self.run_check('{"config":{"version":2}}', field='config.version')['acceptance_verdict'], 'PASS')

    def test_no_expectation(self):
        self.target.write_text('{"version":2}')
        result = cli.check(str(self.project), str(self.base / 'out'), json_files=['config.json'])
        self.assertEqual(result['acceptance_verdict'], 'UNKNOWN')
        self.assertEqual(result['acceptance'], [])

    def test_cross_read_drift(self):
        original = cli.run_checks
        for initial, changed in [(1, 2), (2, 1)]:
            def drift(*args):
                report = original(*args)
                self.target.write_text(json.dumps({'version': changed}))
                return report
            with patch.object(cli, 'run_checks', side_effect=drift):
                result = self.run_check(json.dumps({'version': initial}))
            self.assertEqual(result['acceptance_verdict'], 'UNKNOWN')
            self.assertEqual(result['acceptance'][0]['reason_code'], 'source_drift')

    def test_unreadable_link(self):
        self.target.symlink_to(self.base / 'absent')
        self.assertEqual(self.run_check(None)['acceptance_verdict'], 'UNKNOWN')

    def test_final_control_failure(self):
        original = cli.run_checks
        def invalid(*args):
            report = original(*args)
            report['policy_consistency']['reason_code'] = 'policy_drift'
            return report
        with patch.object(cli, 'run_checks', side_effect=invalid):
            self.assertEqual(self.run_check('{"version":2}')['acceptance_verdict'], 'UNKNOWN')

    def test_rejected_before_writes(self):
        cases = [[['config.json', f, '2']] for f in ['', '../version', 'a[0]', 'a..b', 'a.' * 16 + 'b', 'x' * 65]]
        cases += [[['config.json', 'version', e]] for e in ['', 'NaN', 'Infinity', '{}', '[]', '"' + 'x' * 4096 + '"']]
        cases += [[['../outside', 'version', '2']], [['x', 'v']], [['x', 'v', '2']] * 33,
                  [['x', 'v', '2'], ['x', 'w', '3']]]
        for value in cases:
            with self.subTest(value=str(value)[:80]), self.assertRaises((ValueError, TypeError)):
                cli.check(str(self.project), str(self.base / 'out'), expectations=value)
        self.assertEqual(list(self.project.iterdir()), [])
        self.assertFalse((self.base / 'out').exists())

    def test_cli_expected_and_omitted(self):
        self.target.write_text('{"version":2}')
        args = ['check', '--project', str(self.project), '--output', str(self.base / 'out'), '--expect-json', 'config.json', 'version']
        with self.assertRaises(SystemExit) as raised:
            cli.main(args)
        self.assertEqual(raised.exception.code, 2)
        self.assertFalse((self.base / 'out').exists())
        self.assertEqual(cli.main(args + ['2']), 1)
        self.assertEqual(json.loads((self.base / 'out/integration.json').read_text())['acceptance_verdict'], 'PASS')
