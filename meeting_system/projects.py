"""
projects — R60 ② プロジェクト単位管理 + 自動紐付け (3者合意 R59 loop=5)

データモデル (R59合意):
- project_id: 主キー (snake_case)
- repo_path: 絶対パス (Claude Code / Codex で起動時に自動マッチ)
- tool: claude_code / codex / manual / other
- room_id: 紐付ける会議室 (1 project ↔ 1 room、 1:1)
- participants / default_order: room設定の継承
- status: active / archived

格納先: data/projects.json (JSON単一ファイル、 atomic update)

自動紐付けロジック:
- 起動時に repo_path で完全一致 → 該当 room自動activate
- 完全一致なし & prefix一致1件 → 該当 room自動activate
- 曖昧 (prefix一致2件以上 or noなし) → 自動紐付けせず、 Shujiさん確認
"""
from __future__ import annotations

import json
import os
import tempfile
from datetime import datetime
from pathlib import Path

from .state_schema import DEFAULT_BASE, JST, read_state, write_state_atomic

ENC = "utf-8"


def _projects_path(base: Path) -> Path:
    return base / "data" / "projects.json"


def _read_projects(base: Path) -> dict:
    p = _projects_path(base)
    if not p.exists():
        return {"projects": []}
    try:
        return json.loads(p.read_text(encoding=ENC))
    except Exception:
        return {"projects": []}


def _write_projects(data: dict, base: Path) -> None:
    p = _projects_path(base)
    p.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        mode="w", encoding=ENC, dir=p.parent, delete=False,
        prefix=".tmp_projects_", suffix=".json",
    ) as tmp:
        json.dump(data, tmp, ensure_ascii=False, indent=2)
        tmp_path = Path(tmp.name)
    os.replace(tmp_path, p)


def list_projects(base: Path = DEFAULT_BASE) -> list[dict]:
    return _read_projects(base).get("projects", [])


def register_project(
    project_id: str,
    repo_path: str | None,
    tool: str,
    room_id: str,
    participants: list[str] | None = None,
    default_order: list[str] | None = None,
    base: Path = DEFAULT_BASE,
) -> dict:
    if not project_id or "/" in project_id or ".." in project_id:
        raise ValueError("invalid_project_id")
    if tool not in ("claude_code", "codex", "manual", "other"):
        raise ValueError(f"invalid_tool:{tool}")
    data = _read_projects(base)
    projects = data.setdefault("projects", [])
    # upsert
    existing = next((p for p in projects if p.get("project_id") == project_id), None)
    payload = {
        "project_id": project_id,
        "repo_path": (str(Path(repo_path).resolve()) if repo_path else None),
        "tool": tool,
        "room_id": room_id,
        "participants": participants or ["gpt", "gemini", "claude"],
        "default_order": default_order or ["gpt", "gemini", "claude"],
        "status": "active",
    }
    if existing:
        existing.update(payload)
        existing["updated_at"] = datetime.now(JST).isoformat()
    else:
        payload["created_at"] = datetime.now(JST).isoformat()
        projects.append(payload)
    _write_projects(data, base)
    # room側にも紐付け書き込み (R60 ②)
    try:
        st = read_state(room_id, base)
        st["project_id"] = project_id
        st["repo_path"] = payload["repo_path"]
        st["tool"] = tool
        st.setdefault("edit_history", []).append({
            "ts": datetime.now(JST).isoformat(),
            "editor": "system",
            "changes": [
                {"field": "project_id", "old": None, "new": project_id},
                {"field": "tool", "old": None, "new": tool},
            ],
        })
        write_state_atomic(room_id, st, base)
    except Exception:
        pass
    return payload


def find_project_by_path(
    cwd: str, base: Path = DEFAULT_BASE,
) -> dict | None:
    """R60 ②: 起動時自動紐付け。

    完全一致 → 1件返す
    prefix一致1件 → 1件返す
    曖昧 (prefix一致2件以上 or 何もなし) → None (Shuji確認に回す)
    """
    cwd_abs = str(Path(cwd).resolve())
    projects = list_projects(base)
    # 完全一致
    exact = [p for p in projects
             if p.get("repo_path") == cwd_abs and p.get("status") == "active"]
    if len(exact) == 1:
        return exact[0]
    if len(exact) > 1:
        return None  # 曖昧
    # prefix一致 (子ディレクトリから起動)
    prefix = [
        p for p in projects
        if p.get("repo_path")
        and cwd_abs.startswith(p["repo_path"] + os.sep)
        and p.get("status") == "active"
    ]
    if len(prefix) == 1:
        return prefix[0]
    return None


def self_test() -> bool:
    import shutil
    import tempfile as _tmp
    tmp_base = Path(_tmp.mkdtemp(prefix="projects_test_"))
    try:
        from .state_schema import create_room
        create_room("test_room", base=tmp_base)
        p = register_project(
            "test_proj", str(tmp_base), "manual", "test_room", base=tmp_base,
        )
        assert p["project_id"] == "test_proj"
        assert p["tool"] == "manual"
        # 完全一致
        found = find_project_by_path(str(tmp_base), base=tmp_base)
        assert found and found["project_id"] == "test_proj"
        # prefix一致 (subdir)
        sub = tmp_base / "sub"
        sub.mkdir()
        found2 = find_project_by_path(str(sub), base=tmp_base)
        assert found2 and found2["project_id"] == "test_proj"
        # 一致なし
        found3 = find_project_by_path("/tmp", base=tmp_base)
        assert found3 is None
        # room側 紐付け確認
        st = read_state("test_room", base=tmp_base)
        assert st.get("project_id") == "test_proj"
        print("PASS: projects self_test")
        return True
    finally:
        shutil.rmtree(tmp_base, ignore_errors=True)


if __name__ == "__main__":
    raise SystemExit(0 if self_test() else 1)
