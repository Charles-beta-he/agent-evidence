"""Six diagnostic views of a single freeze; no discovery, source reads or repair."""
_EXECUTED_CODE = __import__('sys')._getframe().f_code
from .inventory import consumption, plain
from .contracts import require

VIEWS = ('profile', 'checks', 'procedures', 'remediation', 'lifecycle', 'adapter')


def project_inventory(frozen):
    """Observe the current clock once; all six views consume that same decision.

    The procedure view is inventory coverage, NOT procedure-evidence evaluation.
    Suspension never resolves an earlier failure or removes a required row.
    """
    code = consumption(frozen)
    data = frozen.data; admission = data['admission']
    control = data['control_snapshot'] if code != 'inventory_expired' else {}
    policy = control.get('policy', {}).get('domains', {})
    rows = []
    if admission:
        for declaration in admission['controls']['declarations']['procedures']:
            domains = set()
            for source in declaration['source_ids']:
                domains.update(admission['domains'][source])
            known = bool(control) and all(d in policy for d in domains)
            disabled = known and any(not policy[d]['enabled'] for d in domains)
            verdict = ('NOT_APPLICABLE' if disabled else 'PASS' if data['valid'] and code == 'observed'
                       else 'UNKNOWN')
            rows.append({'procedure_id': declaration['procedure_id'], 'system_id': declaration['system_id'],
                         'required': declaration['required'], 'verdict': verdict,
                         'applicability': 'disabled' if disabled else 'enabled' if known else 'unknown',
                         'execution_eligible': False, 'resolves_failure': False})
    elif data.get('requested_declarations'):
        from .procedures import _safe_id
        for declaration in data['requested_declarations']['procedures']:
            raw = declaration if isinstance(declaration, (dict, type(data))) else {}
            rows.append({'procedure_id': _safe_id(raw.get('procedure_id')),
                         'system_id': _safe_id(raw.get('system_id')),
                         'required': raw.get('required') if type(raw.get('required')) is bool else True,
                         'verdict': 'UNKNOWN', 'applicability': 'unknown',
                         'execution_eligible': False, 'resolves_failure': False})
    shared = {'run_id': data['run_id'], 'reason_code': code,
              'inventory_valid': data['valid'] and code == 'observed',
              'control_snapshot': plain(control), 'rows': rows,
              'required_count': sum(r['required'] for r in rows),
              'required_gap_count': sum(r['required'] and r['verdict'] != 'PASS' for r in rows),
              'drift': data['drift'] or code == 'inventory_expired',
              'live_admission': True, 'certified_healthy': False}
    # Independent mutable JSON outputs, identical values; frozen input remains immutable.
    return {name: plain(shared) for name in VIEWS}


def evaluate_supplied(value):
    """Untrusted stored diagnostic data is never reconstructed as live admission."""
    require(isinstance(value, dict))
    if value.get('schema') == 'agent_evidence_procedure_bundle_v1':
        from .procedures import evaluate_bundle
        return evaluate_bundle(value)
    return {'mode': 'supplied_evidence_only', 'live_admission': False,
            'inventory_valid': False, 'verdict': 'UNKNOWN',
            'reason_code': 'inventory_not_live', 'certified_healthy': False}
