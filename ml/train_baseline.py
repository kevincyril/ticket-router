import argparse
import json
import time
from pathlib import Path
import joblib
import pandas as pd
import psutil
from sklearn.pipeline import Pipeline
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import f1_score
from ml.common import SEED, save, sha, environment
from ml.evaluate import report, choose_threshold, latency


def main():
    frame=pd.read_json('data/prepared/samples.jsonl',lines=True)
    train=frame[frame.split=='train'].reset_index(drop=True)
    validation=frame[frame.split=='validation'].reset_index(drop=True)
    test=frame[frame.split=='test'].reset_index(drop=True)
    trials=[]
    best=None
    start=time.perf_counter()
    for c in (.5,2,8):
        model=Pipeline([('tfidf',TfidfVectorizer(ngram_range=(1,2),min_df=2,sublinear_tf=True,max_features=60000)),
                        ('classifier',LogisticRegression(C=c,max_iter=700,random_state=SEED))])
        model.fit(train.text,train.label)
        score=f1_score(validation.label,model.predict(validation.text),average='macro')
        trials.append({'C':c,'validation_macro_f1':score})
        if best is None or score>best[0]:
            best=(score,model,c)
    _,model,c=best
    probabilities=model.predict_proba(validation.text)
    threshold=choose_threshold(validation.label,probabilities,model.classes_)
    root=Path('artifacts/baseline')
    root.mkdir(parents=True,exist_ok=True)
    joblib.dump(model,root/'model.joblib')
    metadata={'kind':'tfidf-logistic-regression','version':'baseline-'+sha(root/'model.joblib')[:12],
              'labels':list(model.classes_), 'threshold':threshold,'seed':SEED,'C':c,
              'data_sha256':sha('data/prepared/samples.jsonl'),'split_sha256':sha('data/prepared/manifest.json'),
              'training_seconds':time.perf_counter()-start,'artifact_bytes':(root/'model.joblib').stat().st_size,
              'command':'python -m ml.train_baseline','environment':environment()}
    save(root/'metadata.json',metadata)
    # Only final selected model is evaluated on held-out test.
    evaluation={'status':'trained','metadata':metadata,'selection_trials':trials,
                'threshold_policy':'maximum validation coverage with threshold >=0.5, >=98% empirical accuracy and >=100 accepted; else all review (1.0)',
                'validation':report(validation,probabilities,model.classes_,threshold),
                'test':report(test,model.predict_proba(test.text),model.classes_,threshold),
                'latency':latency(model.predict_proba,validation.text.tolist()),
                'process_rss_mb':psutil.Process().memory_info().rss/2**20}
    save(root/'evaluation.json',evaluation)
    print(json.dumps({k:evaluation[k] for k in ['latency','process_rss_mb']},indent=2))
    print('test',evaluation['test']['accuracy'],evaluation['test']['macro_f1'],'threshold',threshold)


if __name__=='__main__':
    main()
