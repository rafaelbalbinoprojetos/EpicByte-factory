"""Reproducible local checks, never starts a live Codex mission when authenticated."""
import json
import os
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def main():
    env = {**os.environ, 'PYTHONIOENCODING': 'utf-8'}
    results = []
    def run(*args):
        command = [sys.executable, *args]
        result = subprocess.run(command, cwd=ROOT, env=env, capture_output=True, text=True, encoding='utf-8', timeout=60)
        results.append({'command': command, 'exit_code': result.returncode, 'stdout': result.stdout, 'stderr': result.stderr})
        return result
    suite = run('-m', 'unittest', 'discover', '-s', 'tests', '-v')
    health = run('factory.py', 'doctor', '--probe')
    dry = run('factory.py', 'dry-run', 'missions/mission_001.md', '--plan', 'missions/mission_001_plan.json')
    info = json.loads(health.stdout)
    blocked_run = None
    if not info['authenticated']:
        blocked_run = run('factory.py', 'run', 'missions/mission_001.md', '--plan', 'missions/mission_001_plan.json')
        ident = blocked_run.stdout.splitlines()[0].split(': ', 1)[1]
        run('factory.py', 'status', ident)
        run('factory.py', 'logs', ident)
        run('factory.py', 'pause', ident)
        run('factory.py', 'status', ident)
    run('factory.py', 'agents')
    api_results = {}
    process = None
    try:
        with socket.socket() as sock:
            sock.bind(('127.0.0.1', 0))
            port = sock.getsockname()[1]
        process = subprocess.Popen([sys.executable, 'factory.py', 'serve', '--port', str(port)], cwd=ROOT, env=env,
                                   stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, encoding='utf-8')
        client = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        deadline = time.monotonic() + 8
        while True:
            try:
                with client.open(f'http://127.0.0.1:{port}/missions', timeout=1) as response:
                    api_results['GET /missions'] = response.status
                    api_results['json_valid'] = isinstance(json.loads(response.read()), list)
                break
            except (urllib.error.URLError, TimeoutError):
                if process.poll() is not None or time.monotonic() >= deadline:
                    raise RuntimeError('API não iniciou')
                time.sleep(.1)
        request = urllib.request.Request(f'http://127.0.0.1:{port}/missions', headers={'Origin': 'https://example.invalid'})
        try:
            client.open(request, timeout=2)
        except urllib.error.HTTPError as error:
            api_results['cross_origin_status'] = error.code
        request = urllib.request.Request(f'http://127.0.0.1:{port}/missions', headers={'Host': 'attacker.invalid'})
        try:
            client.open(request, timeout=2)
        except urllib.error.HTTPError as error:
            api_results['untrusted_host_status'] = error.code
    except (OSError, RuntimeError) as error:
        api_results['error'] = str(error)
    finally:
        if process is not None:
            process.terminate()
            process.communicate(timeout=5)
    passed = suite.returncode == 0 and dry.returncode == 0 and api_results.get('GET /missions') == 200 and api_results.get('cross_origin_status') == 403 and api_results.get('untrusted_host_status') == 403
    report = {'timestamp': datetime.now(timezone.utc).isoformat(), 'local_checks_passed': passed,
              'live_codex_mission_executed': False, 'results': results, 'api': api_results,
              'limitations': ['Escrita de agentes bloqueada sem backend certificado', 'Resultados de orquestração da suíte usam mocks, sem consumo de cota']}
    target = ROOT / 'logs/factory_validation.json'
    target.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps({'report': str(target), 'local_checks_passed': passed, 'api': api_results}, ensure_ascii=False, indent=2))
    return 0 if passed else 1


if __name__ == '__main__':
    raise SystemExit(main())
