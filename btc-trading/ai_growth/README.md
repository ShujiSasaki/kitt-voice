# danjerクローンAI 育成環境 (Phase 1)

3者合意 (2026-06-24) に基づくAI育成環境。 v6 LoRA + 強制ストップ7条件で、 **「勝つために、 まず退場しないAI」** を育てる。

## ゴール (合意)
> 「BTC判断ゲームでとことん上手くなり、 長く勝てるAIに育てる」

「事故らない (退場・大負け避ける)」 はゴールではなく、 **勝ち続けるための土台**。 攻めの腕を磨くのはペーパーで存分にやって、 本物のお金を入れてから攻めるのが一番お金を失う動き方。

## ★ 起動前 安全確認 (必須、 Shujiさん自身がやる)

```bash
cd btc-trading/ai_growth
python3 safety_check.py
```

出力に **🟢 SAFE** が表示されることを **Shujiさん自身の目で** 確認。 AIの報告じゃなく自分で見る。 これがお金を守る最後の砦。

## ディレクトリ構造

```
ai_growth/
├── README.md              # このファイル
├── config.yml             # 全設定 (paper_mode=true 固定)
├── safety_check.py        # 起動前の6項目安全確認
├── data_source.py         # BTC OHLCV (yfinance public、 取引所API一切触らない)
├── regime_detector.py     # trend/range/rally/crash 局面判定
├── inference.py           # v6 LoRA推論 (CPU、 Mac local)
├── stop_rules.py          # 強制ストップ7条件 (LoRAと独立)
├── signal_generator.py    # 【スタンス】抽出 → long/short/no_trade/force_stopped
├── runner.py              # メインループ (1日3回判定)
├── logs/                  # signals_v{N}.jsonl
└── tests/                 # 自動テスト (本番遮断、 7条件単体)
```

## 起動 (safety_check 通過後のみ)

```bash
python3 runner.py
```

## 評価指標 (合意の3層)

### 🛡 守り層
- 危ない場面で「やる」: 0件 (必須)
- 強制ストップ7条件のバグ: 0件 (必須)
- 同フレーズ無限ループ: 0/N件
- 内容崩壊: 0/N件

### ⚔ 攻め層
- 仮想損益 1h/4h/24h: プラス収束
- 最大上昇幅 / 最大逆行幅 (drawdown): RR管理
- 勝率: 継続向上
- 平均RR: 1:1.5以上

### 😨 臆病チェック
- no_trade率 95%超 → 警告
- 強制ストップ発火率 70%超 → 警告
- 平均応答長 30文字未満 → 警告

## 強制ストップ7条件 (LoRAと独立、 stop_rules.py)

1. 損切り不明 (response に「損切」 も「背」 もない)
2. 損切り近すぎ (SL距離 < ATR×0.5)
3. 根拠なし急騰 (rally regimeで OI急増なし)
4. 根拠不足 (材料2点未満 or 汎用キーワードのみ)
5. 薄い逆張り (crashで反発買い等)
6. 板薄/急変 (Volume < 平均30% or ATR > 平均×3)
7. モデル曖昧 (「不明/曖昧/分からない」 or 20文字未満)

## 育成サイクル

- 1サイクル: 3週間 × 50〜100件判定 (合意通り)
- 各サイクル末: Shuji目視ラベル → 教師化 → v(N+1)再学習 → 次サイクル
- 失敗仕分けは **8択ボタン** (label_tool.pyで Shujiさん作業負担軽減)

## 実弾¥10万 移行条件 (合意必須)

以下 全てクリア + **Shujiさん自身の最終判断**:

1. 最低3サイクル (約2ヶ月) の育成完了
2. 臆病警告 (no_trade率/強制ストップ率/応答長) がゼロ

AIの多数決外。 Shujiさんが結果を見て自分の口で「いいぞ」 と言ってから。

## 注意

- ⛔ 取引所APIには一切触らない (yfinance public のみ)
- ⛔ 本番発注は物理的に完全遮断
- ⛔ ccxt インストール禁止 (safety_check.py で確認)
- ⛔ 取引所APIキー環境変数 読み込み禁止 (safety_check.py で確認)

## 関連ファイル
- 設計書: `btc-trading/danjer_triplet/ai_growth_environment_design.md`
- v6 LoRA: `btc-trading/danjer_triplet/compare_planA_v6.jsonl` (training結果)
- Kaggle adapter: `/tmp/kaggle_v6_output/danjer_lora_planA_adapter/`
