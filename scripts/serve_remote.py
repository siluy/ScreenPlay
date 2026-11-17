"""Run the study service and its existing Cloudflare connector together."""
import argparse
import json
import os
from pathlib import Path
import shutil
import shlex
import signal
import socket
import sqlite3
import subprocess
import sys
import time
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[1]


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--origin', default='https://study.example.org')
    p.add_argument('--data', type=Path, default=ROOT/'runs/my-study')
    p.add_argument('--token-file', type=Path, default=ROOT/'.cache/cloudflare/tunnel-token.txt')
    p.add_argument('--cloudflared', type=Path)
    p.add_argument('--stop', action='store_true', help='Stop this project\'s recorded service when no participant is answering')
    args = p.parse_args()
    folder = ROOT/'.cache/cloudflare'
    if args.stop:
        record = json.loads((folder/'remote-runtime.json').read_text())
        command = subprocess.check_output(['ps','-p',str(record['supervisor_pid']),'-o','command='],text=True).strip()
        if shlex.split(command) != record['command']:
            p.error('Recorded process no longer matches this service; nothing was stopped')
        with sqlite3.connect(Path(record['data'])/'study.sqlite3') as db:
            if db.execute("SELECT COUNT(*) FROM attempts WHERE status IN ('starting','active','paused')").fetchone()[0]:
                p.error('A participant is still answering; wait for the attempt to finish')
        os.kill(record['supervisor_pid'],signal.SIGTERM)
        print('Stop requested; study data is retained.')
        return
    origin = urlsplit(args.origin)
    if origin.scheme != 'https' or not origin.hostname or origin.path or origin.query or origin.fragment or origin.username:
        p.error('Use an exact HTTPS origin, without a path')
    binary = args.cloudflared or (ROOT/'.tools/cloudflared/2026.10.5/cloudflared')
    if not Path(binary).is_file(): binary = shutil.which('cloudflared')
    if not binary or not args.token_file.is_file(): p.error('The Cloudflare connector and private tunnel token file must be configured first')
    with socket.socket() as sock:
        if sock.connect_ex(('127.0.0.1',8790)) == 0:
            p.error('Port 8790 is already served. Stop the existing study service first, when nobody is answering.')
    folder.mkdir(parents=True, exist_ok=True, mode=0o700)
    children=[]
    def stop(*_): raise KeyboardInterrupt
    signal.signal(signal.SIGTERM,stop)
    signal.signal(signal.SIGINT,stop)
    try:
        server=subprocess.Popen([sys.executable,'-m','screenplay_human','serve','--data',str(args.data.resolve()),'--port','8790','--public-origin',args.origin,'--trusted-proxy'],cwd=ROOT)
        children.append(server)
        deadline=time.monotonic()+10
        while time.monotonic()<deadline:
            if server.poll() is not None: raise RuntimeError('Study service did not start')
            try:
                with socket.create_connection(('127.0.0.1',8790),timeout=.3): break
            except OSError: time.sleep(.2)
        else: raise RuntimeError('Study service startup timed out')
        connector=subprocess.Popen([str(binary),'tunnel','--no-autoupdate','--loglevel','info','--logfile',str(folder/'tunnel.log'),'run','--token-file',str(args.token_file.resolve())],cwd=ROOT)
        children.append(connector)
        if sys.platform=='darwin':
            children.append(subprocess.Popen(['/usr/bin/caffeinate','-i','-s','-w',str(os.getpid())]))
        command=shlex.split(subprocess.check_output(['ps','-p',str(os.getpid()),'-o','command='],text=True).strip())
        record={'supervisor_pid':os.getpid(),'server_pid':server.pid,'connector_pid':connector.pid,'origin':args.origin,'data':str(args.data.resolve()),'started_at':time.time(),'command':command}
        (folder/'remote-runtime.json').write_text(json.dumps(record,indent=2)+'\n')
        print(json.dumps({'participant_url':args.origin,'local_admin':'http://127.0.0.1:8790/admin','notice':'Keep this terminal open; Ctrl+C stops the study and connector.'}),flush=True)
        while server.poll() is None and connector.poll() is None: time.sleep(1)
        raise RuntimeError('A remote-study process exited; logs and study records have been retained')
    except KeyboardInterrupt:
        pass
    finally:
        for child in reversed(children):
            if child.poll() is None:
                child.terminate()
                try: child.wait(timeout=10)
                except subprocess.TimeoutExpired: child.kill();child.wait(timeout=3)


if __name__=='__main__': main()
