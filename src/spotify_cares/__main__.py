"""Allow ``python -m spotify_cares`` to run the CLI."""

from spotify_cares.cli import main


if __name__ == "__main__":
    raise SystemExit(main())

