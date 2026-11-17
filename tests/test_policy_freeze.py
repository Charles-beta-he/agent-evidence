"""Maximum bounded denominators and control-read exhaustion, with persisted reports."""
import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from agent_evidence import runner, inventory
from agent_evidence.fixtures import fixture
from agent_evidence.serialization import encode, CONTROL_LIMIT, REPORT_LIMIT
from agent_evidence.receipts import raw_digest


class MaximumBudget(unittest.TestCase):
    def test_maximum_requested_rows_survive_exhaustion_and_persist(self):
        with tempfile.TemporaryDirectory() as temp:
            base=Path(temp).resolve(); source=base/'input'; fixture(str(source), inventory=True)
            spec=json.loads((source/'manifest.json').read_text())
            sample=spec['checks'][0]
            spec['checks']=[{**sample,'check_id':f'check-{i}'} for i in range(128)]
            spec['schema']='agent_evidence_procedure_run_v1'; spec['procedures']='procedures.json'
            (source/'manifest.json').write_bytes(encode(spec))
            declarations=json.loads((source/'declarations.json').read_text())
            item=declarations['procedures'][0]
            declarations['procedures']=[{**item,'procedure_id':f'procedure-{i:04d}', 'system_id':f'system-{i:04d}'} for i in range(1024)]
            raw=encode(declarations); (source/'declarations.json').write_bytes(raw)
            scope=json.loads((source/'scope.json').read_text())
            scope.update(declarations_sha256=raw_digest(raw),procedure_ids=sorted(r['procedure_id'] for r in declarations['procedures']))
            scope_raw=encode(scope); (source/'scope.json').write_bytes(scope_raw)
            for name in ('attestation','catalog'):
                row=json.loads((source/(name+'.json')).read_text())
                row.update(declarations_sha256=raw_digest(raw),procedure_ids=scope['procedure_ids'],approved_scope_sha256=raw_digest(scope_raw))
                (source/(name+'.json')).write_bytes(encode(row))
            (source/'procedures.json').write_bytes(encode({'schema':'agent_evidence_procedure_bundle_v1',
                'declarations':declarations,'receipts':[],'admitted_evidence':{}}))
            original=runner.acquire_inventory
            def exhaust(*args):
                batch=original(*args)
                self.assertIsNotNone(batch.admission)
                batch.budget.left=0
                return batch
            with patch.object(runner,'acquire_inventory',exhaust), patch.object(runner,'observe_check',side_effect=AssertionError('no worker after exhaustion')):
                report=runner.run_checks(str(source),'manifest.json',str(base/'output'))
            self.assertEqual(len(report['checks']),128)
            self.assertEqual(len(report['procedures']['rows']),1024)
            self.assertEqual(report['procedures']['required_gap_count'],1024)
            for view in report['views'].values():
                self.assertEqual(len(view['rows']),1024)
                self.assertEqual(view['required_gap_count'],1024)
            raw=(base/'output/report.json').read_bytes()
            self.assertGreater(len(raw),CONTROL_LIMIT); self.assertLess(len(raw),REPORT_LIMIT)
            self.assertEqual(json.loads(raw),report)
            self.assertFalse(report['complete']); self.assertFalse(report['certified_healthy'])

    def test_declaration_denominator_retained_when_later_control_fails(self):
        with tempfile.TemporaryDirectory() as temp:
            base=Path(temp).resolve(); source=base/'input'; fixture(str(source),procedures=True)
            (source/'catalog.json').unlink()
            report=runner.run_checks(str(source),'manifest.json',str(base/'output'))
            for view in report['views'].values():
                self.assertEqual(view['required_count'],1)
                self.assertEqual(view['required_gap_count'],1)
            self.assertEqual(report['procedures']['required_count'],1)
            self.assertEqual(report['procedures']['required_gap_count'],1)
            self.assertFalse(report['complete'])
