#!/usr/bin/env python3
"""
Project danjer-GAIA — Data Pipeline
====================================
既存の読解結果を統合し、 v3 用のデータ形式に変換するパイプライン。

入力:
- 既存17,650件 GPT読解: /Users/shuji/Desktop/btc-trading/danjer_gpt_readings_all.jsonl
- 既存17,650件 Claude読解: /Users/shuji/Desktop/btc-trading/danjer_claude_readings_all.jsonl
- 新規14,200件 Anthropic Batch読解: btc-trading/danjer_gaia/batch_input/anthropic_batch_output.jsonl
- SQLite x_tweets.db (本文・投稿時刻)
- SQLite tweet_market (投稿後リターン)
- danjer_market_contexts.json (市場コンテキスト)

出力:
- btc-trading/danjer_gaia/data/danjer_posts_unified.jsonl
  各レコード = 1ポスト + 読解結果(GPT/Claude/Anthropic) + 市場コンテキスト + 投稿後リターン

実行: python3 data_pipeline.py unify  # 全件統合
"""
from __future__ import annotations
import os
import sys
import json
import sqlite3
from pathlib import Path
from datetime import datetime


WORKDIR = Path('/Users/shuji/Desktop/kitt-voice/btc-trading/danjer_gaia/data')
WORKDIR.mkdir(exist_ok=True, parents=True)

OUTPUT_FILE = WORKDIR / 'danjer_posts_unified.jsonl'

# 既存読解結果
GPT_READINGS = '/Users/shuji/Desktop/btc-trading/danjer_gpt_readings_all.jsonl'
CLAUDE_READINGS = '/Users/shuji/Desktop/btc-trading/danjer_claude_readings_all.jsonl'
MARKET_CONTEXTS = '/Users/shuji/Desktop/btc-trading/danjer_market_contexts.json'

# 新規 Anthropic Batch 結果
ANTHROPIC_BATCH_OUTPUT = '/Users/shuji/Desktop/kitt-voice/btc-trading/danjer_gaia/batch_input/anthropic_batch_output.jsonl'

SQLITE_DB = '/Users/shuji/Desktop/kitt-voice/btc-trading/x_tweets.db'


def load_existing_readings(path: str, source: str) -> dict[str, dict]:
    """既存読解 jsonl を tweet_id → reading dict にロード
    実フォーマット: {tweet_id, created_at, raw_text, image_url, has_image, gpt_reading}
    """
    result = {}
    if not Path(path).exists():
        print(f"WARN: {path} not found, skipping {source}")
        return result
    # 読解結果のフィールド名は source によって異なる
    reading_field = 'gpt_reading' if 'gpt' in source else 'claude_reading'
    with open(path) as f:
        for line in f:
            try:
                d = json.loads(line)
                tid = str(d.get('tweet_id', ''))
                if not tid:
                    continue
                content = d.get(reading_field) or d.get('gpt_reading') or d.get('claude_reading') or ''
                if content:
                    result[tid] = {
                        'source': source,
                        'content': content,
                        'has_image': d.get('has_image', False),
                    }
            except Exception:
                pass
    print(f"  {source}: {len(result)}件 ロード")
    return result


def load_anthropic_batch_output() -> dict[str, dict]:
    """Anthropic Batch出力を tweet_id → reading にロード"""
    result = {}
    if not Path(ANTHROPIC_BATCH_OUTPUT).exists():
        print(f"  Anthropic Batch: {ANTHROPIC_BATCH_OUTPUT} まだない (Batch未完了)")
        return result
    with open(ANTHROPIC_BATCH_OUTPUT) as f:
        for line in f:
            try:
                d = json.loads(line)
                cid = d.get('custom_id', '')
                tid = cid.replace('tweet_', '') if cid.startswith('tweet_') else cid
                # Anthropic Batch format: result.message.content[0].text
                res = d.get('result', {})
                if res.get('type') == 'succeeded':
                    msg = res.get('message', {})
                    content_list = msg.get('content', [])
                    if content_list:
                        text = content_list[0].get('text', '')
                        result[tid] = {
                            'source': 'anthropic-haiku-4.5',
                            'content': text,
                        }
            except Exception:
                pass
    print(f"  Anthropic Batch: {len(result)}件 ロード")
    return result


def load_market_contexts() -> dict[str, dict]:
    """市場コンテキスト (BTC価格/MA/RSI/MACD/FR) を tweet_id → ctx"""
    if not Path(MARKET_CONTEXTS).exists():
        return {}
    with open(MARKET_CONTEXTS) as f:
        return json.load(f)


def unify_all():
    """全データ統合"""
    print("=== Data Pipeline: 統合開始 ===\n")

    print("1. 既存読解 ロード")
    gpt = load_existing_readings(GPT_READINGS, 'gpt-4.1-mini')
    claude_old = load_existing_readings(CLAUDE_READINGS, 'claude-haiku-4.5-old')
    anthropic_new = load_anthropic_batch_output()

    print(f"\n2. 市場コンテキスト ロード")
    contexts = load_market_contexts()
    print(f"  market_contexts: {len(contexts)}件")

    print(f"\n3. SQLite から本文・投稿後リターン取得")
    conn = sqlite3.connect(SQLITE_DB)
    cur = conn.cursor()
    cur.execute("""
        SELECT t.tweet_id, t.created_at, t.full_text, t.is_retweet, t.is_quote,
               t.favorite_count, t.retweet_count,
               m.btc_price, m.ret_4h, m.ret_12h, m.ret_1d, m.ret_2d,
               m.ret_3d, m.ret_7d, m.ret_30d, m.ret_90d
        FROM tweets t
        LEFT JOIN tweet_market m ON t.tweet_id = m.tweet_id
        WHERE t.screen_name='smile_danjer' AND t.is_retweet=0
    """)
    rows = cur.fetchall()
    print(f"  tweets: {len(rows)}件")
    conn.close()

    print(f"\n4. 統合 (1ポスト = 既存読解+新読解+市場+リターン)")
    written = 0
    with open(OUTPUT_FILE, 'w') as fout:
        for row in rows:
            tid = row[0]
            record = {
                'tweet_id': tid,
                'created_at': row[1],
                'full_text': row[2],
                'is_retweet': row[3],
                'is_quote': row[4],
                'favorite_count': row[5],
                'retweet_count': row[6],
                'market_at_post': {
                    'btc_price': row[7],
                },
                'returns': {
                    'ret_4h': row[8], 'ret_12h': row[9], 'ret_1d': row[10],
                    'ret_2d': row[11], 'ret_3d': row[12], 'ret_7d': row[13],
                    'ret_30d': row[14], 'ret_90d': row[15],
                },
                'readings': {},
            }
            if tid in gpt:
                record['readings']['gpt'] = gpt[tid]
            if tid in claude_old:
                record['readings']['claude_old'] = claude_old[tid]
            if tid in anthropic_new:
                record['readings']['anthropic_new'] = anthropic_new[tid]
            if tid in contexts:
                record['market_context'] = contexts[tid]
            fout.write(json.dumps(record, ensure_ascii=False) + '\n')
            written += 1

    print(f"\n✅ 統合完了: {OUTPUT_FILE} ({written}件)")

    # 統計
    stats = {
        'total_posts': written,
        'with_gpt_reading': sum(1 for tid in (r[0] for r in rows) if tid in gpt),
        'with_claude_old_reading': sum(1 for tid in (r[0] for r in rows) if tid in claude_old),
        'with_anthropic_new_reading': sum(1 for tid in (r[0] for r in rows) if tid in anthropic_new),
        'with_market_context': sum(1 for tid in (r[0] for r in rows) if tid in contexts),
    }
    stats_path = WORKDIR / 'unify_stats.json'
    stats_path.write_text(json.dumps(stats, indent=2))
    print(f"\n統計:\n{json.dumps(stats, indent=2)}")


if __name__ == '__main__':
    cmd = sys.argv[1] if len(sys.argv) > 1 else 'help'
    if cmd == 'unify':
        unify_all()
    else:
        print("Usage: python3 data_pipeline.py unify")
