#!/usr/bin/env python3
"""Run a persistent, loopback-only SQLite rehearsal; never touches an external database."""
import os
import secrets
import signal
import socket
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

ROOT=Path(__file__).resolve().parent
RUNTIME=ROOT/'.runtime'
children=[]

def run(args,cwd,env=None):
    subprocess.run([str(a) for a in args],cwd=cwd,env=env,check=True)

def stop(*_):
    for child in reversed(children):
        if child.poll() is None: child.terminate()
    for child in reversed(children):
        try: child.wait(timeout=8)
        except subprocess.TimeoutExpired: child.kill();child.wait()

def main():
    for port in (8000,5173):
        with socket.socket() as sock:
            try:sock.bind(('127.0.0.1',port))
            except OSError:raise SystemExit(f'Port {port} is already in use. Stop the existing preview before launching another.')
    RUNTIME.mkdir(mode=0o700,exist_ok=True)
    python=os.environ.get('PARKRECEIPT_PYTHON')
    if not python:
        python=RUNTIME/'venv'/'bin'/'python'
        if not python.exists():run([sys.executable,'-m','venv',RUNTIME/'venv'],ROOT)
        requirements=ROOT/'backend'/'requirements.txt'
        marker=RUNTIME/'requirements.installed'
        if not marker.exists() or marker.read_text()!=requirements.read_text():
            run([python,'-m','pip','install','-r',requirements],ROOT)
            marker.write_text(requirements.read_text())
    if not (ROOT/'frontend'/'node_modules'/'vite').exists():run(['npm','ci'],ROOT/'frontend')
    password_file=RUNTIME/'login-password.txt'
    if not password_file.exists():
        fd=os.open(password_file,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
        with os.fdopen(fd,'w') as f:f.write(secrets.token_urlsafe(18))
    password=password_file.read_text().strip()
    env={**os.environ,'DATABASE_URL':'sqlite:///'+str(RUNTIME/'rehearsal.db'),'SEED_PASSWORD':password,'PAYMENT_MODE':'demo','APP_ORIGIN':'http://localhost:5173','COOKIE_SECURE':'false'}
    run([python,'-m','alembic','upgrade','head'],ROOT/'backend',env)
    run([python,'-m','app.seed'],ROOT/'backend',env)
    children.append(subprocess.Popen([str(python),'-m','uvicorn','app.main:app','--host','127.0.0.1','--port','8000','--no-access-log'],cwd=ROOT/'backend',env=env))
    children.append(subprocess.Popen(['npm','run','dev','--','--port','5173','--strictPort'],cwd=ROOT/'frontend'))
    for _ in range(60):
        if any(c.poll() is not None for c in children):raise RuntimeError('A server stopped during startup. Read the error above.')
        try:
            with urllib.request.urlopen('http://localhost:5173/api/locations',timeout=1) as res:
                if res.status==200:break
        except Exception:time.sleep(.5)
    else:raise RuntimeError('Preview did not become ready.')
    print('\nParkReceipt is ready: http://localhost:5173/',flush=True)
    print('Accounts: owner, staff-a, staff-b, staff-c',flush=True)
    print(f'Local rehearsal password: {password}',flush=True)
    print('Data persists in .runtime/rehearsal.db. Online payments are simulated.\nPress Ctrl+C to stop both servers.',flush=True)
    while all(c.poll() is None for c in children):time.sleep(1)
    raise RuntimeError('A server stopped; shutting down the preview.')

if __name__=='__main__':
    signal.signal(signal.SIGTERM,lambda *_:sys.exit(0))
    try:main()
    except KeyboardInterrupt:pass
    except (RuntimeError,subprocess.CalledProcessError) as e:print(str(e),file=sys.stderr);sys.exit(1)
    finally:stop()
