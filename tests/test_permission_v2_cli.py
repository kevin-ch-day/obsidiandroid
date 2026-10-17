"""The normal consumer command cannot supply its own approval or invent a split."""
import json
import pytest
from obsidiandroid.cli import permission_v2 as cli


def test_missing_approval_is_a_refusal(monkeypatch, capsys):
    def unavailable(_):
        raise ValueError("private error detail")
    monkeypatch.setattr(cli.v2, "_checked_export", unavailable)
    assert cli.main(["inspect", "--export", "missing.json"]) == 2
    output = capsys.readouterr().out
    assert json.loads(output)["status"] == "PI_V2_CONSUMPTION_REFUSED"
    assert "private error detail" not in output


@pytest.mark.parametrize("training", [[], [True], [1.0], ["1"], [1, 1], [1, 2], [3], {}])
def test_invalid_or_unpartitioned_split_refused(monkeypatch, tmp_path, training):
    export = {"samples": [{"sample_id": 1, "sha256": "a" * 64},
                           {"sample_id": 2, "sha256": "b" * 64}]}
    monkeypatch.setattr(cli.v2, "_checked_export", lambda _: (b"", b"", export))
    def forbidden(*args, **kwargs):
        raise AssertionError("invalid split reached feature construction")
    monkeypatch.setattr(cli.v2, "build_v2_unresolved_features", forbidden)
    split = tmp_path / "split.json"
    split.write_text(json.dumps(training))
    with pytest.raises(ValueError):
        cli.check_features(tmp_path / "export.json", split)


@pytest.mark.parametrize("args", [
    ["features", "--export", "x"],
    ["inspect", "--export", "x", "--training-ids", "y"],
    ["inspect", "--export", "x", "--approval", "y"],
])
def test_invalid_cli_authority_or_mode_arguments(args):
    with pytest.raises(SystemExit) as exc:
        cli.main(args)
    assert exc.value.code == 2
