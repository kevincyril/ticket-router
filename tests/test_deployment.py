import hashlib
import json
from pathlib import Path
import pytest
from app.config import Settings
from scripts.model_bundle import unpack


@pytest.mark.parametrize('scheme',['postgres','postgresql'])
def test_hosted_postgres_urls_use_installed_driver(scheme):
    value=Settings(database_url=scheme+'://demo:secret@localhost/relay')
    assert value.database_url=='postgresql+psycopg://demo:secret@localhost/relay'


def test_committed_bundle_is_exact_frozen_model(tmp_path):
    unpack('deploy/serving-model.tar.gz',tmp_path)
    metadata=json.loads((tmp_path/'metadata.json').read_text(encoding='utf-8'))
    assert hashlib.sha256((tmp_path/'model.joblib').read_bytes()).hexdigest()==metadata['artifact_sha256']
    assert hashlib.sha256((tmp_path/'support.joblib').read_bytes()).hexdigest()==metadata['support_sha256']


def test_bundle_tampering_is_rejected(tmp_path):
    bundle=tmp_path/'bad.tar.gz'
    bundle.write_bytes(b'not a trusted model')
    bundle.with_suffix('.json').write_text('{"sha256":"wrong"}',encoding='utf-8')
    with pytest.raises(ValueError,match='checksum'):
        unpack(bundle,tmp_path/'output')
