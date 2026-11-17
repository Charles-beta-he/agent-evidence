"""Validation of supplied procedure evidence, never procedure execution.

References are IDs into caller-admitted bytes, not paths or capabilities. Record
assertions are checked structurally and by identity/hash, not independently
observed business facts. Distinct IDs do not prove independent people or runs.
Semantic lineage and upstream permission notices: THIRD_PARTY_NOTICES.md.
"""
_EXECUTED_CODE = __import__('sys')._getframe().f_code
import time
from .contracts import keys, require, identifier, digest, ids, combine
from .serialization import decode, encode, EvidenceError
from .receipts import timestamp, raw_digest
from .inventory import consumption, plain

BASE_FIELDS = ('procedure_id', 'system_id', 'required', 'exempt', 'source_ids', 'domains')
VALIDATION_FIELDS = ('implementation_state', 'freshness_seconds', 'min_successes',
                     'acceptance_atoms', 'negative_assertions', 'allowed_side_effects',
                     'issuer', 'action', 'scope')


def validate_declaration(value):
    keys(value, (*BASE_FIELDS, 'validation'))
    identifier(value['procedure_id']); identifier(value['system_id'])
    require(type(value['required']) is bool and type(value['exempt']) is bool)
    require(not (value['required'] and value['exempt']))
    ids(value['source_ids']); ids(value['domains']); require(bool(value['source_ids']))
    rule = value['validation']; keys(rule, VALIDATION_FIELDS)
    require(rule['implementation_state'] in ('missing', 'scaffolded', 'implemented', 'enabled', 'disabled'))
    require(type(rule['freshness_seconds']) is int and 0 < rule['freshness_seconds'] <= 86400)
    require(type(rule['min_successes']) is int and 0 < rule['min_successes'] <= 32)
    for field in ('acceptance_atoms', 'negative_assertions', 'allowed_side_effects'):
        ids(rule[field])
    require(bool(rule['acceptance_atoms']))
    for field in ('issuer', 'action', 'scope'):
        identifier(rule[field])
    return value


class Negative(EvidenceError):
    """Definite contradiction within supplied evidence; not missing evidence."""


def _equal(actual, expected):
    if actual != expected:
        raise Negative('evidence_contradiction')


def _record(pointer, admitted):
    keys(pointer, ('id', 'sha256')); identifier(pointer['id']); digest(pointer['sha256'])
    require(pointer['id'] in admitted, 'evidence_missing')
    raw = admitted[pointer['id']]
    require(isinstance(raw, bytes), 'evidence_invalid')
    _equal(raw_digest(raw), pointer['sha256'])
    return decode(raw)


def _assertion(pointer, admitted, receipt, kind, name):
    record = _record(pointer, admitted)
    keys(record, ('schema', 'receipt_id', 'procedure_id', 'system_id', 'kind', 'name', 'status'))
    _equal(record['schema'], 'agent_evidence_assertion_v1')
    for field in ('receipt_id', 'procedure_id', 'system_id'):
        _equal(record[field], receipt[field])
    _equal(record['kind'], kind); _equal(record['name'], name)
    require(record['status'] in ('PASS', 'FAIL', 'UNKNOWN'))
    if record['status'] == 'FAIL':
        raise Negative('assertion_failed')
    require(record['status'] == 'PASS', 'assertion_unknown')


def _receipt(receipt, declaration, admitted, current):
    keys(receipt, ('schema', 'receipt_id', 'procedure_id', 'system_id', 'declaration_sha256',
                   'started_at', 'completed_at', 'result', 'execution_mode', 'grant',
                   'acceptance', 'negative', 'cleanup', 'side_effects_observed'))
    for field in ('receipt_id', 'procedure_id', 'system_id'):
        identifier(receipt[field])
    _equal(receipt['schema'], 'agent_evidence_procedure_receipt_v1')
    for field in ('procedure_id', 'system_id'):
        _equal(receipt[field], declaration[field])
    digest(receipt['declaration_sha256'])
    _equal(receipt['declaration_sha256'], raw_digest(encode(declaration)))
    start = timestamp(receipt['started_at']); finish = timestamp(receipt['completed_at'])
    rule = declaration['validation']
    require(start <= finish <= current and current - finish <= rule['freshness_seconds'], 'evidence_stale')
    require(receipt['result'] in ('PASS', 'FAIL', 'UNKNOWN'))
    if receipt['result'] == 'FAIL':
        raise Negative('receipt_failed')
    require(receipt['result'] == 'PASS', 'receipt_unknown')
    _equal(receipt['execution_mode'], 'live_e2e')
    ids(receipt['side_effects_observed'])
    if not set(receipt['side_effects_observed']).issubset(rule['allowed_side_effects']):
        raise Negative('side_effect_denied')
    grant = _record(receipt['grant'], admitted)
    keys(grant, ('schema', 'grant_id', 'receipt_id', 'procedure_id', 'system_id', 'issuer',
                 'action', 'scope', 'status', 'valid_from', 'expires_at'))
    _equal(grant['schema'], 'agent_evidence_procedure_grant_v1')
    _equal(grant['grant_id'], receipt['grant']['id'])
    for field in ('receipt_id', 'procedure_id', 'system_id'):
        _equal(grant[field], receipt[field])
    for field in ('issuer', 'action', 'scope'):
        _equal(grant[field], rule[field])
    _equal(grant['status'], 'active')
    begin = timestamp(grant['valid_from']); expiry = timestamp(grant['expires_at'])
    require(begin <= start <= finish <= current < expiry, 'grant_expired')
    for field, names, kind in (('acceptance', rule['acceptance_atoms'], 'acceptance'),
                               ('negative', rule['negative_assertions'], 'negative')):
        require(isinstance(receipt[field], dict))
        require(set(receipt[field]) == set(names), 'assertion_missing')
        for name in names:
            _assertion(receipt[field][name], admitted, receipt, kind, name)
    _assertion(receipt['cleanup'], admitted, receipt, 'cleanup', 'cleanup')


def _safe_id(value):
    try:
        return identifier(value)
    except (ValueError, TypeError):
        return None


def _evaluate_row(declaration, receipts, admitted, current, duplicate):
    raw = declaration if isinstance(declaration, dict) else {}
    row = {'procedure_id': _safe_id(raw.get('procedure_id')), 'system_id': _safe_id(raw.get('system_id')),
           'required': raw.get('required') if type(raw.get('required')) is bool else True,
           'verdict': 'UNKNOWN', 'reason_code': 'declaration_invalid',
           'successful_receipt_count': 0, 'execution_eligible': False, 'resolves_failure': False}
    try:
        validate_declaration(declaration)
        require(not duplicate, 'declaration_ambiguous')
        rule = declaration['validation']
        require(rule['implementation_state'] == 'enabled', 'implementation_pending')
        matching = [r for r in receipts if isinstance(r, dict) and r.get('procedure_id') == row['procedure_id']]
        require(bool(matching), 'receipt_missing')
        # Unparseable chronology can conceal a latest failure, so cannot be ignored.
        ordered = sorted(matching, key=lambda r: timestamp(r.get('completed_at')))
        latest_time = timestamp(ordered[-1]['completed_at'])
        identities = {}
        for receipt in ordered:
            rid = identifier(receipt.get('receipt_id'))
            pin = raw_digest(encode(receipt))
            require(rid not in identities or identities[rid] == pin, 'receipt_ambiguous')
            identities[rid] = pin
        evaluated = []
        successes = set()
        for receipt in ordered:
            try:
                _receipt(receipt, declaration, admitted, current)
                state, code = 'PASS', 'supplied_evidence_valid'
                successes.add(receipt['receipt_id'])
            except Negative as error:
                state, code = 'FAIL', str(error)
            except (ValueError, TypeError, KeyError):
                state, code = 'UNKNOWN', 'evidence_missing_invalid_or_stale'
            evaluated.append((timestamp(receipt['completed_at']), state, code))
        row['successful_receipt_count'] = len(successes)
        latest = [e for e in evaluated if e[0] == latest_time]
        verdict = combine(e[1] for e in latest)
        if verdict == 'PASS' and len(successes) < rule['min_successes']:
            verdict = 'UNKNOWN'
        code = ('success_threshold_unmet' if verdict == 'UNKNOWN' and all(e[1] == 'PASS' for e in latest)
                else next((e[2] for e in latest if e[1] == verdict), 'evidence_ambiguous'))
        row.update(verdict=verdict, reason_code=code)
    except (ValueError, TypeError, KeyError):
        pass  # Invalid/missing declarations and chronology never disappear.
    return row


def evaluate_procedures(declarations, receipts, admitted_evidence, frozen_inventory=None):
    """Pure validation of exact admitted bytes. No caller-supplied clock override.

    A frozen object is consumed with the current clock without reopening files.
    Serialized data cannot restore acquisition trust. Inputs are bounded via the
    same strict serialization contract as the CLI; invalid rows remain required.
    """
    encode(declarations); encode({'receipts': receipts})
    keys(declarations, ('schema', 'procedures'))
    require(declarations['schema'] == 'agent_evidence_inventory_declarations_v1')
    requested = declarations['procedures']
    require(isinstance(requested, list) and isinstance(receipts, list))
    require(isinstance(admitted_evidence, dict) and len(admitted_evidence) <= 1024)
    total = 0
    for key, raw in admitted_evidence.items():
        identifier(key); require(isinstance(raw, bytes))
        total += len(raw); require(total <= 262144, 'control_limit')
    if frozen_inventory is not None:
        consumption(frozen_inventory)  # Reject stored/forged mappings before access.
        admission = frozen_inventory.data['admission']
        requested_inventory = (admission['controls']['declarations'] if admission else
                               frozen_inventory.data.get('requested_declarations'))
        if requested_inventory:
            expected = plain(requested_inventory)['procedures']
            # A bundle cannot shrink the reviewed denominator or change required.
            requested = requested + [r for r in expected if r not in requested]
    names = [r.get('procedure_id') if isinstance(r, dict) else None for r in requested]
    current = time.time()
    rows = [_evaluate_row(r, receipts, admitted_evidence, current, names.count(names[i]) != 1)
            for i, r in enumerate(requested)]
    unmapped = sum(not isinstance(r, dict) or r.get('procedure_id') not in names for r in receipts)
    valid_inventory = False
    if frozen_inventory is not None:
        code = consumption(frozen_inventory)
        data = frozen_inventory.data; admission = data['admission']
        bound = bool(admission) and plain(admission['controls']['declarations']) == declarations
        valid_inventory = bound and code == 'observed' and data['valid']
        policy = data['control_snapshot'].get('policy', {}).get('domains', {}) if code != 'inventory_expired' else {}
        for row, declaration in zip(rows, requested):
            domains = set()
            if bound:
                for source in declaration['source_ids']:
                    domains.update(admission['domains'][source])
            disabled = bound and bool(policy) and all(d in policy for d in domains) and any(not policy[d]['enabled'] for d in domains)
            if disabled:
                row.update(verdict='NOT_APPLICABLE', reason_code='policy_disabled')
            elif not valid_inventory and row['verdict'] != 'FAIL':
                row.update(verdict='UNKNOWN', reason_code='inventory_unverified')
    required = [r for r in rows if r['required']]
    verdict = combine(r['verdict'] for r in required)
    if unmapped and verdict != 'FAIL':
        verdict = 'UNKNOWN'
    return {'schema': 'agent_evidence_procedure_report_v1', 'mode': 'supplied_evidence_only',
            'scope': 'validation_of_supplied_evidence', 'rows': rows, 'verdict': verdict,
            'required_count': len(required), 'required_gap_count': sum(r['verdict'] != 'PASS' for r in required),
            'unmapped_receipt_count': unmapped, 'inventory_valid': bool(valid_inventory),
            'live_admission': False, 'complete': False, 'certified_healthy': False,
            'certification_status': 'not_provided'}


def evaluate_bundle(value, frozen_inventory=None):
    keys(value, ('schema', 'declarations', 'receipts', 'admitted_evidence'))
    require(value['schema'] == 'agent_evidence_procedure_bundle_v1')
    encode(value)
    require(isinstance(value['admitted_evidence'], dict))
    require(all(isinstance(v, str) for v in value['admitted_evidence'].values()))
    admitted = {key: text.encode('utf-8') for key, text in value['admitted_evidence'].items()}
    return evaluate_procedures(value['declarations'], value['receipts'], admitted, frozen_inventory)
