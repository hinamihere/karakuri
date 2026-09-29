"""Command line entry point for the intent router.

Two subcommands, both fully offline:

``build-index``
    Embed every recipe in ``[app].recipe_dir`` and write the FAISS index to
    ``[app].recipe_index_path``. Run it after adding or editing a recipe.

``route``
    Print the Mode A / Mode B decision for one intent as JSON. This is the
    manual verification path for KARA-9: a known recipe prompt prints
    ``"mode": "mode_a"`` with a similarity at or above the threshold and no
    network call is made.

    ``tree_snapshot_hash`` is required because contracts.md §2.1 forbids an
    all-zero hash and requires it on every telemetry event. The canonical
    hash is produced by the pruner (KARA-6); ``--tree-file`` hashes the bytes
    of a serialized tree file so this tool can be used before the two modules
    are wired together.
"""

from __future__ import annotations

import argparse
import dataclasses
import hashlib
import json
import sys

from agent.router.config import MatcherConfig, MatcherConfigError, load_matcher_config
from agent.router.embedder import EmbedderError, OnnxEmbedder
from agent.router.index import IndexLoadError, RecipeIndex
from agent.router.router import IntentRouter, RouteResult
from agent.router.telemetry import (
    JsonlTelemetrySink,
    MemoryTelemetrySink,
    TelemetryEventError,
    TelemetrySink,
)

DEFAULT_CONFIG = "config.toml"


def _sha256_file(path: str) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="python -m agent.router")
    sub = parser.add_subparsers(dest="command", required=True)

    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--config", default=DEFAULT_CONFIG, help="path to config.toml")
    common.add_argument("--model", default=None, help="override [matcher].onnx_model_path")
    common.add_argument("--recipe-dir", default=None, help="override [app].recipe_dir")
    common.add_argument("--index", default=None, help="override [app].recipe_index_path")

    sub.add_parser("build-index", parents=[common], help="embed recipes into the index")

    route = sub.add_parser("route", parents=[common], help="route one intent")
    route.add_argument("--intent", required=True, help="natural-language intent")
    route.add_argument("--window-title", default="", help="foreground window title")
    hash_group = route.add_mutually_exclusive_group(required=True)
    hash_group.add_argument("--tree-hash", default=None, help="64-char hex tree snapshot hash")
    hash_group.add_argument(
        "--tree-file",
        default=None,
        help="serialized tree file; sha256 of its bytes is used as the hash",
    )
    route.add_argument(
        "--telemetry",
        default="logs/telemetry.jsonl",
        help="telemetry JSONL path (use 'none' to discard events)",
    )
    return parser


def _load_config(args: argparse.Namespace) -> MatcherConfig:
    config = load_matcher_config(args.config)
    overrides: dict[str, object] = {}
    if args.model:
        overrides["onnx_model_path"] = args.model
        overrides["tokenizer_path"] = None
    if getattr(args, "recipe_dir", None):
        overrides["recipe_dir"] = args.recipe_dir
    if getattr(args, "index", None):
        overrides["recipe_index_path"] = args.index
    if overrides:
        config = dataclasses.replace(config, **overrides)
    for warning in config.warnings:
        print(f"warning: {warning.message}", file=sys.stderr)
    return config


def _cmd_build_index(args: argparse.Namespace) -> int:
    config = _load_config(args)
    embedder = OnnxEmbedder(config.onnx_model_path, config.tokenizer_path)
    router = IntentRouter(
        embedder,
        RecipeIndex.empty(embedder.dim),
        config,
        telemetry=MemoryTelemetrySink(),
    )
    index = router.build_index(config.recipe_dir)
    target = router.save_index(index, args.index)
    print(
        json.dumps(
            {
                "index": target,
                "recipes": len(index),
                "ids": list(index.ids),
                "dim": index.dim,
                "problems": [str(p) for p in router.recipe_problems],
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


def _cmd_route(args: argparse.Namespace) -> int:
    config = _load_config(args)
    tree_hash = args.tree_hash or _sha256_file(args.tree_file)
    embedder = OnnxEmbedder(config.onnx_model_path, config.tokenizer_path)
    index = IntentRouter.load_index(config.recipe_index_path, embedder.dim)
    telemetry: TelemetrySink
    if args.telemetry == "none":
        telemetry = MemoryTelemetrySink()
    else:
        telemetry = JsonlTelemetrySink(args.telemetry)
    router = IntentRouter(embedder, index, config, telemetry)
    result: RouteResult = router.route(
        args.intent,
        window_title=args.window_title,
        tree_snapshot_hash=tree_hash,
    )
    print(
        json.dumps(
            {
                "mode": result.mode,
                "recipe_id": result.recipe_id,
                "similarity": result.similarity,
                "threshold": result.threshold,
                "candidates": [
                    {"recipe_id": c.recipe_id, "similarity": c.similarity}
                    for c in result.candidates
                ],
                "telemetry_events": list(result.telemetry_events),
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    try:
        if args.command == "build-index":
            return _cmd_build_index(args)
        return _cmd_route(args)
    except MatcherConfigError as exc:
        print(f"config error ({exc.error_category}): {exc}", file=sys.stderr)
        return 2
    except EmbedderError as exc:
        print(f"embedder error ({exc.error_category}): {exc}", file=sys.stderr)
        return 3
    except IndexLoadError as exc:
        print(f"index error: {exc}", file=sys.stderr)
        return 4
    except TelemetryEventError as exc:
        print(f"telemetry error: {exc}", file=sys.stderr)
        return 5
    except OSError as exc:
        print(f"OS error ({exc.errno}): {exc}", file=sys.stderr)
        return 6


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
