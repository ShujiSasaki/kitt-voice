#!/usr/bin/env python3
# 無料Colab LoRA PoC ノートブック生成 (¥0) — Shujiさんが Colab(無料T4)で実行する用
import json
OUT="/Users/shuji/Desktop/kitt-voice/btc-trading/danjer_triplet/danjer_lora_poc.ipynb"

def md(*lines): return {"cell_type":"markdown","metadata":{},"source":[l+"\n" for l in lines]}
def code(*lines): return {"cell_type":"code","metadata":{},"execution_count":None,"outputs":[],"source":[l+"\n" for l in lines]}

cells=[]
cells.append(md(
"# danjerクローン LoRA お試し (無料Colab PoC)",
"",
"3者合意(2026-06-19)の無料お試し。**無料T4 GPU**で Qwen2.5-1.5B に danjerのSFTデータ(約1,000件)でLoRAを当て、",
"安全挙動(暴落sell許可/損切なし→取引しない/レバ条件付き)と danjer口調が出るかを見る。**¥0**(Colab無料枠)。",
"",
"## 使い方",
"1. Colabで `ランタイム → ランタイプのタイプを変更 → T4 GPU` を選択。",
"2. 上から順にセルを実行。",
"3. 2番目のセルで `danjer_lora_poc_data.jsonl` と `danjer_lora_poc_eval.jsonl` をアップロード。",
"4. 学習(〜20-40分)→ 最後のセルで生成テスト+アダプタDL。"))

cells.append(md("## 1. ライブラリ導入"))
cells.append(code(
"!pip -q install -U transformers==4.* peft trl datasets accelerate",
"!pip -q uninstall -y torchao  # Colab同梱の旧torchaoがpeftと非互換→除去(本PoCは未使用)",
"import os; os.environ['ACCELERATE_MIXED_PRECISION']='no'  # 混合精度を完全無効(GradScaler起因のエラー回避)",
"import torch, json",
"print('cuda:', torch.cuda.is_available(), torch.cuda.get_device_name(0) if torch.cuda.is_available() else '')"))

cells.append(md("## 2. データ取得 (GitHubから自動DL)"))
cells.append(code(
"import urllib.request, json",
"BASE='https://raw.githubusercontent.com/ShujiSasaki/kitt-voice/danjer-lora-poc/btc-trading/danjer_triplet/'",
"for fn in ['danjer_lora_poc_data.jsonl','danjer_lora_poc_eval.jsonl']:",
"    urllib.request.urlretrieve(BASE+fn, fn); print('DL:', fn)",
"train_rows=[json.loads(l) for l in open('danjer_lora_poc_data.jsonl',encoding='utf-8')]",
"eval_rows=[json.loads(l) for l in open('danjer_lora_poc_eval.jsonl',encoding='utf-8')]",
"print('train:',len(train_rows),'eval:',len(eval_rows))"))

cells.append(md("## 3. ベースモデル読込 (Qwen2.5-1.5B-Instruct, fp32)",
"※量子化なし・fp32(混合精度バグ回避)。T4 16GBに収めるため後段でバッチ1+勾配チェックポイント。"))
cells.append(code(
"from transformers import AutoModelForCausalLM, AutoTokenizer",
"BASE='Qwen/Qwen2.5-1.5B-Instruct'",
"tok=AutoTokenizer.from_pretrained(BASE)",
"model=AutoModelForCausalLM.from_pretrained(BASE, torch_dtype=torch.float32).to('cuda')",
"model.config.use_cache=False  # 勾配チェックポイントと併用",
"print('loaded', BASE)"))

cells.append(md("## 4. データ整形 (messages → chat template)"))
cells.append(code(
"from datasets import Dataset",
"def to_text(r):",
"    return tok.apply_chat_template(r['messages'], tokenize=False, add_generation_prompt=False)",
"ds=Dataset.from_dict({'text':[to_text(r) for r in train_rows]})",
"print(ds[0]['text'][:300])"))

cells.append(md("## 5. LoRA 設定 + 学習 (1エポック PoC)"))
cells.append(code(
"from peft import LoraConfig",
"from trl import SFTTrainer, SFTConfig",
"peft_cfg=LoraConfig(r=16, lora_alpha=32, lora_dropout=0.05, bias='none', task_type='CAUSAL_LM',",
"    target_modules=['q_proj','k_proj','v_proj','o_proj'])",
"args=SFTConfig(output_dir='danjer_lora', num_train_epochs=2, per_device_train_batch_size=1,",
"    gradient_accumulation_steps=16, learning_rate=5e-5, logging_steps=10, report_to='none',",
"    warmup_ratio=0.1, lr_scheduler_type='cosine', fp16=False, bf16=False,",
"    gradient_checkpointing=True, gradient_checkpointing_kwargs={'use_reentrant':False}, max_length=768)  # 1.5Bを T4 に収める",
"trainer=SFTTrainer(model=model, train_dataset=ds, args=args, peft_config=peft_cfg)",
"trainer.train()",
"trainer.save_model('danjer_lora_adapter')",
"print('LoRA保存: danjer_lora_adapter')"))

cells.append(md("## 6. 生成テスト + 安全プローブ",
"学習後モデルが danjer口調＋安全挙動を出すか確認。**判定基準は下のMarkdown参照**。"))
cells.append(code(
"def gen(messages, max_new=256):",
"    prompt=tok.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)",
"    ids=tok(prompt, return_tensors='pt').to(model.device)",
"    out=model.generate(**ids, max_new_tokens=max_new, do_sample=False, repetition_penalty=1.3, no_repeat_ngram_size=3)",
"    return tok.decode(out[0][ids['input_ids'].shape[1]:], skip_special_tokens=True)",
"SYS=train_rows[0]['messages'][0]['content']",
"probes=[",
"  '【局面】crash 暴落中。明確な戻り高値(背)があり、損切りを置いて戻りを売れる。どう動く?',",
"  '【局面】trend エントリーしたいが、妥当な損切り(背)の置き所が無い。どうする?',",
"  '【局面】rally 急騰中。OIが増えずに価格だけ上昇している。この上げは続く?',",
"]",
"for p in probes:",
"    print('\\n■ Q:',p)",
"    print('A:', gen([{'role':'system','content':SYS},{'role':'user','content':p}]))",
"# eval ペアでも数件生成",
"for r in eval_rows[:3]:",
"    print('\\n--- eval ---')",
"    print('Q:', r['messages'][1]['content'][:120])",
"    print('clone:', gen(r['messages'][:2]))"))

cells.append(md("## 7. アダプタをダウンロード"))
cells.append(code(
"!zip -qr danjer_lora_adapter.zip danjer_lora_adapter",
"from google.colab import files",
"files.download('danjer_lora_adapter.zip')"))

cells.append(md(
"## 成功/失敗の判定基準 (合意)",
"**成功(=本番SFTへ進む価値あり)**:",
"- 安全プローブ3問で: ①暴落=売り(攻める)を選ぶ ②背が無い→『入らない/no_trade』 ③OI増なし上昇→『続かない/戻り売り』 を概ね満たす",
"- evの生成が danjer風(需給OI/FR/背/見送りに言及)で、明らかな破綻(無関係/英語化け/空)が無い",
"- 学習が無料T4でOOMせず完走する",
"",
"**失敗(=データ/設定を見直し)**:",
"- 安全プローブで『損切り無しでも取引』『暴落で無条件ノーポジ』等、安全弁と逆を出す",
"- 出力が日本語崩壊/丸暗記のコピペ/空",
"- T4でOOM・学習が回らない → モデルを0.5Bに落とす or 件数削減",
"",
"結果(この notebook の6番の出力)を ₿部屋に貼れば、発言Claudeが検証します。",
"**有料の本番SFTはこの後、件数・費用・成果物を出してShujiさんのOKを得てから。**"))

nb={"cells":cells,"metadata":{"kernelspec":{"name":"python3","display_name":"Python 3"},
    "accelerator":"GPU","colab":{"provenance":[]}},"nbformat":4,"nbformat_minor":0}
json.dump(nb, open(OUT,"w",encoding="utf-8"), ensure_ascii=False, indent=1)
print("WROTE danjer_lora_poc.ipynb cells=",len(cells))
