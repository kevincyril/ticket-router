"""Prepare a small immutable serving bundle; never train during deployment."""
import argparse
import gzip
import hashlib
import io
import json
from pathlib import Path
import tarfile

FILES=('metadata.json','model.joblib','support.joblib')


def package(source,destination):
    source,destination=Path(source),Path(destination)
    metadata=json.loads((source/'metadata.json').read_text(encoding='utf-8'))
    for name,key in [('model.joblib','artifact_sha256'),('support.joblib','support_sha256')]:
        if hashlib.sha256((source/name).read_bytes()).hexdigest()!=metadata[key]:
            raise ValueError('Serving artifact checksum mismatch: '+name)
    destination.parent.mkdir(exist_ok=True,parents=True)
    with destination.open('wb') as raw:
        with gzip.GzipFile(fileobj=raw,mode='wb',mtime=0,filename='') as compressed:
            with tarfile.open(fileobj=compressed,mode='w') as archive:
                for name in FILES:
                    payload=(source/name).read_bytes()
                    entry=tarfile.TarInfo(name)
                    entry.size=len(payload);entry.mtime=0;entry.mode=0o644
                    archive.addfile(entry,io.BytesIO(payload))
    record={'sha256':hashlib.sha256(destination.read_bytes()).hexdigest(),'model_version':metadata['version'],
       'files':{name:hashlib.sha256((source/name).read_bytes()).hexdigest() for name in FILES},
       'source':'Already-trained frozen model; no training/download occurs at image build or runtime.',
       'data_attribution':'Bitext, CDLA-Sharing-1.0; see docs/DATASET.md and docs/DATA_LICENSE.txt.'}
    destination.with_suffix('.json').write_text(json.dumps(record,indent=2)+'\n',encoding='utf-8')
    print('Packaged',destination,'bytes',destination.stat().st_size,'version',metadata['version'])


def unpack(bundle,destination):
    bundle,destination=Path(bundle),Path(destination)
    record=json.loads(bundle.with_suffix('.json').read_text(encoding='utf-8'))
    if hashlib.sha256(bundle.read_bytes()).hexdigest()!=record['sha256']:
        raise ValueError('Serving bundle checksum mismatch')
    destination.mkdir(exist_ok=True,parents=True)
    with tarfile.open(bundle,'r:gz') as archive:
        members=archive.getmembers()
        if {item.name for item in members}!=set(FILES) or len(members)!=len(FILES) or not all(item.isfile() for item in members):
            raise ValueError('Unexpected bundle members')
        for item in members:
            payload=archive.extractfile(item).read()
            if hashlib.sha256(payload).hexdigest()!=record['files'][item.name]:
                raise ValueError('Bundled artifact checksum mismatch')
            (destination/item.name).write_bytes(payload)


if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('action',choices=['pack','unpack'])
    parser.add_argument('--bundle',default='deploy/serving-model.tar.gz')
    parser.add_argument('--directory',default='artifacts/robustness/deployed')
    args=parser.parse_args()
    if args.action=='pack':package(args.directory,args.bundle)
    else:unpack(args.bundle,args.directory)
