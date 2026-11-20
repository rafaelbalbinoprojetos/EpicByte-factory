"""Ensaio da fábrica: missão web completa com agentes simulados e verificações reais.

Rode antes de qualquer missão real depois de mudar o motor:
    python scripts/rehearsal.py
"""
import os
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.chdir(ROOT)
import epicbyte  # noqa: E402,F401  (ferramentas no PATH)

os.environ['EPICBYTE_REHEARSAL'] = '1'
suite = unittest.defaultTestLoader.loadTestsFromName('tests.test_rehearsal_web')
result = unittest.TextTestRunner(verbosity=2).run(suite)
raise SystemExit(0 if result.wasSuccessful() else 1)
