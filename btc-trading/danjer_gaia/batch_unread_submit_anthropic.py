#!/usr/bin/env python3
"""
未読解14,468件 → Anthropic Batch API (Claude Haiku 4.5) で読解

- モデル: claude-haiku-4-5-20251001 (安価 + Session 45 と同モデル)
- Batch API: 50%割引
- 推定コスト: $0.5-1.5
- 推定時間: 24h以内
"""
import os
import sys
import json
import sqlite3
from pathlib import Path
from datetime import datetime


def load_env():
    env_path = '/Users/shuji/Desktop/kitt-voice/.env'
    with open(env_path) as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith('#') and '=' in line:
                k, v = line.split('=', 1)
                os.environ[k.strip()] = v.strip().strip("'\"")
load_env()


WORKDIR = Path('/Users/shuji/Desktop/kitt-voice/btc-trading/danjer_gaia/batch_input')
WORKDIR.mkdir(exist_ok=True, parents=True)

UNREAD_IDS_FILE = WORKDIR / 'unread_tweet_ids.json'
BATCH_ID_FILE = WORKDIR / 'anthropic_batch_id.json'
BATCH_OUTPUT_FILE = WORKDIR / 'anthropic_batch_output.jsonl'

SQLITE_DB = '/Users/shuji/Desktop/kitt-voice/btc-trading/x_tweets.db'

SYSTEM_PROMPT = """あなたはBitcoin相場分析の専門家。 danjer氏 (smile_danjer) のX投稿を読解する。

判定項目 (JSON で返す):
- is_trading_decision (bool): 投資判断関連か (true/false)
- category (str): 'entry_signal'/'exit'/'warning'/'cycle_view'/'macro'/'chart_pattern'/'sentiment'/'chat'/'meta'
- direction (str): 'long'/'short'/'neutral'/'wait'
- timeframe (str): 'scalp'/'short'/'mid'/'long'/'cycle'
- confidence (float): 0.0-1.0
- key_indicators (list[str]): 言及テクニカル指標 (MA/RSI/MACD/FR/OI/フィボ/エリオット/サイクル等)
- reasoning (str): 100文字以内 要旨

出力は JSON のみ。 余計な解説禁止。 「投資判断」=具体的なエントリー/エグジット/警戒/方向感の表明。 雑談・個人事情・冗談は false。"""

USER_TEMPLATE = "投稿日時: {created_at}\n投稿本文:\n{text}\n\n上記JSONで読解結果のみ返答。"


def submit_batch():
    """Anthropic Batch APIに直接投入 (リスト形式)"""
    try:
        from anthropic import Anthropic
    except ImportError:
        print("ERROR: pip3 install --break-system-packages anthropic")
        sys.exit(1)

    if not UNREAD_IDS_FILE.exists():
        print(f"ERROR: {UNREAD_IDS_FILE} がない")
        sys.exit(1)

    unread_ids = json.loads(UNREAD_IDS_FILE.read_text())
    print(f"未読解 ID数: {len(unread_ids)}")

    # SQLite から本文取得 → リクエスト構築
    conn = sqlite3.connect(SQLITE_DB)
    cur = conn.cursor()

    requests_list = []
    skipped = 0
    for tid in unread_ids:
        cur.execute(
            "SELECT tweet_id, created_at, full_text FROM tweets "
            "WHERE tweet_id=? AND screen_name='smile_danjer'",
            (tid,)
        )
        row = cur.fetchone()
        if not row:
            skipped += 1
            continue
        tweet_id, created_at, full_text = row
        if not full_text or len(full_text.strip()) < 5:
            skipped += 1
            continue

        requests_list.append({
            "custom_id": f"tweet_{tweet_id}",
            "params": {
                "model": "claude-haiku-4-5-20251001",
                "max_tokens": 400,
                "system": SYSTEM_PROMPT,
                "messages": [
                    {"role": "user", "content": USER_TEMPLATE.format(
                        created_at=created_at, text=full_text)}
                ],
            }
        })

    conn.close()
    print(f"準備完了: {len(requests_list)}件 / スキップ: {skipped}件")

    # Anthropic Batch API は 1リクエストあたり 100,000件まで
    # 14,000件なら 1バッチでOK
    client = Anthropic()
    print(f"\nAnthropic Batch API投入中...")
    batch = client.messages.batches.create(requests=requests_list)
    print(f"\n✅ Batch投入完了: id={batch.id}")
    print(f"   processing_status: {batch.processing_status}")
    print(f"   request_counts: {batch.request_counts}")

    BATCH_ID_FILE.write_text(json.dumps({
        "batch_id": batch.id,
        "submitted_at": datetime.utcnow().isoformat(),
        "model": "claude-haiku-4-5-20251001",
        "request_count": len(requests_list),
        "skipped": skipped,
    }, indent=2))
    print(f"   ID保存: {BATCH_ID_FILE}")


def check_status():
    from anthropic import Anthropic
    info = json.loads(BATCH_ID_FILE.read_text())
    client = Anthropic()
    batch = client.messages.batches.retrieve(info['batch_id'])
    print(f"batch_id: {batch.id}")
    print(f"  processing_status: {batch.processing_status}")
    print(f"  request_counts: {batch.request_counts}")
    print(f"  created_at: {batch.created_at}")
    if batch.ended_at:
        print(f"  ended_at: {batch.ended_at}")


def download_output():
    from anthropic import Anthropic
    info = json.loads(BATCH_ID_FILE.read_text())
    client = Anthropic()
    batch = client.messages.batches.retrieve(info['batch_id'])
    if batch.processing_status != 'ended':
        print(f"ERROR: まだ {batch.processing_status} 状態")
        return
    # Results をストリーミングで取得 (JSONL)
    n = 0
    with open(BATCH_OUTPUT_FILE, 'w') as fout:
        for result in client.messages.batches.results(info['batch_id']):
            fout.write(json.dumps(result.model_dump(), ensure_ascii=False) + '\n')
            n += 1
    print(f"✅ ダウンロード完了: {BATCH_OUTPUT_FILE} ({n}件)")


if __name__ == '__main__':
    cmd = sys.argv[1] if len(sys.argv) > 1 else 'help'
    if cmd == 'submit':
        submit_batch()
    elif cmd == 'status':
        check_status()
    elif cmd == 'download':
        download_output()
    else:
        print("Usage: python3 batch_unread_submit_anthropic.py [submit|status|download]")
