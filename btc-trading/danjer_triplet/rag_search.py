#!/usr/bin/env python3
# タスクA: RAG検索インターフェース (¥0)
# danjer_rag.db を検索。本人の言葉(danjer_text)を最優先、
# 回答は出典(source_type)別に分けて表示=本人引用とAI推測を混ぜない。
# 使い方: python3 rag_search.py "OI 急騰 ショートカバー" [--k 8]
import sqlite3, sys, re

DB="/Users/shuji/Desktop/kitt-voice/btc-trading/danjer_triplet/danjer_rag.db"
LABEL={"danjer_text":"本人(danjer)","image_reading":"AI画像読取","model_inference":"AI推測(整理)"}

def fts_query(q):
    # trigram FTS: 語をスペース区切りでAND、3文字未満は無視されるので連結も試す
    terms=[t for t in re.split(r"\s+",q.strip()) if t]
    parts=[f'"{t}"' for t in terms if len(t)>=3]
    if not parts: parts=[f'"{q.strip()}"']
    return " ".join(parts)

def search(q,k=8):
    """出典別クォータ検索: 本人(danjer_text)を最優先で多く、AI推測(判断連鎖)も
    補助として必ず数件拾う。各source_type内は関連度(bm25)順。混ぜず分離して返す。
    """
    db=sqlite3.connect(DB); c=db.cursor()
    m=fts_query(q)
    # 本人を厚く、補助(推測/画像)も確保するクォータ
    quota={"danjer_text":max(k, 6), "model_inference":max(2, k//3), "image_reading":2}
    rows=[]
    for st,lim in quota.items():
        rs=c.execute("""
          SELECT ch.source_type, ch.src_rank, ch.kind, ch.technique, ch.date, ch.regime, ch.text,
                 bm25(chunks_fts) AS score
          FROM chunks_fts JOIN chunks ch ON ch.rowid=chunks_fts.rowid
          WHERE chunks_fts MATCH ? AND ch.source_type=?
          ORDER BY score ASC LIMIT ?""",(m,st,lim)).fetchall()
        rows.extend(rs)
    db.close()
    return rows

def main():
    if len(sys.argv)<2:
        print('usage: python3 rag_search.py "クエリ" [--k 8]'); return
    k=8
    if "--k" in sys.argv:
        k=int(sys.argv[sys.argv.index("--k")+1])
    q=sys.argv[1]
    rows=search(q,k)
    if not rows:
        print(f"(ヒットなし: {q})"); return
    # 出典別に分けて表示 (混ぜない)
    buckets={"danjer_text":[],"image_reading":[],"model_inference":[]}
    for r in rows:
        buckets[r[0]].append(r)
    print(f"=== 検索: {q} ===")
    for st in ["danjer_text","image_reading","model_inference"]:
        b=buckets[st][:k]
        if not b: continue
        print(f"\n■ 出典: {LABEL[st]} ({len(b)}件)")
        for r in b:
            txt=r[6].replace("\n"," ")
            tech=f"[{r[3]}] " if (r[3] and not txt.startswith("[")) else ""
            meta=f"{r[4]}/{r[5]}" if r[4] else r[2]
            print(f"  〈{meta}〉{tech}{txt[:140]}")

if __name__=="__main__":
    main()
