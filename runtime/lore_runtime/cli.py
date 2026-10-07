import argparse
import json
import sys

from lore_runtime.events import handle


def main(argv=None):
    parser = argparse.ArgumentParser(prog="lore-event")
    parser.add_argument(
        "event",
        choices=[
            "session_start",
            "after_edit",
            "after_shell",
            "health",
            "session_end",
            "after_error",
        ],
    )
    parser.add_argument("--cwd", default=".")
    parser.add_argument("--path", default="")
    parser.add_argument("--cmd", default="")
    parser.add_argument("--error", default="")
    args = parser.parse_args(argv)
    try:
        result = handle(
            args.event,
            args.cwd,
            path=args.path or None,
            cmd=args.cmd or None,
            error=args.error or None,
        )
    except Exception as e:
        result = {
            "ok": False,
            "event": args.event,
            "cwd": args.cwd,
            "status": "missing",
            "context_path": None,
            "additional_context": "",
            "warnings": [str(e)],
            "env": {},
            "matches": [],
        }
    sys.stdout.write(json.dumps(result, ensure_ascii=False))
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
