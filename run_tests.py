import pathlib
import subprocess
import sys

root = pathlib.Path(__file__).resolve().parent
compile_targets = [str(x) for folder in ('src', 'scripts', 'tools') for x in (root / folder).glob('*.py')]
result = subprocess.run([sys.executable, '-m', 'py_compile', *compile_targets])
if result.returncode:
    raise SystemExit(result.returncode)
result = subprocess.run([sys.executable, '-m', 'unittest', 'discover', '-s', str(root / 'tests'), '-v'], cwd=root)
raise SystemExit(result.returncode)
