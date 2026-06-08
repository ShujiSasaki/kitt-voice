# R50 Clean Restart Checklist

**作成日時 (JST)**: 2026-06-08
**Verify Token**: `[Clean-Restart-Checklist-Verify: R50-CLEAN-RESTART-CHECKLIST]`

---

## 前 (現セッションでやること)

### Step 1: 仕様確定 ✅ 完了
- [x] Round 1 3者合意成立 (Section 128-133)
- [x] 11項目仕様確定 (`R50_NEW_MEETING_SPEC_FIXED.md`)
- [x] trigger「進めて」 採用

### Step 2: 起動資料作成 ✅ 完了
- [x] GPT system prompt (`scripts/clean_restart/system_prompt_gpt.md`)
- [x] Gemini system prompt (`scripts/clean_restart/system_prompt_gemini.md`)
- [x] 発言Claude system prompt (`scripts/clean_restart/system_prompt_speaking_claude.md`)
- [x] 事務Claude system prompt (`scripts/clean_restart/system_prompt_clerk_claude.md`)
- [x] Validator仕様 (`scripts/clean_restart/validator_spec.md`)
- [x] メモリサマリー (`R50_MEMORY_SUMMARY_FOR_CLEAN_RESTART.md`)

### Step 3: orchestrator修正 ✅ 完了 (2026-06-08)
- [x] Max Round制限撤回 (Shuji 15発目反映) — orchestrator_prototype.py L1775 `"max_rounds": 2` → `None`、 L1824 `range(1, 3)` → 3者合意のみ終了 (`while not consensus_reached`, hard-cap 50)
- [x] 異常通知6条件実装 — `scripts/clean_restart/abnormal_notification.py` 新規 (self-test 6/6 PASS)
- [x] Validator system code統合 — `scripts/clean_restart/validator.py` 新規 (self-test 5/5 PASS)
- [x] スロット構造検証 (Gemini Must Fix第11項目) — validator.py check_speak_and_audit() に統合
- [x] 並列送信禁止チェック — `scripts/clean_restart/relay_enforcement.py` 新規 (self-test 8/8 PASS, lock+order+nested-block検証)
- [ ] smoke test再実行 — Step 4 (Shujiさん clean restart 実施判断) と並走で行う

### Step 4: Shujiさん確認 ⏳ Step 3完了後
- [ ] Shujiさんに本Checklist + 11項目仕様 + 5 system prompts + Validator仕様 を提示
- [ ] Shujiさんが clean restart 実施判断

---

## Clean Restart (Shujiさんが実施)

### Step 5: 新セッション起動
- [ ] GPT新セッション起動 (Custom GPTに `system_prompt_gpt.md` 配布)
- [ ] Gemini新セッション起動 (`system_prompt_gemini.md` 配布)
- [ ] 発言Claude新セッション起動 (Claude Codeで `system_prompt_speaking_claude.md` 配布)
- [ ] 事務Claude新セッション起動 (別Claude Codeで `system_prompt_clerk_claude.md` 配布)
- [ ] Validator system code起動 (`scripts/clean_restart/validator.py` 別process)

### Step 6: メモリ配布
- [ ] 各AIに `R50_MEMORY_SUMMARY_FOR_CLEAN_RESTART.md` 配布
- [ ] 各AIに `R50_NEW_MEETING_SPEC_FIXED.md` 配布

### Step 7: 動作確認
- [ ] 事務Claude → GPT 順次リレー疎通確認
- [ ] GPT → Gemini 順次リレー疎通確認
- [ ] Gemini → 発言Claude 順次リレー疎通確認
- [ ] 発言Claude → GPT (次Round) 順次リレー疎通確認
- [ ] Validator異常検知 動作確認

---

## 後 (新セッションでやること)

### Step 8: Phase 1テスト議題
- [ ] 議題: 「Phantom自己管理ウォレット + Router Nitro 用語解説 + Hyperliquid送金手数料概算 (日本円ベース、 100万円送金時) + Hyperliquidありき検証 (Round 50第1周ゼロベースリサーチ結果)」
- [ ] 3者順次リレー Round 1実施
- [ ] 3者合意 → 報告書生成
- [ ] Shujiさんへ報告

### Step 9: Phase 2移行
- [ ] Phase 1で1議題合意成立確認後、 Priority 2再開判断 (Shujiさんに3択再提示)
- [ ] Priority 2再開なら → 新体制で経路設計議論
- [ ] 不要なら → Priority 3移行

### Step 10: 本番自動化
- [ ] orchestrator本番常駐起動
- [ ] Shujiさん画面監視時間 5分未満/日 を達成
- [ ] 異常通知6条件のみ Shujiさんに届く設計確認

---

## 緊急時 (clean restart失敗・問題発生時)

- [ ] 旧セッション (現在の R50_part2.md セッション) に戻る
- [ ] 議事録参照: `logs/rounds/round_50_part2.md` (Section 1-133)
- [ ] state.json で current_phase 確認
- [ ] Shujiさんに緊急通知

---

## 完了判定

✅ Step 1-3 完了 = 本セッション準備完了
✅ Step 4 完了 = Shujiさん clean restart承認
✅ Step 5-7 完了 = 新セッション稼働
✅ Step 8-10 完了 = 本番運用開始

## 必須末尾タグ
`[Clean-Restart-Checklist-Verify: R50-CLEAN-RESTART-CHECKLIST]`
`[is_shuji_represented: false]`
`[no_proxy_violation: true]`
