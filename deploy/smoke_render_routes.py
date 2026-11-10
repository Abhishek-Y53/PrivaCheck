"""No-database smoke test for Render-hosted routes and legacy local routes.

Run from repo root after installing requirements-web.txt and creating a dummy
frontend_dist/index.html plus frontend_dist/assets/. CI does these steps.
"""
from __future__ import annotations

import os
import subprocess
import sys

SMOKE = r"""
from fastapi.testclient import TestClient
from backend.api.main import app
client = TestClient(app, follow_redirects=False)
assert client.get('/healthz').status_code == 200
if __import__('os').environ.get('PRIVACHECK_SERVE_FRONTEND') == '1':
    assert 'PrivaCheck SPA smoke test' in client.get('/').text
    assert 'PrivaCheck SPA smoke test' in client.get('/scans').text
    assert 'PrivaCheck SPA smoke test' in client.get('/admin').text
    assert client.get('/api/auth/csrf').status_code == 200
    assert client.get('/api/scans').status_code == 401
    assert client.get('/auth/google/callback').status_code == 303
    assert client.get('/api/bogus').status_code == 404
    assert client.get('/no-such-file.js').status_code == 404
else:
    assert client.get('/').json()['status'] == 'ok'
    assert client.get('/auth/csrf').status_code == 200
    assert client.get('/scans').status_code == 401
print('Smoke routes OK')
"""
for hosted in ('', '1'):
    env = os.environ.copy()
    if hosted:
        env['PRIVACHECK_SERVE_FRONTEND'] = hosted
    else:
        env.pop('PRIVACHECK_SERVE_FRONTEND', None)
    result = subprocess.run([sys.executable, '-c', SMOKE], env=env, check=False)
    if result.returncode:
        raise SystemExit(result.returncode)
