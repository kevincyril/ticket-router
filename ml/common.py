import hashlib
import json
import platform
import sys
from pathlib import Path

SEED = 42
ROOT = Path(__file__).resolve().parents[1]


def save(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False), encoding='utf-8')


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def environment():
    import importlib.metadata
    import psutil
    return {'python': sys.version, 'platform': platform.platform(), 'cpu': platform.processor(),
            'logical_cpus': psutil.cpu_count(), 'ram_gb': round(psutil.virtual_memory().total/2**30, 2),
            'packages': {p: importlib.metadata.version(p) for p in ['numpy','scikit-learn','torch','transformers']}}
