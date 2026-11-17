"""Installed-code drift tests use disposable copies, never mutate the installation."""
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
import agent_evidence
from agent_evidence.revisions import MODULES, revision


class LoadedIdentity(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory(); self.addCleanup(temp.cleanup)
        self.base = Path(temp.name).resolve()
        shutil.copytree(Path(agent_evidence.__file__).parent, self.base/'agent_evidence',
                        ignore=shutil.ignore_patterns('__pycache__'))

    def run_copy(self, body):
        script = 'import sys; sys.path.insert(0, sys.argv[1]);\n' + body
        return subprocess.run([sys.executable, '-I', '-B', '-c', script, str(self.base)],
                              capture_output=True, timeout=15)

    def test_fixed_closure_and_fresh_load(self):
        self.assertEqual(set(MODULES), {str(p.relative_to(Path(agent_evidence.__file__).parent))[:-3]
                         for p in Path(agent_evidence.__file__).parent.rglob('*.py')})
        result = self.run_copy('from agent_evidence.revisions import revision; print(revision())')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.decode().strip(), revision())

    def test_stale_timestamp_pyc_is_rejected(self):
        for helper in ('serialization', 'revisions', '_worker', 'adapters/hermes'):
            with self.subTest(helper=helper):
                result = self.run_copy('''import os, py_compile
from pathlib import Path
p = Path(sys.argv[1])/'agent_evidence'/HELPER
raw = p.read_text(); before = p.stat()
py_compile.compile(str(p), doraise=True, invalidation_mode=py_compile.PycInvalidationMode.TIMESTAMP)
# Same byte length and timestamp: ordinary CPython accepts this stale cache.
p.write_text(raw.replace('_EXECUTED_CODE =', '_EXECUTED_C0DE =', 1))
os.utime(p, ns=(before.st_atime_ns, before.st_mtime_ns))
try:
 from agent_evidence.revisions import revision
 revision()
except ValueError as error:
 assert str(error) == 'revision_drift'; print('rejected-stale-cache')
else:
 raise AssertionError('stale bytecode accepted')
finally:
 p.write_text(raw)
 for cache in p.parent.glob('__pycache__/' + p.stem + '.*.pyc'): cache.unlink()
'''.replace('HELPER', repr(helper+'.py')))
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertIn(b'rejected-stale-cache', result.stdout)

    def test_source_changed_after_import_and_fresh_helper_identity(self):
        result = self.run_copy('''from pathlib import Path
from agent_evidence.revisions import revision
before = revision()
p = Path(sys.argv[1])/'agent_evidence/serialization.py'
p.write_text(p.read_text().replace('CONTROL_LIMIT = 262144', 'CONTROL_LIMIT = 262143'))
try: revision()
except ValueError as error: assert str(error) == 'revision_drift'
else: raise AssertionError('loaded/source drift accepted')
print(before)
''')
        self.assertEqual(result.returncode, 0, result.stderr)
        fresh = self.run_copy('from agent_evidence.revisions import revision; print(revision())')
        self.assertEqual(fresh.returncode, 0, fresh.stderr)
        self.assertNotEqual(result.stdout, fresh.stdout)

    def test_main_worker_loaded_entry_is_checked(self):
        # Actual -m execution has __main__ and separately imported _worker copies.
        result = self.run_copy('''import runpy
from pathlib import Path
p = Path(sys.argv[1])/'agent_evidence/_worker.py'
raw = p.read_text()
# Inject a deterministic accidental source replacement after the -m code loads.
raw = raw.replace('def main():', "def main():\\n    from pathlib import Path\\n    p = Path(__file__)\\n    p.write_text(p.read_text().replace('return 0', 'return 9', 1))\\n    revision()")
p.write_text(raw)
try: runpy.run_module('agent_evidence._worker', run_name='__main__', alter_sys=True)
except ValueError as error: assert str(error) == 'revision_drift'; print('entry-drift-rejected')
''')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn(b'entry-drift-rejected', result.stdout)
