import json
import os
from pathlib import Path
import tempfile
import unittest

from agent_evidence_integration.cli import check, install, main, skill_files


class ProjectIntegration(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.base = Path(temp.name).resolve()
        self.project = self.base / 'project'
        self.project.mkdir()
        self.out = self.base / 'out'

    def test_real_observations_are_not_task_completion(self):
        (self.project / 'value.json').write_text('{"value":42}')
        result = check(str(self.project), str(self.out), json_files=['value.json'])
        self.assertEqual(result['observation_verdict'], 'PASS')
        self.assertEqual(result['task_verdict'], 'UNKNOWN')
        self.assertFalse(result['complete'])
        self.assertFalse(result['certified_healthy'])
        report = json.loads((self.out / 'report.json').read_text())
        self.assertEqual(report['check_verdict'], 'PASS')
        self.assertFalse(report['complete'])
        self.assertEqual(len(list(self.out.glob('check-*.json'))), 1)
        self.assertNotIn('value":42', (self.out / 'integration.json').read_text())

    def test_false_claim_cannot_supply_completion(self):
        (self.project / 'claim.json').write_text('{"complete":true,"tests":"all passed"}')
        result = check(str(self.project), str(self.out), json_files=['claim.json'])
        self.assertEqual(result['observation_verdict'], 'PASS')
        self.assertEqual(result['task_verdict'], 'UNKNOWN')
        self.assertFalse(result['complete'])

    def test_missing_and_invalid_json_are_negative(self):
        for index, (path, body) in enumerate([('missing', None), ('bad.json', 'not json')]):
            with self.subTest(path=path):
                if body:
                    (self.project / path).write_text(body)
                result = check(str(self.project), str(self.base / f'out{index}'), json_files=[path])
                self.assertEqual(result['observation_verdict'], 'UNKNOWN' if body is None else 'FAIL')
                self.assertFalse(result['complete'])

    def test_invalid_selection_has_no_writes(self):
        for paths in ([], ['../outside'], ['/etc/passwd'], ['x', 'x']):
            with self.subTest(paths=paths), self.assertRaises(ValueError):
                check(str(self.project), str(self.out), files=paths)
        self.assertEqual(list(self.project.iterdir()), [])
        self.assertFalse(self.out.exists())

    def test_symlink_target_not_followed(self):
        (self.base / 'outside').write_text('private')
        (self.project / 'link').symlink_to(self.base / 'outside')
        result = check(str(self.project), str(self.out), files=['link'])
        self.assertNotEqual(result['observation_verdict'], 'PASS')
        self.assertNotIn('private', (self.out / 'report.json').read_text())

    def test_install_idempotent_uninstall_preserves_user_config(self):
        for tool, folder in [('codex', '.agents'), ('claude', '.claude')]:
            with self.subTest(tool=tool):
                config = self.project / folder
                config.mkdir()
                (config / 'settings.json').write_text('user-owned')
                install(str(self.project), tool)
                target = config / 'skills' / 'agent-evidence'
                before = {name: (target / name).stat().st_mtime_ns for name in skill_files(tool)}
                install(str(self.project), tool)
                self.assertEqual(before, {name: (target / name).stat().st_mtime_ns for name in before})
                install(str(self.project), tool, uninstall=True)
                install(str(self.project), tool, uninstall=True)
                self.assertFalse(target.exists())
                self.assertEqual((config / 'settings.json').read_text(), 'user-owned')

    def test_changed_or_extra_installation_is_never_deleted(self):
        for tool, folder in [('codex', '.agents'), ('claude', '.claude')]:
            install(str(self.project), tool)
            target = self.project / folder / 'skills' / 'agent-evidence'
            (target / 'mine').write_text('keep')
            for uninstall in (False, True):
                with self.assertRaises(ValueError):
                    install(str(self.project), tool, uninstall=uninstall)
            self.assertTrue((target / 'SKILL.md').exists())
            (target / 'mine').unlink()
            (target / 'SKILL.md').write_text('user edited')
            with self.assertRaises(ValueError):
                install(str(self.project), tool, uninstall=True)
            self.assertEqual((target / 'SKILL.md').read_text(), 'user edited')

    def test_linked_config_refused_without_writes(self):
        outside = self.base / 'outside'
        outside.mkdir()
        (self.project / '.agents').symlink_to(outside)
        with self.assertRaises(OSError):
            install(str(self.project), 'codex')
        self.assertEqual(list(outside.iterdir()), [])

    def test_both_disable_implicit_invocation(self):
        self.assertIn(b'allow_implicit_invocation: false', skill_files('codex')['agents/openai.yaml'])
        self.assertIn(b'disable-model-invocation: true', skill_files('claude')['SKILL.md'])

    def test_cli_exit_contract(self):
        (self.project / 'present').write_text('real observation')
        self.assertEqual(main(['check', '--project', str(self.project), '--output', str(self.out),
                               '--file', 'present']), 1)
        self.assertEqual(main(['check', '--project', str(self.project), '--output', str(self.out)]), 2)

    def test_missing_uninstall_creates_nothing(self):
        install(str(self.project), 'codex', uninstall=True)
        install(str(self.project), 'claude', uninstall=True)
        self.assertEqual(list(self.project.iterdir()), [])

    def test_declared_commands_are_only_data(self):
        sentinel = self.base / 'must-not-exist'
        (self.project / 'commands.json').write_text(json.dumps({'command': f'touch {sentinel}'}))
        result = check(str(self.project), str(self.out), json_files=['commands.json'])
        self.assertEqual(result['observation_verdict'], 'PASS')
        self.assertFalse(sentinel.exists())
        self.assertEqual(result['task_verdict'], 'UNKNOWN')

    def test_hardlinked_skill_refused(self):
        install(str(self.project), 'claude')
        target = self.project / '.claude/skills/agent-evidence/SKILL.md'
        os.link(target, self.base / 'external-link')
        with self.assertRaises(ValueError):
            install(str(self.project), 'claude', uninstall=True)
        self.assertTrue(target.exists())

    def test_partial_skill_refused(self):
        install(str(self.project), 'codex')
        target = self.project / '.agents/skills/agent-evidence'
        (target / 'agents/openai.yaml').unlink()
        with self.assertRaises(ValueError):
            install(str(self.project), 'codex', uninstall=True)
        self.assertTrue((target / 'SKILL.md').exists())

    def test_helper_has_no_discovery_execution_or_fixture_shortcut(self):
        import ast
        import agent_evidence_integration.cli as integration
        source = Path(integration.__file__).read_text()
        for text in ('os.environ', 'expanduser', 'Path.home', 'subprocess', 'from .fixtures',
                     'import fixture', 'glob(', 'rglob('):
            self.assertNotIn(text, source)
        for node in ast.walk(ast.parse(source)):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
                self.assertNotIn(node.func.id, ('eval', 'exec', 'compile'))

    def test_existing_output_or_nested_output_refused(self):
        self.out.mkdir()
        for out in (self.out, self.project / 'nested'):
            with self.assertRaises(ValueError):
                check(str(self.project), str(out), files=['file'])
        self.assertEqual(list(self.project.iterdir()), [])
