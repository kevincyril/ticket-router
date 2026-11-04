"""Download source, provenance and unmodified CDLA license at an immutable commit."""
import json
import urllib.request
from pathlib import Path
from ml.common import save, sha

REPO = 'bitext/customer-support-llm-chatbot-training-dataset'


def fetch(url):
    request = urllib.request.Request(url, headers={'User-Agent': 'ticket-router-portfolio/1.0'})
    return urllib.request.urlopen(request, timeout=120).read()


def main():
    root = Path('data/raw')
    root.mkdir(parents=True, exist_ok=True)
    pinned = root / 'source.json'
    revision = json.loads(pinned.read_text(encoding='utf-8-sig'))['revision'] if pinned.exists() else json.loads(Path('config/training.json').read_text(encoding='utf-8-sig'))['dataset_revision']
    files = json.loads(fetch(f'https://api.github.com/repos/{REPO}/git/trees/{revision}?recursive=1'))['tree']
    candidates = [f['path'] for f in files if f['path'].endswith('.csv')]
    if len(candidates) != 1:
        raise ValueError(f'Expected one CSV: {candidates}')
    source = candidates[0]
    for remote, local in [(source, 'dataset.csv'), ('LICENSE.txt', 'LICENSE.txt'), ('README.md', 'README.md')]:
        (root / local).write_bytes(fetch(f'https://raw.githubusercontent.com/{REPO}/{revision}/{remote}'))
    license_text = (root / 'LICENSE.txt').read_text(encoding='utf-8')
    assert 'Community Data License Agreement' in license_text and 'Sharing' in license_text
    save(pinned, {'provider': 'Bitext', 'repository': f'https://github.com/{REPO}', 'revision': revision,
                  'file': source, 'sha256': sha(root / 'dataset.csv'), 'license': 'CDLA-Sharing-1.0'})
    Path('docs/DATA_LICENSE.txt').write_bytes((root / 'LICENSE.txt').read_bytes())
    save('artifacts/dataset-source.json', json.loads(pinned.read_text(encoding='utf-8-sig')))
    print(pinned.read_text(encoding='utf-8-sig'))


if __name__ == '__main__':
    main()
