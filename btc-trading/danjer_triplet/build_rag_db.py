#!/usr/bin/env python3
# タスクA: RAG検索DB構築 (¥0・課金なし/埋め込み不要)
# danjer_rag_chunks.jsonl → SQLite FTS5(trigram=日本語部分一致) の検索DB。
# source_type を保持し、検索優先度 danjer_text > image_reading > model_inference。
import sqlite3, json, os

OUT="/Users/shuji/Desktop/kitt-voice/btc-trading/danjer_triplet"
SRC=OUT+"/danjer_rag_chunks.jsonl"
DB=OUT+"/danjer_rag.db"
RANK={"danjer_text":3,"image_reading":2,"model_inference":1}

if os.path.exists(DB): os.remove(DB)
db=sqlite3.connect(DB); c=db.cursor()
c.execute("""CREATE TABLE chunks(
  id TEXT PRIMARY KEY, kind TEXT, source_type TEXT, src_rank INT,
  technique TEXT, date TEXT, regime TEXT, text TEXT)""")
# trigram FTS = 日本語の部分一致検索が可能
c.execute("CREATE VIRTUAL TABLE chunks_fts USING fts5(text, tokenize='trigram', content='chunks', content_rowid='rowid')")

n=0
for l in open(SRC,encoding="utf-8"):
    d=json.loads(l)
    st=d.get("source_type","model_inference")
    tech=d.get("technique") or d.get("technique_type") or ""
    c.execute("INSERT INTO chunks(id,kind,source_type,src_rank,technique,date,regime,text) VALUES(?,?,?,?,?,?,?,?)",
        (d["id"],d.get("kind",""),st,RANK.get(st,1),tech,d.get("date",""),d.get("regime",""),d.get("text","")))
    n+=1
# FTS充填
c.execute("INSERT INTO chunks_fts(rowid,text) SELECT rowid,text FROM chunks")
c.execute("CREATE INDEX idx_src ON chunks(src_rank)")
c.execute("CREATE INDEX idx_kind ON chunks(kind)")
db.commit()
print(f"built danjer_rag.db: {n} chunks")
for r in c.execute("SELECT source_type,COUNT(*) FROM chunks GROUP BY source_type"):
    print("  ",r[0],r[1])
db.close()
