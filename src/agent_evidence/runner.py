"""Explicit observer, frozen inventory and supplied-procedure coordinator."""
_EXECUTED_CODE = __import__('sys')._getframe().f_code
import os
import time
import uuid
from .contracts import Budget, manifest, combine, require, member
from .serialization import decode, encode, CONTROL_LIMIT, REPORT_LIMIT
from ._io import directory, identity, read, publish, new_directory, absolute, bound
from .policy import locked, snapshot, dependencies, admit
from .checks import observe_check
from .receipts import outcome, reason
from .revisions import revision
from .inventory import acquire_inventory, freeze_inventory, record_observation, plain
from .projections import project_inventory


def run_checks(input_root, manifest_name, output_root, *, hermes=False):
    """Run real fixed observers. Scoped completeness is never certification.

    Roots must be absolute lexical POSIX paths, with no symlink components.
    The caller directly authorizes manifest_name as a bounded control input.
    Its contents only authorize exact check targets, not inventory or procedures.
    This API is sequential; do not share mutable inputs or run state across threads.
    """
    absolute(input_root); absolute(output_root); member(manifest_name)
    require(not (input_root == output_root or output_root.startswith(input_root + '/') or input_root.startswith(output_root + '/')), 'boundary_invalid')
    budget = Budget.start()
    with directory(input_root) as source:
        spec = manifest(decode(read(source,manifest_name,budget,CONTROL_LIMIT)))
        require(hermes == (spec['schema'] == 'agent_evidence_hermes_run_v1'))
        require(manifest_name not in {t['path'] for t in spec['targets'].values()})
        source_identity = identity(source)
        code = revision()
        new_directory(output_root)
        with directory(output_root) as output:
            output_identity = identity(output)
            run_id = uuid.uuid4().hex
            rows = []; initial_pin = None; initial_error = None; lock_pin = None
            batch = None; inventory_checks = []
            procedure_input = None
            if 'inventory' in spec:
                batch = acquire_inventory(source, spec, budget, run_id)
                initial_error = batch.error
                policy, initial_pin, lock_pin = batch.policy, batch.policy_pin, batch.lock_pin
                if batch.admission:
                    inventory_checks = [{'system_id':'inventory', 'check_id':key, 'target_id':key,
                                         'operation':'presence', 'required':True}
                                        for key in batch.admission['source_pins']]
            else:
                try:
                    with locked(source,spec['lock'],budget) as lock_pin:
                        policy, initial_pin = snapshot(source,spec['policy'],budget)
                except (OSError,ValueError,TypeError) as error:
                    initial_error = reason(error)
            if 'procedures' in spec:
                try:
                    procedure_input = decode(read(source, spec['procedures'], budget, CONTROL_LIMIT))
                except (OSError, ValueError, TypeError):
                    procedure_input = None
            for index, check in enumerate(spec['checks'] + inventory_checks):
                result = outcome(initial_error or 'not_observed')
                if initial_error is None:
                    try:
                        domains = (list(batch.admission['domains'][check['target_id']]) if batch
                                   else dependencies(spec,check['target_id']))
                        admit(policy,domains)  # No target context or target worker before this.
                        budget.tick()
                        ctx = {key:check[key] for key in ('system_id','check_id','target_id','operation')}
                        ctx.update(run_id=run_id,profile_id=spec['profile_id'],
                            candidate_revision=spec['candidate_revision'],check_revision=code,
                            input_identity=source_identity,output_identity=output_identity,policy_sha256=initial_pin)
                        request = dict(phase='observe',input_root=input_root,output_root=output_root,
                            context=ctx, policy=spec['policy'],lock=spec['lock'],lock_identity=lock_pin,
                            target=spec['targets'][check['target_id']]['path'],domains=domains,
                            deadline=budget.deadline,remaining_bytes=budget.left,
                            receipt=f'check-{index}.json',receipt_sha256=None)
                        result = observe_check(request,output,budget)
                    except (OSError,ValueError,TypeError) as error:
                        result = outcome(reason(error))
                if index >= len(spec['checks']):
                    record_observation(batch, check['target_id'], result)
                else:
                    rows.append({'system_id':check['system_id'],'check_id':check['check_id'],
                                 'required':check['required'],**result})
            final_started = False; final_pin = None; final_error = None; views = None
            try:
                bound(input_root, source); bound(output_root, output)
            except (OSError, ValueError) as error:
                final_error = reason(error)
                if batch:
                    batch.error = batch.error or final_error
            if batch:
                frozen = freeze_inventory(source, batch)
                views = project_inventory(frozen)
                final_started = frozen.data['final_observation_started']
                final_pin = views['profile']['control_snapshot'].get('policy_sha256')
                if final_pin is None:
                    final_error = views['profile']['reason_code']
            else:
                try:
                    require(final_error is None, final_error or 'boundary_invalid')
                    budget.tick(); final_started = True
                    with locked(source,spec['lock'],budget,lock_pin):
                        _, final_pin = snapshot(source,spec['policy'],budget)
                    require(final_pin == initial_pin, 'policy_drift')
                    require(revision() == code, 'revision_drift')
                    budget.tick()
                except (OSError,ValueError,TypeError) as error:
                    final_error = reason(error); final_pin = None
            if final_error:
                for index, row in enumerate(rows):
                    if row['verdict'] == 'FAIL':
                        continue
                    adapter = row.get('adapter', {})
                    if (row['verdict'] == 'PASS' and row['evidence_state'] == 'verified'
                            and adapter.get('verdict') == 'FAIL'):
                        # Only observe_check's validated independent readback reaches here.
                        # Revoke the outer positive verdict, not its conclusive negative.
                        rows[index] = {**row, 'verdict':'FAIL', 'reason_code':adapter['reason_code']}
                    else:
                        rows[index] = {**{k:v for k,v in row.items() if k != 'adapter'},
                                       **outcome(final_error)}
            report = {'schema':'agent_evidence_checks_report_dev1','run_id':run_id,
                'check_revision':code,'candidate_revision':spec['candidate_revision'],
                'checks':rows,'check_verdict':combine(r['verdict'] for r in rows),
                'policy_consistency':{'final_observation_started':final_started,
                    'control_sha256':final_pin,'reason_code':final_error or 'observed'},
                'bytes_read':8*1024*1024-budget.left,
                'complete':False,'implementation_status':'partial_checks_only',
                'certified_healthy':False,'certification_status':'not_provided'}
            if batch:
                report['implementation_status'] = 'partial_inventory_slice'
                report['inventory'] = {k: plain(frozen.data[k]) for k in
                    ('valid','reason_code','drift','final_observation_started','control_snapshot','observations')}
                report['views'] = views
                if 'procedures' in spec:
                    from .procedures import evaluate_bundle, evaluate_procedures
                    try:
                        report['procedures'] = evaluate_bundle(procedure_input, frozen)
                    except (ValueError, TypeError, KeyError):
                        declarations = (plain(batch.requested_declarations) if batch.requested_declarations else
                                        {'schema':'agent_evidence_inventory_declarations_v1','procedures':[]})
                        report['procedures'] = evaluate_procedures(declarations, [], {}, frozen)
                    report['implementation_status'] = 'partial_procedure_slice'
            if hermes:
                from .adapters.hermes import project
                report['hermes'] = project(rows)
                report['implementation_status'] = 'partial_hermes_slice'
            required = [r for r in rows if r['required']]
            procedure = report.get('procedures', {})
            report['complete'] = bool(required) and all(r['verdict'] == 'PASS' for r in required) and (
                final_error is None and report['check_verdict'] == 'PASS'
                and report.get('inventory', {}).get('valid') is True
                and procedure.get('inventory_valid') is True
                and procedure.get('required_count', 0) > 0
                and procedure.get('required_gap_count') == 0
                and procedure.get('unmapped_receipt_count') == 0
                and procedure.get('verdict') == 'PASS'
                and (not hermes or all(r['verdict'] == 'PASS' for r in report['hermes']['checks'])))
            report['implementation_status'] = 'scoped_evidence_pipeline'
            publish(output,'report.json',encode(report, limit=REPORT_LIMIT))
            return report
