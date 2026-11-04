import json
import time
from pathlib import Path
from functools import lru_cache
import joblib
from app.config import settings
from app.routing_policy import calibrated,features,decisions,review_reasons,conflicting_clauses


class Predictor:
    def __init__(self,directory):
        path=Path(directory)
        self.metadata=json.loads((path/'metadata.json').read_text(encoding='utf-8-sig'))
        self.model=joblib.load(path/'model.joblib')
        self.policy=self.metadata.get('routing_policy')
        self.support=joblib.load(path/'support.joblib') if self.policy else None

    def assess(self,text):
        start=time.perf_counter()
        raw=self.model.predict_proba([text])
        probabilities=calibrated(raw,self.metadata.get('temperature',1.0))
        best=int(probabilities[0].argmax())
        category=str(self.model.classes_[best])
        confidence=float(probabilities[0,best])
        evidence={'raw_confidence':float(raw[0].max()),'temperature':self.metadata.get('temperature',1.0),
                  'top_categories':[{'category':str(self.model.classes_[i]),'confidence':float(probabilities[0,i])}
                     for i in probabilities[0].argsort()[-3:][::-1]]}
        if self.policy:
            values=features([text],probabilities,self.support['vectorizer'],self.support['vectors'],self.support['labels'],self.model.classes_)
            values['conflict']=conflicting_clauses([text],self.model.predict_proba,self.metadata['temperature'],self.support,self.model.classes_,self.policy['clause_min_similarity'])
            auto=bool(decisions(values,self.policy)[0])
            evidence.update(review_reasons=review_reasons(values,self.policy),nearest_similarity=float(values['similarity'][0]),
                            neighbor_agreement=bool(values['neighbor_agreement'][0]),clause_conflict=bool(values['conflict'][0]))
        else:
            auto=confidence>=self.metadata['threshold']
            evidence['review_reasons']=[] if auto else ['low_confidence']
        return {'category':category,'confidence':confidence,'inference_ms':(time.perf_counter()-start)*1000,
                'auto_route':auto,'evidence':evidence}

    def predict(self,text):
        result=self.assess(text)
        return result['category'],result['confidence'],result['inference_ms']


@lru_cache
def predictor():
    return Predictor(settings().model_dir)


def routing():
    return json.loads(Path(settings().routing_path).read_text(encoding='utf-8-sig'))
