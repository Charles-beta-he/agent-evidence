"""Fixed installed closure checked against the code objects actually executed.

Normal package loading is unchanged. Each module retains its executing module
code object; source_to_code compiles only this fixed package's source for equality
checking, never executes it. This detects stale caches and source/load drift, not
malicious caller mutation, hostile same-UID writers or a compromised interpreter.
"""
_EXECUTED_CODE = __import__('sys')._getframe().f_code
import hashlib
import importlib
from importlib.machinery import SourceFileLoader
from pathlib import Path
import sys
from .serialization import EvidenceError

MODULES = ('__init__','__main__','cli','contracts','serialization','revisions','_io',
           '_transport','_worker','receipts','checks','policy','runner','fixtures','inventory','projections','procedures','adapters/__init__','adapters/hermes')


def revision():
    root = Path(__file__).parent
    value = hashlib.sha256()
    try:
        for name in MODULES:
            qualified = 'agent_evidence' + ('' if name == '__init__' else '.' + name.replace('/__init__', '').replace('/', '.'))
            module = importlib.import_module(qualified)
            path = root / (name + '.py')
            raw = path.read_bytes()
            expected = SourceFileLoader(qualified, str(path)).source_to_code(raw, str(path), _optimize=sys.flags.optimize)
            loaded = getattr(module, '_EXECUTED_CODE', None)
            if loaded != expected:
                raise EvidenceError('revision_drift')
            # -m executes a second module as __main__; validate that actual entry
            # too, rather than mistaking the ordinary import for the running one.
            entry = sys.modules.get('__main__')
            if getattr(getattr(entry, '__spec__', None), 'name', None) == qualified:
                if getattr(entry, '_EXECUTED_CODE', None) != expected:
                    raise EvidenceError('revision_drift')
            value.update(name.encode() + b'\0' + hashlib.sha256(raw).digest())
    except (OSError, SyntaxError, ImportError):
        raise EvidenceError('revision_drift') from None
    return value.hexdigest()
