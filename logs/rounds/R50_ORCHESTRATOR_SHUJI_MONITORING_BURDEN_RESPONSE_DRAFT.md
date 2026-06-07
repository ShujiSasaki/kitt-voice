# R50 Orchestrator Shujiさん監視負担問題への回答ドラフト

**作成日時 (JST)**: 2026-06-07 13:20:00
**Verify Token**: `[Orchestrator-Burden-Draft-Verify: R50-ORCHESTRATOR-SHUJI-MONITORING-BURDEN-RESPONSE-DRAFT]`
**Author**: Claude (実装担当)
**Status**: GPTレビュー前ドラフト (Shujiさん未提示)
**Trigger**: Shujiさん2発目「会議へ発言」 「いつまで私は3人の発言を監視して止まってたらclaudeに動いてって言わなければいけない？」

---

## 結論 (逃げず明確に)

**Shujiさんが3人の発言を監視し続ける運用は失敗です。 即時改善すべきP0問題です。**

本来は監視不要にすべきところを、 現状はClaude自動loopが本番運用できていないため、 Shujiさんが「動いて」 「止まってる？」 等のtriggerを入力する役を負ってしまっている。 これは Phase 1.5実装の目的とズレている。

---

## 1. なぜ今もShujiさんが監視役になっているのか

### Phase 1.5 で実装したもの (動作確認済み)
- race condition / stall Watchdog (P0)
- proxy check / token budget (P1)
- Claude Code event-driven subprocess / Phase 2 trigger (P2)
- 統合テスト + smoke test (controlled real relay) 全PASS

### Phase 1.5実装後でも残った監視負担の原因
1. **Phase 1.5は実装完了したが、 本番運用の自動loop モードに切り替えていない**
   - smoke test (1 cycle GPT→Gemini→Claude→GPT) はPASSしたが、 連続多cycle運用は未投入
   - Round 50後半のPriority 2議論は Claude手動 で1ステップずつ実行
2. **「Shujiさんが画面で監視している」 が暗黙の前提になっていた**
   - GPT/Gemini/Claudeのストリーミング完了をShujiさんが視認 → Claudeに「動いて」 trigger
   - Claudeはwait→fetch→処理→送信→wait のloopを自動化できる仕組みは持っているが起動していない
3. **proxy check等のセーフガードが厳格 = 自動loopをためらう要因**
   - 万一 proxy violation が出たときの巻き戻しコストを恐れて手動運用継続

### Phase 1.5実装の目的とのズレ
- 本来 Phase 1.5 = Shujiさん介入ゼロで 3者会議が自動進行 = 自動loop本番運用
- 現状 = Phase 1.5は実装済みだが本番未投入、 Shujiさんが画面監視

---

## 2. 推奨案: A+B+Cの併用 (GPT判定と整合)

### A. 自動loop化
- ClaudeがGPT/Gemini応答完了を定期fetch (例: 30秒間隔)
- stop/streaming完了確認 → 応答取得 → 必須タグ検証 → next_actorに応じて自動転送
- **Shujiさんに「次の指示」 言わせない**
- 既存orchestrator_prototype.py の自動loopモードを本番起動

### B. 通知化
**Shujiさんに通知するのは以下のみ**:
1. Shujiさん承認が必要な瞬間 (consensus_candidate=true 等)
2. HUMAN_REQUIRED (Watchdog stall 400秒超)
3. proxy violation 重大
4. 3回連続 fetch失敗
5. consensus_candidate=true 到達
6. Must Fix 発生

**通知以外の通常往復は黙って進める** (Shujiさんは画面を見なくてよい)

通知手段 (memory feedback_communication_channels.md準拠):
- Claude Codeチャット (現状の入力欄)
- KITT音声 (KITT PWA経由)
- Email (sasakishuji316@gmail.com)
- ❌ Slack不使用

### C. バッチ化
- 1メッセージごとに Shujiさんに見せない
- **1ラウンド / 1論点ごとにまとめて報告**
- verbatimログは裏で保存 (round_50_part2.md 継続)
- Shujiさんには **要点と承認判断だけ** 出す

### D. 現状維持 (不採用)
- Shujiさんが監視役になるため失敗

---

## 3. Claude/GPT/Geminiそれぞれの停止検知の限界

### Claude (現状の限界)
- Claude自身がwait中は「停止状態」 と外部から見える
- ただし内部的にはbackground commandが動作中で、 通知が来ると再起動
- → 「Claudeが止まっている」 という見え方は **wait中の自然な状態**

### GPT (現状の限界)
- ストリーミング完了タイミングがDOMで検知可能 (stop button消失)
- ただし長文応答時は数十秒〜数分のwait発生
- → wait_gpt_done.py で対応中、 ただし手動trigger必要

### Gemini (現状の限界)
- 同様にDOMでstop button検知可能
- ただし応答時間がGPTより長い場合あり
- → 同じくwait pattern

### 共通の限界
- ストリーミング完了 ≠ 応答品質OK
- 必須タグ (Verify/NextActor/EndTime) が抜けることがあり、 retry必要
- Phase 1.5実装のWatchdogで400秒/600秒の threshold ですべて自動判定可能

---

## 4. 今すぐできる運用改善 (Phase 0 - 緊急)

1. **state.json に `auto_loop_enabled: true` フラグを追加**
   - Claudeはこのフラグを毎ループ確認
   - true = 自動loop継続、 false = 手動trigger待ち
2. **orchestrator_prototype.py の auto loop mode を本番起動**
   - GPT→Gemini→Claude→GPT の循環をShujiさん介入なしで継続
3. **通知発生条件をstate.jsonに明示**
   - 6条件のいずれかでShujiさんへpush

## 5. 実装すべき自動loop案 (Phase 1 - 本格運用)

### loop構造
```
while auto_loop_enabled and not termination_condition:
    1. fetch_current_state (next_actor確認)
    2. if next_actor == "GPT": wait_for_gpt_response + send_to_gemini
    3. if next_actor == "Gemini": wait_for_gemini_response + send_to_gpt
    4. if next_actor == "Claude": claude_implement_task + send_completion
    5. if proxy_violation or human_required: notify_shuji + break
    6. if consensus_candidate == true: notify_shuji + pause
    7. else: continue
```

### 終了条件
- Shujiさん介入待ち (consensus_candidate=true、 Must Fix発生等)
- 自動修復不可能な技術エラー (3回連続失敗)
- Shujiさんからの明示停止指示

### 通知条件
上記 Section 2.B の6条件

### Shujiさんが介入すべき場面
- consensus_candidate=true 到達時の最終承認
- Must Fix への対応判断
- proxy violation の重大判定
- 新規アジェンダの追加

### Shujiさんが介入不要な場面
- 通常の3者往復
- Claude実装タスク (ファイル更新、 commit、 push等)
- 必須タグ検証 retry
- 軽微な proxy_check_stage1 hit (JUSTIFY_PROXY_SAFE bypass )

---

## 6. A+B+C推奨案の評価

| 案 | Shuji負担削減 | 実装コスト | 起動可能タイミング |
|---|---|---|---|
| A. 自動loop化 | 大 | 中 (orchestrator_prototype.py起動 + 動作確認) | 即時可能 |
| B. 通知化 | 大 | 中 (通知条件実装 + KITT音声/Email連携) | 数日 |
| C. バッチ化 | 中 | 小 (報告フォーマット変更) | 即時可能 |
| D. 現状維持 | なし | なし | (不採用) |

**推奨: A+B+C 同時着手** (A最優先、 BとCはAの安定後)

---

## 7. 次のステップ

### Phase 0 (今日中):
- C案 (バッチ化) のフォーマット策定 → Claudeが Shujiさんへ報告するときは「1ラウンド分まとめ」 のみ
- state.json に `auto_loop_enabled` 追加

### Phase 1 (数日内):
- A案 (自動loop化) orchestrator_prototype.py 本番起動
- 起動前にGPT/Geminiでloop設計レビュー
- smoke test → 本番投入

### Phase 2 (数日〜1週間):
- B案 (通知化) 実装
- KITT音声連携 + Email通知
- 6条件発火検証

### Phase 3 (Phase 1/2安定後):
- Priority 2承認依頼に戻す
- その後 Priority 3-7 自動進行

---

## 8. Shujiさんへの透明な情報共有

### 「いつまで監視必要か」 の答え (回避せず)

**現状**: Phase 1.5実装完了済みだが本番未投入のため、 Shujiさんが画面監視役を担っている。 これは設計意図とズレている。

**改善後 (A+B+C実装後)**:
- Shujiさんが画面を見る必要があるのは「Shujiさん判断が必要な瞬間」 のみ
- 通常の3者往復は通知すら不要 (裏で進む)
- Shujiさんは Email/KITT音声で「Shujiさん承認待ちです」 等を受け取って、 そのタイミングで画面を開く

**目標**: 1日あたりShujiさん画面監視時間 5分未満 (現状は数時間)

---

## 必須末尾タグ

`[Orchestrator-Burden-Draft-Verify: R50-ORCHESTRATOR-SHUJI-MONITORING-BURDEN-RESPONSE-DRAFT]`
`[NextActor: GPT]`
`[EndTime-JST: 13:20:00 (real Bash取得予定)]`
`[recommended: A+B+C併用 (自動loop化 + 通知化 + バッチ化)]`
`[priority2_approval_paused_by_shuji_questions: true]`
`[orchestrator_burden_issue_open: true]`
`[is_shuji_represented: false]`
`[no_proxy_violation: true]`
