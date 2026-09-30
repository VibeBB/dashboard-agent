#!/usr/bin/env python3
"""Deny a small set of destructive shell commands and forbidden git actions."""

from __future__ import annotations

import json
import shlex
import sys


def evaluate(command: str) -> str | None:
    try:
        tokens = shlex.split(command)
    except ValueError:
        return None
    names = [token.rsplit("/", 1)[-1] for token in tokens]
    if any(name in {"shutdown", "reboot", "poweroff", "mkfs", "fdisk", "wipefs"} for name in names):
        return "system or disk destructive command is denied"
    for index, name in enumerate(names[:-1]):
        args = tokens[index + 1 :]
        if (
            name == "rm"
            and any(flag in {"-rf", "-fr", "--recursive"} for flag in args)
            and any(target in {"/", "~", "$HOME", "${HOME}"} for target in args)
        ):
            return "recursive deletion of root or home is denied"
        if name == "git" and args:
            action = args[0]
            if action == "reset" and "--hard" in args:
                return "git reset --hard is denied"
            if action == "clean" and any(flag.startswith("-") and "f" in flag for flag in args):
                return "git clean -f is denied"
            if action == "add" and any(value in {".", "-A", "--all"} for value in args[1:]):
                return "stage files explicitly; git add . and -A are denied"
            if action == "commit" and any(
                value in {"--amend", "--no-verify", "-n"} for value in args
            ):
                return "git commit --amend and --no-verify are denied"
            if action == "push" and (
                any(value in {"-f", "--force", "--force-all"} for value in args)
                or any(value in {"main", "master"} for value in args[1:])
            ):
                return "force-push and pushes to main/master are denied"
    return None


def main() -> int:
    try:
        payload = json.load(sys.stdin)
    except (json.JSONDecodeError, OSError) as exc:
        print(f"invalid hook input: {exc}", file=sys.stderr)
        return 2
    if isinstance(payload, dict) and payload.get("tool_name") == "terminal":
        tool_input = payload.get("tool_input")
        command = tool_input.get("command") if isinstance(tool_input, dict) else None
        if isinstance(command, str):
            reason = evaluate(command)
            if reason:
                print(f"safety rail: {reason}", file=sys.stderr)
                return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
