"""Prompt in → JCR decision + receipt out. The draft is never an answer until release."""

from __future__ import annotations

import argparse
import json
import sys

from adapter import MockAdapter, select_adapter
from envload import load_dotenv
from pipeline import run


def main(argv: list[str] | None = None) -> int:
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


if __name__ == "__main__":
    raise SystemExit(main())
