import fcntl
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import unittest
from agent_evidence._io import directory, read, publish
from agent_evidence.contracts import Budget
from agent_evidence.serialization import EvidenceError
from agent_evidence.fixtures import fixture
from agent_evidence.runner import run_checks


class Boundaries(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.base=Path(self.tmp.name).resolve()

    def test_no_follow_ancestors_leaf_fifo_hardlink(self):
        outside=self.base/'real'; outside.mkdir(); (outside/'a').write_bytes(b'body')
        (self.base/'alias').symlink_to(outside,target_is_directory=True)
        with self.assertRaises(OSError),directory(str(self.base/'alias')):
            pass
        (self.base/'leaf').symlink_to(outside/'a')
        os.mkfifo(self.base/'fifo')
        os.link(outside/'a',self.base/'hard')
        for name in ('leaf','fifo','hard','../real/a'):
            with self.subTest(name=name), directory(str(self.base)) as fd:
                with self.assertRaises((OSError,EvidenceError)):
                    read(fd,name,Budget.start())

    def test_oversize_and_budget(self):
        (self.base/'big').write_bytes(b'x'*1048577)
        with directory(str(self.base)) as fd:
            with self.assertRaises(EvidenceError):
                read(fd,'big',Budget.start())
        (self.base/'small').write_bytes(b'x'*100)
        with directory(str(self.base)) as fd:
            budget=Budget.start(size=150)
            self.assertEqual(len(read(fd,'small',budget)),100)
            with self.assertRaises(EvidenceError):
                read(fd,'small',budget)
            self.assertEqual(budget.left,50)

    def test_concurrent_exclusive_publish(self):
        script='from agent_evidence._io import directory,publish; import sys;\nwith directory(sys.argv[1]) as fd: publish(fd,"winner.json",sys.argv[2].encode())'
        children=[subprocess.Popen([sys.executable,'-I','-B','-c',script,str(self.base),str(i)],stdout=subprocess.PIPE,stderr=subprocess.PIPE) for i in range(6)]
        codes=[]
        for child in children:
            child.communicate(timeout=5); codes.append(child.returncode)
        self.assertEqual(codes.count(0),1)
        self.assertIn((self.base/'winner.json').read_text(),[str(i) for i in range(6)])
        self.assertEqual([p.name for p in self.base.iterdir()],['winner.json'])

    def test_exclusive_lock_contention_is_bounded(self):
        source=self.base/'source'; fixture(str(source))
        with (source/'policy.lock').open('rb') as stream:
            fcntl.flock(stream,fcntl.LOCK_EX | fcntl.LOCK_NB)
            start=time.monotonic()
            report=run_checks(str(source),'manifest.json',str(self.base/'out'))
            self.assertLess(time.monotonic()-start,2)
            self.assertEqual(report['check_verdict'],'UNKNOWN')
            self.assertFalse(list((self.base/'out').glob('check-*.json')))
        report=run_checks(str(source),'manifest.json',str(self.base/'recovered'))
        self.assertEqual(report['check_verdict'],'PASS')

    def test_root_and_ancestor_replacement_detected_on_exit(self):
        for component in ('root','ancestor'):
            with self.subTest(component=component):
                ancestor=self.base/component; ancestor.mkdir(); root=ancestor/'root'; root.mkdir()
                with self.assertRaises(EvidenceError), directory(str(root)):
                    victim=root if component=='root' else ancestor
                    victim.rename(victim.with_name(victim.name+'-old')); victim.mkdir()
                    if component=='ancestor': (victim/'root').mkdir()

    def test_nested_target_ancestor_replacement_during_read(self):
        from unittest.mock import patch
        folder=self.base/'nested'; folder.mkdir(); (folder/'a').write_bytes(b'old')
        original=os.read; changed=False
        def replacing(fd,size):
            nonlocal changed
            data=original(fd,size)
            if not changed:
                changed=True; folder.rename(self.base/'previous'); folder.mkdir()
                (folder/'a').write_bytes(b'old')
            return data
        with directory(str(self.base)) as root, patch('agent_evidence._io.os.read',side_effect=replacing):
            with self.assertRaises(EvidenceError): read(root,'nested/a',Budget.start())

    def test_root_swap_before_final_freeze_cannot_leave_complete_report(self):
        from unittest.mock import patch
        import json
        import shutil
        from agent_evidence import runner
        source=self.base/'input'; fixture(str(source),procedures=True)
        original=runner.observe_check; changed=False
        def observe(*args):
            nonlocal changed
            result=original(*args)
            if not changed:
                changed=True; source.rename(self.base/'old-input'); shutil.copytree(self.base/'old-input',source)
            return result
        with patch.object(runner,'observe_check',side_effect=observe), self.assertRaises((OSError,EvidenceError)):
            runner.run_checks(str(source),'manifest.json',str(self.base/'output'))
        report=json.loads((self.base/'output/report.json').read_text())
        self.assertFalse(report['complete']); self.assertFalse(report['inventory']['valid'])
        self.assertEqual(report['procedures']['required_count'],1)

    def test_lock_writer_transition_invalidates_final_snapshot(self):
        from unittest.mock import patch
        import json
        from agent_evidence import runner
        source=self.base/'input'; fixture(str(source),procedures=True)
        original=runner.observe_check; changed=False
        def observe(*args):
            nonlocal changed
            result=original(*args)
            if not changed:
                changed=True
                with (source/'policy.lock').open('rb') as lock:
                    fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
                    policy=json.loads((source/'policy.json').read_text())
                    policy['domains']['demo']['enabled']=False
                    (source/'policy.json').write_text(json.dumps(policy))
                    fcntl.flock(lock,fcntl.LOCK_UN)
            return result
        with patch.object(runner,'observe_check',side_effect=observe):
            report=runner.run_checks(str(source),'manifest.json',str(self.base/'output'))
        self.assertFalse(report['complete']); self.assertFalse(report['inventory']['valid'])
        self.assertEqual(report['procedures']['required_gap_count'],1)
        self.assertFalse(any(row['verdict']=='PASS' for row in report['checks']))

    def test_two_complete_runs_same_output_have_one_winner(self):
        import json
        source=self.base/'input'; fixture(str(source),procedures=True); output=self.base/'output'
        command=[sys.executable,'-I','-B','-m','agent_evidence','run','--input-root',str(source),'--manifest','manifest.json','--output-root',str(output)]
        children=[subprocess.Popen(command,stdout=subprocess.PIPE,stderr=subprocess.PIPE) for _ in range(2)]
        values=[p.communicate(timeout=20) for p in children]
        # An existing output fails admission before any observation (CLI exit 2),
        # not a completed run with incomplete evidence (exit 1).
        self.assertEqual(sorted(p.returncode for p in children),[0,2])
        winner=next(i for i,p in enumerate(children) if p.returncode==0)
        loser=1-winner
        self.assertEqual(values[loser],(b'',b'input_unavailable\n'))
        self.assertEqual(values[winner][1],b'')
        report=json.loads(values[winner][0])
        self.assertEqual(report,json.loads((output/'report.json').read_text()))
        self.assertTrue(report['complete'])
        self.assertFalse(report['certified_healthy'])
        self.assertTrue(report['inventory']['valid'])
        self.assertEqual(report['procedures']['required_gap_count'],0)
        receipts=list(output.glob('check-*.json'))
        self.assertTrue(receipts)
        for path in receipts:
            receipt=json.loads(path.read_text())
            self.assertEqual(receipt['context']['run_id'],report['run_id'])
            self.assertEqual(receipt['result']['verdict'],'PASS')
        before={p.name:p.read_bytes() for p in output.iterdir()}
        repeated=subprocess.run(command,capture_output=True,timeout=20)
        self.assertEqual(repeated.returncode,2)
        self.assertEqual((repeated.stdout,repeated.stderr),(b'',b'input_unavailable\n'))
        self.assertEqual(before,{p.name:p.read_bytes() for p in output.iterdir()})
        self.assertFalse(list(output.glob('pending-*')))

    def test_unsafe_control_and_identifier_inputs_do_not_echo_payloads(self):
        import json
        for name in ('manifest','policy','scope','declarations','attestation','catalog','procedures'):
            with self.subTest(control=name):
                source=self.base/(name+'-input'); fixture(str(source),procedures=True)
                path=source/(name+'.json'); value=json.loads(path.read_text())
                value['PRIVATE_BODY_SENTINEL']='/home/private-owner/API_SECRET_SENTINEL'
                path.write_text(json.dumps(value))
                result=subprocess.run([sys.executable,'-I','-B','-m','agent_evidence','run','--input-root',str(source),'--manifest','manifest.json','--output-root',str(self.base/(name+'-output'))],capture_output=True,timeout=20)
                output=self.base/(name+'-output')
                if name=='manifest':
                    self.assertEqual(result.returncode,2)
                    self.assertEqual((result.stdout,result.stderr),(b'',b'schema_invalid\n'))
                    self.assertFalse(output.exists())  # rejected before run admission
                else:
                    self.assertEqual(result.returncode,1)
                    self.assertEqual(result.stderr,b'')
                    report=json.loads(result.stdout)
                    self.assertEqual(report,json.loads((output/'report.json').read_text()))
                    self.assertFalse(report['complete'])
                    self.assertFalse(report['certified_healthy'])
                    if name=='procedures':
                        self.assertGreater(report['procedures']['required_gap_count'],0)
                    else:
                        self.assertFalse(report['inventory']['valid'])
                        self.assertEqual(report['inventory']['reason_code'],'schema_invalid')
                published=b''.join(p.read_bytes() for p in output.glob('*.json'))
                for marker in (b'PRIVATE_BODY_SENTINEL',b'API_SECRET_SENTINEL',b'/home/private-owner'):
                    self.assertNotIn(marker,result.stdout+result.stderr+published)
        for field in ('system_id','check_id'):
            source=self.base/(field+'-input'); fixture(str(source),procedures=True)
            path=source/'manifest.json'; value=json.loads(path.read_text())
            value['checks'][0][field]='/home/private-owner/PRIVATE_BODY_SENTINEL'
            path.write_text(json.dumps(value))
            result=subprocess.run([sys.executable,'-I','-B','-m','agent_evidence','run','--input-root',str(source),'--manifest','manifest.json','--output-root',str(self.base/(field+'-output'))],capture_output=True,timeout=20)
            self.assertEqual(result.returncode,2)
            self.assertEqual((result.stdout,result.stderr),(b'',b'schema_invalid\n'))
            self.assertFalse((self.base/(field+'-output')).exists())
            self.assertNotIn(b'PRIVATE_BODY_SENTINEL',result.stdout+result.stderr)

