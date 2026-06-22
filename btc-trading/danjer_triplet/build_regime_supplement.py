#!/usr/bin/env python3
# Q3 別冊補強: crash/range/rally 局面別 danjer挙動の実データ抽出 (¥0)
# 出力 /tmp/regime_src.json: 局面ごとに [支配的手法ランキング][行動別 実引用][combos]
import sqlite3, json, collections, re

DB="/Users/shuji/Desktop/kitt-voice/btc-trading/btc_trading_ai.db"
OUT="/Users/shuji/Desktop/kitt-voice/btc-trading/danjer_triplet"
def _grab(path,var):
    src=open(path).read(); m=re.search(var+r" *= *\{.*?\n\}",src,re.S)
    return eval(m.group(0)[len(var):].split("=",1)[1])
TAXO=_grab(OUT+"/build_corpus.py","TAXO")

def g(d,k):
    v=d.get(k); return (v if isinstance(v,str) else "").strip()
def clean(s): return re.sub(r"\s+"," ",s).strip()
READOUT=["が表示されて","描画されて","描かれて","ローソク足は","チャートには","チャート上に",
         "価格スケール","現在の売値","現在の買値","と表示され","画像読取","画像:","の範囲。","ローソク足で"]
VOICE=["＠","⇒","→","1️⃣","2️⃣","3️⃣","背に","だぬ","かぬ","やぬ","ぬ。","w","想定","狙","利確","損切",
       "ロング","ショート","買い","売り","ここ","この後","と思","かな","です。","ます。"]
def is_text(c):
    return (("画像読取" not in c) and ("画像:" not in c)
            and sum(c.count(x) for x in READOUT)<=1
            and sum(1 for x in VOICE if x in c)>=2)

# 行動カテゴリ: danjerが局面で何をするか
ACTIONS={
 "ノーポジ・様子見・見送り":["ノーポジ","ノーポジション","様子見","見送り","手出し無用","触らない","静観","ノーエントリー","手を出さ","休も","待機"],
 "逃げ・撤退・損切り":["逃げ","撤退","損切","ロスカ","畳む","降りる","手仕舞","損切り","逃げる","ストップ"],
 "ショート・売り":["ショート","戻り売り","ドテンショート","空売り","Sイン","売り場","売り目線","売り向か"],
 "買い場・拾う・打診":["買い場","拾う","打診","逆張り","仕込","買い向か","買い増し","リバ取り","底打ち","底値"],
 "利確・分割":["利確","半値戻し","分割","建値","リグる","利食"],
}

db=sqlite3.connect(DB); c=db.cursor()
rows=c.execute("SELECT tweet_id,posted_at_utc,regime,extract_json FROM danjer_bottomup WHERE extracted=1").fetchall()

REG=["crash","range","rally"]
tech=collections.defaultdict(collections.Counter)   # regime->技術件数
acts=collections.defaultdict(lambda:collections.defaultdict(list))  # regime->action->[quotes]
combos=collections.defaultdict(list)

for tid,dt,rg,js in rows:
    if rg not in REG: continue
    try: j=json.loads(js)
    except: continue
    if not isinstance(j,dict): continue
    day=(dt or "")[:10]; blobs=set()
    for m in j.get("materials",[]) or []:
        if not isinstance(m,dict): continue
        what=clean(g(m,"what")); how=clean(g(m,"how")); cite=clean(g(m,"citation"))
        blob=" ".join([what,how,cite]); blobs.add(blob)
        for key,kw in TAXO.items():
            if any(w in blob for w in kw): tech[rg][key]+=1
        # 行動別 実引用 (本人テキスト優先)
        if cite and is_text(cite):
            for act,kws in ACTIONS.items():
                if any(k in cite for k in kws):
                    acts[rg][act].append({"cite":cite,"date":day})
    combo=clean(g(j,"combination")); stance=clean(g(j,"stance"))
    if combo and len(combo)>=40:
        combos[rg].append({"combo":combo,"stance":stance,"date":day})

out={}
for rg in REG:
    # 行動別: 重複除去
    a={}
    for act,lst in acts[rg].items():
        seen=set(); u=[]
        for e in sorted(lst,key=lambda x:len(x["cite"]),reverse=True):
            sig=re.sub(r"\s+","",e["cite"])[:35]
            if sig in seen: continue
            seen.add(sig); u.append(e)
        a[act]={"n":len(lst),"ex":u[:8]}
    # combos重複除去
    seen=set(); cu=[]
    for e in sorted(combos[rg],key=lambda x:len(x["combo"]),reverse=True):
        sig=re.sub(r"\s+","",e["combo"])[:50]
        if sig in seen: continue
        seen.add(sig); cu.append(e)
    out[rg]={"tech":tech[rg].most_common(12),"actions":a,"combos":cu[:25],
             "n_posts":len(combos[rg])}
json.dump(out,open("/tmp/regime_src.json","w"),ensure_ascii=False)
for rg in REG:
    print(f"\n===== {rg} (posts {out[rg]['n_posts']}) =====")
    print("  top tech:", [f"{k.split()[0]}:{v}" for k,v in out[rg]["tech"][:8]])
    for act,d in out[rg]["actions"].items():
        print(f"  [{act}] n={d['n']}")
print("\nWROTE /tmp/regime_src.json")
