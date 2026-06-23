# 議題: 生成PoC失敗 (base/trained両崩壊) → ハーネス再修正の合意取り直し

Colab cell #6 を実行して `danjer_poc_compare.jsonl` (23件、15KB) を取得した。
事前合意した判定式 (base正常+trainedだけ崩れる→学習側 / 両方崩れる→ハーネス側) に照らすと、**ハーネス側の問題と確定**。学習PoCの是非はまだ判定できない。

## 安全プローブ3問の結果 (全件 `btc-trading/danjer_triplet/danjer_poc_compare.jsonl` 参照)

```
Q1 暴落=戻り売りを選ぶか:
  BASE   : 「現在の C. 19999999999999999...」(無限ループ)
  TRAINED: 「【单选字典当____是____ is a 1. 19999999...」

Q2 背がない時 no_trade を選ぶか:
  BASE   : 「この度的正确答案。A. 199999999...」
  TRAINED: 「バックの C. 199999999...」

Q3 OI伴わず急騰=続かないと判定するか:
  BASE   : 「現在の C. 1999999999...」
  TRAINED: 「【单选字典当____是____ is a 1. 199999999...」
```

eval 20問も同様の崩壊で、安全プローブ自動判定は 0/3 OK。

## 崩壊の特徴 (発言Claude視点の原因仮説)

1. 数字「9」が無限ループ → greedy + `repetition_penalty=1.1` 暴発の典型
2. 中国語の選択問題テンプレ「单选字典」が漏出 → Qwen2.5の事前学習データ片
3. 構造化された日本語応答が0件 → chat template / EOS 設定の不整合

## 原因の切り分け候補 (3者で議論したい)

| # | 仮説 | 根拠 | 修正案 |
|---|------|------|--------|
| A | `repetition_penalty=1.1` + `do_sample=False` の greedy 暴発 | 数字「9」無限ループ典型 | repetition_penalty を削除 or 1.0、`do_sample=True` + temp=0.7 を試す |
| B | `pad_token=eos` で eos_token_id が pad扱いされ生成停止条件が崩れる | 「終わらない」現象 | `tok.pad_token_id` と `tok.eos_token_id` を分ける、または `generate(pad_token_id=tok.pad_token_id, eos_token_id=tok.eos_token_id)` を明示分離 |
| C | `apply_chat_template(add_generation_prompt=True)` が Qwen2.5公式テンプレと微妙にズレる | 「单选字典」事前学習データ漏出 | Qwen2.5公式の `<|im_start|>system\n...<|im_end|>\n<|im_start|>user\n...<|im_end|>\n<|im_start|>assistant\n` を手動構築して比較 |
| D | `fp32 + use_cache=False` の後遺症で generate が壊れる | grad_checkpointing の名残 | generate前に `model.config.use_cache=True` + `model.eval()` 明示 |

## 議論したい合意点

1. **A〜D の優先順位と修正の同時適用範囲** (1個ずつ切り分けか、まとめて当てるか)
2. **再Colab実行のスコープ** (cell #6だけ実行で済むか、学習 cell #5から再走か)
3. **学習PoC本体の妥当性判断は据え置く** で合意できるか (有料SFT 13,671件 GO/NO-GO はまだ早い)
4. **完走ライン**: 安全プローブ3問のうち何問OKで「ハーネス問題解決」とみなすか (前回合意は2/3以上)

## 検収物

- `btc-trading/danjer_triplet/danjer_poc_compare.jsonl` (commit f66c35e にpush済)
- 安全プローブ自動判定スコア: 0/3 OK (合意ライン未達)

3者の意見をお願いします。
