"""Manual dispatch for the preserved collectors; imports only the selected one."""
import argparse
import importlib

PLATFORMS = ("youtube", "x", "telegram", "reddit", "tiktok", "truthsocial")


def main(argv=None):
    parser = argparse.ArgumentParser(description="Run a legacy social collector from the current working directory.")
    parser.add_argument("--platform", required=True, choices=PLATFORMS)
    args = parser.parse_args(argv)
    runtime = importlib.import_module(f"engine.legacy.{args.platform}")
    runtime.main()


if __name__ == "__main__":
    main()
