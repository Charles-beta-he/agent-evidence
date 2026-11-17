import copy
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

from agent_evidence.adapters.hermes import PAIRS, BLOCKED, evaluate_inputs, evaluate_pair, route
from agent_evidence.fixtures import fixture
from agent_evidence.runner import run_checks


def job(**updates):
    current = time.time()
    value = dict(id='synthetic-job', enabled=True, state='scheduled',
                 schedule={'kind':'interval','minutes':10}, last_status='ok',
                 last_run_at=current-10, next_run_at=current+600,
                 execution_error=False, delivery_error=False, deliver='local',
                 script='experience_ratchet_watchdog.py', no_agent=True)
    value.update(updates)
    return value


def jobs(*rows):
    return {'schema':'agent_evidence_hermes_jobs_v1','jobs':list(rows)}


class HermesSemantics(unittest.TestCase):
    def health(self, *rows):
        return evaluate_pair('cron','cron_error_cluster_watch',jobs(*rows))

    def test_catalog_and_empty_zero_io(self):
        self.assertEqual(len(PAIRS),21)
        with patch('builtins.open',side_effect=AssertionError), patch('os.open',side_effect=AssertionError), patch('subprocess.Popen',side_effect=AssertionError):
            rows = evaluate_inputs({})
        self.assertEqual(len(rows),21)
        self.assertTrue(all(r['required'] and r['verdict']=='UNKNOWN' for r in rows))
        class Poison(dict):
            def get(self,*args): raise AssertionError('forbidden input access')
        for sid,cid in PAIRS:
            if cid in BLOCKED:
                self.assertEqual(evaluate_pair(sid,cid,Poison())['reason_code'],BLOCKED[cid])

    def test_active_history_and_state_table(self):
        self.assertEqual(self.health(job())['verdict'],'PASS')
        for state in ('paused','completed'):
            result=self.health(job(),job(id='old',state=state,last_status='error'))
            self.assertEqual(result['verdict'],'PASS')
            self.assertEqual(result['metadata']['historical_observed_failures'],1)
        self.assertEqual(self.health(job(),job(id='old',enabled=False,last_status='error'))['verdict'],'PASS')
        for state in (None,'','  '):
            self.assertEqual(self.health(job(state=state))['verdict'],'PASS')
        for state in (False,{},'rogue'):
            self.assertEqual(self.health(job(state=state))['verdict'],'UNKNOWN')
        self.assertEqual(self.health(job(enabled=False))['verdict'],'UNKNOWN')
        self.assertEqual(self.health(job(enabled=1))['verdict'],'UNKNOWN')

    def test_fail_priority_and_timing_table(self):
        current=time.time()
        for updates in ({'state':'error'},{'last_status':'error'},{'execution_error':True},{'delivery_error':True}):
            self.assertEqual(self.health(job(**updates),job(id='ambiguous',deliver='nonsense'))['verdict'],'FAIL')
        for updates in ({'last_run_at':None},{'last_run_at':current+3600},{'last_run_at':current-90000},
                        {'next_run_at':None},{'next_run_at':current-1},{'last_status':'unknown'}):
            self.assertEqual(self.health(job(**updates))['verdict'],'UNKNOWN')
        self.assertEqual(self.health(job(last_status='error',last_run_at=current-90000))['verdict'],'UNKNOWN')
        self.assertEqual(self.health(job(state='error',last_run_at=None))['verdict'],'FAIL')

    def test_route_table(self):
        for value in (None,'',[],[''],'local'):
            self.assertEqual(route(value),{'platforms':['local'],'malformed':False,'unresolved':False})
        for value in ('local,telegram',['local','telegram'],['local,telegram']):
            self.assertEqual(route(value)['platforms'],['local','telegram'])
        for value in ('origin','all','ALL'):
            self.assertTrue(route(value)['unresolved'])
        for value in ('  ',',','invalid',False,{},['local',3],'telegram:'):
            self.assertTrue(route(value)['malformed'])
        # Destination-bearing values are excluded by the sanitized v1 contract.
        self.assertTrue(route('telegram:synthetic-address')['malformed'])

    def test_registration_exact_and_fail_priority(self):
        sid,cid='experience-ratchet','experience_ratchet_watchdog_cron'
        def check(*rows): return evaluate_pair(sid,cid,jobs(*rows))['verdict']
        self.assertEqual(check(job()),'PASS')
        self.assertEqual(check(job(script='prefix-experience_ratchet_watchdog.py')),'UNKNOWN')
        for updates in ({'no_agent':False},{'enabled':False},{'deliver':'telegram,origin'},{'deliver':['telegram',3]},{'deliver':'telegram:synthetic-address'}):
            self.assertEqual(check(job(**updates),job(id='unknown',deliver='origin')),'FAIL')
        for updates in ({'state':'paused'},{'state':'error'},{'deliver':'origin'},{'deliver':'garbage'}):
            self.assertEqual(check(job(**updates)),'UNKNOWN')

    def test_structural_delivery_not_send(self):
        for sid in ('delivery:local','delivery:telegram'):
            source=jobs(job(deliver=['local','telegram']))
            result=evaluate_pair(sid,'delivery_job_config_readback',source)
            self.assertEqual(result['verdict'],'PASS')
            self.assertEqual(result['metadata']['semantics'],'configuration_not_delivery')
            self.assertEqual(evaluate_pair(sid,'delivery_failure_watch',source)['verdict'],'UNKNOWN')
            self.assertEqual(evaluate_pair(sid,'delivery_job_config_readback',jobs(job(deliver='origin')))['verdict'],'UNKNOWN')
        self.assertEqual(evaluate_pair('cron','cron_list_readback',jobs())['verdict'],'PASS')
        self.assertEqual(evaluate_pair('cron','cron_list_readback',jobs(job(),job()))['verdict'],'FAIL')

    def test_heartbeat_and_proposal_scopes(self):
        current=time.time()
        heartbeat={'schema':'agent_evidence_hermes_heartbeat_v1','heartbeat_at':current-1,'success_at':current-2}
        def hb(v): return evaluate_pair('cron','cron_ticker_heartbeat_watch',v)
        self.assertEqual(hb(heartbeat)['verdict'],'PASS')
        self.assertEqual(hb(heartbeat)['metadata']['semantics'],'timestamps_not_writer_or_job_success')
        for field in ('heartbeat_at','success_at'):
            self.assertEqual(hb({**heartbeat,field:current+100})['verdict'],'UNKNOWN')
            self.assertEqual(hb({**heartbeat,field:current-500})['verdict'],'FAIL')
        proposal={'schema':'agent_evidence_hermes_proposal_v1','observed_at':current-1,'entry_count':2,'write_blocked':True,'auto_trim_memory':False}
        def prop(v): return evaluate_pair('memory-hygiene-dream','memory_hygiene_dream_latest_proposal_readback',v)['verdict']
        self.assertEqual(prop(proposal),'UNKNOWN')
        self.assertEqual(prop({**proposal,'auto_trim_memory':True}),'FAIL')
        self.assertEqual(prop({**proposal,'write_blocked':False,'observed_at':None}),'FAIL')
        self.assertEqual(prop({**proposal,'observed_at':current-200000}),'UNKNOWN')

    def test_metadata_whitelist_no_body_echo(self):
        marker='PRIVATE_BODY_SENTINEL'
        for key in ('prompt','last_error','target','command','config','body'):
            result=self.health(job(**{key:marker}))
            self.assertEqual(result['verdict'],'UNKNOWN')
            self.assertNotIn(marker,json.dumps(result))
        status={'schema':'agent_evidence_hermes_status_v1','dirty':True,'record_count':1}
        self.assertEqual(evaluate_pair('hermes-core','dirty_worktree_awareness',status)['reason_code'],'status_producer_unbound')


class HermesInstalledPipeline(unittest.TestCase):
    def test_blocked_worker_request_rejected_before_io(self):
        from agent_evidence._worker import perform
        for sid,cid in PAIRS:
            if cid not in BLOCKED: continue
            ctx=dict(run_id='test',profile_id='synthetic',system_id=sid,check_id=cid,
                     target_id='poison',operation='hermes',candidate_revision='a'*64,
                     check_revision='b'*64,input_identity='c'*64,output_identity='d'*64,policy_sha256='e'*64)
            request=dict(phase='observe',input_root='/poison',output_root='/poison-out',context=ctx,
                policy='policy.json',lock='policy.lock',target='poison',domains=[],deadline=time.monotonic()+5,
                remaining_bytes=1024,receipt='check.json',receipt_sha256=None,lock_identity='f'*64)
            with patch('agent_evidence._worker.directory',side_effect=AssertionError), patch('os.open',side_effect=AssertionError):
                with self.assertRaises(ValueError): perform(request)

    def test_schema_unknown_binding_and_version_fail_before_worker(self):
        from agent_evidence.contracts import manifest
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp).resolve(); src=root/'in'; fixture(str(src),hermes=True)
            value=json.loads((src/'manifest.json').read_text())
            for change in ('version','blocked','checks'):
                spec=copy.deepcopy(value)
                if change=='version': spec['hermes']['schema']='future'
                if change=='blocked': spec['hermes']['inputs']['hermes_doctor']='jobs'
                if change=='checks': spec['checks']=[{}]
                with self.assertRaises(ValueError): manifest(spec)

    def test_all_supported_semantics_pure_zero_io(self):
        values={'jobs':jobs(job()),'heartbeat':{'schema':'agent_evidence_hermes_heartbeat_v1',
            'heartbeat_at':time.time()-1,'success_at':time.time()-2}}
        with patch('builtins.open',side_effect=AssertionError), patch('os.open',side_effect=AssertionError), patch('subprocess.Popen',side_effect=AssertionError):
            rows=evaluate_inputs(values)
        self.assertEqual(len(rows),21)
        self.assertTrue(any(r['verdict']=='PASS' for r in rows))

    def test_inventory_disabled_fifo_and_no_target_read(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp).resolve(); src=root/'in'; fixture(str(src),hermes=True,procedures=True)
            policy=json.loads((src/'policy.json').read_text()); policy['domains']['demo']['enabled']=False
            (src/'policy.json').write_text(json.dumps(policy))
            for name in ('jobs.json','sample.json'):
                (src/name).unlink(); os.mkfifo(src/name)
            from agent_evidence._io import read as real_read
            opened=[]
            def traced(fd,name,*args,**kw):
                opened.append(name)
                self.assertNotIn(name,('jobs.json','sample.json','heartbeat.json','proposal.json','status.json'))
                return real_read(fd,name,*args,**kw)
            with patch('agent_evidence.runner.observe_check',side_effect=AssertionError), patch('agent_evidence.runner.read',side_effect=traced), patch('agent_evidence.inventory.read',side_effect=traced), patch('agent_evidence.policy.read',side_effect=traced):
                report=run_checks(str(src),'manifest.json',str(root/'out'),hermes=True)
            self.assertEqual(report['hermes']['required_count'],21)
            self.assertFalse(report['procedures']['complete'])
            self.assertTrue(all(r['verdict']=='NOT_APPLICABLE' for r in report['hermes']['checks'] if r['check_id'] not in BLOCKED))

    def test_shared_budget_retains_all_rows(self):
        from agent_evidence.contracts import Budget
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp).resolve(); src=root/'in'; fixture(str(src),hermes=True)
            budget=Budget.start(size=20000)
            from agent_evidence.runner import observe_check as real_observe
            ledgers=[]
            def observed(request,output,ledger):
                ledgers.append((id(ledger),request['deadline'],request['remaining_bytes']))
                return real_observe(request,output,ledger)
            with patch('agent_evidence.runner.Budget.start',return_value=budget), patch('agent_evidence.runner.observe_check',side_effect=observed):
                report=run_checks(str(src),'manifest.json',str(root/'out'),hermes=True)
            self.assertEqual(report['hermes']['required_count'],21)
            self.assertTrue(ledgers)
            self.assertEqual(len({(i,d) for i,d,_ in ledgers}),1)
            self.assertEqual([b for _,_,b in ledgers],sorted((b for _,_,b in ledgers),reverse=True))
            self.assertFalse(report['complete'])
            self.assertFalse(any(r['verdict']=='PASS' for r in report['hermes']['checks']))

    def test_poison_export_body_not_emitted_real_workers(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp).resolve(); src=root/'in'; out=root/'out'; fixture(str(src),hermes=True)
            (src/'jobs.json').write_text(json.dumps(jobs(job(prompt='PRIVATE_BODY_SENTINEL'))))
            report=run_checks(str(src),'manifest.json',str(out),hermes=True)
            self.assertNotIn('PRIVATE_BODY_SENTINEL',json.dumps(report))
            for path in out.iterdir(): self.assertNotIn(b'PRIVATE_BODY_SENTINEL',path.read_bytes())
            row=next(r for r in report['hermes']['checks'] if r['check_id']=='cron_error_cluster_watch')
            self.assertEqual(row['verdict'],'UNKNOWN')

    def test_real_fixture_cli_and_readback(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp).resolve(); src=root/'in'; out=root/'out'
            fixture(str(src),hermes=True,procedures=True)
            proc=subprocess.run([sys.executable,'-I','-B','-m','agent_evidence','hermes','run','--input-root',str(src),'--manifest','manifest.json','--output-root',str(out)],capture_output=True)
            self.assertEqual(proc.returncode,1,proc.stderr)
            report=json.loads(proc.stdout)
            self.assertEqual(len(report['hermes']['checks']),21)
            self.assertEqual(report['hermes']['required_count'],21)
            self.assertEqual(report['procedures']['verdict'],'PASS')
            self.assertTrue(report['inventory']['valid'])
            self.assertFalse(report['complete'])
            self.assertEqual(json.loads((out/'report.json').read_text()),report)
            rows={(r['system_id'],r['check_id']):r for r in report['hermes']['checks']}
            self.assertEqual(rows['cron','cron_error_cluster_watch']['verdict'],'PASS')
            receipts=[json.loads(p.read_text()) for p in out.glob('check-*.json')]
            self.assertTrue(any(r['context']['operation']=='hermes' for r in receipts))
            self.assertTrue(all(r['result']['observed_sha256'] for r in receipts))

    def test_disabled_poison_never_spawns_target_worker(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp).resolve(); src=root/'in'; out=root/'out'
            fixture(str(src),hermes=True)
            policy=json.loads((src/'policy.json').read_text()); policy['domains']['demo']['enabled']=False
            (src/'policy.json').write_text(json.dumps(policy))
            (src/'jobs.json').unlink(); os.mkfifo(src/'jobs.json')
            with patch('agent_evidence.runner.observe_check',side_effect=AssertionError('target worker forbidden')):
                report=run_checks(str(src),'manifest.json',str(out),hermes=True)
            rows=report['hermes']['checks']
            self.assertEqual(len(rows),21)
            self.assertTrue(all(r['required'] for r in rows))
            self.assertTrue(any(r['verdict']=='NOT_APPLICABLE' for r in rows))
            self.assertFalse(report['complete'])

    def test_blocked_and_missing_binding_zero_target_io(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp).resolve(); src=root/'in'
            fixture(str(src),hermes=True)
            path=src/'manifest.json'; spec=json.loads(path.read_text()); spec['hermes']['inputs']={}
            path.write_text(json.dumps(spec))
            with patch('agent_evidence.runner.observe_check',side_effect=AssertionError):
                report=run_checks(str(src),'manifest.json',str(root/'out'),hermes=True)
            self.assertEqual(len(report['hermes']['checks']),21)
            self.assertTrue(all(r['verdict']=='UNKNOWN' for r in report['hermes']['checks']))

    def _final_control_case(self, fault, evidence, inventory=True):
        from agent_evidence import runner, checks, _transport
        from agent_evidence.contracts import Budget
        from agent_evidence.serialization import encode
        from agent_evidence.receipts import raw_digest
        from agent_evidence.cli import main
        import io
        from contextlib import redirect_stdout

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve(); src = root/'in'; out = root/'out'
            fixture(str(src), hermes=True, procedures=inventory)
            if evidence != 'positive':
                value = json.loads((src/'jobs.json').read_bytes())
                value['jobs'][0].update(last_status='error', execution_error=True)
                (src/'jobs.json').write_bytes(encode(value))
            ledger = Budget.start()
            captured = []; late_results = []
            real_observe, real_freeze = runner.observe_check, runner.freeze_inventory
            real_snapshot, real_call, real_decode = runner.snapshot, checks.call, _transport.decode

            def observe(*args):
                value = real_observe(*args)
                if args[0]['context']['check_id'] == 'cron_error_cluster_watch':
                    captured.append(copy.deepcopy(value))
                return value

            def call(request, budget):
                if request['phase'] == 'readback' and request['context']['check_id'] == 'cron_error_cluster_watch':
                    if evidence == 'unverified':
                        # A real observed FAIL is not trusted if independent identity validation fails.
                        path = out/request['receipt']; value = json.loads(path.read_bytes())
                        self.assertEqual(value['result']['adapter']['verdict'], 'FAIL')
                        value['context']['run_id'] = 'different'
                        raw = encode(value); path.write_bytes(raw)
                        request = {**request, 'receipt_sha256': raw_digest(raw)}
                    if evidence == 'late':
                        def late_decode(raw):
                            value = real_decode(raw)
                            late_results.append(copy.deepcopy(value['result']))
                            budget.deadline = time.monotonic() - 1
                            return value
                        # The real child returned FAIL, but transport admission is now late.
                        with patch.object(_transport, 'decode', side_effect=late_decode):
                            return real_call(request, budget)
                return real_call(request, budget)

            def corrupt():
                if fault == 'invalid':
                    (src/'policy.json').write_bytes(b'{')
                elif fault == 'drift':
                    value = json.loads((src/'policy.json').read_bytes())
                    value['domains']['demo']['epoch'] += 1
                    (src/'policy.json').write_bytes(encode(value))
                else:
                    ledger.deadline = time.monotonic() - 1

            def freeze(*args):
                corrupt()
                return real_freeze(*args)

            snapshots = []
            def snapshot(*args):
                if snapshots:
                    corrupt()
                snapshots.append(True)
                return real_snapshot(*args)

            class Output:
                buffer = io.BytesIO()
            stdout = Output(); stdout.buffer = io.BytesIO()
            with patch.object(runner.Budget, 'start', return_value=ledger), patch.object(runner, 'observe_check', side_effect=observe), patch.object(checks, 'call', side_effect=call), patch.object(runner, 'freeze_inventory', side_effect=freeze), patch.object(runner, 'snapshot', side_effect=snapshot), redirect_stdout(stdout):
                code = main(['hermes', 'run', '--input-root', str(src), '--manifest', 'manifest.json', '--output-root', str(out)])
            self.assertEqual(code, 1)
            report = json.loads(stdout.buffer.getvalue())
            self.assertEqual(report, json.loads((out/'report.json').read_bytes()))
            self.assertFalse(report['complete'])
            self.assertEqual(report['hermes']['required_count'], 21)
            self.assertEqual(len(report['hermes']['checks']), 21)
            self.assertTrue(all(r['required'] for r in report['hermes']['checks']))
            self.assertIsNone(report['policy_consistency']['control_sha256'])
            expected_control = 'budget_exhausted' if evidence == 'late' or fault == 'timeout' else 'policy_' + fault
            self.assertEqual(report['policy_consistency']['reason_code'], expected_control)
            self.assertFalse(any(r['verdict'] == 'PASS' for r in report['checks']))
            self.assertFalse(any(r['verdict'] == 'PASS' for r in report['hermes']['checks']))
            row = next(r for r in report['hermes']['checks'] if r['check_id'] == 'cron_error_cluster_watch')
            if evidence == 'negative':
                self.assertEqual(captured[0]['verdict'], 'PASS')
                self.assertEqual(captured[0]['evidence_state'], 'verified')
                self.assertEqual(captured[0]['adapter']['verdict'], 'FAIL')
                self.assertEqual(row['verdict'], 'FAIL')
                self.assertEqual(row['reason_code'], 'cron_recent_failure')
                self.assertEqual(row['metadata'], captured[0]['adapter']['metadata'])
                self.assertEqual(report['check_verdict'], 'FAIL')
            else:
                self.assertEqual(row['verdict'], 'UNKNOWN')
                self.assertEqual(row['metadata'], {})
                if evidence == 'positive':
                    self.assertFalse(any(r['verdict'] == 'FAIL' for r in report['hermes']['checks']))
                elif evidence == 'unverified':
                    self.assertEqual(captured[0]['reason_code'], 'receipt_invalid')
                    self.assertNotIn('adapter', captured[0])
                else:
                    self.assertEqual(late_results[0]['adapter']['verdict'], 'FAIL')
                    self.assertFalse(captured)

    def test_verified_failure_survives_final_control_real_workers(self):
        for inventory in (True, False):
            for fault in ('invalid', 'drift', 'timeout'):
                with self.subTest(inventory=inventory, fault=fault):
                    self._final_control_case(fault, 'negative', inventory)

    def test_final_control_cannot_create_business_failure_real_workers(self):
        for fault in ('invalid', 'drift', 'timeout'):
            with self.subTest(fault=fault):
                self._final_control_case(fault, 'positive')

    def test_unverified_or_late_failure_not_retained_real_workers(self):
        for evidence in ('unverified', 'late'):
            for fault in ('invalid', 'drift', 'timeout'):
                with self.subTest(evidence=evidence, fault=fault):
                    self._final_control_case(fault, evidence)

    def test_final_failure_not_repaired(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp).resolve(); src=root/'in'
            fixture(str(src),hermes=True)
            from agent_evidence.policy import snapshot
            calls=[]
            def changed(*args):
                calls.append(1)
                if len(calls)>1: raise FileNotFoundError()
                return snapshot(*args)
            with patch('agent_evidence.runner.snapshot',side_effect=changed):
                report=run_checks(str(src),'manifest.json',str(root/'out'),hermes=True)
            self.assertTrue(report['policy_consistency']['final_observation_started'])
            self.assertEqual(report['policy_consistency']['reason_code'],'target_missing')
            self.assertFalse(any(r['verdict']=='PASS' for r in report['hermes']['checks']))
