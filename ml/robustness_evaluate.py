"""Final held-out scoring. Never selects or changes thresholds/models."""
import json,time
from pathlib import Path
import joblib
import numpy as np
import pandas as pd
from sklearn.metrics import f1_score,accuracy_score
from sklearn.feature_extraction.text import HashingVectorizer
from app.routing_policy import calibrated,features,decisions
from app.predictor import Predictor
from ml.robustness_select import Models,ROOT,DEV,score,clause_conflicts
from ml.common import save,sha,environment
from ml.evaluate import calibration,latency


def main():
    selection_path=ROOT/'selection.json'
    frozen_sha=sha(selection_path)
    selection=json.loads(selection_path.read_text(encoding='utf-8'))
    bundle=json.loads((ROOT/'deployed/metadata.json').read_text(encoding='utf-8'))
    assert bundle['selection_sha256']==frozen_sha
    manifest=json.loads(Path('data/challenge/manifest.json').read_text(encoding='utf-8'))
    for split in ['validation','test']:
        assert sha(f'data/challenge/{split}.jsonl')==manifest['splits'][split]['sha256']
    rows=[json.loads(line) for line in Path('data/challenge/test.jsonl').read_text(encoding='utf-8').splitlines()]
    validation=[json.loads(line) for line in Path('data/challenge/validation.jsonl').read_text(encoding='utf-8').splitlines()]
    models=Models()
    support=joblib.load(ROOT/'support.joblib')
    data=pd.read_json('data/prepared/samples.jsonl',lines=True)
    source_test=data[data.split=='test'].reset_index(drop=True)
    results={'protocol':json.loads((ROOT/'protocol.json').read_text(encoding='utf-8')),'selection_sha256':frozen_sha,
       'selected':selection['selected'],'heldout_count':len(rows),'results':{},'historical_source_test_regression':{},
       'metric_definitions':{'confident_misrouting_count':'Automatically routed cases that are wrong-category or must-review. Counts unsafe routes, not merely high probability.',
        'high_confidence_wrong_count':'Probability >=0.8 while category wrong or request must-review; includes predictions that routing gates correctly reject.',
        'auto_accuracy':'Correct single supported category / all automatically routed cases. Any automated vague/mixed/OOD case counts as incorrect.',
        'coverage_denominator':'All 88 challenge requests, including required-review cases; maximum possible safe coverage is 48/88.'}}
    texts=[r['text'] for r in rows]
    for name in ['baseline','improved','transformer']:
        raw=models.predict(name,texts)
        chosen=selection['candidates'][name]
        probs=calibrated(raw,chosen['temperature'])
        evidence=features(texts,probs,support['vectorizer'],support['vectors'],support['labels'],models.labels)
        evidence['conflict']=clause_conflicts(models,name,texts,chosen['temperature'],support)
        for mode,predictions,accepted in [('legacy',raw,raw.max(axis=1)>=.5),('gated',probs,decisions(evidence,chosen['policy']))]:
            key=f'{name}_{mode}'
            item={'overall':score(rows,predictions,models.labels,accepted),'by_type':{},'rows':[]}
            for kind in ['paraphrase','vague','mixed','out_of_scope']:
                mask=np.array([r['kind']==kind for r in rows])
                item['by_type'][kind]=score([r for r in rows if r['kind']==kind],predictions[mask],models.labels,accepted[mask])
            for i,row in enumerate(rows):
                label=models.labels[int(predictions[i].argmax())]
                item['rows'].append({**row,'predicted_category':label,'confidence':float(predictions[i].max()),
                    'raw_confidence':float(raw[i].max()),'auto_routed':bool(accepted[i]),'nearest_similarity':float(evidence['similarity'][i]),
                    'neighbor_agreement':bool(evidence['neighbor_agreement'][i]),'clause_conflict':bool(evidence['conflict'][i])})
            clear=np.array([not r['must_review'] for r in rows])
            item['clear_calibration']=calibration([r['acceptable_labels'][0] for r in rows if not r['must_review']],predictions[clear],models.labels)
            results['results'][key]=item
            print(key,json.dumps(item['overall']),flush=True)
        source_raw=models.predict(name,source_test.text.tolist())
        source_probs=calibrated(source_raw,chosen['temperature'])
        source_evidence=features(source_test.text.tolist(),source_probs,support['vectorizer'],support['vectors'],support['labels'],models.labels)
        source_evidence['conflict']=clause_conflicts(models,name,source_test.text.tolist(),chosen['temperature'],support)
        source_accepted=decisions(source_evidence,chosen['policy'])
        source_prediction=np.array(models.labels)[source_probs.argmax(axis=1)]
        results['historical_source_test_regression'][name]={'note':'Original source test has been reported previously; regression check, not new independent evidence.',
            'macro_f1':float(f1_score(source_test.label,source_prediction,average='macro')),'accuracy':float(accuracy_score(source_test.label,source_prediction)),
            'auto_coverage':float(source_accepted.mean()),'auto_accuracy':float((source_prediction[source_accepted]==source_test.label.to_numpy()[source_accepted]).mean()) if source_accepted.any() else None,
            'calibration_before':calibration(source_test.label,source_raw,models.labels),'calibration_after':calibration(source_test.label,source_probs,models.labels)}
    predictor=Predictor(ROOT/'deployed')
    results['development']=[{'text':text,**predictor.assess(text)} for text in DEV]
    timings=[]
    for _ in range(3):predictor.assess(texts[0])
    for text in texts:
        timings.append(predictor.assess(text)['inference_ms'])
    results['deployed_latency']={'count':len(timings),'median_ms':float(np.median(timings)),'p95_ms':float(np.percentile(timings,95)),
        'includes':'word/char classification, temperature scaling, train-example support lookup, clause conflict checks','command':'python -m ml.robustness_evaluate'}
    from ml.prepare import normalize
    train=data[data.split=='train']
    normalized_train=set(train.text.map(normalize))
    normalized_val={normalize(r['text']) for r in validation}
    results['overlap_audit']={'exact_normalized_training_overlaps':[r['id'] for r in rows if normalize(r['text']) in normalized_train],
       'exact_normalized_challenge_validation_overlaps':[r['id'] for r in rows if normalize(r['text']) in normalized_val],
       'development_exact_overlap':[r['id'] for r in rows if normalize(r['text']) in {normalize(t) for t in DEV}]}
    hashing=HashingVectorizer(analyzer='char_wb',ngram_range=(3,5),n_features=2**18,alternate_sign=False)
    near=(hashing.transform(texts)@hashing.transform([r['text'] for r in validation]).T).toarray().max(axis=1)
    results['overlap_audit']['char_similarity_085_to_challenge_validation']=[{'id':rows[i]['id'],'similarity':float(v)} for i,v in enumerate(near) if v>=.85]
    results['environment']=environment()
    assert sha(selection_path)==frozen_sha
    save(ROOT/'results.json',results)
    print('development',json.dumps(results['development'],indent=2),flush=True)
    print('latency',results['deployed_latency'],'overlap',results['overlap_audit'],flush=True)


if __name__=='__main__':main()
