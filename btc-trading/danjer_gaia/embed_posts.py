#!/usr/bin/env python3
"""
Project danjer-GAIA — Embedding 投稿ベクトル化
================================================
統合済 danjer_posts_unified.jsonl を読み込み、 投資判断ポストを Gemini Embedding APIで
ベクトル化して numpy ファイルに保存。

モデル: text-multilingual-embedding-002 (768dim、 日本語+英語混在に強い)
コスト: $0.00001 / 1k tokens (input)
推定: 15,000件 × 平均500 tokens ≒ 7.5M tokens × $0.00001 = $0.075

実行:
  python3 embed_posts.py --filter-trading-only  # 投資判断のみ
  python3 embed_posts.py --all                  # 全件
"""
from __future__ import annotations
import os
import sys
import json
import argparse
from pathlib import Path
import time


WORKDIR = Path('/Users/shuji/Desktop/kitt-voice/btc-trading/danjer_gaia/data')
UNIFIED_FILE = WORKDIR / 'danjer_posts_unified.jsonl'
EMBEDDINGS_FILE = WORKDIR / 'danjer_embeddings.npz'
META_FILE = WORKDIR / 'danjer_embeddings_meta.jsonl'


def load_env():
    env_path = '/Users/shuji/Desktop/kitt-voice/.env'
    with open(env_path) as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith('#') and '=' in line:
                k, v = line.split('=', 1)
                os.environ[k.strip()] = v.strip().strip("'\"")
load_env()


def is_trading_decision(record: dict) -> bool:
    """読解結果から投資判断ポストかを判定 (簡易版)
    LLM分類が JSON で返っていれば is_trading_decision フラグを見る
    """
    readings = record.get('readings', {})

    # Anthropic Batch (新規) の結果を優先 (JSON強制)
    for source_key in ('anthropic_new', 'gpt', 'claude_old'):
        r = readings.get(source_key)
        if not r:
            continue
        content = r.get('content', '')
        if not content:
            continue
        # JSONとしてparseを試みる
        try:
            data = json.loads(content)
            if isinstance(data, dict) and 'is_trading_decision' in data:
                return bool(data['is_trading_decision'])
        except json.JSONDecodeError:
            # JSON でない場合は キーワード判定 (フォールバック)
            content_lower = content.lower()
            keywords = ['ロング', 'ショート', 'long', 'short',
                       'エントリー', 'entry', '損切', 'sl',
                       '利確', 'tp', 'take profit',
                       'ターゲット', 'target', 'ブレイク', 'breakout',
                       '反転', 'reversal', 'ピボット', 'pivot']
            if any(k in content_lower for k in keywords):
                return True

    # 読解結果がない場合は False (デフォルト除外)
    return False


def make_embedding_text(record: dict) -> str:
    """ベクトル化用のテキストを構築 (本文+市場コンテキスト+読解要旨)"""
    parts = []
    full_text = record.get('full_text', '')
    parts.append(f"POST: {full_text}")

    mc = record.get('market_context')
    if mc:
        # market_context は str (テキスト形式) または dict のどちらか
        if isinstance(mc, str):
            parts.append(f"MARKET: {mc[:300]}")
        elif isinstance(mc, dict):
            ctx_str = ' / '.join(f"{k}={v}" for k, v in mc.items()
                                if v is not None and k in ('btc_price', 'ma_50', 'ma_200', 'rsi', 'funding_rate'))
            if ctx_str:
                parts.append(f"MARKET: {ctx_str}")

    # 読解要旨 (anthropic_new > gpt > claude_old の優先順)
    readings = record.get('readings', {})
    for source in ('anthropic_new', 'gpt', 'claude_old'):
        r = readings.get(source)
        if r and r.get('content'):
            # JSON ならreasoningだけ、 自然文ならそのまま (短く)
            content = r['content']
            try:
                d = json.loads(content)
                if 'reasoning' in d:
                    parts.append(f"READING: {d['reasoning']}")
                    break
            except json.JSONDecodeError:
                parts.append(f"READING: {content[:200]}")
                break

    return '\n'.join(parts)


def embed_batch(texts: list[str], model: str = 'text-multilingual-embedding-002') -> list[list[float]]:
    """Gemini Embedding API でバッチベクトル化"""
    import google.generativeai as genai
    api_key = os.environ.get('GEMINI_API_KEY')
    if not api_key:
        raise RuntimeError("GEMINI_API_KEY not set")
    genai.configure(api_key=api_key)
    # Gemini SDK で embed_content を 1件ずつ呼び出し (Batch API は別)
    # text-multilingual-embedding-002 は Vertex経由が標準だが、 simpler は genai
    # 簡易: text-embedding-004 を使用 (genai SDK標準)
    results = []
    for text in texts:
        try:
            r = genai.embed_content(
                model='models/gemini-embedding-001',
                content=text,
                task_type='RETRIEVAL_DOCUMENT',
            )
            results.append(r['embedding'])
        except Exception as e:
            print(f"  ERROR embedding: {e}")
            results.append(None)
    return results


def run(filter_trading_only: bool = True, max_records: int = None,
        batch_size: int = 50, dry_run: bool = False):
    """メイン処理"""
    if not UNIFIED_FILE.exists():
        print(f"ERROR: {UNIFIED_FILE} がない。 先に data_pipeline.py unify を実行")
        sys.exit(1)

    print(f"=== Embedding 投稿ベクトル化 ===")
    print(f"  filter_trading_only: {filter_trading_only}")
    print(f"  max_records: {max_records or 'all'}")
    print(f"  dry_run: {dry_run}")
    print()

    # 全件読み込み + フィルタ
    records = []
    n_total = 0
    with open(UNIFIED_FILE) as f:
        for line in f:
            n_total += 1
            r = json.loads(line)
            if filter_trading_only and not is_trading_decision(r):
                continue
            records.append(r)
            if max_records and len(records) >= max_records:
                break

    print(f"  全件: {n_total} / フィルタ後: {len(records)}")

    if dry_run:
        # サンプル出力
        if records:
            print("\nサンプル ベクトル化テキスト (1件目):")
            print(make_embedding_text(records[0])[:500])
        return

    # Embedding
    import numpy as np
    print(f"\n  Embedding 中...")
    all_vecs = []
    meta = []
    start = time.time()
    for i in range(0, len(records), batch_size):
        batch = records[i:i + batch_size]
        texts = [make_embedding_text(r) for r in batch]
        vecs = embed_batch(texts)
        for r, v in zip(batch, vecs):
            if v is not None:
                all_vecs.append(v)
                meta.append({'tweet_id': r['tweet_id'], 'created_at': r['created_at']})
        if (i // batch_size) % 10 == 0:
            elapsed = time.time() - start
            rate = (i + batch_size) / elapsed if elapsed > 0 else 0
            print(f"    {i + batch_size}/{len(records)}件 ({rate:.1f} rec/s)")

    print(f"\n  保存中...")
    arr = np.array(all_vecs, dtype='float32')
    np.savez_compressed(EMBEDDINGS_FILE, embeddings=arr)
    with open(META_FILE, 'w') as f:
        for m in meta:
            f.write(json.dumps(m, ensure_ascii=False) + '\n')

    print(f"\n✅ 完了: {EMBEDDINGS_FILE}")
    print(f"   shape: {arr.shape}")
    print(f"   meta: {META_FILE} ({len(meta)}件)")


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--filter-trading-only', action='store_true', default=True)
    parser.add_argument('--all', action='store_true')
    parser.add_argument('--max', type=int)
    parser.add_argument('--batch-size', type=int, default=50)
    parser.add_argument('--dry-run', action='store_true')
    args = parser.parse_args()

    filter_only = not args.all
    run(filter_trading_only=filter_only, max_records=args.max,
        batch_size=args.batch_size, dry_run=args.dry_run)
