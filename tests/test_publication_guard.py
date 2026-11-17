import ast
from pathlib import Path
import unittest
import agent_evidence
from agent_evidence.revisions import MODULES


class PublicationGuard(unittest.TestCase):
    def test_runtime_has_no_environment_discovery_or_dynamic_execution(self):
        root=Path(agent_evidence.__file__).parent
        forbidden={'eval','exec','compile','getenv','expanduser'}
        for module in MODULES:
            path=root/(module+'.py'); source=path.read_text(); tree=ast.parse(source)
            with self.subTest(module=module):
                self.assertNotIn('os.environ',source)
                self.assertNotIn('sys.path',source)
                self.assertNotIn('/Users/',source)
                self.assertNotIn('HERMES_HOME',source)
                for node in ast.walk(tree):
                    if isinstance(node,ast.Call):
                        name=node.func.id if isinstance(node.func,ast.Name) else node.func.attr if isinstance(node.func,ast.Attribute) else ''
                        self.assertNotIn(name,forbidden)
                        self.assertFalse(name=='home' and isinstance(node.func,ast.Attribute))
