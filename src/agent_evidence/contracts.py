"""Explicit observation-only development contract; not an inventory grant."""
_EXECUTED_CODE = __import__('sys')._getframe().f_code
import re
import time
from dataclasses import dataclass
from .serialization import EvidenceError


def require(condition, reason='schema_invalid'):
    if not condition:
        raise EvidenceError(reason)


def keys(value, expected):
    require(isinstance(value, dict) and set(value) == set(expected))


def identifier(value):
    require(isinstance(value, str) and re.fullmatch(r'[a-zA-Z0-9][a-zA-Z0-9_.:-]{0,63}', value) is not None)
    return value


def digest(value):
    require(isinstance(value, str) and re.fullmatch('[a-f0-9]{64}', value) is not None)
    return value


def member(value):
    require(isinstance(value, str) and 0 < len(value) <= 512)
    require(not value.startswith('/') and '\\' not in value and ':' not in value)
    require(all(p not in ('', '.', '..') and re.fullmatch(r'[a-zA-Z0-9_.-]+', p) for p in value.split('/')))
    return value


def ids(value):
    require(isinstance(value, list) and len(value) <= 32)
    for item in value:
        identifier(item)
    require(len(set(value)) == len(value))


def manifest(value):
    require(isinstance(value, dict))
    hermes = value.get('schema') == 'agent_evidence_hermes_run_v1'
    procedures = value.get('schema') == 'agent_evidence_procedure_run_v1' or hermes and 'procedures' in value
    inventory = procedures or value.get('schema') == 'agent_evidence_inventory_run_v1' or hermes and 'inventory' in value
    keys(value, ('schema','profile_id','candidate_revision','targets','checks','policy','lock', *(['inventory'] if inventory else []), *(['procedures'] if procedures else []), *(['hermes'] if hermes else [])))
    require(value['schema'] in ('agent_evidence_checks_dev1', 'agent_evidence_inventory_run_v1', 'agent_evidence_procedure_run_v1', 'agent_evidence_hermes_run_v1'))
    if inventory:
        keys(value['inventory'], ('declarations', 'scope', 'attestation', 'catalog'))
        for path in value['inventory'].values():
            member(path)
        if procedures:
            member(value['procedures'])
        controls = [value['policy'], value['lock'], *value['inventory'].values(), *([value['procedures']] if procedures else [])]
        require(len(set(controls)) == len(controls))
    identifier(value['profile_id']); digest(value['candidate_revision'])
    member(value['policy']); member(value['lock'])
    targets = value['targets']; checks = value['checks']
    require(isinstance(targets, dict) and 0 < len(targets) <= 1024)
    paths = set()
    for target, entry in targets.items():
        identifier(target); keys(entry, ('path','domains'))
        member(entry['path']); ids(entry['domains'])
        require(entry['path'] not in paths)
        require(entry['path'] not in (value['policy'], value['lock'], *value.get('inventory', {}).values(), value.get('procedures')))
        paths.add(entry['path'])
    require(isinstance(checks, list) and (0 if hermes else 1) <= len(checks) <= 128)
    if hermes:
        # Adapter requests are generated only from the fixed catalog, never from
        # caller-selected operations or a caller-shrunk required denominator.
        require(not checks)
        from .adapters.hermes import prepare
        value = {**value, 'checks':prepare(value)}
        return value
    seen = set()
    for check in checks:
        keys(check, ('system_id','check_id','target_id','operation','domains','required'))
        for key in ('system_id','check_id','target_id'):
            identifier(check[key])
        require(check['target_id'] in targets and check['operation'] in ('presence','json'))
        require(type(check['required']) is bool)
        ids(check['domains'])
        pair = (check['system_id'], check['check_id'])
        require(pair not in seen); seen.add(pair)
    return value


def combine(values):
    values = tuple(values)
    if 'FAIL' in values:
        return 'FAIL'
    if not values or any(v not in ('PASS','NOT_APPLICABLE') for v in values):
        return 'UNKNOWN'
    return 'PASS' if 'PASS' in values else 'NOT_APPLICABLE'


@dataclass
class Budget:
    """One monotonic ledger; never reset between controls, workers or readbacks."""
    deadline: float
    left: int

    @classmethod
    def start(cls, seconds=10.0, size=8*1024*1024):
        require(type(seconds) in (int,float) and 0 < seconds <= 10)
        require(type(size) is int and 0 < size <= 8*1024*1024)
        return cls(time.monotonic() + seconds, size)

    def tick(self):
        require(time.monotonic() < self.deadline and self.left > 0, 'budget_exhausted')

    def charge(self, size):
        require(type(size) is int and 0 <= size <= self.left, 'budget_exhausted')
        self.left -= size
        self.tick()
