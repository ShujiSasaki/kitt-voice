"""
room_cli — 3者合意 R55:
Shujiさん用 CLI で会議部屋作成 / 一覧 / 削除

使い方:
    python3 -m meeting_system.room_cli create <room_id> [--project NAME] [--color #HEX] [--icon EMOJI]
    python3 -m meeting_system.room_cli list
    python3 -m meeting_system.room_cli delete <room_id>
"""
from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path

from .state_schema import (
    DEFAULT_BASE,
    RoomAlreadyExistsError,
    create_room,
    read_state,
)


def cmd_create(args: argparse.Namespace) -> int:
    try:
        state = create_room(
            room_id=args.room_id,
            project_name=args.project or args.room_id,
            color=args.color,
            icon=args.icon,
            cdp_port=args.cdp_port,
            base=Path(args.base),
        )
        print(json.dumps({
            "ok": True,
            "room_id": state["room_id"],
            "project_name": state["project_name"],
            "color": state["color"],
            "icon": state["icon"],
            "created_at": state["created_at"],
        }, ensure_ascii=False, indent=2))
        return 0
    except RoomAlreadyExistsError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 2
    except ValueError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 3


def cmd_list(args: argparse.Namespace) -> int:
    projects_dir = Path(args.base) / "projects"
    if not projects_dir.exists():
        print(json.dumps({"rooms": []}, ensure_ascii=False))
        return 0
    rooms = []
    for room_dir in sorted(projects_dir.iterdir()):
        if not room_dir.is_dir():
            continue
        state_path = room_dir / "state.json"
        if not state_path.exists():
            continue
        try:
            state = read_state(room_dir.name, base=Path(args.base))
            rooms.append({
                "room_id": state["room_id"],
                "project_name": state.get("project_name", ""),
                "color": state.get("color", ""),
                "icon": state.get("icon", ""),
                "created_at": state.get("created_at", ""),
                "is_consensus_established": state.get("is_consensus_established", False),
            })
        except Exception as e:
            rooms.append({"room_id": room_dir.name, "error": str(e)})
    print(json.dumps({"rooms": rooms}, ensure_ascii=False, indent=2))
    return 0


def cmd_delete(args: argparse.Namespace) -> int:
    room_dir = Path(args.base) / "projects" / args.room_id
    if not room_dir.exists():
        print(f"ERROR: room not found: {args.room_id}", file=sys.stderr)
        return 2
    if not args.yes:
        print(f"ERROR: --yes required to delete {args.room_id}", file=sys.stderr)
        return 4
    shutil.rmtree(room_dir)
    print(json.dumps({"ok": True, "deleted": args.room_id}, ensure_ascii=False))
    return 0


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(
        prog="room_cli",
        description="会議部屋 CLI (R55 3者合意実装)",
    )
    p.add_argument(
        "--base",
        default=str(DEFAULT_BASE),
        help=f"meeting_system base path (default: {DEFAULT_BASE})",
    )
    sub = p.add_subparsers(dest="cmd", required=True)

    p_create = sub.add_parser("create", help="新規会議部屋を作成")
    p_create.add_argument("room_id")
    p_create.add_argument("--project", default="", help="表示名 (省略時 room_id)")
    p_create.add_argument("--color", default="#4F46E5")
    p_create.add_argument("--icon", default="💬")
    p_create.add_argument("--cdp-port", type=int, default=9222)
    p_create.set_defaults(func=cmd_create)

    p_list = sub.add_parser("list", help="既存会議部屋一覧")
    p_list.set_defaults(func=cmd_list)

    p_delete = sub.add_parser("delete", help="会議部屋削除 (--yes必須)")
    p_delete.add_argument("room_id")
    p_delete.add_argument("--yes", action="store_true")
    p_delete.set_defaults(func=cmd_delete)

    args = p.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
