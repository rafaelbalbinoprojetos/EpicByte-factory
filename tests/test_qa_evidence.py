import unittest
from types import SimpleNamespace
from epicbyte.engine import test_evidence as evidence


def cmd(text, code):
    return {'type': 'commandExecution', 'status': 'completed', 'command': text, 'exitCode': code}


class QaEvidenceTests(unittest.TestCase):
    def test_requires_a_successful_command(self):
        self.assertFalse(evidence(SimpleNamespace(commands=[])))
        self.assertFalse(evidence(SimpleNamespace(commands=[cmd('python -m unittest', 1)])))
        self.assertTrue(evidence(SimpleNamespace(commands=[cmd('python -m unittest', 0)])))

    def test_undeclared_failure_rejects(self):
        r = SimpleNamespace(commands=[cmd('python -B - < qa.py', 0), cmd('python -B -m unittest discover -v', 1)])
        self.assertFalse(evidence(r, {}))

    def test_declared_out_of_scope_failure_is_tolerated(self):
        r = SimpleNamespace(commands=[cmd('python -B - < qa.py', 0), cmd('python -B -m unittest discover -v', 1)])
        rep = {'fora_do_escopo': [{'comando': 'unittest discover', 'motivo': 'test_conversor.py é da TASK-003'}]}
        self.assertTrue(evidence(r, rep))

    def test_declaration_needs_reason_and_real_match(self):
        r = SimpleNamespace(commands=[cmd('python ok.py', 0), cmd('python -m unittest discover', 1)])
        self.assertFalse(evidence(r, {'fora_do_escopo': [{'comando': 'unittest discover', 'motivo': ''}]}))
        self.assertFalse(evidence(r, {'fora_do_escopo': [{'comando': 'pytest -q', 'motivo': 'x'}]}))
        self.assertFalse(evidence(r, {'fora_do_escopo': [{'comando': 'py', 'motivo': 'curto demais'}]}))
        self.assertFalse(evidence(r, {'fora_do_escopo': 'unittest discover'}))


if __name__ == '__main__':
    unittest.main()
