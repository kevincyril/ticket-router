import time
import numpy as np
from sklearn.metrics import accuracy_score, f1_score, classification_report, confusion_matrix


def calibration(y, probabilities, labels):
    labels = np.array(labels)
    truth = np.array(y)
    pred = labels[probabilities.argmax(axis=1)]
    confidence = probabilities.max(axis=1)
    correct = pred == truth
    bins=[]
    ece=0.
    for low in np.arange(0,1,.1):
        mask=(confidence >= low)&(confidence < low+.1 if low < .9 else confidence <= 1)
        if mask.any():
            accuracy=float(correct[mask].mean())
            average=float(confidence[mask].mean())
            ece += float(mask.mean())*abs(accuracy-average)
            bins.append({'lower':round(float(low),1),'count':int(mask.sum()),'accuracy':accuracy,'confidence':average})
    onehot=(truth[:,None] == labels[None,:]).astype(float)
    return {'ece_10_bins':ece,'brier_multiclass':float(((probabilities-onehot)**2).sum(axis=1).mean()),'bins':bins}


def coverage(y, probabilities, labels):
    correct=np.array(labels)[probabilities.argmax(axis=1)] == np.array(y)
    confidence=probabilities.max(axis=1)
    rows=[]
    for threshold in np.arange(0,1.001,.025):
        threshold=round(float(threshold),3)
        mask=confidence >= threshold
        n=int(mask.sum())
        rows.append({'threshold':round(float(threshold),3),'auto_routed':n,'coverage':float(mask.mean()),
                     'accuracy':float(correct[mask].mean()) if n else None,'error':float(1-correct[mask].mean()) if n else None})
    return rows


def choose_threshold(y, probabilities, labels):
    rows=coverage(y,probabilities,labels)
    eligible=[r for r in rows if r['threshold'] >= .5 and r['accuracy'] is not None and r['accuracy'] >= .98 and r['auto_routed'] >= 100]
    return max(eligible,key=lambda r:r['coverage'])['threshold'] if eligible else 1.0


def report(frame, probabilities, labels, threshold):
    prediction=np.array(labels)[probabilities.argmax(axis=1)]
    errors=[]
    for i in np.argsort(-probabilities.max(axis=1)):
        if prediction[i] != frame.label.iloc[i]:
            errors.append({'text':frame.text.iloc[i],'actual':frame.label.iloc[i], 'predicted':prediction[i], 'confidence':float(probabilities[i].max())})
        if len(errors) == 12:
            break
    auto=probabilities.max(axis=1)>=threshold
    return {'accuracy':float(accuracy_score(frame.label,prediction)), 'macro_f1':float(f1_score(frame.label,prediction,average='macro')),
            'per_class':classification_report(frame.label,prediction,labels=labels,output_dict=True,zero_division=0),
            'labels':list(labels),'confusion_matrix':confusion_matrix(frame.label,prediction,labels=labels).tolist(),
            'errors':errors,'calibration':calibration(frame.label,probabilities,labels),'coverage_curve':coverage(frame.label,probabilities,labels),
            'selected_threshold':threshold,'auto_coverage':float(auto.mean()), 'auto_accuracy':float((prediction[auto]==frame.label.to_numpy()[auto]).mean()) if auto.any() else None,
            'count':len(frame)}


def latency(predict, texts, repeats=100):
    for text in texts[:5]:
        predict([text])
    samples=[]
    for i in range(repeats):
        start=time.perf_counter()
        predict([texts[i%len(texts)]])
        samples.append((time.perf_counter()-start)*1000)
    return {'samples':repeats,'batch_size':1,'median_ms':float(np.median(samples)), 'p95_ms':float(np.percentile(samples,95)),
            'serial_throughput_per_second':1000/float(np.mean(samples))}
