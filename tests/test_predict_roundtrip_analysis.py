"""Static round-trip recognition must not bless arbitrary wrappers or loads."""
from scripts.dev.scan_ml_predict_misuse import scan_file_for_predict_misuse


PREFIX = '''import joblib
from sklearn.pipeline import make_pipeline

def check():
    learner = make_pipeline(step)
'''


def scan(tmp_path, body):
    path = tmp_path / 'candidate.py'
    path.write_text(PREFIX + ''.join('    ' + line + '\n' for line in body.splitlines()))
    return scan_file_for_predict_misuse(str(path))


def test_local_pipeline_roundtrip_is_recognized_without_loading(tmp_path):
    assert not scan(tmp_path, '''joblib.dump({'model': learner}, path)
restored = joblib.load(path)['model']
if list(restored.predict(X)) != list(expected):
    raise ValueError()''')


def test_unknown_and_invalidated_roundtrips_keep_warning(tmp_path):
    cases = [
        "restored = joblib.load(path)['model']\nrestored.predict(X)",
        "joblib.dump({'model': {}}, path)\nrestored = joblib.load(path)['model']\nrestored.predict(X)",
        "joblib.dump({'model': learner}, path)\nrestored = joblib.load(other)['model']\nrestored.predict(X)",
        "joblib.dump({'model': learner}, path)\nrestored = joblib.load(path)\nrestored.predict(X)",
        "joblib.dump({'model': learner}, path)\nrestored = joblib.load(path)['model']\nrestored = {}\nrestored.predict(X)",
        "joblib.dump({'model': learner}, path)\npath = other\nrestored = joblib.load(path)['model']\nrestored.predict(X)",
        "if condition:\n    joblib.dump({'model': learner}, path)\nrestored = joblib.load(path)['model']\nrestored.predict(X)",
        "joblib.dump({'model': learner}, path)\nrestored = joblib.load(path)['model']\nif condition:\n    restored = {}\nrestored.predict(X)",
        "joblib.dump({'model': learner}, path)\nrestored = joblib.load(path)['model']\nrestored.predict(X); data.predict(X)",
    ]
    for body in cases:
        assert scan(tmp_path, body), body


def test_historical_experiment_roundtrip_scans_clean_without_execution():
    from pathlib import Path
    path = Path(__file__).parents[1] / 'src/obsidiandroid/modeling/expanded_av_experiment.py'
    assert not scan_file_for_predict_misuse(str(path))


def test_literal_source_fixture_is_not_an_executed_prediction(tmp_path):
    path = tmp_path / 'literal.py'
    path.write_text('example = """\nrestored.predict(X)\n"""\n')
    assert not scan_file_for_predict_misuse(str(path))
    path.write_text(path.read_text() + 'data.predict(X)\n')
    assert len(scan_file_for_predict_misuse(str(path))) == 1
