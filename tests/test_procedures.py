"""Synthetic supplied evidence, never business execution or authority issuance."""
import copy
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import patch
from agent_evidence import procedures
from agent_evidence.fixtures import procedure_bundle, fixture
from agent_evidence.serialization import encode
from agent_evidence.receipts import raw_digest
from agent_evidence import inventory, runner
from agent_evidence.contracts import Budget, manifest
from agent_evidence._io import directory


class Procedures(unittest.TestCase):
    def setUp(self):
        self.bundle = procedure_bundle()

    def evaluate(self, bundle=None):
        return procedures.evaluate_bundle(bundle or self.bundle)

    def row(self, bundle=None):
        return self.evaluate(bundle)['rows'][0]

    def repin(self):
        self.bundle['receipts'][0]['declaration_sha256'] = raw_digest(encode(self.bundle['declarations']['procedures'][0]))

    def record(self, ref, **changes):
        pointer = self.bundle['receipts'][0][ref]
        value = json.loads(self.bundle['admitted_evidence'][pointer['id']]); value.update(changes)
        raw = encode(value)
        self.bundle['admitted_evidence'][pointer['id']] = raw.decode()
        pointer['sha256'] = raw_digest(raw)

    def test_positive_pure_no_io_or_execution(self):
        with patch('builtins.open',side_effect=AssertionError('no IO')), patch('os.open',side_effect=AssertionError('no IO')), patch('subprocess.Popen',side_effect=AssertionError('no execution')):
            report = self.evaluate()
        self.assertEqual(report['verdict'],'PASS')
        self.assertEqual(report['rows'][0]['successful_receipt_count'],1)
        self.assertFalse(report['live_admission']); self.assertFalse(report['complete'])
        self.assertEqual(report['mode'],'supplied_evidence_only')
        self.assertEqual(report['scope'],'validation_of_supplied_evidence')

    def test_receipt_negative_matrix(self):
        for key,value,want in [('result','FAIL','FAIL'),('execution_mode','mock','FAIL'),
                ('system_id','other','FAIL'),('declaration_sha256','0'*64,'FAIL'),
                ('side_effects_observed',['network-send'],'FAIL'),
                ('completed_at','2000-01-01T00:00:00+00:00','UNKNOWN'),
                ('completed_at','2099-01-01T00:00:00+00:00','UNKNOWN'),
                ('completed_at','bad','UNKNOWN')]:
            with self.subTest(key=key,value=value):
                bundle=copy.deepcopy(self.bundle); bundle['receipts'][0][key]=value
                self.assertEqual(self.row(bundle)['verdict'],want)

    def test_exact_grant_negative_matrix(self):
        original=copy.deepcopy(self.bundle)
        for key,value,want in [('issuer','forged','FAIL'),('grant_id','other','FAIL'),
                ('receipt_id','other','FAIL'),('procedure_id','other','FAIL'),('system_id','other','FAIL'),
                ('action','other','FAIL'),('scope','other','FAIL'),('status','revoked','FAIL'),
                ('valid_from','2099-01-01T00:00:00+00:00','UNKNOWN'),
                ('expires_at','2000-01-01T00:00:00+00:00','UNKNOWN')]:
            with self.subTest(key=key):
                self.bundle=copy.deepcopy(original); self.record('grant',**{key:value})
                self.assertEqual(self.row()['verdict'],want)
        self.bundle=copy.deepcopy(original); self.bundle['receipts'][0]['grant']['sha256']='0'*64
        self.assertEqual(self.row()['verdict'],'FAIL')

    def test_atoms_negatives_cleanup_readback(self):
        original=copy.deepcopy(self.bundle)
        for field in ('acceptance','negative','cleanup'):
            with self.subTest(field=field):
                self.bundle=copy.deepcopy(original)
                if field=='cleanup': self.record(field,status='FAIL')
                else:
                    pointer=self.bundle['receipts'][0][field]['observed' if field=='acceptance' else 'no-extra-effect']
                    record=json.loads(self.bundle['admitted_evidence'][pointer['id']]); record['status']='FAIL'
                    raw=encode(record); self.bundle['admitted_evidence'][pointer['id']]=raw.decode(); pointer['sha256']=raw_digest(raw)
                self.assertEqual(self.row()['verdict'],'FAIL')
        self.bundle=copy.deepcopy(original); self.bundle['receipts'][0]['acceptance']={}
        self.assertEqual(self.row()['verdict'],'UNKNOWN')
        self.bundle=copy.deepcopy(original); self.bundle['admitted_evidence']={}
        self.assertEqual(self.row()['verdict'],'UNKNOWN')

    def test_threshold_distinct_ids_and_duplicate_conflict(self):
        declaration=self.bundle['declarations']['procedures'][0]
        declaration['validation']['min_successes']=2; self.repin()
        self.bundle['receipts']*=2
        self.assertEqual(self.row()['successful_receipt_count'],1)
        self.assertEqual(self.row()['verdict'],'UNKNOWN')
        self.bundle['receipts'][1]=copy.deepcopy(self.bundle['receipts'][0])
        self.bundle['receipts'][1]['result']='FAIL'
        self.assertEqual(self.row()['verdict'],'UNKNOWN')

    def test_latest_failure_stale_and_ambiguous_defeat_history(self):
        old=copy.deepcopy(self.bundle['receipts'][0]); old['receipt_id']='older'
        old['completed_at']=old['started_at']
        for change in ({'result':'FAIL'},{'completed_at':'bad'},{'completed_at':'2099-01-01T00:00:00+00:00'}):
            bundle=copy.deepcopy(self.bundle); bundle['receipts'].insert(0,old)
            bundle['receipts'][-1].update(change)
            self.assertNotEqual(self.row(bundle)['verdict'],'PASS')
        with patch.object(procedures.time,'time',return_value=time.time()+8000):
            self.assertEqual(self.row()['verdict'],'UNKNOWN')

    def test_declaration_types_states_full_digest_empty_required(self):
        for key,value in [('required','false'),('exempt',True),('validation',{})]:
            bundle=copy.deepcopy(self.bundle); bundle['declarations']['procedures'][0][key]=value
            row=self.row(bundle); self.assertEqual(row['verdict'],'UNKNOWN'); self.assertTrue(row['required'])
        for state in ('missing','scaffolded','disabled','unknown'):
            bundle=copy.deepcopy(self.bundle); bundle['declarations']['procedures'][0]['validation']['implementation_state']=state
            self.assertNotEqual(self.row(bundle)['verdict'],'PASS')
        bundle=copy.deepcopy(self.bundle); bundle['declarations']['procedures'][0]['domains']=['changed']
        self.assertEqual(self.row(bundle)['verdict'],'FAIL')
        bundle=copy.deepcopy(self.bundle); bundle['declarations']['procedures']=[]
        self.assertEqual(self.evaluate(bundle)['verdict'],'UNKNOWN')
        self.assertEqual(self.evaluate(bundle)['required_count'],0)

    def test_unknown_receipts_duplicate_declarations_and_rows_retained(self):
        self.bundle['receipts'].append({'procedure_id':'unmapped'})
        self.assertEqual(self.evaluate()['verdict'],'UNKNOWN')
        self.bundle['declarations']['procedures']*=2
        report=self.evaluate(); self.assertEqual(len(report['rows']),2)
        self.assertEqual(report['required_count'],2)
        self.assertTrue(all(r['verdict']=='UNKNOWN' for r in report['rows']))

    def test_refs_are_not_paths_and_raw_hash_is_exact(self):
        self.bundle['receipts'][0]['grant']['id']='file:///private/poison'
        self.assertEqual(self.row()['verdict'],'UNKNOWN')
        self.bundle=procedure_bundle()
        pointer=self.bundle['receipts'][0]['grant']
        self.bundle['admitted_evidence'][pointer['id']]+='\n'
        self.assertEqual(self.row()['verdict'],'FAIL')

    def add_independent_id(self):
        receipt=copy.deepcopy(self.bundle['receipts'][0]); receipt['receipt_id']='second-receipt'
        pointers=[receipt['grant'],receipt['cleanup'],*receipt['acceptance'].values(),*receipt['negative'].values()]
        for pointer in pointers:
            value=json.loads(self.bundle['admitted_evidence'][pointer['id']])
            value['receipt_id']=receipt['receipt_id']; pointer['id']+='-second'
            if 'grant_id' in value: value['grant_id']=pointer['id']
            raw=encode(value); pointer['sha256']=raw_digest(raw)
            self.bundle['admitted_evidence'][pointer['id']]=raw.decode()
        self.bundle['receipts'].append(receipt)
        return receipt

    def test_two_distinct_successes_and_real_historical_pass_defeat(self):
        self.bundle['declarations']['procedures'][0]['validation']['min_successes']=2; self.repin()
        latest=self.add_independent_id()
        self.assertEqual(self.row()['successful_receipt_count'],2)
        self.assertEqual(self.row()['verdict'],'PASS')
        # Two equally recent records: explicit failure wins, never input-order wins.
        latest['result']='FAIL'
        self.assertEqual(self.row()['verdict'],'FAIL')
        latest['result']='PASS'; latest['completed_at']='2099-01-01T00:00:00+00:00'
        self.assertEqual(self.row()['verdict'],'UNKNOWN')
        latest['completed_at']='bad'
        self.assertEqual(self.row()['verdict'],'UNKNOWN')

    def test_record_binding_and_malformed_fields_fail_closed(self):
        original=copy.deepcopy(self.bundle)
        for field,value in [('receipt_id','other'),('procedure_id','other'),('system_id','other'),('kind','acceptance'),('name','other')]:
            with self.subTest(field=field):
                self.bundle=copy.deepcopy(original); self.record('cleanup',**{field:value})
                self.assertEqual(self.row()['verdict'],'FAIL')
        self.bundle=copy.deepcopy(original)
        for field in ('grant','cleanup','acceptance','negative','side_effects_observed'):
            bundle=copy.deepcopy(self.bundle); bundle['receipts'][0].pop(field)
            self.assertEqual(self.row(bundle)['verdict'],'UNKNOWN')
        for field in ('freshness_seconds','min_successes'):
            bundle=copy.deepcopy(self.bundle); bundle['declarations']['procedures'][0]['validation'][field]=True
            self.assertEqual(self.row(bundle)['verdict'],'UNKNOWN')

    def test_runner_cannot_drop_requested_rows(self):
        for case in ('missing-bundle','empty-bundle','changed-required','invalid-inventory-declaration','expired-approval'):
            with self.subTest(case=case), tempfile.TemporaryDirectory() as temp:
                base=Path(temp).resolve(); source=base/'input'; fixture(str(source),procedures=True)
                path=source/'procedures.json'; bundle=json.loads(path.read_text())
                if case=='missing-bundle': path.unlink()
                elif case=='invalid-inventory-declaration':
                    decl=json.loads((source/'declarations.json').read_text()); decl['procedures'][0]['required']='false'
                    (source/'declarations.json').write_bytes(encode(decl)); path.unlink()
                elif case=='expired-approval':
                    value=json.loads((source/'scope.json').read_text()); value['expires_at']='2000-01-01T00:00:00+00:00'
                    (source/'scope.json').write_bytes(encode(value))
                else:
                    if case=='empty-bundle': bundle['declarations']['procedures']=[]
                    if case=='changed-required': bundle['declarations']['procedures'][0]['required']=False
                    path.write_bytes(encode(bundle))
                result=runner.run_checks(str(source),'manifest.json',str(base/'output'))
                report=result['procedures']
                self.assertGreaterEqual(report['required_count'],1)
                self.assertGreaterEqual(report['required_gap_count'],1)
                self.assertNotEqual(report['verdict'],'PASS'); self.assertEqual(len(result['checks']),2)

    def test_runner_cli_and_stored_replay(self):
        with tempfile.TemporaryDirectory() as temp:
            base=Path(temp).resolve(); source=base/'input'
            fixture(str(source),procedures=True)
            report=runner.run_checks(str(source),'manifest.json',str(base/'output'))
            self.assertEqual(report['procedures']['verdict'],'PASS')
            self.assertTrue(report['procedures']['inventory_valid'])
            # The complete generic path is now implemented; supplied replay and
            # all negative cases below still must remain incomplete.
            self.assertTrue(report['complete'])
            self.assertFalse(report['certified_healthy'])
            self.assertEqual(report['check_verdict'],'PASS')
            for root,bundle in ((source,'procedures.json'),(base/'output','report.json')):
                result=subprocess.run([sys.executable,'-I','-B','-m','agent_evidence','evaluate','--input-root',str(root),'--bundle',bundle],capture_output=True,timeout=10)
                self.assertEqual(result.returncode,1,result.stderr)
                replay=json.loads(result.stdout); self.assertFalse(replay['live_admission'])
                self.assertFalse(replay['inventory_valid']); self.assertEqual(replay['mode'],'supplied_evidence_only')

    def test_consumption_expiry_clock_rollback_and_disabled_denominator(self):
        with tempfile.TemporaryDirectory() as temp:
            base=Path(temp).resolve(); source=base/'input'; fixture(str(source),procedures=True)
            spec=manifest(json.loads((source/'manifest.json').read_text()))
            bundle=json.loads((source/'procedures.json').read_text())
            with directory(str(source)) as fd:
                batch=inventory.acquire_inventory(fd,spec,Budget.start(),'synthetic')
                from agent_evidence.receipts import outcome
                inventory.record_observation(batch,'sample',outcome('observed',batch.admission['source_pins']['sample']))
                frozen=inventory.freeze_inventory(fd,batch)
            self.assertEqual(procedures.evaluate_bundle(bundle,frozen)['verdict'],'PASS')
            with patch.object(inventory,'read',side_effect=AssertionError('no reopen')):
                for current in (frozen.data['admission']['expires']+1,frozen.data['frozen_at']-1):
                    with patch.object(inventory.time,'time',return_value=current):
                        self.assertEqual(procedures.evaluate_bundle(bundle,frozen)['verdict'],'UNKNOWN')
            policy=json.loads((source/'policy.json').read_text()); policy['domains']['demo']['enabled']=False
            (source/'policy.json').write_bytes(encode(policy))
            report=runner.run_checks(str(source),'manifest.json',str(base/'disabled'))
            self.assertEqual(report['procedures']['rows'][0]['verdict'],'NOT_APPLICABLE')
            self.assertEqual(report['procedures']['required_count'],1)
            self.assertEqual(report['procedures']['required_gap_count'],1)
            self.assertFalse(report['complete'])
