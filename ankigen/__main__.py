import argparse

from .app import run


def main() -> None:
    parser = argparse.ArgumentParser(prog="ankigen", description="Anki Deck Generator")
    parser.add_argument(
        "--dev", action="store_true", help="load the Vite dev server (localhost:5173)"
    )
    parser.add_argument("--debug", action="store_true", help="enable devtools")
    args = parser.parse_args()
    run(dev=args.dev, debug=args.debug)


if __name__ == "__main__":
    main()
