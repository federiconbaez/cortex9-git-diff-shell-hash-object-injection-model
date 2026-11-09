"""Test runner: fails on any failure, error, skip, or if no test ran."""
import sys
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "src"))

suite = unittest.defaultTestLoader.discover(str(HERE), pattern="test_*.py")
result = unittest.TextTestRunner(verbosity=2).run(suite)
n = result.testsRun
bad = len(result.failures) + len(result.errors) + len(result.skipped) + len(result.unexpectedSuccesses)
print(f"SUMMARY ran={n} failures={len(result.failures)} errors={len(result.errors)} "
      f"skipped={len(result.skipped)}")
sys.exit(0 if n > 0 and bad == 0 else 1)
