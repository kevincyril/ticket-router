"""Single-instance free demo: supervised API + dispatcher + real RQ worker.

PostgreSQL and Redis remain managed services. If any child exits, recycle the
whole instance so the host restarts a consistent process group. No training.
"""
import json
import os
import signal
import subprocess
import sys
import time


def commands(port):
    return {
      'worker':[sys.executable,'-m','app.worker'],
      'dispatcher':[sys.executable,'-m','app.jobs'],
      'api':[sys.executable,'-m','uvicorn','app.main:app','--host','0.0.0.0','--port',str(port)]}


def main():
    if os.name=='nt':raise SystemExit('Use scripts/start-local.ps1 on Windows')
    from app.config import settings
    if not settings().demo_mode or settings().auto_routing_enabled:
        raise SystemExit('Hosted free demo requires DEMO_MODE=true and AUTO_ROUTING_ENABLED=false')
    # Managed services may take a short time to become available at first launch.
    for attempt in range(12):
        result=subprocess.run([sys.executable,'-m','alembic','upgrade','head'])
        if result.returncode==0:break
        time.sleep(5)
    else:raise SystemExit('Database migration could not complete')
    from redis import Redis
    for attempt in range(12):
        try:
            Redis.from_url(settings().redis_url,socket_connect_timeout=2,socket_timeout=2).ping()
            break
        except Exception:time.sleep(5)
    else:raise SystemExit('Redis could not become ready')
    children={}
    stopping=False
    def shutdown(signum,frame):
        nonlocal stopping
        stopping=True
    signal.signal(signal.SIGTERM,shutdown)
    signal.signal(signal.SIGINT,shutdown)
    exit_code=0
    try:
        for role,command in commands(int(os.environ.get('PORT','8000'))).items():
            children[role]=subprocess.Popen(command,start_new_session=True)
            print(json.dumps({'event':'process_started','role':role}),flush=True)
        while not stopping:
            for role,child in children.items():
                if child.poll() is not None:
                    print(json.dumps({'event':'process_exited','role':role,'code':child.returncode}),flush=True)
                    stopping=True;exit_code=1
                    break
            time.sleep(.5)
    finally:
        for child in children.values():
            if child.poll() is None:
                try:os.killpg(child.pid,signal.SIGTERM)
                except ProcessLookupError:pass
        deadline=time.monotonic()+15
        while any(p.poll() is None for p in children.values()) and time.monotonic()<deadline:time.sleep(.1)
        for child in children.values():
            try:os.killpg(child.pid,signal.SIGKILL)
            except ProcessLookupError:pass
    raise SystemExit(exit_code)


if __name__=='__main__':main()
