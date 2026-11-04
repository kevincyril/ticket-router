"""Reevaluate frozen checkpoints with the shared validation threshold policy.

No fitting or test-driven hyperparameter selection occurs in this command.
"""
import json
from pathlib import Path
import numpy as np
import pandas as pd
import psutil
from ml.common import save
from ml.evaluate import choose_threshold,report,latency


def main():
    import torch
    from transformers import AutoTokenizer,AutoModelForSequenceClassification
    import joblib
    frames=pd.read_json('data/prepared/samples.jsonl',lines=True)
    validation=frames[frames.split=='validation'].reset_index(drop=True)
    test=frames[frames.split=='test'].reset_index(drop=True)
    torch.set_num_threads(4)
    for name in ['baseline','transformer']:
        root=Path('artifacts')/name
        evaluation=json.loads((root/'evaluation.json').read_text(encoding='utf-8-sig'))
        labels=evaluation['metadata']['labels']
        if name=='baseline':
            model=joblib.load(root/'model.joblib')
            predict=model.predict_proba
        else:
            tokenizer=AutoTokenizer.from_pretrained(root/'checkpoint')
            model=AutoModelForSequenceClassification.from_pretrained(root/'checkpoint').eval()
            def predict(texts):
                results=[]
                with torch.inference_mode():
                    for start in range(0,len(texts),128):
                        tokens=tokenizer(list(texts[start:start+128]),padding=True,truncation=True,max_length=64,return_tensors='pt')
                        results.append(model(**tokens).logits.softmax(-1).numpy())
                return np.concatenate(results)
        probs=predict(validation.text.tolist())
        threshold=choose_threshold(validation.label,probs,labels)
        evaluation['metadata']['threshold']=threshold
        evaluation['metadata']['evaluation_command']='OMP_NUM_THREADS=2 OPENBLAS_NUM_THREADS=2 python -m ml.evaluate_saved'
        evaluation['threshold_policy']='Maximum validation coverage with confidence threshold >=0.50, >=98% empirical accepted accuracy, >=100 accepted samples; otherwise 1.0. Floor added after initial test reporting to support ambiguous demo requests; no thresholds optimized on test.'
        evaluation['validation']=report(validation,probs,labels,threshold)
        evaluation['test']=report(test,predict(test.text.tolist()),labels,threshold)
        evaluation['latency']=latency(predict,validation.text.tolist())
        evaluation['latency']['protocol']='Warm CPU serial batch-one, 5 warmups +100 timed; no training concurrent; baseline BLAS threads2, transformer torch threads4'
        evaluation['evaluation_process_rss_mb']=psutil.Process().memory_info().rss/2**20
        # Training RSS remains the isolated process measurement in each initial run.
        save(root/'evaluation.json',evaluation)
        save(root/'metadata.json',evaluation['metadata'])
        print(name,threshold,evaluation['test']['macro_f1'],evaluation['latency'],flush=True)


if __name__=='__main__':main()
