#!/usr/bin/env python3
"""
未読解14,468件のdanjer投稿を OpenAI Batch API で読解依頼するスクリプト
- モデル: gpt-4.1-mini (50% off)
- 推定コスト: $0.5-1
- 推定時間: 6-12時間 (Batchは最大24h)
- 出力: batch_input/unread_batch_input.jsonl (Batch投入用)
       batch_input/unread_batch_id.json (job ID保存)

実行方法:
  1. python3 batch_unread_submit.py prepare  # JSONL作成
  2. python3 batch_unread_submit.py submit   # OpenAI投入
  3. python3 batch_unread_submit.py status   # 進捗確認
  4. python3 batch_unread_submit.py download # 完了後ダウンロード
"""
import os
import sys
import json
import sqlite3
from pathlib import Path
from datetime import datetime

# .env 読み込み
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
BATCH_INPUT_FILE = WORKDIR / 'unread_batch_input.jsonl'
BATCH_ID_FILE = WORKDIR / 'unread_batch_id.json'
BATCH_OUTPUT_FILE = WORKDIR / 'unread_batch_output.jsonl'

SQLITE_DB = '/Users/shuji/Desktop/kitt-voice/btc-trading/x_tweets.db'

SYSTEM_PROMPT = """あなたはBitcoin相場分析の専門家。 danjer氏 (smile_danjer) のX投稿を読解する。

判定項目:
- is_trading_decision (bool): 投資判断関連か (true/false)
- category (str): 'entry_signal'/'exit'/'warning'/'cycle_view'/'macro'/'chart_pattern'/'sentiment'/'chat'/'meta'
- direction (str): 'long'/'short'/'neutral'/'wait'
- timeframe (str): 'scalp'/'short'/'mid'/'long'/'cycle' (分〜年単位)
- confidence (float): 0.0-1.0 (danjerの確信度)
- key_indicators (list[str]): 言及されているテクニカル指標 (MA/RSI/MACD/FR/OI/フィボ/エリオット/サイクル等)
- reasoning (str): 100文字以内で danjerの主張要旨

出力は JSON のみ。 余計な解説禁止。 「投資判断」とは具体的なエントリー/エグジット/警戒/方向感の表明。 雑談・個人事情・冗談は false。"""

USER_TEMPLATE = "投稿日時: {created_at}\n投稿本文:\n{text}"


def prepare_batch():
    """SQLite から本文を取得して JSONL を作成"""
    if not UNREAD_IDS_FILE.exists():
        print(f"ERROR: {UNREAD_IDS_FILE} がない。 先に未読解ID抽出が必要")
        sys.exit(1)

    unread_ids = json.loads(UNREAD_IDS_FILE.read_text())
    print(f"未読解 ID数: {len(unread_ids)}")

    conn = sqlite3.connect(SQLITE_DB)
    cur = conn.cursor()

    written = 0
    skipped = 0
    with open(BATCH_INPUT_FILE, 'w') as fout:
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

            req = {
                "custom_id": f"tweet_{tweet_id}",
                "method": "POST",
                "url": "/v1/chat/completions",
                "body": {
                    "model": "gpt-4.1-mini",
                    "messages": [
                        {"role": "system", "content": SYSTEM_PROMPT},
                        {"role": "user", "content": USER_TEMPLATE.format(
                            created_at=created_at, text=full_text)}
                    ],
                    "max_tokens": 400,
                    "temperature": 0.1,
                    "response_format": {"type": "json_object"},
                },
            }
            fout.write(json.dumps(req, ensure_ascii=False) + '\n')
            written += 1
            if written % 1000 == 0:
                print(f"  {written}件...")

    conn.close()
    print(f"\n✅ JSONL作成完了: {BATCH_INPUT_FILE}")
    print(f"   書き込み: {written}件 / スキップ: {skipped}件")
    print(f"   ファイルサイズ: {BATCH_INPUT_FILE.stat().st_size / 1024 / 1024:.2f} MB")


def submit_batch():
    """OpenAI Batch APIに投入"""
    try:
        from openai import OpenAI
    except ImportError:
        print("ERROR: pip3 install openai")
        sys.exit(1)

    client = OpenAI()

    # ファイル upload
    print(f"ファイルアップロード: {BATCH_INPUT_FILE}")
    with open(BATCH_INPUT_FILE, 'rb') as f:
        file_obj = client.files.create(file=f, purpose='batch')
    print(f"  file_id: {file_obj.id}")

    # Batch job 作成
    batch = client.batches.create(
        input_file_id=file_obj.id,
        endpoint="/v1/chat/completions",
        completion_window="24h",
        metadata={
            "project": "danjer-gaia",
            "purpose": "unread_14468_classification",
            "created_at": datetime.utcnow().isoformat(),
        },
    )
    print(f"\n✅ Batch投入完了: batch_id={batch.id}")
    print(f"   status: {batch.status}")
    print(f"   推定完了: {batch.completion_window}")

    # ID保存
    BATCH_ID_FILE.write_text(json.dumps({
        "batch_id": batch.id,
        "file_id": file_obj.id,
        "submitted_at": datetime.utcnow().isoformat(),
        "model": "gpt-4.1-mini",
        "estimated_count": 14468,
    }, indent=2))
    print(f"   ID保存: {BATCH_ID_FILE}")


def check_status():
    from openai import OpenAI
    if not BATCH_ID_FILE.exists():
        print(f"ERROR: {BATCH_ID_FILE} がない")
        return
    info = json.loads(BATCH_ID_FILE.read_text())
    client = OpenAI()
    batch = client.batches.retrieve(info['batch_id'])
    print(f"batch_id: {batch.id}")
    print(f"  status: {batch.status}")
    print(f"  request_counts: {batch.request_counts}")
    print(f"  created_at: {batch.created_at}")
    if batch.completed_at:
        print(f"  completed_at: {batch.completed_at}")
    if batch.output_file_id:
        print(f"  output_file_id: {batch.output_file_id}")


def download_output():
    from openai import OpenAI
    info = json.loads(BATCH_ID_FILE.read_text())
    client = OpenAI()
    batch = client.batches.retrieve(info['batch_id'])
    if batch.status != 'completed':
        print(f"ERROR: まだ {batch.status} 状態")
        return
    output_id = batch.output_file_id
    content = client.files.content(output_id).text
    BATCH_OUTPUT_FILE.write_text(content)
    n_lines = sum(1 for _ in content.split('\n') if _.strip())
    print(f"✅ ダウンロード完了: {BATCH_OUTPUT_FILE} ({n_lines}件)")


if __name__ == '__main__':
    cmd = sys.argv[1] if len(sys.argv) > 1 else 'help'
    if cmd == 'prepare':
        prepare_batch()
    elif cmd == 'submit':
        submit_batch()
    elif cmd == 'status':
        check_status()
    elif cmd == 'download':
        download_output()
    else:
        print("Usage: python3 batch_unread_submit.py [prepare|submit|status|download]")
