# ペーパートレード環境 設計書

3者合意 (2026-06-24 05:51 btc部屋) に従い、 v6 LoRA + 強制ストップ7条件 で BTC のみ・3週間以上・50〜100件 の **資金が動かない** ペーパートレード環境を構築する。

## 基本方針 (合意の核心)

1. **儲けより先に見るもの**:
   - 危ない場面で 100% 見送れたか
   - 強制ストップがバグなく効いたか
2. **本番発注は完全遮断** (物理的に取引所APIへ触らない設計)
3. **設定一つで本物の注文が出る事故を絶対防ぐ**
4. v6 LoRA は **読み込みのみ**、 再学習しない

---

## アーキテクチャ全体

```
┌─────────────────────────────────────────────────────────────┐
│                  ペーパートレード環境                       │
│                                                             │
│  ┌─────────┐    ┌──────────┐    ┌──────────┐    ┌────────┐  │
│  │ BTC OHLCV│ → │ 局面検出 │ → │ v6推論 │ → │ ストップ│  │
│  │ (yfinance│   │engine    │   │engine   │   │ 7条件   │  │
│  │ public) │   │trend/    │   │Qwen+    │   │filter  │  │
│  │         │   │range/    │   │adapter  │   │         │  │
│  │         │   │rally/    │   │         │   │         │  │
│  │         │   │crash)    │   │         │   │         │  │
│  └─────────┘    └──────────┘    └──────────┘    └────┬───┘  │
│                                                       │      │
│                                  ┌────────────────────┘      │
│                                  ↓                            │
│  ┌────────┐    ┌──────────┐    ┌──────────┐                │
│  │信号ログ│ ← │信号生成│ ← │【スタンス】│              │
│  │jsonl   │   │ + 評価   │   │抽出       │                │
│  │        │   │          │   │           │                │
│  └────────┘    └──────────┘    └──────────┘                │
│                     ↓                                       │
│  ┌─────────────────────────────────┐                       │
│  │ 評価ダッシュボード (見送り率 +    │                       │
│  │ 強制ストップ動作 + 内容ログ)     │                       │
│  └─────────────────────────────────┘                       │
│                                                             │
│  🚫 取引所API には一切触らない (物理切り離し)              │
└─────────────────────────────────────────────────────────────┘
```

---

## ディレクトリ構成

```
btc-trading/paper_trading/
├── README.md              # 使い方、 安全確認手順
├── config.yml             # 全設定 (paper_mode=true 固定)
├── data_source.py         # BTC OHLCV取得 (yfinance public、 認証なし)
├── regime_detector.py     # 局面検出 (trend/range/rally/crash)
├── inference.py           # v6 LoRA 推論
├── stop_rules.py          # 強制ストップ7条件
├── signal_generator.py    # 【スタンス】抽出 + 信号生成
├── runner.py              # メインループ (1日2-3回判定)
├── safety_check.py        # 「絶対発注しない」 確認スクリプト
├── dashboard.py           # 評価ダッシュボード (CLI/HTML)
├── logs/                  # 信号ログ + 強制ストップ動作ログ
│   └── signals.jsonl
└── tests/                 # ユニットテスト
    ├── test_no_order.py   # 取引所API呼び出しテスト → 失敗 必須
    └── test_stop_rules.py
```

---

## 各コンポーネントの責務

### 1. data_source.py
- 入力: なし
- 出力: BTC OHLCV (15m/1h/4h/1d)
- 方式: `yfinance` (Yahoo Finance public API、 認証不要、 無料)
- 取引所APIは絶対呼ばない (= 注文発生のリスクゼロ)
- フォールバック: なし (失敗時は判定スキップ、 ログ残す)

### 2. regime_detector.py
- 入力: OHLCV
- 出力: regime ∈ {trend, range, rally, crash}
- ルール:
  - **rally**: 直近 4h ATR > 過去 30d ATR × 2、 価格 +5%以上 / 6h
  - **crash**: 直近 4h ATR > 過去 30d ATR × 2、 価格 -5%以下 / 6h
  - **trend**: 4h EMA20 > 4h EMA50 (上昇トレンド) or 逆 (下降)
  - **range**: 上記いずれにも該当しない

### 3. inference.py
- 入力: regime + 材料リスト (材料は局面ごとにテンプレート)
- 出力: TRAINED応答テキスト
- v6 LoRA を読み込み (`/Users/shuji/Desktop/kitt-voice/...adapter/`)
- ベースモデル: `Qwen/Qwen2.5-1.5B-Instruct`
- 推論モード: CPU (Mac local、 GPUなし)
- 1判定推論時間: 推定 20-60秒/件

### 4. stop_rules.py — **強制ストップ7条件**

合意の7条件をプログラムで実装。 LoRAの判定とは独立して動作:

```python
def force_stop_check(regime, ohlcv, response, candles_recent) -> dict:
    """
    Returns: {triggered: bool, rules_hit: list[str], reason: str}
    """
    triggers = []

    # 1. 損切り不明
    if '損切' not in response and '背' not in response:
        triggers.append('rule_1_no_stop_loss')

    # 2. 損切り近すぎ (response から SL距離を抽出してATRと比較)
    if extract_sl_distance(response, ohlcv) < atr(ohlcv) * 0.5:
        triggers.append('rule_2_sl_too_close')

    # 3. 根拠なし急騰 (rally regimeでOI急増なしの場合は force stop)
    if regime == 'rally' and not has_oi_surge(ohlcv):
        triggers.append('rule_3_unfounded_rally')

    # 4. 根拠不足 (材料リストが2点未満 or 材料の汎用キーワードのみ)
    if not has_sufficient_grounds(response):
        triggers.append('rule_4_insufficient_grounds')

    # 5. 薄い逆張り (crashで反発買い、 trend逆方向ショート 等)
    if is_thin_counter(regime, response):
        triggers.append('rule_5_thin_counter')

    # 6. 板薄/急変 (OHLCVのvolume 過去平均の30%未満、 ATR > 平均×3 等)
    if is_thin_or_extreme(ohlcv):
        triggers.append('rule_6_thin_or_extreme')

    # 7. モデルが曖昧 (応答に「不明」「曖昧」「分からない」 含む、 or 応答長20文字未満)
    if is_ambiguous(response):
        triggers.append('rule_7_model_ambiguous')

    return {
        'triggered': len(triggers) > 0,
        'rules_hit': triggers,
        'reason': '; '.join(triggers)
    }
```

### 5. signal_generator.py
- 入力: response + force_stop結果
- 出力: signal ∈ {long, short, no_trade, force_stopped}
- ロジック:
  - force_stop.triggered = True → `force_stopped` (常に勝つ)
  - response に「【スタンス】no_trade/見送り/様子見」 → `no_trade`
  - response に「【スタンス】ロング/買い/ショート/売り」 → `long`/`short`
  - 不明 → `no_trade` (デフォルト安全)

### 6. runner.py — メインループ
```python
while True:
    ohlcv = data_source.fetch_btc()       # 取引所APIは呼ばない
    regime = regime_detector.detect(ohlcv)
    response = inference.run(regime, materials)
    stop = stop_rules.force_stop_check(regime, ohlcv, response, candles_recent)
    signal = signal_generator.generate(response, stop)
    log_entry = {
        'ts': now(), 'regime': regime, 'response': response,
        'stop_triggered': stop['triggered'], 'stop_rules': stop['rules_hit'],
        'signal': signal,
        'price': ohlcv[-1]['close'], 'no_order_assertion': True
    }
    logs.append(log_entry)
    sleep(8h)  # 1日2-3判定 = 約30件/2週間、 50-100件/3週間
```

### 7. safety_check.py — **本番発注遮断の二重防御**

合意の「設定一つで本物の注文が出る事故が起きうる」 への対処:

```python
# 1. ccxt (取引所API library) を pip install しない
# 2. config.yml に paper_mode=true を強制 (起動時 assert)
# 3. 取引所のAPIキー環境変数 (BYBIT_API_KEY等) を一切読まない
# 4. tests/test_no_order.py で「import ccxt されない」 を自動テスト
# 5. Shujiさん用確認スクリプト:
#    python3 safety_check.py
#    出力:
#    ✅ ccxt not installed
#    ✅ config paper_mode=true
#    ✅ no API keys in env
#    ✅ regime_detector only reads OHLCV
#    ✅ inference only reads/writes local files
#    🟢 SAFE: this environment cannot place real orders
```

### 8. dashboard.py — 評価ダッシュボード
- 入力: logs/signals.jsonl
- 出力: 統計 + 件別ログ (CLI or HTML)
- 主要指標 (合意基準):
  1. **見送り率** (no_trade + force_stopped) / 総件数
  2. **強制ストップ動作率** (force_stopped) / 総件数
  3. **危ない場面で100%見送れたか** (危ない場面 = rally/crash + OI急変なし etc を別途定義)
  4. **強制ストップ7条件の発火頻度** (各ルールの動作実数)
- 合意の合格ライン:
  - 危ない場面で「やる」 = 0件 (必須)
  - 変な繰り返しや崩れ = 0件
  - その他は3者会議で評価

---

## ファイル別実装規模見積もり

| ファイル | LOC | 推定時間 | 依存 |
|---|---|---|---|
| config.yml | 30 | 5分 | なし |
| data_source.py | 60 | 30分 | yfinance |
| regime_detector.py | 100 | 1h | numpy/pandas |
| inference.py | 80 | 1h | transformers + peft |
| stop_rules.py | 200 | 2h | (7条件×30LOC) |
| signal_generator.py | 50 | 30分 | なし |
| runner.py | 100 | 1h | 上記全部 |
| safety_check.py | 80 | 1h | os.path等 |
| dashboard.py | 150 | 2h | tabulate |
| tests/ | 100 | 1h | pytest |
| **計** | **~950 LOC** | **約半日 (5-6h)** | |

---

## 段階的着工 (合意+設計承認後)

| Phase | 内容 | 検証 |
|---|---|---|
| **0** | この設計書をShujiさん承認 + 3者会議で承認 | 設計承認確認 |
| 1 | inference.py + tests/test_no_order.py (推論+発注遮断確認) | v6推論動作確認 |
| 2 | regime_detector.py + data_source.py (BTC局面検出) | 過去データで動作確認 |
| 3 | stop_rules.py (7条件実装) | 各ルール単体テスト |
| 4 | signal_generator.py + runner.py (メインループ) | 5判定で動作確認 |
| 5 | dashboard.py + safety_check.py (評価+安全確認) | Shujiさん自身が確認 |
| 6 | **3週間 実運用** (50-100件蓄積) | 合意の合格ライン照合 |

---

## リスク + 対策

| リスク | 対策 |
|---|---|
| 取引所API呼び出しの事故 | ccxt install禁止、 APIキー読み禁止、 自動テスト |
| OHLCVデータ取得失敗 | yfinanceエラー時 判定スキップ、 ログ残す |
| 推論時間が長すぎる | CPUで20-60秒/件、 1日2-3回なら問題なし |
| LoRA読み込み失敗 | 起動時assert、 失敗時は判定スキップ |
| ストップルール誤判定 | 各ルールのユニットテスト + 過去データバックテスト |
| Shuji設定ミス | safety_check.py で5項目チェック、 「🟢 SAFE」 表示まで起動拒否 |

---

## Shujiさん承認確認

この設計書で実装着手していい? 修正したい点ある?
特に確認したい点:
1. データソース yfinance (Yahoo Finance public、 認証不要、 取引所APIに触らない) でOK?
2. 強制ストップ7条件の実装方針 (合意の意図を捉えてるか)
3. 1日2-3判定 × 3週間 = 50-100件で十分か
4. dashboard はCLI出力でいいか、 HTML/web UI欲しいか
5. 段階的着工順序 (Phase 1-5) でいいか
