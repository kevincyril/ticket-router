"""Freeze serving bundle from validation selection, before test evaluation."""
import json,shutil
from pathlib import Path
from ml.common import save,sha
root=Path('artifacts/robustness')
selection=json.loads((root/'selection.json').read_text(encoding='utf-8'))
name=selection['selected']
if name=='transformer':raise SystemExit('Transformer selected; implement transformer serving before deployment')
source=root/'candidate' if name=='improved' else Path('artifacts/baseline')
target=root/'deployed';target.mkdir(exist_ok=True)
shutil.copyfile(source/'model.joblib',target/'model.joblib')
shutil.copyfile(root/'support.joblib',target/'support.joblib')
chosen=selection['candidates'][name]
metadata={'version':'robust-'+sha(target/'model.joblib')[:12]+'-'+sha(root/'selection.json')[:8],
 'kind':'balanced-word-char-logistic-regression' if name=='improved' else 'tfidf-logistic-regression',
 'display_name':'Balanced word + character classifier' if name=='improved' else 'TF-IDF + logistic regression',
 'labels':json.loads((source/'metadata.json').read_text(encoding='utf-8-sig'))['labels'],
 'threshold':chosen['policy']['confidence'],'temperature':chosen['temperature'],'routing_policy':chosen['policy'],
 'selection_sha256':sha(root/'selection.json'),'training_data_sha256':sha('data/prepared/samples.jsonl'),
 'artifact_sha256':sha(target/'model.joblib'),'support_sha256':sha(target/'support.joblib'),
 'confidence_meaning':'Temperature-scaled class probability conditional on supported single intent; not probability of safe routing.',
 'thresholds_chosen_using_validation_only':True}
save(target/'metadata.json',metadata)
print(json.dumps(metadata,indent=2))
