import argparse
import json
import sys
from pathlib import Path

from pipeline.coder import code_note
from pipeline.config import Config, ConfigError
from pipeline.knowledge import Knowledge
from pipeline.llm import get_provider
from pipeline.notes import load_notes


def main(argv: list[str] | None = None, root: Path | None = None) -> int:
    """Entry point for python -m pipeline; returns process exit code."""
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")
    args = _parse(argv)
    root = root or Path.cwd()
    try:
        config = Config.load(root)
        knowledge = Knowledge.load(config)
        input_path = Path(args.input)
        if not input_path.exists():
            print(f"Input file not found: {input_path}", file=sys.stderr)
            return 1
        notes = load_notes(input_path)
    except (ConfigError, OSError, ValueError) as e:
        print(e, file=sys.stderr)
        return 1

    try:
        provider = get_provider(config)
    except ConfigError as e:
        print(f"warning: {e} - running without a model; all notes will be unresolved",
              file=sys.stderr)
        provider = None

    out_path = root / config.data.get("paths", {}).get("results", "out/results.jsonl")
    if args.out:
        out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    with out_path.open("w", encoding="utf-8") as handle:
        for note in notes:
            line = json.dumps(code_note(note, provider, knowledge).to_dict(), ensure_ascii=False)
            print(line)
            handle.write(line + "\n")
    print(f"{len(notes)} note(s) processed -> {out_path}", file=sys.stderr)
    return 0


def _parse(argv: list[str] | None) -> argparse.Namespace:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(prog="pipeline")
    commands = parser.add_subparsers(dest="command", required=True)
    run = commands.add_parser("run", help="code a file of consult notes")
    run.add_argument("input", help="path to notes file (JSON array, JSONL, or plain text)")
    run.add_argument("--out", default=None, help="results path (default: out/results.jsonl)")
    return parser.parse_args(argv)
