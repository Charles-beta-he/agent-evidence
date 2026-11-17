import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


class CLI(unittest.TestCase):
    def invoke(self,*args):
        return subprocess.run([sys.executable,'-I','-B','-m','agent_evidence',*args],capture_output=True,timeout=15)

    def test_documented_flow_and_exits(self):
        with tempfile.TemporaryDirectory() as temp:
            base=Path(temp).resolve(); source=base/'input'; output=base/'output'
            self.assertEqual(self.invoke('fixture','--out',str(source)).returncode,0)
            result=self.invoke('run','--input-root',str(source),'--manifest','manifest.json','--output-root',str(output))
            self.assertEqual(result.returncode,1,result.stderr)
            value=json.loads(result.stdout)
            self.assertEqual(value['check_verdict'],'PASS'); self.assertFalse(value['complete'])
            self.assertEqual(self.invoke('fixture','--out',str(source)).returncode,2)

    def test_bad_arguments_never_echo_body(self):
        for args in [('run',),('evaluate','PRIVATE_BODY'),('run','--input-root','PRIVATE_BODY'),('PRIVATE_BODY',)]:
            result=self.invoke(*args)
            self.assertEqual(result.returncode,2)
            self.assertNotIn(b'PRIVATE_BODY',result.stdout+result.stderr)
            self.assertNotIn(b'Traceback',result.stderr)

    def test_complete_generic_and_negative_exit_matrix(self):
        with tempfile.TemporaryDirectory() as temp:
            base=Path(temp).resolve()
            for case in ('pass','unknown','fail','disabled','inventory-gap','empty-required'):
                with self.subTest(case=case):
                    source=base/(case+'-input'); output=base/(case+'-output')
                    self.assertEqual(self.invoke('fixture','--procedures','--out',str(source)).returncode,0)
                    if case=='unknown': (source/'sample.json').unlink()
                    if case=='fail': (source/'sample.json').write_bytes(b'[]')
                    if case=='disabled':
                        path=source/'policy.json'; value=json.loads(path.read_text())
                        value['domains']['demo']['enabled']=False; path.write_text(json.dumps(value))
                    if case=='inventory-gap': (source/'catalog.json').unlink()
                    if case=='empty-required':
                        path=source/'manifest.json'; value=json.loads(path.read_text())
                        for check in value['checks']: check['required']=False
                        path.write_text(json.dumps(value))
                    result=self.invoke('run','--input-root',str(source),'--manifest','manifest.json','--output-root',str(output))
                    self.assertEqual(result.returncode,0 if case=='pass' else 1,result.stderr)
                    report=json.loads(result.stdout)
                    self.assertEqual(report,json.loads((output/'report.json').read_text()))
                    self.assertEqual(report['complete'],case=='pass')
                    self.assertFalse(report['certified_healthy'])
                    self.assertEqual(len(report['checks']),2)
                    self.assertEqual(report['procedures']['required_count'],1)
                    if case=='disabled':
                        self.assertEqual(report['procedures']['rows'][0]['verdict'],'NOT_APPLICABLE')
                    if case=='fail': self.assertEqual(report['check_verdict'],'FAIL')

    def test_cold_import_only_interpreter_loading_io(self):
        code='''import sys
sys.dont_write_bytecode=True
def guard(event,args):
 if event == 'open':
  path=str(args[0])
  if not path.endswith(('.py','.pyc')): raise RuntimeError('business IO during import')
 if event in ('subprocess.Popen','os.system','os.mkdir','socket.connect'): raise RuntimeError('side effect')
sys.addaudithook(guard)
import agent_evidence
'''
        result=subprocess.run([sys.executable,'-I','-B','-c',code],capture_output=True,timeout=5)
        self.assertEqual(result.returncode,0,result.stderr)

    def test_import_has_no_io(self):
        code='import sys, importlib, agent_evidence\ndef guard(event,args):\n if event == "open" and args[0] not in (agent_evidence.__file__,agent_evidence.__cached__): raise RuntimeError("forbidden")\n if event in ("subprocess.Popen","os.system","os.mkdir"): raise RuntimeError("forbidden")\nsys.addaudithook(guard)\nimportlib.reload(agent_evidence)'
        result=subprocess.run([sys.executable,'-I','-B','-c',code],capture_output=True,timeout=5)
        self.assertEqual(result.returncode,0,result.stderr)
