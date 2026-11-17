"""Explicit scalar assertions over independently verified observation bytes."""
import re

from agent_evidence._io import bound, read
from agent_evidence.contracts import Budget, combine, member, require
from agent_evidence.receipts import raw_digest, reason
from agent_evidence.serialization import decode, encode


def assertions(values):
    require(isinstance(values, (list, tuple)) and len(values) <= 32)
    result = []
    for item in values:
        require(isinstance(item, (list, tuple)) and len(item) == 3)
        path, field, expected = item
        member(path)
        require(isinstance(field, str) and len(field) <= 256)
        parts = field.split('.')
        require(1 <= len(parts) <= 16 and all(
            re.fullmatch(r'[A-Za-z_][A-Za-z0-9_]{0,63}', p) for p in parts))
        require(isinstance(expected, str) and len(expected.encode('utf-8')) <= 4096)
        value = decode(b'{"expected":' + expected.encode('utf-8') + b'}')
        require(set(value) == {'expected'})
        require(type(value['expected']) in (type(None), bool, int, float, str))
        row = {'file': path, 'field': field, 'expected': value['expected']}
        result.append({**row, 'assertion_sha256': raw_digest(encode(row))})
    return result


def evaluate(project, root, selected, requested, report):
    budget = Budget.start()
    results = []
    checks = {path: report['checks'][i] for i, (path, _) in enumerate(selected)}
    for assertion in requested:
        check = checks[assertion['file']]
        result = {**assertion, 'verdict': 'UNKNOWN', 'reason_code': 'observation_unverified',
                  'run_id': report['run_id'], 'check_id': check['check_id'],
                  'check_revision': report['check_revision'],
                  'candidate_revision': report['candidate_revision'],
                  'observed_sha256': check.get('observed_sha256')}
        results.append(result)
        if not (check['verdict'] == 'PASS' and check['evidence_state'] == 'verified'
                and check.get('observed_sha256')
                and report['policy_consistency']['reason_code'] == 'observed'):
            continue
        try:
            raw = read(root, assertion['file'], budget)
            bound(project, root)
            require(raw_digest(raw) == check['observed_sha256'], 'source_drift')
            value = decode(raw, limit=1048576)
            for part in assertion['field'].split('.'):
                if not isinstance(value, dict) or part not in value:
                    result['reason_code'] = 'field_unavailable'
                    break
                value = value[part]
            else:
                equal = type(value) is type(assertion['expected']) and value == assertion['expected']
                result.update(verdict='PASS' if equal else 'FAIL',
                              reason_code='equal' if equal else 'not_equal')
        except (OSError, ValueError, TypeError) as error:
            result.update(verdict='UNKNOWN', reason_code=reason(error))
    return results, combine(r['verdict'] for r in results) if results else 'UNKNOWN'
