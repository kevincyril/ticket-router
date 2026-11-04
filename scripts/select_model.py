from pathlib import Path
import json
from ml.common import save
baseline=json.loads(Path('artifacts/baseline/evaluation.json').read_text(encoding='utf-8-sig'))
transformer=json.loads(Path('artifacts/transformer/evaluation.json').read_text(encoding='utf-8-sig'))
save('artifacts/model-selection.json',{'deployed':'baseline','policy':'Among models with validation macro-F1 >=0.99, choose lower batch-one median CPU latency; compare artifact size and process RSS. Test is reporting only.',
    'candidates':{name:{'validation_macro_f1':r['validation']['macro_f1'],'latency':r['latency'],
                       'process_rss_mb':r['process_rss_mb'],'artifact_bytes':r['metadata']['artifact_bytes']}
                  for name,r in [('baseline',baseline),('transformer',transformer)]}})
for name,r in [('baseline',baseline),('transformer',transformer)]:
    print(name,'validation',r['validation']['macro_f1'],'test',r['test']['macro_f1'],'threshold',r['test']['selected_threshold'],
          'coverage',r['test']['auto_coverage'],'autoacc',r['test']['auto_accuracy'],'ECE',r['test']['calibration']['ece_10_bins'],
          'rss',r['process_rss_mb'],'time',r['metadata']['training_seconds'])
