"""Manual local ComfyUI reference-art generation, independent of the main UCC CLI."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

from ucc.ai.generate import ComfyUIClient, TextToImageSpec
from ucc.core.errors import UCCError


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Manual local text-to-image concept generation (not 3D)")
    commands = parser.add_subparsers(dest="command", required=True)
    generate = commands.add_parser("generate", help="Queue one approved ComfyUI text-to-image job")
    generate.add_argument("--base-url", default="http://127.0.0.1:8188")
    generate.add_argument("--checkpoint", required=True)
    generate.add_argument("--prompt", required=True)
    generate.add_argument("--negative", default="")
    generate.add_argument("--width", type=int, default=512)
    generate.add_argument("--height", type=int, default=512)
    generate.add_argument("--steps", type=int, default=20)
    generate.add_argument("--cfg", type=float, default=7.0)
    generate.add_argument("--seed", type=int, default=0)
    generate.add_argument("--confirm-local-execution", action="store_true")
    fetch = commands.add_parser("fetch", help="Retrieve completed PNG reference images locally")
    fetch.add_argument("prompt_id")
    fetch.add_argument("--base-url", default="http://127.0.0.1:8188")
    fetch.add_argument("--output-dir", required=True, type=Path)
    args = parser.parse_args(argv)
    try:
        client = ComfyUIClient(args.base_url)
        if args.command == "generate":
            spec = TextToImageSpec(
                checkpoint=args.checkpoint, prompt=args.prompt,
                negative_prompt=args.negative, width=args.width, height=args.height,
                steps=args.steps, cfg=args.cfg, seed=args.seed,
            )
            result = client.submit(spec, explicitly_authorized=args.confirm_local_execution).to_dict()
        else:
            result = client.fetch_images(args.prompt_id, args.output_dir)
        print(json.dumps(result, indent=2))
        return 0
    except (UCCError, ValueError, OSError, TypeError, KeyError) as exc:
        print(f"UCC AI ERROR: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
