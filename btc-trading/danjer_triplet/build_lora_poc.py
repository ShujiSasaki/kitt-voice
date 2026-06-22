#!/usr/bin/env python3
# 無料LoRA PoC 用データ抽出 (¥0) — 3者合意(2026-06-19 20:51)
# danjer_sft.jsonl + danjer_sft_regimes.jsonl から 局面バランスした ~1,000件を抽出。
# 出力: danjer_lora_poc_data.jsonl (train) + danjer_lora_poc_eval.jsonl (eval用 少数)
import json, random
random.seed(42)
OUT="/Users/shuji/Desktop/kitt-voice/btc-trading/danjer_triplet"

def load(f):
    return [json.loads(l) for l in open(f,encoding="utf-8")]
sft=load(OUT+"/danjer_sft.jsonl")
reg=load(OUT+"/danjer_sft_regimes.jsonl")  # range/rally/crash 濃いめ

by={"trend":[],"range":[],"rally":[],"crash":[]}
for r in sft:
    g=r.get("meta",{}).get("regime","trend")
    if g in by: by[g].append(r)
# 薄い局面は regimes pack で補強
reg_by={"range":[],"rally":[],"crash":[]}
for r in reg:
    g=r.get("meta",{}).get("regime")
    if g in reg_by: reg_by[g].append(r)
for g in reg_by: by[g]=reg_by[g] or by[g]

# 目標構成(計~1000): trend 500 / range 200 / rally 200 / crash 100
TARGET={"trend":500,"range":200,"rally":200,"crash":100}
train=[]
for g,n in TARGET.items():
    pool=by[g][:]; random.shuffle(pool)
    train.extend(pool[:n])
random.shuffle(train)

# eval用に train と重複しない少数(各局面5件=20件)を別取り
used=set(id(x) for x in train)
ev=[]
for g in TARGET:
    extra=[x for x in by[g] if id(x) not in used]
    random.shuffle(extra); ev.extend(extra[:5])

with open(OUT+"/danjer_lora_poc_data.jsonl","w",encoding="utf-8") as f:
    for r in train: f.write(json.dumps(r,ensure_ascii=False)+"\n")
with open(OUT+"/danjer_lora_poc_eval.jsonl","w",encoding="utf-8") as f:
    for r in ev: f.write(json.dumps(r,ensure_ascii=False)+"\n")

import collections
c=collections.Counter(r.get("meta",{}).get("regime") for r in train)
print("train:",len(train),"局面:",dict(c))
print("eval:",len(ev))
print("WROTE danjer_lora_poc_data.jsonl / danjer_lora_poc_eval.jsonl")
