"""Explicit inventory admission and one-shot freeze; no serialized live grants.

Sequential API: a batch belongs to one coordinator. Cooperative review metadata
is not a signature. Pure validation cannot construct a live acquisition batch.
"""
_EXECUTED_CODE = __import__('sys')._getframe().f_code
import time
import threading
from dataclasses import dataclass
from types import MappingProxyType
from .contracts import keys, require, identifier, digest, ids
from .serialization import decode, CONTROL_LIMIT, EvidenceError
from .receipts import timestamp, raw_digest, reason
from ._io import read, identity
from .policy import locked, snapshot, dependencies
from .revisions import revision

_CONTROL_NAMES = ('declarations', 'scope', 'attestation', 'catalog')
_TOKEN = object()


def immutable(value):
    if isinstance(value, dict):
        return MappingProxyType({k: immutable(v) for k, v in value.items()})
    if isinstance(value, list):
        return tuple(immutable(v) for v in value)
    return value


def plain(value):
    if isinstance(value, (dict, MappingProxyType)):
        return {k: plain(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [plain(v) for v in value]
    return value


def validate_controls(raws, spec):
    """Pure supplied-byte validation, NOT admission. Uses the current wall clock."""
    keys(raws, _CONTROL_NAMES)
    try:
        values = {name: decode(raws[name]) for name in _CONTROL_NAMES}
    except EvidenceError:
        raise EvidenceError('inventory_control_invalid') from None
    declarations, scope, attestation, catalog = (values[n] for n in _CONTROL_NAMES)
    keys(declarations, ('schema', 'procedures'))
    require(declarations['schema'] == 'agent_evidence_inventory_declarations_v1')
    procedures = declarations['procedures']
    require(isinstance(procedures, list) and 0 < len(procedures) <= 1024)
    names = set(); sources = set(); systems = {}; union = {k: set(dependencies(spec, k)) for k in spec['targets']}
    for row in procedures:
        if isinstance(row, dict) and 'validation' in row:
            from .procedures import validate_declaration
            validate_declaration(row)
        else:
            keys(row, ('procedure_id', 'system_id', 'required', 'exempt', 'source_ids', 'domains'))
        identifier(row['procedure_id']); identifier(row['system_id'])
        require(row['procedure_id'] not in names, 'inventory_binding')
        names.add(row['procedure_id'])
        require(type(row['required']) is bool and type(row['exempt']) is bool)
        require(not (row['required'] and row['exempt']), 'inventory_binding')
        ids(row['source_ids']); ids(row['domains'])
        require(bool(row['source_ids']), 'inventory_binding')
        system_sources = systems.setdefault(row['system_id'], set())
        system_sources.update(row['source_ids'])
        require(len(system_sources) <= 32, 'control_limit')
        for source in row['source_ids']:
            require(source in union, 'inventory_binding')
            sources.add(source); union[source].update(row['domains'])
    common = ('schema', 'owner_id', 'evidence_id', 'basis_id', 'reviewed_at', 'expires_at',
              'revoked', 'max_freshness_seconds', 'declarations_sha256', 'procedure_ids', 'source_pins')
    keys(scope, (*common, 'scope_complete', 'negative_boundaries'))
    keys(attestation, (*common, 'approved_scope_sha256', 'scope_complete'))
    keys(catalog, (*common, 'approved_scope_sha256', 'source_domains'))
    for name, value in (('scope', scope), ('attestation', attestation), ('catalog', catalog)):
        require(value['schema'] == f'agent_evidence_inventory_{name}_v1')
        for key in ('owner_id', 'evidence_id', 'basis_id'):
            identifier(value[key])
        require(type(value['revoked']) is bool and not value['revoked'], 'inventory_revoked')
        require(type(value['max_freshness_seconds']) is int and 0 < value['max_freshness_seconds'] <= 86400, 'inventory_binding')
        digest(value['declarations_sha256'])
        require(value['declarations_sha256'] == raw_digest(raws['declarations']), 'inventory_binding')
        require(value['procedure_ids'] == sorted(names), 'inventory_binding')
        require(isinstance(value['source_pins'], dict) and set(value['source_pins']) == sources, 'inventory_binding')
        for pin in value['source_pins'].values():
            digest(pin)  # Raw-byte SHA-256 only; no selectable weak hash kind.
    for key in common[1:]:
        require(scope[key] == attestation[key] == catalog[key], 'inventory_binding')
    require(scope['scope_complete'] is True and attestation['scope_complete'] is True, 'inventory_binding')
    ids(scope['negative_boundaries']); require(bool(scope['negative_boundaries']), 'inventory_binding')
    for value in (attestation, catalog):
        digest(value['approved_scope_sha256'])
        require(value['approved_scope_sha256'] == raw_digest(raws['scope']), 'inventory_binding')
    require(isinstance(catalog['source_domains'], dict) and set(catalog['source_domains']) == sources, 'inventory_binding')
    for source, domains in catalog['source_domains'].items():
        ids(domains); union[source].update(domains)
    require(all(len(domains) <= 32 for domains in union.values()), 'control_limit')
    reviewed = timestamp(scope['reviewed_at']); expiry = timestamp(scope['expires_at'])
    expires = min(expiry, reviewed + scope['max_freshness_seconds'])
    current = time.time()
    require(reviewed <= current < expires and reviewed < expiry, 'inventory_expired')
    return {'controls': values, 'control_pins': {k: raw_digest(v) for k, v in raws.items()},
            'domains': {k: sorted(v) for k, v in union.items()}, 'reviewed': reviewed,
            'expires': expires, 'validated_at': current, 'source_pins': scope['source_pins']}


def _controls(root_fd, spec, budget):
    return {name: read(root_fd, spec['inventory'][name], budget, CONTROL_LIMIT) for name in _CONTROL_NAMES}


class InventoryBatch:
    """Internal sequential state. Cannot be loaded from a receipt or mapping."""
    def __init__(self, token, spec, budget, root_id, run_id, code):
        require(token is _TOKEN, 'inventory_not_live')
        self.spec = immutable(spec); self.budget = budget
        self.root_id = root_id; self.run_id = run_id; self.code = code
        self.admission = None; self.error = None; self.policy = None
        self.requested_declarations = None
        self.policy_pin = None; self.lock_pin = None; self.observations = {}
        self._frozen = False; self._guard = threading.Lock()


@dataclass(frozen=True)
class FrozenInventory:
    _token: object
    data: object


def acquire_inventory(root_fd, spec, budget, run_id):
    """Admit controls before any check/source worker. Does not read business bytes."""
    batch = InventoryBatch(_TOKEN, spec, budget, identity(root_fd), run_id, revision())
    try:
        with locked(root_fd, spec['lock'], budget) as lock_pin:
            batch.lock_pin = lock_pin
            policy, pin = snapshot(root_fd, spec['policy'], budget)
            controls = {'declarations': read(root_fd, spec['inventory']['declarations'], budget, CONTROL_LIMIT)}
            requested = decode(controls['declarations'])
            if (requested.get('schema') == 'agent_evidence_inventory_declarations_v1'
                    and isinstance(requested.get('procedures'), list)):
                batch.requested_declarations = immutable(requested)
            for name in _CONTROL_NAMES[1:]:
                controls[name] = read(root_fd, spec['inventory'][name], budget, CONTROL_LIMIT)
            admission = validate_controls(controls, spec)
            budget.tick()
            batch.policy = immutable(policy); batch.policy_pin = pin
            batch.admission = immutable(admission)
    except (OSError, ValueError, TypeError) as error:
        batch.error = reason(error)
    return batch


def record_observation(batch, source_id, result):
    require(type(batch) is InventoryBatch and not batch._frozen, 'inventory_not_live')
    require(batch.admission is not None and source_id in batch.admission['source_pins'], 'inventory_binding')
    require(source_id not in batch.observations, 'inventory_already_observed')
    from .receipts import validate_outcome
    validate_outcome(result)
    batch.observations[source_id] = immutable(result)


def freeze_inventory(root_fd, batch):
    """One transition, including failure. Every final read uses the original ledger.

    Two final policy reads bracket complete controls. Never expose first-read
    policy as a successful snapshot, and never replace a concrete error by a later
    deadline failure. No source content is reopened here.
    """
    require(type(batch) is InventoryBatch, 'inventory_not_live')
    with batch._guard:
        require(not batch._frozen, 'inventory_already_frozen')
        batch._frozen = True
    started = False; control = {}; failure = batch.error
    drift = False; valid = False
    if failure is None:
        try:
            batch.budget.tick(); started = True
            require(identity(root_fd) == batch.root_id, 'boundary_invalid')
            spec = plain(batch.spec)
            with locked(root_fd, spec['lock'], batch.budget, batch.lock_pin):
                first, pin = snapshot(root_fd, spec['policy'], batch.budget)
                require(pin == batch.policy_pin, 'policy_drift')
                admitted = validate_controls(_controls(root_fd, spec, batch.budget), spec)
                require(admitted['control_pins'] == plain(batch.admission['control_pins']), 'inventory_drift')
                _, second_pin = snapshot(root_fd, spec['policy'], batch.budget)
                require(pin == second_pin, 'policy_drift')
            require(revision() == batch.code, 'revision_drift')
            current = time.time()
            require(batch.admission['validated_at'] <= current < batch.admission['expires'], 'inventory_expired')
            batch.budget.tick()  # Late success is unusable; no partial snapshot escapes.
            control = {'policy': first, 'policy_sha256': pin, 'lock_identity': batch.lock_pin,
                       'control_pins': admitted['control_pins']}
            valid = all(k in batch.observations and batch.observations[k]['reason_code'] == 'observed'
                        and batch.observations[k]['observed_sha256'] == pin
                        for k, pin in batch.admission['source_pins'].items())
            if not valid:
                failure = 'inventory_source_unverified'
        except (OSError, ValueError, TypeError) as error:
            failure = reason(error); control = {}; drift = started
    data = {'run_id': batch.run_id, 'check_revision': batch.code, 'input_identity': batch.root_id,
            'valid': valid, 'reason_code': failure or 'observed', 'drift': drift,
            'final_observation_started': started, 'control_snapshot': control,
            'observations': {k: plain(v) for k, v in batch.observations.items()},
            'admission': plain(batch.admission) if batch.admission else None,
            'requested_declarations': plain(batch.requested_declarations),
            'frozen_at': time.time(), 'bytes_read': 8*1024*1024-batch.budget.left}
    return FrozenInventory(_TOKEN, immutable(data))


def consumption(frozen):
    """Current-clock, no-I/O consumption gate. There is deliberately no now arg."""
    require(type(frozen) is FrozenInventory and frozen._token is _TOKEN, 'inventory_not_live')
    data = frozen.data; admission = data['admission']; current = time.time()
    if admission is not None and not (admission['validated_at'] <= data['frozen_at'] <= current < admission['expires']):
        return 'inventory_expired'
    return data['reason_code']
