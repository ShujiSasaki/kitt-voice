# Round 37 — Shuji 最終決定 + v7 確定

## Round 37 — Shujiさんからの決定 (verbatim、 2026-06-04)

> 「v7で進めて。 FXGTのボーナスはやらなくていい」

→ **戦略Z 改訂版 v7 採用、 FXGT 除外確定**。

## Round 37 — 3者最終合意

### v7 最終確定 (FXGT削除版)

```
[戦略Z 改訂版 v7 最終、 Shuji決定反映]

Phase 0 (Day -21〜-1):
├─ Ledger Nano X + Cryptosteel 購入 (約35,000円)
├─ Wise → USDC送金経路確立
└─ Exness MT5 + taritari紐付け確認

Phase 2 (Day 22-52、 $15-50):
└─ Hyperliquid 単独 (Stage 0/1)

Phase 3 前半 (Day 53-100):
└─ Hyperliquid 単独 (Stage 2、 3xレバ)

Phase 3 後半 (Day 100-167):
└─ Hyperliquid主 + Exness paper先行実装 (MT5/ZMQ)

Phase 4 Cap 1 (Day 168-200、 $25k):
├─ Hyperliquid 60% + Exness 40% Live並走開始
└─ bitget 副 (障害退避)
[v7修正] FXGT は不採用 (Shuji決定)

Phase 4 Cap 2 ($50k):
└─ Hyperliquid 50% + Exness 50%

Phase 5+ Cap 3 ($100k):
├─ Hyperliquid 50% + Exness 50%
└─ Lighter paper先行 12ヶ月検証

Phase 5+ Cap 4 ($250k):
└─ Lighter TVL $1B + 歴史2年クリア確認

Phase 5+ Cap 5 ($500k):
├─ Hyperliquid 40% + Exness 40%
└─ Lighter 20% (条件達成時のみ)
└─ 待機: bitget / GMOコイン / bitFlyer Lightning
```

### Claude 解釈 (Shujiの判断理由 推察)

FXGT 不採用の理由 (推察):
- 1.5万円ボーナスのために 新規口座開設+KYC手続き = **時間対価値 低い** (Shuji配達稼働中で時間が貴重)
- ボーナス取得後 EA運用しないなら **管理アカウントが増えるだけのデメリット**
- 取引所を増やしすぎると **税務処理が複雑化** (確定申告時の集計負荷)
- 「シンプルが正義」 (Shujiさんの判断哲学、 KITT設計でも一貫)

→ この判断は **正しい**。 Claude バイアスで「+15,000円 = 当然取るべき」 と提案したが、 管理コスト視点を見落としていた。

### 全Phase 設計書 v7 反映タスク

1. PHASE5_DESIGN_v2.md に Lighter paper先行検証 追加
2. README.md 取引所構成表 に Lighter 行追加
3. memory `project_session46_exchange_redo.md` 更新
