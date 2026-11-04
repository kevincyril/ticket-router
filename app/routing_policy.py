"""Reusable routing evidence. No sentence, keyword, category or team overrides."""
import re
import numpy as np
from scipy.special import softmax


def calibrated(probabilities,temperature):
    return softmax(np.log(np.maximum(probabilities,1e-12))/temperature,axis=1)


def clauses(text):
    parts=re.split(r'[.!?;]+|\b(?:and|also|but)\b',text,flags=re.IGNORECASE)
    return [p.strip() for p in parts if len(re.findall(r'\b\w+\b',p))>=3]


def features(texts,probabilities,lexical_model,support_vectors,support_labels,labels):
    """Train-only nearest-neighbor support, not calibrated reliability."""
    vectors=lexical_model.transform(texts)
    predictions=np.asarray(labels)[probabilities.argmax(axis=1)]
    support=[]
    agreement=[]
    for start in range(0,len(texts),128):
        similarity=(vectors[start:start+128]@support_vectors.T).toarray()
        nearest=similarity.argmax(axis=1)
        support.extend(similarity.max(axis=1).tolist())
        agreement.extend((support_labels[nearest]==predictions[start:start+128]).tolist())
    ordered=np.sort(probabilities,axis=1)
    return {'confidence':probabilities.max(axis=1),'margin':ordered[:,-1]-ordered[:,-2],
            'similarity':np.array(support),'neighbor_agreement':np.array(agreement)}


def decisions(evidence,policy):
    accepted=(evidence['confidence']>=policy['confidence'])&(evidence['margin']>=policy['margin'])&(evidence['similarity']>=policy['similarity'])
    if policy.get('require_neighbor_agreement',True):
        accepted &= evidence['neighbor_agreement']
    if 'conflict' in evidence:
        accepted &= ~evidence['conflict']
    if policy.get('disabled',False):
        accepted[:]=False
    return accepted


def review_reasons(evidence,policy,index=0):
    reasons=[]
    for key,reason in [('confidence','low_confidence'),('margin','ambiguous_prediction'),('similarity','insufficient_training_support')]:
        if evidence[key][index]<policy[key]:reasons.append(reason)
    if policy.get('require_neighbor_agreement',True) and not evidence['neighbor_agreement'][index]:reasons.append('nearest_example_disagrees')
    if evidence.get('conflict',[False])[index]:reasons.append('conflicting_clause_predictions')
    if policy.get('disabled',False):reasons.append('automatic_routing_disabled')
    return reasons


def conflicting_clauses(texts,predict,temperature,support,labels,minimum_similarity=.35):
    pieces=[]
    owners=[]
    for i,text in enumerate(texts):
        split=clauses(text)
        if len(split)>1:
            pieces.extend(split)
            owners.extend([i]*len(split))
    result=np.zeros(len(texts),dtype=bool)
    if not pieces:
        return result
    probabilities=calibrated(predict(pieces),temperature)
    evidence=features(pieces,probabilities,support['vectorizer'],support['vectors'],support['labels'],labels)
    votes={}
    for j,owner in enumerate(owners):
        if evidence['similarity'][j]>=minimum_similarity and evidence['confidence'][j]>=.5:
            votes.setdefault(owner,set()).add(int(probabilities[j].argmax()))
    for owner,categories in votes.items():
        result[owner]=len(categories)>1
    return result
