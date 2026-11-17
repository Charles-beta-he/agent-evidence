import copy
import json
import os
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import patch
from agent_evidence import inventory, runner
from agent_evidence.inventory import validate_controls, acquire_inventory, freeze_inventory, plain
from agent_evidence.projections import project_inventory, evaluate_supplied, VIEWS
from agent_evidence.fixtures import fixture
from agent_evidence.contracts import Budget, manifest
from agent_evidence.serialization import encode, EvidenceError
from agent_evidence.receipts import raw_digest
from agent_evidence._io import directory


class InventoryContract(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory(); self.addCleanup(temp.cleanup)
        self.base = Path(temp.name).resolve(); self.source = self.base/'input'
        fixture(str(self.source), inventory=True)
        self.spec = manifest(json.loads((self.source/'manifest.json').read_text()))
        self.raws = {k:(self.source/v).read_bytes() for k,v in self.spec['inventory'].items()}

    def run_case(self, name='output'):
        return runner.run_checks(str(self.source), 'manifest.json', str(self.base/name))

    def write_control(self, name, value):
        (self.source/self.spec['inventory'][name]).write_bytes(encode(value))

    def policy(self, enabled=True, epoch=1):
        (self.source/'policy.json').write_bytes(encode({'schema':'agent_evidence_policy_v1',
            'domains':{'demo':{'enabled':enabled,'epoch':epoch}}}))

    def test_supplied_cannot_become_live(self):
        result = evaluate_supplied({'valid':True,'control_snapshot':{'policy':{}}})
        self.assertEqual(result['mode'], 'supplied_evidence_only')
        self.assertFalse(result['live_admission'])
        with self.assertRaises(ValueError):
            project_inventory({'valid':True})
        with directory(str(self.source)) as fd:
            with self.assertRaises(ValueError):
                freeze_inventory(fd, validate_controls(self.raws, self.spec))

    def test_real_workers_inventory_and_six_views(self):
        report = self.run_case()
        self.assertTrue(report['inventory']['valid'])
        self.assertEqual(report['check_verdict'], 'PASS')
        self.assertEqual(report['inventory']['observations']['sample']['observed_sha256'], raw_digest((self.source/'sample.json').read_bytes()))
        self.assertEqual(len(list((self.base/'output').glob('check-*.json'))), 3)
        self.assertEqual(set(report['views']), set(VIEWS))
        for view in report['views'].values():
            self.assertEqual(view, report['views']['profile'])
            self.assertEqual(view['required_count'], 1)
            self.assertTrue(view['inventory_valid'])
            self.assertFalse(view['rows'][0]['execution_eligible'])
        self.assertFalse(report['complete'])
        self.assertEqual(json.loads((self.base/'output/report.json').read_text()),report)

    def test_three_way_binding_negative_matrix(self):
        cases = [('scope','reviewed_at','2000-01-01T00:00:00+00:00'),
                 ('attestation','owner_id','other'), ('catalog','basis_id','other'),
                 ('catalog','approved_scope_sha256','0'*64),
                 ('attestation','approved_scope_sha256','1'*64),
                 ('scope','scope_complete',False), ('catalog','revoked',True),
                 ('scope','procedure_ids',[]), ('catalog','source_pins',{}),
                 ('attestation','source_pins',{'extra':'0'*64}),
                 ('scope','source_pins',{'sample':'sha1'}),
                 ('catalog','source_domains',{}), ('catalog','max_freshness_seconds',True)]
        for name,key,value in cases:
            with self.subTest(name=name,key=key):
                raw = dict(self.raws); obj = json.loads(raw[name]); obj[key] = value; raw[name] = encode(obj)
                with self.assertRaises(ValueError):
                    validate_controls(raw, self.spec)
        for change in ('same-id-change', 'required-exempt', 'duplicate'):
            raw = dict(self.raws); decl = json.loads(raw['declarations'])
            if change == 'same-id-change': decl['procedures'][0]['domains'] = ['other']
            if change == 'required-exempt': decl['procedures'][0]['exempt'] = True
            if change == 'duplicate': decl['procedures'] *= 2
            raw['declarations'] = encode(decl)
            with self.subTest(change=change), self.assertRaises(ValueError):
                validate_controls(raw, self.spec)
        # Raw-byte approval, not canonical-object equality.
        raw = dict(self.raws); raw['scope'] += b'\n'
        with self.assertRaisesRegex(ValueError,'inventory_binding'):
            validate_controls(raw, self.spec)

    def test_review_future_expiry_and_rewritten_time(self):
        admitted = validate_controls(self.raws, self.spec)
        for current in (admitted['reviewed']-1, admitted['expires'], admitted['expires']+1):
            with patch.object(inventory.time,'time',return_value=current), self.assertRaisesRegex(ValueError,'inventory_expired'):
                validate_controls(self.raws, self.spec)
        # Rewritten scope must still match both independent approvals.
        value = json.loads(self.raws['scope']); value['expires_at'] = '2099-01-01T00:00:00+00:00'
        with self.assertRaises(ValueError):
            validate_controls({**self.raws,'scope':encode(value)},self.spec)

    def test_denied_overlap_zero_target_open_and_worker(self):
        for case in ('disabled','missing','lock-missing','union','invalid-approval'):
            with self.subTest(case=case):
                self.policy()
                (self.source/'policy.lock').touch(exist_ok=True)
                self.write_control('catalog',json.loads(self.raws['catalog']))
                if case == 'disabled': self.policy(False)
                if case == 'missing': (self.source/'policy.json').unlink()
                if case == 'lock-missing': (self.source/'policy.lock').unlink()
                if case == 'union':
                    value = json.loads(self.raws['catalog']); value['source_domains']['sample'] = ['unknown']
                    self.write_control('catalog',value)
                if case == 'invalid-approval':
                    value = json.loads(self.raws['catalog']); value['approved_scope_sha256']='0'*64
                    self.write_control('catalog',value)
                target = self.source/'sample.json'; target.unlink(); os.mkfifo(target)
                opened = []; original = os.open
                def guarded(path,*args,**kwargs):
                    opened.append(str(path))
                    if str(path) == 'sample.json': raise AssertionError('target open forbidden')
                    return original(path,*args,**kwargs)
                with patch('os.open',guarded), patch.object(runner,'observe_check',side_effect=AssertionError('target worker forbidden')):
                    report = self.run_case(case)
                self.assertNotIn('sample.json',opened)
                self.assertFalse(report['inventory']['valid'])
                self.assertEqual(len(report['checks']),2)
                if case == 'disabled':
                    self.assertTrue(report['inventory']['control_snapshot'])
                    for view in report['views'].values():
                        self.assertEqual(view['rows'][0]['verdict'],'NOT_APPLICABLE')
                        self.assertEqual(view['required_gap_count'],1)
                target.unlink(); target.write_bytes(b'{"synthetic":true}')

    def test_source_pin_drift_real_workers(self):
        (self.source/'sample.json').write_bytes(b'{"changed":true}')
        report = self.run_case()
        self.assertFalse(report['inventory']['valid'])
        self.assertEqual(report['inventory']['reason_code'],'inventory_source_unverified')
        self.assertTrue(report['inventory']['control_snapshot'])

    def test_single_freeze_deep_immutable_no_reopen_and_expiry(self):
        with directory(str(self.source)) as fd:
            batch = acquire_inventory(fd,self.spec,Budget.start(),'test-run')
            frozen = freeze_inventory(fd,batch)
            with self.assertRaisesRegex(ValueError,'inventory_already_frozen'):
                freeze_inventory(fd,batch)
        with self.assertRaises(TypeError): frozen.data['control_snapshot']['policy']['domains']['demo']['epoch']=9
        with self.assertRaises(TypeError): frozen.data['admission']['controls']['scope']['source_pins']['sample']='0'*64
        with patch.object(inventory,'read',side_effect=AssertionError('no source reopen')), patch.object(inventory,'snapshot',side_effect=AssertionError('no policy reopen')):
            views=project_inventory(frozen)
            self.assertEqual(len(views),6)
            for current in (frozen.data['admission']['expires']+1, frozen.data['frozen_at']-1):
                with patch.object(inventory.time,'time',return_value=current):
                    views=project_inventory(frozen)
                    for view in views.values():
                        self.assertFalse(view['inventory_valid']); self.assertEqual(view['control_snapshot'],{})
                        self.assertEqual(view['reason_code'],'inventory_expired')
                        self.assertEqual(view['rows'][0]['verdict'],'UNKNOWN')
        self.assertFalse(evaluate_supplied(plain(frozen.data))['live_admission'])

    def test_final_second_read_failures_and_late_negative_priority(self):
        for mutation in ('missing','invalid','reenable','epoch','budget','late-success'):
            self.policy(False)
            with self.subTest(mutation=mutation), directory(str(self.source)) as fd:
                batch = acquire_inventory(fd,self.spec,Budget.start(),'test-run')
                original = inventory.snapshot; calls=[]
                def scheduled(*args):
                    try:
                        value = original(*args)
                    except (ValueError,OSError):
                        # A negative observed before parent deadline expiry must survive.
                        batch.budget.deadline = time.monotonic()-1
                        raise
                    calls.append(value)
                    if len(calls)==1:
                        if mutation=='missing': (self.source/'policy.json').unlink()
                        if mutation=='invalid': (self.source/'policy.json').write_bytes(b'bad')
                        if mutation=='reenable': self.policy(True)
                        if mutation=='epoch': self.policy(False,2)
                        if mutation=='budget': batch.budget.left=0
                    if len(calls)==2 and mutation=='late-success': batch.budget.deadline=time.monotonic()-1
                    return value
                with patch.object(inventory,'snapshot',scheduled): frozen=freeze_inventory(fd,batch)
                self.assertTrue(frozen.data['final_observation_started'])
                self.assertTrue(frozen.data['drift']); self.assertEqual(frozen.data['control_snapshot'],{})
                self.assertFalse(frozen.data['valid'])
                expected={'missing':'target_missing','invalid':'policy_invalid','reenable':'policy_drift','epoch':'policy_drift','budget':'budget_exhausted','late-success':'budget_exhausted'}[mutation]
                self.assertEqual(frozen.data['reason_code'],expected)
                self.assertTrue(all(v['rows'][0]['verdict']=='UNKNOWN' for v in project_inventory(frozen).values()))

    def test_not_started_exhaustion_and_partial_payload_not_live(self):
        self.policy(False)
        with directory(str(self.source)) as fd:
            budget=Budget.start(); batch=acquire_inventory(fd,self.spec,budget,'test-run')
            budget.left=0
            with patch.object(inventory,'snapshot',side_effect=AssertionError('no final reads')):
                frozen=freeze_inventory(fd,batch)
        self.assertFalse(frozen.data['final_observation_started'])
        self.assertFalse(frozen.data['drift']); self.assertEqual(frozen.data['control_snapshot'],{})
        # This generic lane does not implement the optional Hermes disabled fallback.
        self.assertTrue(all(v['rows'][0]['verdict']=='UNKNOWN' for v in project_inventory(frozen).values()))
        with self.assertRaises(ValueError): project_inventory({'control_snapshot':{'policy':{'enabled':False}}})

    def test_lock_identity_and_content_control_drift(self):
        for mutation in ('lock','scope','catalog'):
            with self.subTest(mutation=mutation), directory(str(self.source)) as fd:
                batch=acquire_inventory(fd,self.spec,Budget.start(),'test-run')
                if mutation=='lock':
                    (self.source/'new.lock').write_bytes(b''); os.replace(self.source/'new.lock',self.source/'policy.lock')
                else:
                    path=self.source/self.spec['inventory'][mutation]; path.write_bytes(path.read_bytes()+b'\n')
                frozen=freeze_inventory(fd,batch)
                self.assertEqual(frozen.data['control_snapshot'],{})
                self.assertFalse(frozen.data['valid'])
                self.assertIn(frozen.data['reason_code'],('lock_drift','inventory_binding','inventory_drift'))
                if mutation!='lock': (self.source/self.spec['inventory'][mutation]).write_bytes(self.raws[mutation])

    def test_shared_budget_and_exhausted_report_keeps_rows(self):
        original=runner.observe_check; ledgers=[]
        def scheduled(request, output, budget):
            ledgers.append((id(budget),budget.deadline,budget.left))
            result=original(request,output,budget)
            if len(ledgers)==1: budget.left=0
            return result
        with patch.object(runner,'observe_check',scheduled): report=self.run_case()
        self.assertEqual(len(report['checks']),2)
        self.assertEqual(report['check_verdict'],'UNKNOWN')
        self.assertFalse(report['inventory']['final_observation_started'])
        self.assertEqual(report['bytes_read'],8*1024*1024)
        self.assertEqual(json.loads((self.base/'output/report.json').read_text()),report)
        self.assertEqual(len(ledgers),1)

    def test_same_budget_deadline_every_real_worker(self):
        from agent_evidence import checks
        original=checks.call; seen=[]
        def traced(request,budget):
            seen.append((id(budget),request['deadline'],budget.left))
            return original(request,budget)
        with patch.object(checks,'call',traced): report=self.run_case()
        self.assertTrue(report['inventory']['valid']); self.assertEqual(len(seen),6)
        self.assertEqual(len({(x[0],x[1]) for x in seen}),1)
        self.assertTrue(all(a[2]>b[2] for a,b in zip(seen,seen[1:])))

    def test_inventory_lock_contention_and_recovery(self):
        import fcntl
        with (self.source/'policy.lock').open('rb') as lock:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            start=time.monotonic()
            with patch.object(runner,'observe_check',side_effect=AssertionError('no target worker')):
                report=self.run_case('locked')
            self.assertLess(time.monotonic()-start,2)
            self.assertFalse(report['inventory']['valid'])
            self.assertEqual(report['inventory']['control_snapshot'],{})
        self.assertTrue(self.run_case('recovered')['inventory']['valid'])

    def test_concurrent_freeze_single_winner(self):
        from concurrent.futures import ThreadPoolExecutor
        import threading
        barrier=threading.Barrier(2)
        with directory(str(self.source)) as fd:
            batch=acquire_inventory(fd,self.spec,Budget.start(),'test-run')
            def freeze():
                barrier.wait()
                try: return freeze_inventory(fd,batch)
                except EvidenceError as error: return str(error)
            with ThreadPoolExecutor(max_workers=2) as pool:
                results=list(pool.map(lambda _:freeze(),range(2)))
        self.assertEqual(sum(isinstance(r,inventory.FrozenInventory) for r in results),1)
        self.assertIn('inventory_already_frozen',results)

    def test_concurrent_runs_publication_ownership(self):
        import subprocess
        import sys
        def launch(name):
            return subprocess.Popen([sys.executable,'-I','-B','-m','agent_evidence','run',
                '--input-root',str(self.source),'--manifest','manifest.json','--output-root',str(self.base/name)],
                stdout=subprocess.PIPE,stderr=subprocess.PIPE)
        for names, expected in ((('shared','shared'),[1,2]),(('one','two'),[1,1])):
            children=[launch(name) for name in names]; codes=[]
            try:
                for child in children:
                    out,err=child.communicate(timeout=15); codes.append(child.returncode)
                    if child.returncode==1:
                        self.assertTrue(json.loads(out)['inventory']['valid'])
            finally:
                for child in children:
                    if child.poll() is None: child.kill(); child.communicate()
            self.assertEqual(sorted(codes),expected)
            for name in set(names):
                self.assertTrue(json.loads((self.base/name/'report.json').read_text())['inventory']['valid'])
                self.assertFalse(list((self.base/name).glob('pending-*')))

    def test_worker_rechecks_policy_before_fifo_content(self):
        from agent_evidence import checks
        original=checks.call; count=0
        def transition(request,budget):
            nonlocal count
            count+=1
            if count==1:
                import fcntl
                with (self.source/'policy.lock').open('rb') as lock:
                    fcntl.flock(lock,fcntl.LOCK_EX)
                    self.policy(False,2)
                    target=self.source/'sample.json'; target.unlink(); os.mkfifo(target)
            return original(request,budget)
        with patch.object(checks,'call',transition): report=self.run_case()
        self.assertEqual(report['inventory']['observations']['sample']['reason_code'],'policy_drift')
        self.assertEqual(report['inventory']['control_snapshot'],{})
        self.assertEqual(report['check_verdict'],'UNKNOWN')

    def test_final_invalid_control_is_unknown_not_business_json_fail(self):
        original=runner.observe_check
        def mutate(request, output, budget):
            result=original(request,output,budget)
            (self.source/'policy.json').write_bytes(b'bad')
            return result
        with patch.object(runner,'observe_check',mutate): report=self.run_case()
        self.assertEqual(report['check_verdict'],'UNKNOWN')
        self.assertEqual(report['inventory']['control_snapshot'],{})
