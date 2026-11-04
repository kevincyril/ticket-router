import numpy as np
from ml.prepare import normalize
from ml.evaluate import choose_threshold, coverage, calibration
from app.main import Submission
from pydantic import ValidationError
import pytest


def test_normalization_groups_slots_and_variants():
    assert normalize('Where is ORDER #123?!')==normalize('where is order 456')
    assert normalize('track {{Order Number}}')==normalize('track {{Tracking Number}}')


def test_threshold_uses_accuracy_and_minimum_coverage():
    probabilities=np.array([[.9,.1]]*180+[[.4,.6]]*20)
    labels=['a','b']
    threshold=choose_threshold(['a']*200,probabilities,labels)
    assert .6<threshold<=.9
    row=next(r for r in coverage(['a']*200,probabilities,labels) if r['threshold']==threshold)
    assert row['accuracy']==1 and row['coverage']==.9


def test_all_review_if_insufficient_evidence():
    assert choose_threshold(['a'],np.array([[.6,.4]]),['a','b'])==1


def test_calibration_exposes_overconfidence():
    result=calibration(['b']*10,np.array([[.99,.01]]*10),['a','b'])
    assert result['ece_10_bins']>.98 and result['brier_multiclass']>1.9


def test_whitespace_input_rejected():
    with pytest.raises(ValidationError):
        Submission(text=' '*10)


def test_hard_deadline_terminates_worker_process():
    import subprocess
    import sys
    import time
    start=time.monotonic()
    result=subprocess.run([sys.executable,'-c',
        'from app.worker import ProcessDeadline; import time\nwith ProcessDeadline(1): time.sleep(20)'],timeout=15)
    assert result.returncode==124
    assert time.monotonic()-start<15
