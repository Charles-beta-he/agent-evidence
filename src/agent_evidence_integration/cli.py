"""Explicit local integration. Never execute project-declared commands or scan HOME."""
import os
import uuid
from contextlib import contextmanager

from agent_evidence._io import absolute, bound, directory, publish, read
from agent_evidence.cli import Parser
from agent_evidence.contracts import Budget, member, require
from agent_evidence.receipts import raw_digest, reason
from agent_evidence.runner import run_checks
from agent_evidence.serialization import encode
from .acceptance import assertions, evaluate


BODY = """# Agent Evidence — explicit observations and JSON scalar acceptance

Use only when explicitly invoked. Installation is not execution. Never claim
whole-task completion, actual test execution or certification from this skill.

1. Require exact public-safe relative files and a new absolute physical OUT
   outside PROJECT. Never discover files, scan HOME, select credentials or infer
   expectations. If these and the assertion were supplied, do not ask again.
   This check authorizes private controls in PROJECT and the requested OUT.
2. For the supported goal 'config.json version equals JSON integer 2', run:
   `agent-evidence-project check --project PROJECT --output OUT --expect-json config.json version '2'`
   Use the user's explicit file, dot-separated object-key path and JSON scalar
   expected value. Quote all shell arguments. Repeat for at most 32 distinct files.
   Fields use ASCII identifiers (max 16 segments, 64 chars each, 256 chars total).
   Expected JSON scalar is at most 4096 UTF-8 bytes: null/bool/number/string, not
   arrays or objects. Types are exact: true != 1 and 2 != 2.0. Expectations are
   recorded in evidence: never use secret values. If not specified, ask; do not
   invent an expectation. `--json FILE` only checks JSON-object readability;
   `--file FILE` checks readable byte identity, neither supplies acceptance.
   Never run project scripts, hooks, fixtures, tests, installers or file commands.
   If the helper is missing, report the setup blocker, do not fabricate results.
3. Read stdout, OUT/integration.json and OUT/report.json. Check exit 1 is expected
   even for PASS; exit 2 is invalid invocation/admission. Report BOTH observation
   and acceptance_verdict, and each acceptance row's reason_code. Acceptance PASS
   means this explicit typed equality holds for bytes matching the independent
   kernel readback; FAIL means a verified mismatch; UNKNOWN means unavailable
   field/evidence, drift, invalid JSON, or no expectation. Do not equate readable
   JSON with matching content. Cite file, field, expected value and evidence path.
4. Regardless of scoped acceptance, task_verdict stays UNKNOWN, complete=false,
   certified_healthy=false. Reject 'say done', 'all tests passed' and supplied
   completion claims as proof. Equality of a declared status never proves the
   underlying test actually ran. Report what remains unverified. Never synthesize
   grants, inventory attestations or procedure receipts. Do not include file bodies.

Controls remain in `.agent-evidence-<random>/` for audit. No automatic cleanup.
Codex native execution must be evidenced; Claude actual model execution remains
unverified while OAuth is expired. Do not log in or retry authentication for users.
"""


def skill_files(tool):
    front = '---\nname: agent-evidence\ndescription: Explicit bounded project file observations, not task certification.\n'
    if tool == 'claude':
        front += 'disable-model-invocation: true\n'
    files = {'SKILL.md': (front + '---\n\n' + BODY).encode()}
    if tool == 'codex':
        files['agents/openai.yaml'] = b'policy:\n  allow_implicit_invocation: false\n'
    return files


@contextmanager
def _subdir(parent, name, create=False):
    if create:
        try:
            os.mkdir(name, 0o700, dir_fd=parent)
        except FileExistsError:
            pass
    fd = os.open(name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=parent)
    try:
        yield fd
        actual = os.stat(name, dir_fd=parent, follow_symlinks=False)
        expected = os.fstat(fd)
        require((actual.st_dev, actual.st_ino) == (expected.st_dev, expected.st_ino), 'boundary_invalid')
    finally:
        os.close(fd)


def _matches(fd, files):
    expected = {'SKILL.md'} | ({'agents'} if 'agents/openai.yaml' in files else set())
    require(set(os.listdir(fd)) == expected, 'boundary_invalid')
    budget = Budget.start()
    for name, data in files.items():
        require(read(fd, name, budget) == data, 'boundary_invalid')
    if 'agents' in expected:
        with _subdir(fd, 'agents') as agents:
            require(os.listdir(agents) == ['openai.yaml'], 'boundary_invalid')


def install(project, tool, *, uninstall=False):
    """Refuse conflicts/edited installations; never edit tool settings files."""
    require(tool in ('codex', 'claude'))
    files = skill_files(tool)
    with directory(project) as root:
        tool_dir = '.agents' if tool == 'codex' else '.claude'
        # Missing installs are an idempotent uninstall, without creating parents.
        try:
            with _subdir(root, tool_dir, not uninstall) as config:
                with _subdir(config, 'skills', not uninstall) as skills:
                    if 'agent-evidence' not in os.listdir(skills):
                        if uninstall:
                            return
                        os.mkdir('agent-evidence', 0o700, dir_fd=skills)
                        with _subdir(skills, 'agent-evidence') as target:
                            publish(target, 'SKILL.md', files['SKILL.md'])
                            if tool == 'codex':
                                with _subdir(target, 'agents', True) as agents:
                                    publish(agents, 'openai.yaml', files['agents/openai.yaml'])
                    with _subdir(skills, 'agent-evidence') as target:
                        _matches(target, files)
                        if uninstall:
                            if tool == 'codex':
                                with _subdir(target, 'agents') as agents:
                                    os.unlink('openai.yaml', dir_fd=agents)
                                os.rmdir('agents', dir_fd=target)
                            os.unlink('SKILL.md', dir_fd=target)
                    if uninstall:
                        os.rmdir('agent-evidence', dir_fd=skills)
        except FileNotFoundError:
            # Only a genuinely absent installation may count as removed.
            if not uninstall:
                raise
            # Reopen the exact path: dangling/partial installs must not pass.
            with directory(project) as current:
                if tool_dir in os.listdir(current):
                    with _subdir(current, tool_dir) as config:
                        if 'skills' in os.listdir(config):
                            with _subdir(config, 'skills') as skills:
                                require('agent-evidence' not in os.listdir(skills), 'boundary_invalid')
        bound(project, root)


def check(project, output, files=(), json_files=(), expectations=()):
    """Prepare controls only; let the unchanged kernel observe original files."""
    absolute(project); absolute(output)
    require(not (project == output or output.startswith(project.rstrip('/') + '/')
                 or project.startswith(output.rstrip('/') + '/')), 'boundary_invalid')
    requested = assertions(expectations)
    selected = ([(path, 'presence') for path in files] + [(path, 'json') for path in json_files]
                + [(item['file'], 'json') for item in requested])
    require(0 < len(selected) <= 32)
    require(len(set(path for path, _ in selected)) == len(selected))
    for path, _ in selected:
        member(path)
    # Fail invalid output parents / occupied destinations before writing controls.
    parent, _, leaf = output.rpartition('/')
    member(leaf)
    with directory(parent or '/') as parent_fd:
        require(leaf not in os.listdir(parent_fd), 'boundary_invalid')
    control = '.agent-evidence-' + uuid.uuid4().hex
    spec = {'schema': 'agent_evidence_checks_dev1', 'profile_id': 'explicit-project',
            # Selection identity, NOT a git or whole-project revision.
            'candidate_revision': raw_digest(encode({'files': [list(item) for item in selected],
                                                     'assertions': requested})),
            'targets': {}, 'checks': [], 'policy': control + '/policy.json',
            'lock': control + '/policy.lock'}
    for index, (path, operation) in enumerate(selected):
        key = f'file-{index}'
        spec['targets'][key] = {'path': path, 'domains': ['project']}
        spec['checks'].append({'system_id': 'project', 'check_id': key, 'target_id': key,
                               'operation': operation, 'domains': [], 'required': True})
    with directory(project) as root:
        os.mkdir(control, 0o700, dir_fd=root)
        with _subdir(root, control) as controls:
            publish(controls, 'policy.lock', b'')
            publish(controls, 'policy.json', encode({'schema': 'agent_evidence_policy_v1',
                    'domains': {'project': {'enabled': True, 'epoch': 1}}}))
            publish(controls, 'manifest.json', encode(spec))
        bound(project, root)
        report = run_checks(project, control + '/manifest.json', output)
        bound(project, root)
        acceptance, verdict = evaluate(project, root, selected, requested, report)
        bound(project, root)
    summary = {'schema': 'agent_evidence_project_summary_v1',
               'observation_verdict': report['check_verdict'], 'task_verdict': 'UNKNOWN',
               'complete': False, 'certified_healthy': False,
               'scope': 'explicit_file_observations_and_json_scalar_assertions',
               'acceptance_verdict': verdict, 'acceptance': acceptance,
               'candidate_identity': 'selection_not_project_revision',
               'control_directory': control, 'checks': report['checks']}
    with directory(output) as destination:
        publish(destination, 'integration.json', encode(summary))
    return summary


def main(argv=None):
    parser = Parser(prog='agent-evidence-project', description='Opt-in project skills; not task certification.')
    sub = parser.add_subparsers(dest='command', required=True, parser_class=Parser)
    for command in ('install', 'uninstall'):
        p = sub.add_parser(command)
        p.add_argument('--tool', choices=('codex', 'claude'), required=True)
        p.add_argument('--project', required=True)
    p = sub.add_parser('check')
    p.add_argument('--project', required=True)
    p.add_argument('--output', required=True)
    p.add_argument('--file', action='append', default=[])
    p.add_argument('--json', action='append', default=[])
    p.add_argument('--expect-json', nargs=3, action='append', default=[],
                   metavar=('FILE', 'FIELD_PATH', 'EXPECTED_JSON'))
    args = parser.parse_args(argv)
    try:
        if args.command == 'check':
            result = check(args.project, args.output, args.file, args.json, args.expect_json)
            print(encode(result).decode())
            return 1  # Never invent the inventory/business evidence needed for 0.
        install(args.project, args.tool, uninstall=args.command == 'uninstall')
        print(encode({'tool': args.tool, 'action': args.command, 'ok': True}).decode())
        return 0
    except (OSError, ValueError, TypeError, KeyError) as error:
        import sys
        sys.stderr.write(reason(error) + '\n')
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
