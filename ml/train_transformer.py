"""CPU-friendly fine-tune of a pretrained two-layer BERT; never used untrained."""
import json
import random
import time
from pathlib import Path
import numpy as np
import pandas as pd
import psutil
import torch
from huggingface_hub import model_info
from transformers import AutoTokenizer, AutoModelForSequenceClassification
from ml.common import SEED, save, sha, environment
from ml.evaluate import report, choose_threshold, latency

MODEL = 'google/bert_uncased_L-2_H-128_A-2'


def main():
    torch.set_num_threads(4)
    torch.manual_seed(SEED)
    np.random.seed(SEED)
    random.seed(SEED)
    torch.use_deterministic_algorithms(True)
    root=Path('artifacts/transformer')
    root.mkdir(parents=True, exist_ok=True)
    revision=json.loads(Path('config/training.json').read_text(encoding='utf-8-sig'))['transformer_revision']
    tokenizer=AutoTokenizer.from_pretrained(MODEL,revision=revision)
    data=pd.read_json('data/prepared/samples.jsonl',lines=True)
    labels=sorted(data.label.unique())
    label_to_id={label:i for i,label in enumerate(labels)}
    model=AutoModelForSequenceClassification.from_pretrained(MODEL,revision=revision,num_labels=len(labels),
        id2label=dict(enumerate(labels)),label2id=label_to_id)
    frames={s:data[data.split==s].reset_index(drop=True) for s in ['train','validation','test']}
    encoded={s:tokenizer(f.text.tolist(),padding='max_length',truncation=True,max_length=64,return_tensors='pt') for s,f in frames.items()}
    truth={s:torch.tensor([label_to_id[y] for y in f.label]) for s,f in frames.items()}
    optimizer=torch.optim.AdamW(model.parameters(),lr=5e-4,weight_decay=.01)

    def probabilities(split):
        model.eval()
        results=[]
        with torch.inference_mode():
            for start in range(0,len(frames[split]),128):
                batch={k:v[start:start+128] for k,v in encoded[split].items()}
                results.append(model(**batch).logits.softmax(-1).numpy())
        return np.concatenate(results)

    def predict(texts):
        model.eval()
        with torch.inference_mode():
            return model(**tokenizer(texts,padding=True,truncation=True,max_length=64,return_tensors='pt')).logits.softmax(-1).numpy()

    start=time.perf_counter()
    best=-1
    trials=[]
    for epoch in range(1,4):
        model.train()
        order=torch.randperm(len(frames['train']))
        loss_sum=0.
        for indices in order.split(64):
            optimizer.zero_grad(set_to_none=True)
            output=model(**{k:v[indices] for k,v in encoded['train'].items()},labels=truth['train'][indices])
            output.loss.backward()
            torch.nn.utils.clip_grad_norm_(model.parameters(),1.)
            optimizer.step()
            loss_sum+=output.loss.item()*len(indices)
        probs=probabilities('validation')
        score=report(frames['validation'],probs,labels,0)['macro_f1']
        trials.append({'epoch':epoch,'train_loss':loss_sum/len(order),'validation_macro_f1':score})
        print(json.dumps(trials[-1]),flush=True)
        if score>best:
            best=score
            model.save_pretrained(root/'checkpoint',safe_serialization=True)
            tokenizer.save_pretrained(root/'checkpoint')
    model=AutoModelForSequenceClassification.from_pretrained(root/'checkpoint')
    validation_probs=probabilities('validation')
    threshold=choose_threshold(frames['validation'].label,validation_probs,labels)
    metadata={'kind':'pretrained-bert-finetuned','version':'transformer-'+sha(root/'checkpoint/model.safetensors')[:12],
              'base_model':MODEL,'base_revision':revision,'base_license':'Apache-2.0','labels':labels,
              'threshold':threshold,'seed':SEED,'epochs':3,'learning_rate':5e-4,'max_length':64,'batch_size':64,
              'data_sha256':sha('data/prepared/samples.jsonl'),'split_sha256':sha('data/prepared/manifest.json'),
              'training_seconds':time.perf_counter()-start,'artifact_bytes':sum(p.stat().st_size for p in (root/'checkpoint').glob('*')),
              'command':'python -m ml.train_transformer','device':'cpu','torch_threads':4,'environment':environment()}
    save(root/'metadata.json',metadata)
    evaluation={'status':'trained','metadata':metadata,'selection_trials':trials,
                'validation':report(frames['validation'],validation_probs,labels,threshold),
                'test':report(frames['test'],probabilities('test'),labels,threshold),
                'latency':latency(predict,frames['validation'].text.tolist()),'process_rss_mb':psutil.Process().memory_info().rss/2**20}
    save(root/'evaluation.json',evaluation)
    print(json.dumps({'test_macro_f1':evaluation['test']['macro_f1'],'latency':evaluation['latency']}),flush=True)


if __name__=='__main__':
    main()
