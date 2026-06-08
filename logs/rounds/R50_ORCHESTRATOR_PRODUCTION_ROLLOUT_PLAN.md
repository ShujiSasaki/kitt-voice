# R50 Orchestrator Production Rollout Plan

**作成日時 (JST)**: 2026-06-07 09:35:00
**Verify Token**: `[Orchestrator-Rollout-Verify: R50-ORCHESTRATOR-PRODUCTION-ROLLOUT-PLAN]`
**Trigger**: Shuji 6発目 (システム導入許可) + Gemini Section 123 (MUST EXECUTE)
**Status**: GPTレビュー前ドラフト

---

## 1. orchestrator_prototype.py 本番移行 controlled rollout

### Phase 0: 状態リセット (即時)
- 旧Priority 2 consensus_candidate=true 破棄 (実施済)
- state.json に `auto_loop_enabled: false` (初期値) 追加
- `real_send_enabled: false` 維持
- 全 3者 (GPT/Gemini/発言Claude) に「Shuji 1-7再同期済み状態」 を共有 (実施済)

### Phase 1: 第一タスク = Shuji 1-7再同期済み状態からの再テスト
- orchestrator を smoke test ではなく **本物の議題で1 Round** 実行
- 議題: Shuji 1発目「Phantom/Router Nitro/手数料/Hyperliquidありき検証」
- Max Round 3 制限を有効化
- Shujiさん介入なしで報告書到達まで自動実行
- 失敗時: Watchdog HUMAN_REQUIRED でShujiさん通知

### Phase 2: 制限緩和 (Max Round 3固定維持)
- Phase 1で1議題合意成立を確認後、 Priority 2 残課題 (経路B v4.1 再判定) を投入
- **Max Round 3 固定維持** (Phase 1-2 共通)
- Max Round 5以上への緩和は、 **Shujiさん明示承認 + 3AI合意** 後のみ
- **初期本番では無制限loop禁止**
- 通知6条件を実装 (Email/KITT音声/Claude Codeチャット)

### Phase 3: 完全自動運転
- Priority 3-7 を順次 orchestrator で自動議論
- Shujiさん画面監視時間 5分未満/日 を達成
- Phase 2 → Phase 3 移行は3者合意が必要

## 2. 必須制約

### real_send_enabled制御
- **本番移行中も `real_send_enabled=false` を維持**
- Geminiに送信する瞬間のみ controlled で true に切替、 送信後即座にfalseに戻す
- 無制限 auto loop は禁止

### Max Round制限 (Gemini必須要件)
- 1議題あたり最大 3 Round (Phase 2まで)
- Phase 3で緩和検討
- コスト暴走防止

### 通知6条件
1. 合意成立 (consensus_candidate=true)
2. Max Round到達 (論点整理あり)
3. 議論決裂検出
4. Validator異常検知
5. Watchdog HUMAN_REQUIRED
6. 3回連続技術エラー

### Validator必須
- orchestratorと並列実行
- 代弁・捏造検出時に即時 Shujiさん通知

## 3. 既存資産との接続

- `scripts/orchestrator_prototype.py` (Phase 1.5実装済、 smoke test PASS)
- `logs/state.json` (現状の state管理)
- `logs/rounds/round_50_part*.md` (議事録 verbatim)
- `~/.claude/projects/-Users-shuji-Desktop-kitt-voice/memory/MEMORY.md` (Claude memory)

## 4. 第一タスクの具体的実行計画

### 議題: Shuji 1発目「Phantom/Router Nitro/手数料/Hyperliquidありき検証」

#### 入力
- Phantom自己管理ウォレットの解説
- Router Nitroの解説
- 経路B (主・副・第二バックアップ) の手数料概算 (**日本円ベース**、 100万円送金時)
- Hyperliquidありきだったかの検証 (Round 50第1周のゼロベースリサーチ結果含む)

#### 期待出力
- 3者合意の Shujiさん向け回答報告書
- 議事録 (3者発言 verbatim)
- consensus_candidate true or false 判定

#### Max Round
- 3 Round以内で合意 → 報告書出力
- 3 Round未合意 → 論点整理 + Shujiさん判断依頼

## 5. 失敗時のロールバック

- orchestrator異常停止時 → Shujiさんに即時通知 + 旧手動運用に戻す
- 報告書品質が低い場合 → Shujiさん B案 (先に手数料概算だけ出す) に切替
- 3 Round以内合意不可 → Shujiさん C案 (Priority 2完全停止して会議運営だけ作る) に切替

## 6. Shujiさん介入タイミング

- 議題提示時
- 報告書確認時 (Phase 1終了)
- 6条件発火時の通知受領

## 必須末尾タグ
`[Orchestrator-Rollout-Verify: R50-ORCHESTRATOR-PRODUCTION-ROLLOUT-PLAN]`
`[NextActor: GPT]`
`[EndTime-JST: 09:35:00 (real Bash取得予定)]`
`[real_send_enabled_maintained: false]`
`[max_round_limit: 3 (Phase 1-2)]`
`[notification_conditions: 6項目]`
`[is_shuji_represented: false]`
`[no_proxy_violation: true]`
