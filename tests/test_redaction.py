import unittest
from epicbyte.storage import clean


class RedactionTests(unittest.TestCase):
    def test_task_ids_are_not_redacted(self):
        self.assertEqual(clean('TASK-001 aprovada; depende de TASK-002 e DESK-9'), 'TASK-001 aprovada; depende de TASK-002 e DESK-9')

    def test_real_secrets_are_redacted(self):
        self.assertNotIn('abcdefghijklmnop1234', clean('chave sk-ant-abcdefghijklmnop1234 usada'))
        self.assertNotIn('xyz', clean('Authorization: Bearer xyz'))
        self.assertEqual(clean({'api_key': 'segredo'}), {'api_key': '[REDACTED]'})


if __name__ == '__main__':
    unittest.main()
