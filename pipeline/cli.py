import argparse
import json
import sys
from pathlib import Path

import yaml

from pipeline.coder import code_note, replay_note
from pipeline.config import Config, ConfigError
from pipeline.knowledge import Knowledge
from pipeline.llm import LLMError, get_provider
from pipeline.notes import load_notes
from pipeline.replay import ResponseRecorder, ResponseStore


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
    except (ConfigError, OSError, ValueError, yaml.YAMLError) as e:
        print(e, file=sys.stderr)
        return 1

    paths = config.data.get("paths", {})
    responses_path = root / paths.get("responses", "out/responses.jsonl")
    if args.responses:
        responses_path = Path(args.responses)

    store = None
    provider = None
    recorder = None
    if args.command == "replay":
        if not responses_path.exists():
            print(f"Recorded responses not found: {responses_path}", file=sys.stderr)
            return 1
        try:
            store = ResponseStore.load(responses_path)
        except (OSError, ValueError) as e:
            print(e, file=sys.stderr)
            return 1
    else:
        try:
            provider = get_provider(config)
        except (ConfigError, LLMError) as e:
            print(f"warning: {e} - running without a model; all notes will be unresolved",
                  file=sys.stderr)
        if provider is not None:
            llm = config.data.get("llm", {})
            recorder = ResponseRecorder(responses_path, provider=llm.get("provider", ""),
                                        model=llm.get("model", ""))

    out_path = root / paths.get("results", "out/results.jsonl")
    if args.out:
        out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    with out_path.open("w", encoding="utf-8") as handle:
        for note in notes:
            if store is not None:
                decision = replay_note(note, store, knowledge)
            else:
                decision = code_note(note, provider, knowledge, recorder)
            line = json.dumps(decision.to_dict(), ensure_ascii=False)
            print(line)
            handle.write(line + "\n")
    if recorder is not None:
        recorder.close()
        print(f"raw responses recorded -> {responses_path}", file=sys.stderr)
    print(f"{len(notes)} note(s) processed -> {out_path}", file=sys.stderr)
    return 0


def _parse(argv: list[str] | None) -> argparse.Namespace:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(prog="pipeline")
    commands = parser.add_subparsers(dest="command", required=True)
    run = commands.add_parser("run", help="code a file of consult notes")
    run.add_argument("input", help="path to notes file (JSON array, JSONL, or plain text)")
    run.add_argument("--out", default=None, help="results path (default: out/results.jsonl)")
    run.add_argument("--responses", default=None,
                     help="where to record raw model responses (default: out/responses.jsonl)")
    replay = commands.add_parser(
        "replay", help="re-run the parser and validator over recorded responses; no model, no key")
    replay.add_argument("input", help="the notes file the responses were recorded against")
    replay.add_argument("--out", default=None, help="results path (default: out/results.jsonl)")
    replay.add_argument("--responses", default=None,
                        help="recorded responses to replay (default: out/responses.jsonl)")
    return parser.parse_args(argv)
