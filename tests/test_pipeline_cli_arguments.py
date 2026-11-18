"""The pipeline starts only after the command line has been validated."""

import pytest

from obsidiandroid.cli import main as pipeline_cli


@pytest.mark.parametrize(("arguments", "exit_code"), [
    (["--help"], 0),
    (["--dry-run"], 2),
    (["--allow-global"], 2),
    (["--allow-global-artifacts", "unexpected"], 2),
])
def test_pipeline_help_and_invalid_arguments_never_start_work(monkeypatch, arguments, exit_code):
    def unexpected_run(**kwargs):
        pytest.fail("pipeline started before accepting the command line")

    monkeypatch.setattr(pipeline_cli, "run_pipeline", unexpected_run)
    with pytest.raises(SystemExit) as result:
        pipeline_cli.main(arguments)
    assert result.value.code == exit_code


@pytest.mark.parametrize(("arguments", "allow_override", "allow_global"), [
    ([], False, False),
    (["--allow-evidence-override"], True, False),
    (["--allow-global-artifacts"], False, True),
    (["--allow-evidence-override", "--allow-global-artifacts"], True, True),
])
def test_pipeline_cli_forwards_only_explicit_flags(monkeypatch, arguments, allow_override, allow_global):
    calls = []

    def fake_run(**options):
        calls.append(options)
        return 7

    monkeypatch.setattr(pipeline_cli, "run_pipeline", fake_run)
    assert pipeline_cli.main(arguments) == 7
    assert calls == [{"allow_evidence_override": allow_override, "allow_global_artifacts": allow_global}]
