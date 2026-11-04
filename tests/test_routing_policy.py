import hashlib,json
from pathlib import Path
import numpy as np
import pytest
from app.routing_policy import calibrated,decisions,clauses,review_reasons


def evidence(**overrides):
    result={'confidence':np.array([.99]),'margin':np.array([.9]),'similarity':np.array([.8]),'neighbor_agreement':np.array([True]),'conflict':np.array([False])}
    for key,value in overrides.items():result[key]=np.array([value])
    return result

POLICY={'confidence':.65,'margin':0,'similarity':.4,'require_neighbor_agreement':True}


@pytest.mark.parametrize('change,reason',[
    ({'similarity':.1},'insufficient_training_support'),
    ({'neighbor_agreement':False},'nearest_example_disagrees'),
    ({'conflict':True},'conflicting_clause_predictions'),
    ({'confidence':.6},'low_confidence')])
def test_high_score_is_insufficient_for_routing(change,reason):
    values=evidence(**change)
    assert not decisions(values,POLICY)[0]
    assert reason in review_reasons(values,POLICY)


def test_calibration_does_not_prove_support():
    p=calibrated(np.array([[.7,.2,.1]]),.5)
    assert p.argmax()==0 and p.max()>.7
    assert not decisions(evidence(confidence=float(p.max()),similarity=.1),POLICY)[0]


def test_clause_splitting_is_general():
    assert len(clauses('Please correct the invoice; also change the delivery address.'))==2
    assert len(clauses('Please correct the invoice.'))==1


def test_frozen_challenge_integrity_and_development_exclusion():
    root=Path('data/challenge')
    manifest=json.loads((root/'manifest.json').read_text(encoding='utf-8'))
    sets={}
    for split,info in manifest['splits'].items():
        raw=(root/f'{split}.jsonl').read_bytes()
        assert hashlib.sha256(raw).hexdigest()==info['sha256']
        rows=[json.loads(line) for line in raw.decode().splitlines()]
        assert len(rows)==info['count']
        sets[split]={r['text'] for r in rows}
        assert not sets[split].intersection(manifest['development_cases_excluded'])
    assert not sets['test'].intersection(sets['validation'])


def test_serving_candidate_matches_frozen_offline_decisions():
    # Optional trained-artifact regression check; CI requires no model download.
    root=Path('artifacts/robustness')
    if not (root/'deployed/model.joblib').exists():pytest.skip('Trained local artifact unavailable')
    from app.predictor import Predictor
    model=Predictor(root/'deployed')
    report=json.loads((root/'results.json').read_text(encoding='utf-8'))
    for row in report['results']['improved_gated']['rows']:
        actual=model.assess(row['text'])
        assert actual['auto_route']==row['auto_routed']
        assert actual['category']==row['predicted_category']
        assert actual['confidence']==pytest.approx(row['confidence'])
