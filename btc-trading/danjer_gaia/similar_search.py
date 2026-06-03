"""
Project danjer-GAIA — 類似局面検索
====================================
現在の市場状態 → Gemini Embedding → cosine類似度で top-N 類似 danjer ポスト取得

3者会議 Phase 1.1 Day 7-8 合意:
- Top-3 類似局面+その後の値動き (ret_4h/12h/1d) を Slow Brain に渡す
- Phase 1.1 は numpy cosine で十分 (15,000件規模、 メモリ可能)
- Phase 2 以降に BQ Vector Search or pgvector に拡張
"""
from __future__ import annotations
import os
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Optional
import numpy as np


WORKDIR = Path('/Users/shuji/Desktop/kitt-voice/btc-trading/danjer_gaia/data')
EMBEDDINGS_FILE = WORKDIR / 'danjer_embeddings.npz'
META_FILE = WORKDIR / 'danjer_embeddings_meta.jsonl'
UNIFIED_FILE = WORKDIR / 'danjer_posts_unified.jsonl'


@dataclass
class SimilarMatch:
    tweet_id: str
    created_at: str
    similarity: float
    full_text: str
    reasoning: str
    ret_4h: Optional[float]
    ret_12h: Optional[float]
    ret_1d: Optional[float]
    ret_7d: Optional[float]


class SimilarSearcher:
    """類似ポスト検索インデックス"""

    def __init__(self):
        self.embeddings: Optional[np.ndarray] = None
        self.meta: list[dict] = []
        self.posts: dict[str, dict] = {}  # tweet_id → record

    def load(self):
        """既存のembedding と統合済 posts をメモリにロード"""
        if not EMBEDDINGS_FILE.exists():
            raise FileNotFoundError(f"{EMBEDDINGS_FILE} がない。 embed_posts.py 実行必須")

        npz = np.load(EMBEDDINGS_FILE)
        self.embeddings = npz['embeddings']
        # 正規化 (cosine類似のため)
        norms = np.linalg.norm(self.embeddings, axis=1, keepdims=True)
        self.embeddings = self.embeddings / np.where(norms > 0, norms, 1.0)

        with open(META_FILE) as f:
            self.meta = [json.loads(line) for line in f]

        # tweet_id → record for retrieval
        with open(UNIFIED_FILE) as f:
            for line in f:
                r = json.loads(line)
                self.posts[r['tweet_id']] = r

        print(f"Loaded: {self.embeddings.shape[0]} embeddings, "
              f"{len(self.posts)} total posts")

    def _embed_query(self, text: str) -> np.ndarray:
        """クエリテキストをベクトル化"""
        import google.generativeai as genai
        api_key = os.environ.get('GEMINI_API_KEY')
        if not api_key:
            # .env再ロード
            env_path = '/Users/shuji/Desktop/kitt-voice/.env'
            with open(env_path) as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith('#') and '=' in line:
                        k, v = line.split('=', 1)
                        os.environ[k.strip()] = v.strip().strip("'\"")
            api_key = os.environ.get('GEMINI_API_KEY')
        genai.configure(api_key=api_key)
        r = genai.embed_content(
            model='models/gemini-embedding-001',
            content=text,
            task_type='RETRIEVAL_QUERY',
        )
        v = np.array(r['embedding'], dtype='float32')
        n = np.linalg.norm(v)
        return v / n if n > 0 else v

    def search(self, query_text: str, top_k: int = 3,
               min_similarity: float = 0.6) -> list[SimilarMatch]:
        """類似ポスト top-K取得 (cosine similarity)"""
        if self.embeddings is None:
            self.load()

        q = self._embed_query(query_text)
        sims = self.embeddings @ q  # 内積 (両方正規化済なのでcosine)
        # 降順 top_k
        top_idx = np.argsort(-sims)[:top_k]

        matches = []
        for idx in top_idx:
            sim = float(sims[idx])
            if sim < min_similarity:
                break
            m = self.meta[idx]
            tid = m['tweet_id']
            post = self.posts.get(tid, {})
            readings = post.get('readings', {})
            reasoning = ''
            for src in ('anthropic_new', 'gpt', 'claude_old'):
                r = readings.get(src)
                if r:
                    content = r.get('content', '')
                    try:
                        d = json.loads(content)
                        if 'reasoning' in d:
                            reasoning = d['reasoning']
                            break
                    except json.JSONDecodeError:
                        reasoning = content[:200]
                        break
            returns = post.get('returns', {})
            matches.append(SimilarMatch(
                tweet_id=tid,
                created_at=m['created_at'],
                similarity=sim,
                full_text=post.get('full_text', '')[:200],
                reasoning=reasoning,
                ret_4h=returns.get('ret_4h'),
                ret_12h=returns.get('ret_12h'),
                ret_1d=returns.get('ret_1d'),
                ret_7d=returns.get('ret_7d'),
            ))

        return matches

    def aggregate_outcomes(self, matches: list[SimilarMatch]) -> dict:
        """類似ポストの 投稿後リターンを集計"""
        if not matches:
            return {'count': 0, 'pf_estimate': None}

        rets_1d = [m.ret_1d for m in matches if m.ret_1d is not None]
        rets_4h = [m.ret_4h for m in matches if m.ret_4h is not None]
        if not rets_1d:
            return {'count': len(matches), 'pf_estimate': None}

        gains = [r for r in rets_1d if r > 0]
        losses = [-r for r in rets_1d if r < 0]
        if losses:
            pf = sum(gains) / sum(losses)
        else:
            pf = float('inf') if gains else 0.0

        return {
            'count': len(matches),
            'mean_ret_4h': sum(rets_4h) / len(rets_4h) if rets_4h else None,
            'mean_ret_1d': sum(rets_1d) / len(rets_1d),
            'win_rate_1d': sum(1 for r in rets_1d if r > 0) / len(rets_1d),
            'pf_estimate': pf,
            'max_ret_1d': max(rets_1d),
            'min_ret_1d': min(rets_1d),
        }


# CLI
if __name__ == '__main__':
    import sys
    if len(sys.argv) < 2:
        print("Usage: python3 similar_search.py 'クエリテキスト'")
        sys.exit(1)
    query = sys.argv[1]
    top_k = int(sys.argv[2]) if len(sys.argv) > 2 else 3

    searcher = SimilarSearcher()
    searcher.load()
    matches = searcher.search(query, top_k=top_k)

    print(f"Query: {query}\n")
    for i, m in enumerate(matches, 1):
        print(f"[{i}] sim={m.similarity:.3f} | {m.created_at}")
        print(f"    {m.full_text[:120]}...")
        print(f"    reasoning: {m.reasoning[:100]}")
        print(f"    ret_4h={m.ret_4h} ret_1d={m.ret_1d} ret_7d={m.ret_7d}")
        print()

    agg = searcher.aggregate_outcomes(matches)
    print(f"Aggregate: {json.dumps(agg, ensure_ascii=False, indent=2)}")
