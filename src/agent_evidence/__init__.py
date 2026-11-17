"""Experimental local evidence observations. Importing performs no I/O."""
_EXECUTED_CODE = __import__('sys')._getframe().f_code
__version__ = '0.1.0.dev0'


def run_checks(input_root, manifest_name, output_root):
    """Run explicit checks, optionally with reviewed inventory; package is partial."""
    from ._io import supported
    supported()
    from .runner import run_checks as run
    return run(input_root, manifest_name, output_root)


def evaluate_procedures(declarations, receipts, admitted_evidence, frozen_inventory=None):
    """Validate explicitly supplied bytes; never execute or certify business work."""
    from .procedures import evaluate_procedures as evaluate
    return evaluate(declarations, receipts, admitted_evidence, frozen_inventory)
