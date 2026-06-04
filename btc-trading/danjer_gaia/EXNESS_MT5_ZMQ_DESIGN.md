# Exness MT5/ZMQ ブリッジ 設計書 (Phase 3後半着手用)

更新: 2026-06-04 (Round 34-38 戦略Z v8 反映)
着手予定: Phase 3後半 (Day 100-167)
実装工数: **10-16日**

## 1. 目的と位置づけ

### Round 34 で確定した役割
- **Phase 4 Cap 1 ($25k) から並走Live開始** で taritari CB 月$93→$1,854 を稼ぐ
- AI 育成自体は Hyperliquid 単独 (Phase 2-3) で完結、 Exness は **収益+** のための副系統
- AI 学習データには **Exness 約定情報を混ぜない** (CFD独自レートのノイズ防止)

### システム構成 (Round 34 Gemini 設計)

```
[Cloud Run: slow-brain-server (Python)]
  ├─ Hyperliquid 主軸: hyperliquid_client.py 経由で直接発注
  └─ Exness 副: ZMQ Publisher で発注指示

  ZMQ TCP/TLS WAN
        ↓ (平均遅延 80-150ms)

[VPS (Exness無料VPS、 Windows Server)]
  ├─ MT5 + Exness 口座 (taritari紐付け済)
  ├─ MQL5 EA: ZMQ受信→MT5発注
  └─ ZMQ Publisher: 約定情報を Cloud Run へ返却
```

## 2. 通信プロトコル仕様

### ZMQ チャネル

| Channel名 | Pattern | 方向 | 用途 |
|---|---|---|---|
| `exness:order:place` | REQ/REP | Cloud Run → VPS | 新規発注指示 |
| `exness:order:cancel` | REQ/REP | Cloud Run → VPS | 注文キャンセル |
| `exness:position:close` | REQ/REP | Cloud Run → VPS | ポジション決済 |
| `exness:fill` | PUB/SUB | VPS → Cloud Run | 約定通知 |
| `exness:market` | PUB/SUB | VPS → Cloud Run | 市場データ (board/tick) |
| `exness:health` | PUB/SUB | VPS → Cloud Run | heartbeat (1秒間隔) |

### メッセージ JSON フォーマット

#### 発注指示 (Cloud Run → VPS):
```json
{
  "type": "place_order",
  "decision_trace_id": "uuid",
  "symbol": "BTCUSD",
  "side": "buy" | "sell",
  "size": 0.01,
  "order_type": "market" | "limit",
  "price": 100000.0,
  "leverage": 3.0,
  "sl_price": 99000.0,
  "tp_price": 102000.0,
  "comment": "danjer_gaia",
  "magic_number": 20260604
}
```

#### 約定通知 (VPS → Cloud Run):
```json
{
  "type": "fill",
  "decision_trace_id": "uuid",
  "order_id": "MT5_ticket_number",
  "symbol": "BTCUSD",
  "side": "buy",
  "size": 0.01,
  "filled_size": 0.01,
  "filled_price": 100050.0,
  "sl_order_id": "MT5_sl_ticket",
  "fees": 0.35,
  "swap": 0.0,
  "timestamp_utc": "2026-09-15T12:34:56.789Z"
}
```

#### Heartbeat (VPS → Cloud Run、 1秒間隔):
```json
{
  "type": "heartbeat",
  "timestamp_utc": "2026-09-15T12:34:56Z",
  "mt5_connected": true,
  "exness_account": "active",
  "open_positions_count": 1
}
```

## 3. MQL5 EA 実装仕様 (VPS側)

### ファイル構成
```
MQL5/Experts/DanjerGAIA/
├── DanjerGAIA.mq5           # メイン EA
├── ZMQBridge.mqh            # ZMQ ラッパー (mql-zmq ライブラリ依存)
├── OrderManager.mqh         # 発注・決済ロジック
└── HealthMonitor.mqh        # heartbeat 送信
```

### 必要ライブラリ
- **mql-zmq** (https://github.com/dingmaotu/mql-zmq、 公式ZMQ MQL ラッパー)
- libzmq.dll (Windows、 VPSにインストール)

### EA 主要関数

```mql5
// === ZMQ初期化 (OnInit) ===
int OnInit() {
    Context.Init();
    OrderSocket.Connect("tcp://cloud-run-ip:5555");  // REQ/REP
    FillPublisher.Bind("tcp://*:5556");              // PUB
    HealthPublisher.Bind("tcp://*:5557");            // PUB
    EventSetTimer(1);  // 1秒heartbeat
    return INIT_SUCCEEDED;
}

// === メインループ (OnTimer 1秒間隔) ===
void OnTimer() {
    SendHeartbeat();
    // 発注リクエスト受信処理
    while(ReceiveOrderRequest(request)) {
        ExecuteOrder(request);
    }
}

// === 約定検知 (OnTradeTransaction) ===
void OnTradeTransaction(const MqlTradeTransaction& trans,
                       const MqlTradeRequest& request,
                       const MqlTradeResult& result) {
    if(trans.type == TRADE_TRANSACTION_DEAL_ADD) {
        // 約定情報を ZMQ で Cloud Run へ送信
        PublishFillNotification(trans, result);
    }
}
```

### EA セキュリティ
- ZMQ TCP通信は **TLS over TCP** で暗号化 (ZMQ Curve mechanism)
- 認証: VPS と Cloud Run で事前共有鍵
- IP制限: VPS は Cloud Run の固定IPからのみ接続許可
- マジックナンバー (20260604): 別 EA との混信防止

## 4. Python ZMQ Publisher 実装仕様 (Cloud Run側)

### ファイル配置
```
btc-trading/danjer_gaia/exchange/
└── exness_client.py     # ExchangeBase 実装 (ZMQ経由)
```

### exness_client.py 実装方針

```python
import zmq
from .base import ExchangeBase, ...

class ExnessClient(ExchangeBase):
    name = "exness"
    
    def __init__(self, config: ExnessConfig):
        self.config = config
        self._context = zmq.Context()
        # REQ/REP for orders
        self._order_socket = self._context.socket(zmq.REQ)
        self._order_socket.connect(config.vps_order_endpoint)
        # SUB for fills
        self._fill_socket = self._context.socket(zmq.SUB)
        self._fill_socket.connect(config.vps_fill_endpoint)
        # SUB for heartbeat
        self._health_socket = self._context.socket(zmq.SUB)
        self._health_socket.connect(config.vps_health_endpoint)
        self._last_heartbeat = datetime.now(timezone.utc)
    
    def place_order(self, symbol, side, size, ...) -> OrderResult:
        # ZMQ 発注リクエスト送信
        request = self._build_request(symbol, side, size, ...)
        self._order_socket.send_json(request)
        # 30秒タイムアウトで応答待機
        response = self._order_socket.recv_json(zmq.NOBLOCK)
        # 約定通知 (SUB) を別スレッドで監視、 OrderResult に変換
        ...
    
    def _heartbeat_monitor(self):
        """30秒以上 heartbeat 途絶 → 接続障害扱い (R84)"""
        ...
```

## 5. Order Router 統合

`exchange_router.py` の `_translate_symbol` は実装済 (BTC→BTCUSD)。

### 並走時の挙動 (Round 34 Gemini設計)
```
Slow Brain判断: LONG BTC $20k, lev=3x
↓
ExchangeRouter (Phase 4 Cap 1):
├─ allocations = {hyperliquid: $12k (60%), exness: $8k (40%)}
├─ Hyperliquid: BTC LONG 0.12 ($12k × 1 lev、 内部で3x適用)
└─ Exness:      BTCUSD LONG 0.08 ($8k × 1 lev、 内部で3x適用)
↓
両者約定情報を集約:
├─ 約定価格ズレ < 50pip → OK
└─ 約定価格ズレ ≥ 50pip → 1取引所キャンセル + 全量再発注 (R85)
```

## 6. リスク R84-R87 対策実装

| # | リスク | 実装対応 |
|---|---|---|
| R84 | MT5/Cloud Run間 ZMQ通信障害 | heartbeat 1秒間隔、 30秒応答なしで Exness全閉+Slack通知 |
| R85 | 両取引所約定価格ズレ | exchange_router で 50pip超ズレ検知時に エラーマーク + 後段で再発注ロジック |
| R86 | 緊急退避時 Exness出金遅延 | 残高上限 $50k (Cap 2まで)、 上限超は Hyperliquid sweep |
| R87 | Exness出金経路安全性 | 月次出金で Bitwallet経由 → 国内銀行振込 (1-3日許容) |

## 7. テスト戦略

### 単体テスト (Phase 3前半着手可)
- `tests/test_exness_client.py`: ZMQ mock_mode (実 ZMQ 接続なし、 in-memory メッセージキュー)
- mock_mode で 発注・決済・heartbeat の動作確認

### 結合テスト (Phase 3後半着手)
- ローカル VPS シミュレータ (Docker compose で MT5+ZMQ 環境)
- testnet 取引所 + Cloud Run 経由の E2E テスト
- 通信障害シナリオ (heartbeat 途絶)

### Live検証 (Phase 4 Cap 1 直前)
- 実 VPS + Exness 本口座 + $50 USDT で 1ヶ月並走
- taritari CB 反映の実測 ($93/月 想定)
- 約定価格ズレ統計 (R85)

## 8. 工数試算 (3者会議 Round 34 採用)

| 作業 | 工数 |
|---|---|
| MQL5 EA (DanjerGAIA.mq5 + ZMQ + OrderManager + HealthMonitor) | 3-5日 |
| Python ZMQ Publisher (exness_client.py + テスト) | 1-2日 |
| Order Router 統合 (exchange_router.py に Exness fully) | 2-3日 (済1日 + 追加1-2日) |
| 結合テスト (Docker環境 + E2E) | 2-3日 |
| Live検証 (1週間運用) | 7日 (Shuji作業 5-10分/日のみ) |
| **合計 (Live検証除く)** | **8-13日** |

Round 34 試算 10-16日 とほぼ整合 (検証期間含む合計)。

## 9. 着手前提条件

- [ ] Phase 3 Stage 2 完了 (Day 100以降)
- [ ] Hyperliquid 単独運用が Live で30日以上 安定
- [ ] Shuji が Exness MT5 ログイン状態確認 (既登録口座有効化)
- [ ] Exness 無料VPS 申請 (取引額一定以上で自動付与、 もしくは自前VPS)
- [ ] taritari Exness 紐付け再確認 (Round 30で確認済)

## 10. 着手後の責務分担

| 担当 | 作業 |
|---|---|
| Claude | MQL5 EA + Python ZMQ Publisher + Order Router 統合 + テスト |
| Shuji | VPS立ち上げ確認、 Exness MT5 動作確認、 本番Live移行承認 |
| 3者会議 | Phase 3後半 着手前に Round 39で確認 (現時点ではv8確定、 再議論不要) |

## 付録: 想定する CB 取得経路 (Round 34 Gemini 試算)

```
[Phase 4 Cap 1 例、 月30トレード想定]
1トレード:
- Hyperliquid: 0.6 BTC × $100k = $60k notional × maker rebate -0.001% = -$0.6 (収入)
- Exness:      0.4 BTC × $100k = $40k notional
  ├─ Exness スプレッド: 0.3pip × 0.4 BTC = $12 コスト
  └─ taritari CB: 45.75% × $12 = $5.49 戻り → 実質コスト $6.51

月30トレード:
- Hyperliquid 純益: -$18 (rebate収入)
- Exness 純コスト: $195 (スプレッド) - $89 (CB) = $106
- 合計コスト: $88 (Hyperliquid単独なら $0)

→ Exness 並走による 純追加コスト $88/月
→ ただし taritari CB は税務上「課税対象外の景品扱い」 (Round 34 Gemini確認、 一部解釈に注意)
→ 実質、 Exness 並走の経済効果は 規模拡大 (Cap 3-5) で初めて正味プラス
```

⚠️ Round 34 試算では「Phase 4 Cap 1 で月$93のCB」 と書いたが、 これは **スプレッドコストを控除後の純CB**。 上記再計算で 「並走の経済効果は規模拡大時に発現」 を明示。 Phase 3後半着手時に再評価必要。
