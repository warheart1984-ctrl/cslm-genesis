"""Prompt in → JCR decision + receipt out. The draft is never an answer until release."""

from __future__ import annotations

import argparse
import json
import sys

from adapter import MockAdapter, select_adapter
from dlt_eval import main as eval_main
from envload import load_dotenv
from ledger import build_receipt_export
from pipeline import run
from replay import main as replay_main
from session import SessionManager
from store import load_receipt


def _run_prompt(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(
        description="CSLM-Genesis language organ: release only after a JCR decision."
    )
    parser.add_argument("prompt", nargs="?", help="User prompt")
    parser.add_argument("--prompt", dest="prompt_opt", help="User prompt (flag form)")
    parser.add_argument(
        "--draft",
        help="Mock base-LM draft text (skips local Ollama / live adapter)",
    )
    args = parser.parse_args(argv)
    load_dotenv()
    prompt = args.prompt_opt or args.prompt
    if not prompt:
        parser.error("a prompt is required")
    if args.draft is not None:
        adapter = MockAdapter(args.draft)
    else:
        adapter = select_adapter()
    result = run(prompt, adapter=adapter)
    json.dump(result.public_payload(), sys.stdout, indent=2, ensure_ascii=False)
    sys.stdout.write("\n")
    return 0 if result.decision == "release" else 2


def _export_session(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description="Export a session bundle for an external ledger.")
    parser.add_argument("session_id", help="Session id to export")
    args = parser.parse_args(argv)
    load_dotenv()
    bundle = SessionManager().export_session(args.session_id)
    json.dump(bundle, sys.stdout, indent=2, ensure_ascii=False)
    sys.stdout.write("\n")
    return 0


def _export_receipt(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description="Export a receipt event for an external ledger.")
    parser.add_argument("receipt_id", help="Receipt id to export")
    args = parser.parse_args(argv)
    load_dotenv()
    event = build_receipt_export(load_receipt(args.receipt_id))
    json.dump(event, sys.stdout, indent=2, ensure_ascii=False)
    sys.stdout.write("\n")
    return 0


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if args and args[0] == "replay":
        return replay_main(args[1:])
    if args and args[0] == "eval":
        return eval_main(args[1:])
    if args and args[0] == "export-session":
        return _export_session(args[1:])
    if args and args[0] == "export-receipt":
        return _export_receipt(args[1:])
    return _run_prompt(args)


if __name__ == "__main__":
    raise SystemExit(main())
