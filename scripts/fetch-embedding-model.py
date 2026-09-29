#!/usr/bin/env python3
"""Fetch the local embedding assets for the intent matcher (one-shot).

Karakuri is local-first: the **runtime** never touches the network, but the
ONNX weights have to come from somewhere the first time. This script is that
"somewhere", and after it has run the matcher is fully air-gapped.

Default asset (fits contracts.md §9.2's <150 MB matcher budget):

* ``intfloat/multilingual-e5-small``, int8-quantised ONNX export published by
  ``Xenova/multilingual-e5-small`` — 118,054,593 bytes of weights.

BGE-M3 is not offered as a default: its export is ~570 MB quantised, which
cannot satisfy the frozen 150 MB matcher budget. Point
``[matcher].onnx_model_path`` at your own BGE-M3 export if you accept the
RAM cost.

Air-gapped machines: download the files elsewhere, copy them into a folder,
then run ``--from-dir <folder>``. No network access is required.

Usage::

    python scripts/fetch-embedding-model.py
    python scripts/fetch-embedding-model.py --dest models
    python scripts/fetch-embedding-model.py --from-dir /media/usb/karakuri-models
"""

from __future__ import annotations

import argparse
import hashlib
import os
import shutil
import sys
import urllib.error
import urllib.request

DEFAULT_REPO = "Xenova/multilingual-e5-small"
DEFAULT_BASE_URL = "https://huggingface.co"

# (path inside the repo, output filename)
DEFAULT_ASSETS = (
    ("onnx/model_int8.onnx", "multilingual-e5-small-int8.onnx"),
    ("tokenizer.json", "tokenizer.json"),
    ("tokenizer_config.json", "tokenizer_config.json"),
    ("config.json", "config.json"),
)


def _download(url: str, dest: str, timeout: float) -> None:
    request = urllib.request.Request(url, headers={"User-Agent": "karakuri-fetch/1.0"})
    tmp = dest + ".part"
    with urllib.request.urlopen(request, timeout=timeout) as response:
        total = int(response.headers.get("Content-Length") or 0)
        done = 0
        with open(tmp, "wb") as handle:
            while True:
                chunk = response.read(1024 * 256)
                if not chunk:
                    break
                handle.write(chunk)
                done += len(chunk)
                if total:
                    sys.stderr.write(
                        f"\r  {done / 1e6:8.1f} / {total / 1e6:.1f} MB"
                    )
                    sys.stderr.flush()
    if total:
        sys.stderr.write("\n")
    os.replace(tmp, dest)


def fetch(repo: str, base_url: str, dest_dir: str, timeout: float, force: bool) -> list[str]:
    os.makedirs(dest_dir, exist_ok=True)
    written: list[str] = []
    for remote, local in DEFAULT_ASSETS:
        target = os.path.join(dest_dir, local)
        if os.path.exists(target) and not force:
            print(f"skip  {local} (already present)")
            continue
        url = f"{base_url.rstrip('/')}/{repo}/resolve/main/{remote}"
        print(f"get   {local} <- {url}")
        try:
            _download(url, target, timeout)
        except (urllib.error.URLError, OSError) as exc:
            print(f"FAILED {local}: {exc}", file=sys.stderr)
            if os.path.exists(target + ".part"):
                os.remove(target + ".part")
            raise SystemExit(1) from exc
        written.append(target)
    return written


def install_from_dir(source_dir: str, dest_dir: str, force: bool) -> list[str]:
    os.makedirs(dest_dir, exist_ok=True)
    written: list[str] = []
    for _, local in DEFAULT_ASSETS:
        src = os.path.join(source_dir, local)
        if not os.path.exists(src):
            raise SystemExit(f"--from-dir is missing {local}: {src}")
        target = os.path.join(dest_dir, local)
        if os.path.exists(target) and not force:
            print(f"skip  {local} (already present)")
            continue
        shutil.copyfile(src, target)
        print(f"copy  {local}")
        written.append(target)
    return written


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--dest", default="models", help="output directory (default: models)")
    parser.add_argument("--repo", default=DEFAULT_REPO, help=f"HuggingFace repo (default {DEFAULT_REPO})")
    parser.add_argument(
        "--base-url",
        default=DEFAULT_BASE_URL,
        help="mirror base URL (default: %(default)s)",
    )
    parser.add_argument("--from-dir", default=None, help="install from a local folder instead of downloading")
    parser.add_argument("--force", action="store_true", help="re-fetch even if the file exists")
    parser.add_argument("--timeout", type=float, default=120.0, help="per-file timeout in seconds")
    args = parser.parse_args(argv)

    if args.from_dir:
        written = install_from_dir(args.from_dir, args.dest, args.force)
    else:
        written = fetch(args.repo, args.base_url, args.dest, args.timeout, args.force)

    model = os.path.join(args.dest, "multilingual-e5-small-int8.onnx")
    if os.path.exists(model):
        size = os.path.getsize(model)
        print(f"model weights: {size:,} bytes ({size / 1e6:.1f} MB)")
        if size >= 150_000_000:
            print(
                "WARNING: weights exceed the 150 MB matcher budget "
                "(contracts.md §9.2)",
                file=sys.stderr,
            )
    if written:
        digest = hashlib.sha256()
        for path in written:
            with open(path, "rb") as handle:
                digest.update(handle.read())
        print(f"batch sha256: {digest.hexdigest()}")
    print("done — the matcher itself never performs a network call.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
