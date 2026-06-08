# R50 新ぐるぐる3者会議 仕様確定版

**作成日時 (JST)**: 2026-06-08
**Verify Token**: `[New-Meeting-Spec-Fixed-Verify: R50-NEW-MEETING-SPEC-FIXED]`
**3者合意**: GPT (Section 128/129/131) + Gemini (Section 130/132) + 発言Claude (Section 133) で確定
**Round 1 完了**: Round 2不要、 Round 1で全Q1-Q11合意

---

## 確定仕様 (11項目、 メモリ化必須)

### 1. 司会なし
GPT/Gemini/発言Claudeの誰も司会権限を持たない。 順次リレーで自動進行。

### 2. 全アクター 発言+監査 (Shuji 13発目)
3者全員 (GPT/Gemini/発言Claude) は **自分の意見発言** + **他者発言の監査** を両方実施する。 監査だけする人はいない。

### 3. 輪番運用 (Shuji 12/14発目)
**GPT → Gemini → 発言Claude → (Round完了判定) → GPT** の単線直列バトンリレー。

### 4. 並列送信禁止 (Shuji 14発目)
Shujiさん発言含めて並列送信絶対禁止。 緊急共有ログのみ参考扱い (議事録 verbatim残存)。

### 5. 終了条件: 3者合意のみ (Shuji 15発目)
3者 (GPT/Gemini/発言Claude) 全員が consensus_candidate=true を出した場合のみ終了。

### 6. Max Round強制終了なし
Round数による強制終了は **しない**。 議論は3者合意成立まで継続。

### 7. 異常通知条件 (終了条件ではない)
以下6条件で Shujiさんへ通知 (議論は継続):
1. 3者合意成立 (報告書生成)
2. 議論決裂検出
3. Validator異常
4. Watchdog HUMAN_REQUIRED
5. 3回連続技術エラー
6. **コスト/時間/論点停滞** の上限到達 (Gemini Section 123要件)

### 8. 事務Claude/orchestratorは思考しない
verbatim transmissionのみ。 議題への意見・代弁・捏造は禁止。

### 9. Validator機械検証 (system code主体)
以下7項目を検証:
1. verbatim一致 (Shuji発言/3者発言と転送内容のchunk比較)
2. 必須タグ確認 ([Verify], [NextActor], [EndTime-JST], [is_shuji_represented], [no_proxy_violation])
3. proxy violation検出 (「Shujiさんなら」 等パターン)
4. 未共有検出 (各発言が3者全員に転送されたか)
5. 順番飛ばし検出 (GPT→Gemini→Claude順序遵守)
6. 発言監査欠落検出 (3者全員が「発言+監査」 両方実施)
7. **スロット構造遵守検証** (Gemini Must Fix第11項目)

### 10. Priority 2旧合意無効、 Shuji C選択により完全停止
Priority 2 consensus_candidate=true は2026-06-07に無効化済。 Shujiさん C選択 = Priority 2完全停止 + 会議運営システム作成優先。

### 11. 全アクター必須出力スロット構造 (Gemini Must Fix第11項目)
各AIコアは以下の見出し出力を物理義務化:
- `### 1. 自身の意見・回答セクション`
- `### 2. 前走者発言への監査・批判セクション`

これを忘れると clean session移行後また「発言のみで監査サボる」 状態に逆戻り。

---

## trigger運用

### 過渡期 (本仕様実装中)
- **基本**: 「進めて」
- 明示: 「次のスロットへ」
- AI指定が必要な時のみ: 「Geminiの発言を取って」 等
- **禁止**: 「gptに次の指示を仰いで」 (司会GPT残響)

### 本番 (orchestrator自動化後)
- **Shujiさん trigger不要**
- orchestrator が自動進行
- Shujiさん介入は: 議題提示 + 報告書確認 + 緊急停止 + 訂正 + 追加指示 のみ

---

## clean restart方針

### 6ステップ (GPT Section 129)
1. 現行セッションで新会議仕様確定 ← **完了** (Round 1)
2. 仕様確定サマリー作成 ← 本ファイル
3. GPT/Gemini/発言Claude/事務Claude/Validator用 起動資料作成 ← 次の実装
4. Shujiさん確認
5. clean restart
6. 新セッションで最初のテスト議題実施

---

## Shujiさんの介入タイミング

### 介入する
- 議題提示時
- 報告書確認時
- 6条件通知受領時 (合意/決裂/異常/HUMAN_REQUIRED/技術エラー/コスト停滞)
- 緊急停止/訂正/追加指示

### 介入しない
- 通常の3者発言往復
- 事務Claude/orchestrator動作
- Validator検証動作
- 議事録更新

### 目標
Shujiさん画面監視時間 **1日5分未満**

---

## 必須末尾タグ
`[New-Meeting-Spec-Fixed-Verify: R50-NEW-MEETING-SPEC-FIXED]`
`[round1_consensus: true]`
`[memory_items_count: 11]`
`[max_round_revoked: true]`
`[meeting_termination_condition: 3-agent consensus only]`
`[parallel_relay_allowed: false]`
`[trigger_transitional: 進めて]`
`[trigger_production: none (orchestrator自動)]`
`[is_shuji_represented: false]`
`[no_proxy_violation: true]`
