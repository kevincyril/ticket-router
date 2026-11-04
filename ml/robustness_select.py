"""Validation-only model/policy selection. Does not open challenge test."""
import json,time
from pathlib import Path
import joblib
import numpy as np
import pandas as pd
from scipy.optimize import minimize_scalar
from sklearn.pipeline import Pipeline,FeatureUnion
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import log_loss,f1_score
from app.routing_policy import calibrated,features,decisions,clauses
from ml.common import save,sha,environment
from ml.evaluate import calibration

ROOT=Path('artifacts/robustness')
DEV=['Money left my account two times for one purchase.','Something is wrong. Please help.','I was charged twice for the same order. Can you refund the extra payment?']


class Models:
    def __init__(self):
        import torch
        from transformers import AutoTokenizer,AutoModelForSequenceClassification
        torch.set_num_threads(2)
        self.torch=torch
        self.baseline=joblib.load('artifacts/baseline/model.joblib')
        self.improved=joblib.load(ROOT/'candidate/model.joblib')
        self.tokenizer=AutoTokenizer.from_pretrained('artifacts/transformer/checkpoint',local_files_only=True)
        self.bert=AutoModelForSequenceClassification.from_pretrained('artifacts/transformer/checkpoint',local_files_only=True).eval()
        self.labels=list(self.baseline.classes_)
    def predict(self,name,texts):
        if name!='transformer':return getattr(self,name).predict_proba(texts)
        result=[]
        with self.torch.inference_mode():
            for start in range(0,len(texts),128):
                tokens=self.tokenizer(texts[start:start+128],padding=True,truncation=True,max_length=64,return_tensors='pt')
                result.append(self.bert(**tokens).logits.softmax(-1).numpy())
        return np.concatenate(result)


def clause_conflicts(models,name,texts,temperature,support,minimum_similarity=.35):
    from app.routing_policy import conflicting_clauses
    return conflicting_clauses(texts,lambda t:models.predict(name,t),temperature,support,models.labels,minimum_similarity)


def score(rows,probabilities,labels,accepted):
    pred=np.array(labels)[probabilities.argmax(axis=1)]
    correct=np.array([not r['must_review'] and p in r['acceptable_labels'] for r,p in zip(rows,pred)])
    should_review=np.array([r['must_review'] for r in rows])
    clear=~should_review
    return {'count':len(rows),'auto_routed':int(accepted.sum()),'auto_coverage':float(accepted.mean()),
        'auto_accuracy':float(correct[accepted].mean()) if accepted.any() else None,'manual_review_rate':float((~accepted).mean()),
        'confident_misrouting_count':int((accepted&~correct).sum()),'confident_misrouting_rate':float((accepted&~correct).mean()),
        'high_confidence_wrong_count':int(((probabilities.max(axis=1)>=.8)&~correct).sum()),
        'required_review_recall':float((~accepted[should_review]).mean()) if should_review.any() else None,
        'clear_category_accuracy':float(correct[clear].mean()) if clear.any() else None}


def main():
    ROOT.mkdir(exist_ok=True,parents=True)
    data=pd.read_json('data/prepared/samples.jsonl',lines=True)
    train=data[data.split=='train'].reset_index(drop=True)
    val=data[data.split=='validation'].reset_index(drop=True)
    # Calibration and policy validation are disjoint by original near-duplicate group.
    calibration_mask=(val.group%2)==0
    calibration_frame=val[calibration_mask].reset_index(drop=True)
    policy_frame=val[~calibration_mask].reset_index(drop=True)
    challenge=[json.loads(line) for line in Path('data/challenge/validation.jsonl').read_text(encoding='utf-8').splitlines()]
    save(ROOT/'protocol.json',{'seed':42,'training_source_sha256':sha('data/prepared/samples.jsonl'),
      'calibration_source_rows':calibration_frame.source_row.tolist(),'policy_source_rows':policy_frame.source_row.tolist(),
      'challenge_validation_sha256':sha('data/challenge/validation.jsonl'),'challenge_test_sha256':sha('data/challenge/test.jsonl'),
      'test_not_used_for_selection':True,'selection':'Max challenge validation auto coverage with >=98% accepted accuracy, zero auto-routed must-review cases and >=5 accepts; require >=98% source policy-validation accepted accuracy with >=100 accepts. Tie: source coverage then cheaper model.',
      'confidence_warning':'Calibrated in-domain class probability is not probability the request is supported/unambiguous.'})
    # A richer, class-balanced representation, trained strictly on original train.
    path=ROOT/'candidate';path.mkdir(exist_ok=True)
    start=time.perf_counter()
    improved=Pipeline([('features',FeatureUnion([
       ('words',TfidfVectorizer(ngram_range=(1,2),min_df=2,sublinear_tf=True,max_features=60000)),
       ('chars',TfidfVectorizer(analyzer='char_wb',ngram_range=(3,5),min_df=3,sublinear_tf=True,max_features=60000))])),
       ('classifier',LogisticRegression(C=2,class_weight='balanced',max_iter=700,random_state=42))])
    improved.fit(train.text,train.label)
    joblib.dump(improved,path/'model.joblib')
    save(path/'metadata.json',{'kind':'balanced-word-char-logistic-regression','training_seconds':time.perf_counter()-start,
        'labels':list(improved.classes_),'training_only':True,'no_user_examples_or_challenge_texts_in_training':True})
    models=Models()
    vectorizer=models.baseline.named_steps['tfidf']
    support={'vectorizer':vectorizer,'vectors':vectorizer.transform(train.text),'labels':train.label.to_numpy()}
    joblib.dump(support,ROOT/'support.joblib')
    candidates={};best=None
    for name in ['baseline','improved','transformer']:
        calibration_probs=models.predict(name,calibration_frame.text.tolist())
        optimized=minimize_scalar(lambda temp:log_loss(calibration_frame.label,calibrated(calibration_probs,temp),labels=models.labels),bounds=(.5,5),method='bounded')
        temperature=float(optimized.x)
        probs=calibrated(models.predict(name,policy_frame.text.tolist()),temperature)
        challenge_probs=calibrated(models.predict(name,[r['text'] for r in challenge]),temperature)
        ev=features(policy_frame.text.tolist(),probs,vectorizer,support['vectors'],support['labels'],models.labels)
        ce=features([r['text'] for r in challenge],challenge_probs,vectorizer,support['vectors'],support['labels'],models.labels)
        ev['conflict']=clause_conflicts(models,name,policy_frame.text.tolist(),temperature,support)
        ce['conflict']=clause_conflicts(models,name,[r['text'] for r in challenge],temperature,support)
        truth=np.array(models.labels)[probs.argmax(axis=1)]==policy_frame.label.to_numpy()
        trials=[]
        for confidence in [.5,.65,.8,.9,.95,.98,.995]:
          for similarity in [0,.2,.3,.4,.5,.6,.7,.8,.9]:
           for margin in [0,.2,.4,.6]:
            policy={'confidence':confidence,'similarity':similarity,'margin':margin,'require_neighbor_agreement':True,'clause_min_similarity':.35}
            accepted=decisions(ev,policy);challenge_accepted=decisions(ce,policy)
            s=score(challenge,challenge_probs,models.labels,challenge_accepted)
            source_accuracy=float(truth[accepted].mean()) if accepted.any() else 0
            eligible=s['auto_routed']>=5 and s['auto_accuracy']>=.98 and s['required_review_recall']==1 and accepted.sum()>=100 and source_accuracy>=.98
            if eligible:
                trials.append({'policy':policy,'challenge_validation':s,'source_validation_coverage':float(accepted.mean()),'source_validation_auto_accuracy':source_accuracy})
        if trials:
            chosen=max(trials,key=lambda r:(r['challenge_validation']['auto_coverage'],r['source_validation_coverage']))
        else:
            chosen={'policy':{'confidence':1.01,'similarity':1.01,'margin':1.01,'disabled':True},'challenge_validation':score(challenge,challenge_probs,models.labels,np.zeros(len(challenge),dtype=bool)),'source_validation_coverage':0,'source_validation_auto_accuracy':None}
        candidates[name]={'temperature':temperature,**chosen,
          'source_policy_validation_macro_f1':float(f1_score(policy_frame.label,np.array(models.labels)[probs.argmax(axis=1)],average='macro')),
          'calibration_before':calibration(calibration_frame.label,calibration_probs,models.labels),
          'calibration_after':calibration(calibration_frame.label,calibrated(calibration_probs,temperature),models.labels),
          'raw_validation_challenge':score(challenge,models.predict(name,[r['text'] for r in challenge]),models.labels,models.predict(name,[r['text'] for r in challenge]).max(axis=1)>=.5)}
        ranking=(chosen['challenge_validation']['auto_coverage'],chosen['source_validation_coverage'],-['baseline','improved','transformer'].index(name))
        if best is None or ranking>best[0]:best=(ranking,name)
        print(name,json.dumps({k:v for k,v in candidates[name].items() if not k.startswith('calibration')}),flush=True)
    selected=best[1]
    save(ROOT/'selection.json',{'selected':selected,'candidates':candidates,'environment':environment(),'command':'python -m ml.robustness_select',
       'selection_frozen_before_test':True,'challenge_manifest_sha256':sha('data/challenge/manifest.json')})
    save(ROOT/'development.json',{'note':'User cases are development only, never independent evaluation.',
       'models':{name:[{'text':text,'predicted':models.labels[int(p.argmax())],'confidence':float(p.max())} for text,p in zip(DEV,models.predict(name,DEV))] for name in candidates}})


if __name__=='__main__':main()
