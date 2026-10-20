import hashlib
from pathlib import Path
import pytest
from obsidiandroid.modeling.av_only_experiment import execute, prepare


def test_missing_recorded_label_provenance_blocks_before_features():
    with pytest.raises(ValueError, match='label provenance'):
        prepare({'members': [{}]}, 'a'*64)


def test_changed_snapshot_and_existing_output_cannot_run(tmp_path):
    snapshot = tmp_path/'snapshot.json'
    snapshot.write_text('{}')
    with pytest.raises(ValueError, match='reviewed digest'):
        execute(snapshot, 'a'*64, tmp_path/'new-output', train=True)
    assert not (tmp_path/'new-output').exists()
    with pytest.raises(ValueError, match='new directory'):
        execute(snapshot, hashlib.sha256(snapshot.read_bytes()).hexdigest(), tmp_path, train=True)
    assert snapshot.read_text() == '{}'


def test_unsupported_model_rejected_before_source_read(tmp_path):
    with pytest.raises(ValueError, match='Unsupported development model'):
        execute(tmp_path/'missing', 'a'*64, tmp_path/'out', train=True, model_type='other')
    assert not (tmp_path/'out').exists()
