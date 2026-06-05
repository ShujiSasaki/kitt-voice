"""議事録 round_table_v3.md を Round毎に分割 + INDEX生成

Round 46 で 議事録 7,400行/400KB に膨張、 GitHub の outline 出ない問題への対応。
"""
import re
from pathlib import Path

SRC = Path(__file__).parent.parent / "logs" / "round_table_v3.md"
DEST_DIR = Path(__file__).parent.parent / "logs" / "rounds"
DEST_DIR.mkdir(exist_ok=True)

with open(SRC) as f:
    content = f.read()

lines = content.split('\n')
current_round_num = None
current_lines = []
header_lines = []
rounds = {}

def round_match(line: str):
    m = re.match(r'^#+\s*(?:🚨\s*)?Round\s+(\d+)\s*[—‐―\-]', line)
    return int(m.group(1)) if m else None

for line in lines:
    rnum = round_match(line)
    if rnum is not None:
        if current_round_num is not None:
            rounds.setdefault(current_round_num, []).extend(current_lines)
        else:
            header_lines.extend(current_lines)
        current_round_num = rnum
        current_lines = [line]
    else:
        current_lines.append(line)

if current_round_num is not None:
    rounds.setdefault(current_round_num, []).extend(current_lines)
else:
    header_lines.extend(current_lines)

# Header保存
header_path = DEST_DIR / "_header.md"
with open(header_path, "w") as f:
    f.write('\n'.join(header_lines).rstrip() + '\n')
print(f"Header: {header_path.name} ({len(header_lines)}行)")

# 各 Round 保存
for rnum, lns in sorted(rounds.items()):
    fname = DEST_DIR / f"round_{rnum:02d}.md"
    with open(fname, "w") as f:
        f.write('\n'.join(lns).rstrip() + '\n')
    print(f"  Round {rnum:02d}: round_{rnum:02d}.md ({len(lns)}行)")

# INDEX
index_lines = [
    "# BTC danjer判断AI 3者会議 v3 — 議事録 INDEX",
    "",
    "開始: 2026-06-03",
    "",
    "**ファイル分割理由**: Round 46で議事録が 7,400行 (400KB) を超え、",
    "GitHub の outline が表示されなくなったため (Round 46 Shuji指摘)。",
    "今後の Round は `rounds/round_NN.md` として追加 + このINDEX更新。",
    "",
    "## 📂 構成",
    "",
    "- [_header.md](rounds/_header.md) — 会議ルール + Round 0 起点発言 + 初期議論",
    "- [rounds/](rounds/) — 各Round 個別ファイル (Round 1〜)",
    "",
    "## 📑 Round一覧",
    "",
]

for rnum in sorted(rounds.keys()):
    first_header = ""
    for line in rounds[rnum]:
        if line.startswith("##") or line.startswith("# "):
            cleaned = re.sub(r'^#+\s*', '', line).strip()
            m = re.match(r'(?:🚨\s*)?Round\s+\d+\s*[—‐―\-]\s*(.+)', cleaned)
            if m:
                first_header = m.group(1).strip()
            else:
                first_header = cleaned
            break
    summary = first_header[:80].rstrip()
    index_lines.append(f"- [Round {rnum:02d}](rounds/round_{rnum:02d}.md) — {summary}")

index_lines.extend([
    "",
    "---",
    "",
    "**運用**: 新規Roundは新規ファイル追加 + このINDEX更新。 ライブpush継続。",
    "",
])

# round_table_v3.md を INDEX に書き換え
with open(SRC, "w") as f:
    f.write('\n'.join(index_lines))
print(f"\nINDEX: {SRC.name} ({len(index_lines)}行)")
print(f"分割完了: {len(rounds)} Rounds")
