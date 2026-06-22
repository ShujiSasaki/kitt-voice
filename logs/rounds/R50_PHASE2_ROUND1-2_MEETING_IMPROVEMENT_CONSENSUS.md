# 【会議システム改善】Phase 2 (Round 1-2) 3者合意成立 報告書

**作成日時 (JST)**: 2026-06-08 14:43 JST
**Verify Token (内部用)**: `[Phase2-Consensus-Report-Verify: R50-PHASE2-ROUND1-2-MEETING-IMPROVEMENT]`
**3者合意**: GPT (R2訂正後) + Gemini (R1) + 発言Claude (R1) で確定
**異常通知 condition**: 1 (consensus_reached) 発火

---

## 承認カード (新フォーマット 実演)

### 今回決めること
**会議システム改善5項目 (Phase 2成果) の実装着手 を承認するか**

### 承認すると次に起きること (自動実行)
1. 発言Claudeセッション (別Claude Code) に実装委任
2. 5項目の優先順位で実装着手 (TodoList作成 → 順次完了)
3. 各実装完了ごとに smoke test + commit + push
4. 全実装完了で Shujiさん最終承認カード再提示

### 承認しなかったら何が起きるか
- Phase 1 (Phantom/Router Nitro/手数料/Hyperliquid) の承認も保留継続
- 既存の英語タグ表記+Section番号のみで議事録運用継続 → Shujiさん画面監視時間 1日5分未満目標未達リスク

### リスク (最悪ケース・確率)
- 実装中に追加 Must Fix発見 → 追加Round発生 (確率: 中)
- 既存orchestrator (3777行) との統合で regression発生 (確率: 低、 統合前 smoke test全PASS確認済)
- 承認カードschema が複雑すぎて Shujiさん側で読みづらい (確率: 中、 実装後Shujiさんfeedbackで調整可能)

### 専門用語1行解説 (3つ)
- **承認カードschema**: Shujiさんへの承認依頼を毎回同じフォーマットで提示する型 (Jinja2テンプレート)
- **packet方式**: 発言Claudeを1ターン1プロセスで起動する方式 (セッションを残さない、 堅牢性高い)
- **TOC (Table of Contents)**: 議事録冒頭の目次 (Section番号→日本語タイトルのリスト)

### 推奨option (3つ、 推奨に印)
- ✅ **(A) 全5項目 + bonus 4項目 すべて実装着手** (推奨: 一気にやれば 1日で運用変更完了)
- (B) 優先1-3項目のみ着手 (承認カード/議事録分割/日本語ラベル)、 4-5項目とbonusはPhase 3で議論
- (C) 議論結果は保存、 実装着手はPhase 1承認後に保留

### 判断ポイント (最大3つ)
1. **Shujiさん画面監視を「1日5分未満」 目標達成したいか** (Yes→A推奨)
2. **実装中の追加 Must Fix発生時に追加Round承認できる時間ある** (Yes→A、 No→B)
3. **Phase 1承認とPhase 2実装の順序: 並行進行OKか** (Yes→AまたはB、 No→C)

### 実送金・不可逆操作
**なし** (実装作業のみ、 commit/pushは git revert可能、 実取引なし)

### 承認token (内部用)
`approve:APPROVE-R50-PHASE2-CONSENSUS-001:CONFIRM`

---

## Phase 2 議題 (Shuji 5論点)

1. 各AIが力を最大限発揮できているか (リサーチ/提案/監査/インスピレーション)
2. 議論スピード向上方法 (技術的改善)
3. 事務Claude英語タグ→日本語化 (理解負荷低減)
4. 議事録のターン分割+日本語タイトル+outline
5. 承認求め時の判断材料不足 (先見え、 知識不足)

## 合意成立内容 (5論点)

### 論点1 — 各AI力発揮 (consensus: true)
- **問題認識**: Phase 1で監査機能 OK、 インスピレーション (他者発言から新価値) 弱い
- **改善策**: 各AI発言に「### 追加インスピレーション:」 1行を物理義務化 (Validator regex検出)
- **役割明確化**: GPT=司会・統合、 Gemini=突飛だが安全な代替案、 発言Claude=実装制約・既存資産整合
- **追加: 各Round開始時にGPTが「今Roundの最重要監査観点」 1行宣言** (発言Claude発案)

### 論点2 — 議論スピード向上 (consensus: true)
- **発言Claude起動方式: packet方式 (ステートレス) 単一** (短命セッションプール案撤回)
  - `clean_restart/spawn_claude_turn.sh` 新規
  - state.json + recent_log_diff.md + current_packet.md を引数渡し
  - `claude --model opus-4-7 --no-interactive`
  - 1ターン1プロセス、 終了後state.json更新
- **UI貼付け失敗検知**: `validator.py::check_paste_integrity()` (文字数200以上 + 末尾[no_proxy_violation:true]検証)
  - Quill stop button stuck対策含む
- **並行化対象** (3者発言は単線維持): 議事録append/TOC生成/Validator/log write を asyncio/concurrent.futures、 `fcntl.flock` on state.json で排他
- **議題packetテンプレ**: `templates/agenda_packet.md.j2` (Jinja2)
- **追加: state.json next_actor watcher** (watchdog ライブラリ) で次AI起動trigger自動化
- **追加: packet_hash + state_before/after_hash** で発言追跡 (GPT発案)

### 論点3 — 英語タグ→日本語化 (consensus: true)
- **「日本語ラベル+英語タグ併記」 が唯一の安全設計** (内部英語維持 = トークン効率 + Validator互換)
- **変換テーブル**:
  - `[Claude-Verify]` → 【発言Claude署名】
  - `[NextActor]` → 【次の発言者】
  - `[EndTime-JST]` → 【発言時刻JST】
  - `[is_shuji_represented:false]` → 【Shujiさん代弁:なし】
  - `[no_proxy_violation:true]` → 【代弁違反:なし】
- **実装**: 事務Claude側 (KITT PWA index.html or dashboard_meeting.html) で表示時のみ変換
- **tools/render_minutes_jp.py** で minutes.md → minutes_jp.md 変換 (Shujiさん閲覧用)
- **追加: タグ色分け表示** (CSS変数 verify=green / actor=amber / violation=red) で視認性最大化 (発言Claude発案)

### 論点4 — 議事録ターン分割+日本語タイトル+outline (consensus: true)
- **ファイル構造**: `minutes/R{N}_phase{P}/turn_{seq:03d}_{actor}.md` (1ターン1ファイル、 immutable)
- **TOC**: `minutes/R{N}_phase{P}/TOC.md` を `tools/generate_toc.py` で **新規ターン追加時のみappend** (過去全走査しない = I/O物理限界回避)
- **日本語タイトル生成**: 各ターン冒頭3行から Gemini API (`gemini-2.5-flash`, thinkingBudget:0) で 30文字以内タイトル生成 → ターンファイル先頭に `# [R{N}-P{P}-T{seq}] {jp_title}` 挿入
- **outline**: TOC.md冒頭に `## アウトライン` (論点1: R1合意→R2実装議論→R3合意 形式で周次進捗)
- **UTF-8 validation**: `tools/validate_minutes.py` で encoding='utf-8', errors='strict' (破損防止)
- **追加: ファイル名 _consensus/_dispute suffix** で `grep -l _dispute` で揉めた箇所瞬時抽出 (発言Claude発案)

### 論点5 — 承認カード形式固定 (consensus: true)
- **必須 fields** (`templates/approval_card.md.j2`):
  - card_id
  - 今回決めること (1文)
  - 承認後の自動実行内容 (箇条書き)
  - リスク (最悪ケース・発生確率)
  - 専門用語1行解説 (3つまで)
  - 推奨option (最大3つ、 推奨に印)
  - 実送金/不可逆操作: Dry-run結果生データ + 実行APIコマンド verbatim + 最大許容損失 (Slippage上限) + 別途明示承認token
- **承認token**: 実送金時のみ Shujiさんが `approve:APPROVE-R{N}-{seq}:CONFIRM` を返答 → token照合一致で実行 (不一致時は実行拒否)
- **履歴**: `approvals/APPROVE-R{N}-{seq}.json` に card+返答+実行結果 永続化
- **追加: 「承認しなかったら何が起きるか」 1行必須化** (機会損失/現状維持コスト、 発言Claude発案)

## 3者発言overall_consensus_candidate

| Actor | R1 | R2 | 最終 |
|---|---|---|---|
| GPT | true (両論併記) | **true** (Must Fix受諾、 packet方式単一確定) | true |
| Gemini | true (5論点物理限界補強) | (R1で確定) | true |
| 発言Claude | true (実装観点詳細化) | (R1で確定、 GPT両論併記Must Fix→受諾) | true |

→ **Phase 2 3者合意成立 (overall_consensus_candidate: true)**

## 優先実装順 (発言Claude推奨、 工数+Shujiさん体感改善の積)

1. **承認カードschema** (`templates/approval_card.md.j2` + jsonschema validation)
2. **議事録ターン分割+TOC append-only** (`minutes/R{N}_phase{P}/` ディレクトリ構造 + `tools/generate_toc.py`)
3. **日本語ラベル併記表示** (KITT PWA側 CSS + JS変換) + タグ色分け
4. **議題packetテンプレ+UI貼付け失敗検知** (`templates/agenda_packet.md.j2` + `validator.py::check_paste_integrity()`)
5. **追加インスピレーション義務化** (`validator.py::validate_inspiration()`)

Bonus (3者会議の inspiration成果):
- packet_hash/state_hash (GPT)
- state.json watcher (発言Claude)
- タグ色分け (発言Claude)
- 承認カード「やらない時のコスト」 (発言Claude)

## Validator 7検証 (Phase 2 Round 1-2 通算)
- Item 1 verbatim一致: PASS
- Item 2 必須タグ: PASS (3者全Round)
- Item 3 proxy violation: PASS (0件)
- Item 4 未共有検出: PASS
- Item 5 順番飛ばし: PASS (R1 GPT→Gemini→Claude、 R2 GPT訂正発言)
- Item 6 発言監査欠落: PASS
- Item 7 スロット構造遵守: PASS

## 並列送信禁止
PASS (Round 1-2 通じて順次タイムスタンプ遵守、 0件違反)

## Shujiさん最終承認待機事項
本承認カードの (A)(B)(C) から選択。 推奨: (A)。

---

## 異常通知 (内部用)
- condition: 1 (consensus_reached)
- 通知時刻 (JST): 2026-06-08 14:43 JST
- severity: info
- requires_shuji_action: true

## 必須末尾タグ (内部用、 Validator互換維持)
`[Phase2-Consensus-Report-Verify: R50-PHASE2-ROUND1-2-MEETING-IMPROVEMENT]`
`[phase2_consensus_candidate: true]`
`[gpt_round2_correction_received: true]`
`[abnormal_notification_code: 1]`
`[is_shuji_represented: false]`
`[no_proxy_violation: true]`

**【内部タグ→日本語ラベル変換 (Shujiさん閲覧用)】**
- 【Phase 2合意報告署名】: R50-PHASE2-ROUND1-2-MEETING-IMPROVEMENT
- 【Phase 2合意候補】: true
- 【GPT Round 2訂正受領】: true
- 【異常通知コード】: 1 (合意成立)
- 【Shujiさん代弁】: なし
- 【代弁違反】: なし
