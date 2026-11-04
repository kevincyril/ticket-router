"""Group connected near duplicates before a deterministic group-disjoint split.

Grouping representation is a stateless HashingVectorizer; no vocabulary or IDF
is fitted on validation/test. This is a split hygiene step, not model training.
"""
import json
import re
import unicodedata
from pathlib import Path
import numpy as np
import pandas as pd
from sklearn.feature_extraction.text import HashingVectorizer
from sklearn.neighbors import NearestNeighbors
from sklearn.model_selection import StratifiedGroupKFold
from ml.common import SEED, save, sha


def normalize(text):
    text = unicodedata.normalize('NFKC', text).lower()
    text = re.sub(r'\{\{.*?\}\}|\b\d+\b', ' placeholder ', text)
    return ' '.join(re.findall(r'[a-z]+', text))


def prepare():
    frame = pd.read_csv('data/raw/dataset.csv').rename(columns={'instruction':'text', 'category':'label'})
    frame['normalized'] = frame.text.map(normalize)
    frame['source_row'] = np.arange(len(frame))
    # Ambiguous exact texts with conflicting labels are excluded entirely.
    conflicts = frame.groupby('normalized').label.nunique()
    frame = frame[~frame.normalized.isin(conflicts[conflicts > 1].index)]
    frame = frame.drop_duplicates('normalized').reset_index(drop=True)
    parent = np.arange(len(frame))

    def find(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    def union(a,b):
        a,b = find(a),find(b)
        if a != b:
            parent[max(a,b)] = min(a,b)

    # Character similarity captures slot, spelling and close template variants.
    vectorizer = HashingVectorizer(analyzer='char_wb', ngram_range=(3,5), n_features=2**18, alternate_sign=False)
    vectors = vectorizer.transform(frame.normalized)
    neighbors = NearestNeighbors(metric='cosine', algorithm='brute', radius=.15, n_jobs=2).fit(vectors)
    for start in range(0, len(frame), 128):
        for offset, matches in enumerate(neighbors.radius_neighbors(vectors[start:start+128], return_distance=False)):
            for other in matches:
                union(start+offset, int(other))
    frame['group'] = [find(i) for i in range(len(frame))]
    # Five group folds: 60% train / 20% validation / 20% test (approximately).
    fold = np.empty(len(frame), dtype=int)
    for n, (_, indices) in enumerate(StratifiedGroupKFold(5, shuffle=True, random_state=SEED).split(frame, frame.label, frame.group)):
        fold[indices] = n
    frame['split'] = np.where(fold == 0, 'test', np.where(fold == 1, 'validation', 'train'))
    root = Path('data/prepared')
    root.mkdir(parents=True, exist_ok=True)
    frame.to_json(root / 'samples.jsonl', orient='records', lines=True)
    manifest = {'seed':SEED, 'raw_sha256':sha('data/raw/dataset.csv'), 'prepared_sha256':sha(root/'samples.jsonl'),
                'source':json.loads(Path('data/raw/source.json').read_text(encoding='utf-8-sig')),
                'dedup': 'NFKC lowercase punctuation/slot normalization; exclude label conflicts; deduplicate exact; connected components of char 3-5 cosine >= .85',
                'raw_count':len(pd.read_csv('data/raw/dataset.csv')), 'retained':len(frame),
                'groups':int(frame.group.nunique()), 'largest_group':int(frame.groupby('group').size().max()),
                'counts':frame.groupby(['split','label']).size().unstack(fill_value=0).to_dict(orient='index'),
                'rows':frame[['source_row','group','split']].to_dict(orient='records')}
    save(root/'manifest.json', manifest)
    save('artifacts/split-manifest.json', manifest)
    save('artifacts/split-summary.json', {k:v for k,v in manifest.items() if k!='rows'})
    for label in frame.label.unique():
        assert set(frame[frame.label == label].split) == {'train','validation','test'}, label
    assert frame.groupby('group').split.nunique().max() == 1
    print(json.dumps({k:v for k,v in manifest.items() if k not in ('rows','counts')}, indent=2))


if __name__ == '__main__':
    prepare()
