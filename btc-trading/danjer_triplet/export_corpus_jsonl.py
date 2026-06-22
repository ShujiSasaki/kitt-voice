#!/usr/bin/env python3
# danjerクローンAI 生学習コーパス書き出し (¥0)
# danjer_bottomup 全件 → 2本のJSONL:
#   danjer_seed_materials.jsonl  … 全材料(知識: type/what/how/citation)
#   danjer_seed_reasoning.jsonl  … 全投稿の判断連鎖(combination + stance + topics)
# fine-tune / RAG どちらにも使える素の種。
import sqlite3, json, re

DB="/Users/shuji/Desktop/kitt-voice/btc-trading/btc_trading_ai.db"
OUT="/Users/shuji/Desktop/kitt-voice/btc-trading/danjer_triplet"

# トピック分類は教科書と同一の TAXO を流用
import importlib.util
spec=importlib.util.spec_from_file_location("bc",OUT+"/build_corpus.py")
# build_corpus は import時に main() が走るので TAXO だけ抜き出す
src=open(OUT+"/build_corpus.py").read()
m=re.search(r"TAXO = \{.*?\n\}",src,re.S)
TAXO=eval(m.group(0)[7:])

def g(d,k):
    v=d.get(k); return (v if isinstance(v,str) else "").strip()
def clean(s): return re.sub(r"\s+"," ",s).strip()
# 3者合意 Q4: 出典ラベル 本人 / AI画像
READOUT=["が表示されて","描画されて","描かれて","ローソク足は","チャートには","チャート上に",
         "価格スケール","現在の売値","現在の買値","現在価格を示す","と表示され","図が示され",
         "画像読取","画像:","スケールは右","の範囲。","ローソク足で"]
VOICE=["＠","⇒","→","1️⃣","2️⃣","3️⃣","背に","だぬ","かぬ","やぬ","ぬ。","ぬ！","ですぬ","w",
       "想定","狙","利確","損切","ロング","ショート","買い","売り","ここ","この後","と思","かな","です。","ます。"]
# 3者合意 Q4 正式仕様: source_type = danjer_text / image_reading / model_inference
def src_type(cite):
    if "画像読取" in cite or "画像:" in cite: return "image_reading"
    ro=sum(cite.count(x) for x in READOUT); vo=sum(1 for x in VOICE if x in cite)
    return "image_reading" if ro>vo else "danjer_text"
def topics_of(blob_set):
    out=[]
    for key,kws in TAXO.items():
        if any(kw in b for kw in kws for b in blob_set): out.append(key)
    return out

db=sqlite3.connect(DB); c=db.cursor()
rows=c.execute("SELECT tweet_id,posted_at_utc,regime,extract_json FROM danjer_bottomup WHERE extracted=1").fetchall()

fm=open(OUT+"/danjer_seed_materials.jsonl","w",encoding="utf-8")
fr=open(OUT+"/danjer_seed_reasoning.jsonl","w",encoding="utf-8")
nmat=0; nreas=0
for tid,dt,rg,js in rows:
    try: j=json.loads(js)
    except: continue
    if not isinstance(j,dict): continue
    day=(dt or "")[:10]
    blobs=set()
    for mat in j.get("materials",[]) or []:
        if not isinstance(mat,dict): continue
        what=g(mat,"what"); how=g(mat,"how"); cite=g(mat,"citation")
        if not (what or how or cite): continue
        blobs.add(" ".join([what,how,cite]))
        cclean=clean(cite)
        rec={"tweet_id":str(tid),"date":day,"regime":rg,
             "type":mat.get("type","?"),"what":clean(what),
             "citation":cclean,"source_type":src_type(cclean),  # danjer_text / image_reading
             "how":clean(how),"how_source_type":"model_inference"}  # how は常に推測
        fm.write(json.dumps(rec,ensure_ascii=False)+"\n"); nmat+=1
    combo=g(j,"combination"); stance=g(j,"stance")
    if combo:
        rec={"tweet_id":str(tid),"date":day,"regime":rg,
             "combination":clean(combo),"stance":clean(stance),
             "source_type":"model_inference",
             "topics":[t for t in topics_of(blobs)]}
        fr.write(json.dumps(rec,ensure_ascii=False)+"\n"); nreas+=1
fm.close(); fr.close()
print(f"materials.jsonl: {nmat} 行")
print(f"reasoning.jsonl: {nreas} 行")
