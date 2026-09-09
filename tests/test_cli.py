from spotify_cares.cli import main


def test_help_is_available(capsys):
    assert main([]) == 0
    output = capsys.readouterr().out
    assert "SpotifyCares support-agent project tools" in output
    assert "config" in output
    assert "extract" in output
    assert "preprocess" in output
    assert "validate-splits" in output
    assert "prepare-annotations" in output
    assert "validate-annotations" in output
    assert "extend-training-queue" in output
    assert "freeze-guide" in output


def test_version_is_available(capsys):
    try:
        main(["--version"])
    except SystemExit as error:
        assert error.code == 0
    assert capsys.readouterr().out.strip() == "0.1.0"
