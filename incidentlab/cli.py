from __future__ import annotations

import argparse
import json

from .agent import Investigator
from .evaluation import score
from .fixtures import load_incident


def main() -> None:
    parser = argparse.ArgumentParser(prog="rootsignal")
    subparsers = parser.add_subparsers(dest="command", required=True)
    investigate = subparsers.add_parser("investigate")
    investigate.add_argument("fixture")
    evaluate = subparsers.add_parser("evaluate")
    evaluate.add_argument("fixture")
    args = parser.parse_args()

    incident = load_incident(args.fixture)
    result = Investigator().investigate(incident)
    payload = result.as_dict() if args.command == "investigate" else score(incident, result).as_dict()
    print(json.dumps(payload, indent=2))


if __name__ == "__main__":
    main()
