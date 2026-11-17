import subprocess
import sys
import time
import unittest
from unittest.mock import patch
from agent_evidence import _transport
from agent_evidence.contracts import Budget
from agent_evidence.serialization import EvidenceError


class Limits(unittest.TestCase):
    def adversary(self, code, request):
        original = subprocess.Popen
        children = []
        def launch(command, **kwargs):
            self.assertEqual(command,[sys.executable,'-I','-B','-m','agent_evidence._worker'])
            self.assertEqual(kwargs['env'],{'LC_ALL':'C','LANG':'C'})
            child=original([sys.executable,'-I','-B','-c',code],**kwargs)
            children.append(child)
            return child
        budget=Budget.start(seconds=.2)
        start=time.monotonic()
        with patch.object(_transport.subprocess,'Popen',launch):
            with self.assertRaises((EvidenceError,OSError)):
                _transport.call(request,budget)
        self.assertLess(time.monotonic()-start,2)
        self.assertEqual(budget.left,0)
        self.assertTrue(children)
        self.assertTrue(all(p.poll() is not None for p in children))

    def test_stdin_never_read_cannot_block_deadline(self):
        self.adversary('import time; time.sleep(10)',{'data':['x'*4000]*50})

    def test_stdout_flood_is_capped(self):
        self.adversary('import os;\nwhile True: os.write(1,b"x"*16384)',{'x':1})

    def test_stderr_flood_is_capped(self):
        self.adversary('import os;\nwhile True: os.write(2,b"x"*16384)',{'x':1})

    def test_inherited_pipe_holder_reaped(self):
        self.adversary('import os,time; pid=os.fork();\nif pid==0: time.sleep(10)\nelse: os._exit(0)',{'x':1})

    def test_actual_worker_rejects_unknown_operation(self):
        budget=Budget.start()
        with self.assertRaises(EvidenceError):
            _transport.call({'command':'arbitrary-code'},budget)
        self.assertEqual(budget.left,0)
