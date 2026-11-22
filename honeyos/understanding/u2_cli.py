"""Local, explicit-home management CLI for U2."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from .u2_manage import explain, forget, suppress
from .u2_store import UnderstandingStore


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="honeyos-understanding")
    parser.add_argument("--home", type=Path, required=True)
    sub = parser.add_subparsers(dest="command", required=True)
    listing = sub.add_parser("list")
    for name in ("owner", "lane", "namespace"):
        listing.add_argument(f"--{name}", required=True)
    for name in ("explain", "suppress", "forget"):
        command = sub.add_parser(name)
        command.add_argument("label_id")
    args = parser.parse_args(argv)
    store = UnderstandingStore(args.home.expanduser().resolve() / "understanding_v2.db")
    store.initialize()
    if args.command == "list":
        result = [dict(row) for row in store.list_labels(args.owner, args.lane, args.namespace)]
    elif args.command == "explain":
        result = explain(store, args.label_id)
    elif args.command == "suppress":
        result = {"policy_epoch": suppress(store, args.label_id)}
    else:
        result = {"policy_epoch": forget(store, args.label_id)}
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
