import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from epicbyte.api import fixed_password


class FixedPasswordTests(unittest.TestCase):
    def test_random_when_not_configured(self):
        with tempfile.TemporaryDirectory() as d, patch.dict(os.environ, {'EPICBYTE_PASSWORD': ''}):
            self.assertIsNone(fixed_password(d))

    def test_file_and_env(self):
        with tempfile.TemporaryDirectory() as d:
            (Path(d) / '.factory').mkdir()
            (Path(d) / '.factory' / 'senha.txt').write_text(' 1234abcd\n', encoding='utf-8')
            with patch.dict(os.environ, {'EPICBYTE_PASSWORD': ''}):
                self.assertEqual(fixed_password(d), '1234abcd')
            with patch.dict(os.environ, {'EPICBYTE_PASSWORD': 'env-vence'}):
                self.assertEqual(fixed_password(d), 'env-vence')


if __name__ == '__main__':
    unittest.main()
