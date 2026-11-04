"""Preload once per persistent worker. Linux fork workers inherit the model.

Windows uses a supervised SimpleWorker with a hard process deadline because
RQ's SpawnWorker relies on os.wait4 in the installed version. A timeout exits
the child; Postgres lease recovery redelivers safely and the supervisor restarts.
"""
import os
import subprocess
import sys
import threading
from redis import Redis
from rq import Worker, SimpleWorker
from rq.timeouts import BaseDeathPenalty
from app.config import settings
from app.predictor import predictor


class ProcessDeadline(BaseDeathPenalty):
    def setup_death_penalty(self):
        self.timer=threading.Timer(self._timeout,lambda:os._exit(124))
        self.timer.daemon=True
        self.timer.start()

    def cancel_death_penalty(self):
        self.timer.cancel()


class WindowsWorker(SimpleWorker):
    death_penalty_class=ProcessDeadline


def main():
    import logging
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    if settings().lease_seconds<=settings().job_timeout:
        raise ValueError('LEASE_SECONDS must exceed JOB_TIMEOUT')
    if os.name=='nt' and '--child' not in sys.argv:
        while True:
            result=subprocess.call([sys.executable,'-m','app.worker','--child'])
            if result==0:
                return
            import time
            time.sleep(1)
    else:
        predictor()
        cls=WindowsWorker if os.name=='nt' else Worker
        cls(['tickets'],connection=Redis.from_url(settings().redis_url)).work()


if __name__=='__main__':
    main()
