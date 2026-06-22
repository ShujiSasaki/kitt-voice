#!/usr/bin/env python3
# danjerクローンAI 学習フォーマット整形 (¥0) — 3者合意 Q5 次段
# danjer_bottomup から 2種の学習データを生成。全レコードに source_type を付与
# (3者合意 Q4/Q5: 画像幻覚の継承防止)。
#   danjer_rag_chunks.jsonl … RAG検索用チャンク(教科書ルール/材料/判断連鎖)
#   danjer_sft.jsonl        … fine-tune用 input→output 会話ペア(観測→danjerの読み)
import sqlite3, json, re

DB="/Users/shuji/Desktop/kitt-voice/btc-trading/btc_trading_ai.db"
OUT="/Users/shuji/Desktop/kitt-voice/btc-trading/danjer_triplet"

# TAXO / PROSE を既存スクリプトから抽出(再実装しない)
def _grab(path, var):
    src=open(path).read()
    m=re.search(var+r" *= *\{.*?\n\}", src, re.S)
    return eval(m.group(0)[len(var):].split("=",1)[1])
TAXO=_grab(OUT+"/build_corpus.py","TAXO")
PROSE=_grab(OUT+"/generate_textbook.py","PROSE")

def g(d,k):
    v=d.get(k); return (v if isinstance(v,str) else "").strip()
def clean(s): return re.sub(r"\s+"," ",s).strip()
READOUT=["が表示されて","描画されて","描かれて","ローソク足は","チャートには","チャート上に",
         "価格スケール","現在の売値","現在の買値","現在価格を示す","と表示され","図が示され",
         "画像読取","画像:","スケールは右","の範囲。","ローソク足で"]
VOICE=["＠","⇒","→","1️⃣","2️⃣","3️⃣","背に","だぬ","かぬ","やぬ","ぬ。","ぬ！","ですぬ","w",
       "想定","狙","利確","損切","ロング","ショート","買い","売り","ここ","この後","と思","かな","です。","ます。"]
def src_type(cite):
    if "画像読取" in cite or "画像:" in cite: return "image_reading"
    ro=sum(cite.count(x) for x in READOUT); vo=sum(1 for x in VOICE if x in cite)
    return "image_reading" if ro>vo else "danjer_text"
def topics_of(blobs):
    return [k for k,kw in TAXO.items() if any(w in b for w in kw for b in blobs)]

SYS=("あなたはBTCトレーダー「danjer」の思考を学習したクローンAI。"
     "danjerの手法(水平線/レンジ・ブレイク/トレンドライン/一目雲/移動平均・グランビル/"
     "サイクル理論/フラクタル/エリオット/チャートパターン/ローソク足/フィボ半値/CME窓/"
     "煮詰まり・IVバンド/オシレーター、需給=OI公式・FR・清算・踏み上げ、アノマリー、"
     "板読み・オプション・出来高・VRVP・Coinbase Premium)を複数組み合わせて相場を読む。"
     "単一指標で判断せず、必ず需給(OI/FR/清算)を重ね、最後に背(損切り)とリスクリワード1:2以上、"
     "条件未達なら見送りを添える。")

db=sqlite3.connect(DB); c=db.cursor()
rows=c.execute("SELECT tweet_id,posted_at_utc,regime,extract_json FROM danjer_bottomup WHERE extracted=1").fetchall()

frag=open(OUT+"/danjer_rag_chunks.jsonl","w",encoding="utf-8")
fsft=open(OUT+"/danjer_sft.jsonl","w",encoding="utf-8")
nrag=0; nsft=0; cid=0

# 1) 教科書ルール(curated)を高信号チャンクに
for key,lines in PROSE.items():
    cid+=1
    frag.write(json.dumps({"id":f"rule_{cid}","kind":"textbook_rule",
        "technique":key,"source_type":"model_inference",
        "text":f"【{key}】\n"+"\n".join("・"+l for l in lines)},ensure_ascii=False)+"\n"); nrag+=1

for tid,dt,rg,js in rows:
    try: j=json.loads(js)
    except: continue
    if not isinstance(j,dict): continue
    day=(dt or "")[:10]
    mats=[]; blobs=set()
    for m in j.get("materials",[]) or []:
        if not isinstance(m,dict): continue
        what=clean(g(m,"what")); how=clean(g(m,"how")); cite=clean(g(m,"citation"))
        if not (what or cite): continue
        st=src_type(cite)
        mats.append({"type":m.get("type","?"),"what":what,"how":how,"cite":cite,"st":st})
        blobs.add(" ".join([what,how,cite]))
    topics=topics_of(blobs)
    # 2) 材料チャンク (RAG)
    for m in mats:
        cid+=1
        frag.write(json.dumps({"id":f"mat_{cid}","kind":"material","technique_type":m["type"],
            "source_type":m["st"],"date":day,"regime":rg,
            "text":f"[{m['type']}] {m['what']} — {m['how']} (引用:{m['cite']})"},ensure_ascii=False)+"\n"); nrag+=1
    combo=clean(g(j,"combination")); stance=clean(g(j,"stance"))
    if combo:
        cid+=1
        frag.write(json.dumps({"id":f"reason_{cid}","kind":"reasoning",
            "source_type":"model_inference","date":day,"regime":rg,"topics":topics,
            "text":combo+(f" / スタンス: {stance}" if stance else "")},ensure_ascii=False)+"\n"); nrag+=1
        # 3) SFTペア: 観測(材料what)→danjerの読み(combination+stance)
        if len(mats)>=2:
            obs="\n".join(f"- {m['what']}" for m in mats[:8])
            user=f"【局面】{rg}\n【日付】{day}\n【今わたし(danjer)が見ている材料】\n{obs}\n\nこの状況をどう読む?"
            asst=combo+(f"\n\n【スタンス】{stance}" if stance else "")
            fsft.write(json.dumps({"messages":[
                {"role":"system","content":SYS},
                {"role":"user","content":user},
                {"role":"assistant","content":asst}],
                "meta":{"tweet_id":str(tid),"date":day,"regime":rg,
                        "output_source_type":"model_inference","topics":topics}},
                ensure_ascii=False)+"\n"); nsft+=1
frag.close(); fsft.close()
print(f"danjer_rag_chunks.jsonl : {nrag} チャンク")
print(f"danjer_sft.jsonl        : {nsft} 会話ペア")
