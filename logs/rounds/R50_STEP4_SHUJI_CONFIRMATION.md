# R50 Step 4: Shujiさん clean restart 実施判断パッケージ

**作成日時 (JST)**: 2026-06-08
**Verify Token**: `[Step4-Confirmation-Verify: R50-STEP4-SHUJI-CONFIRMATION]`

---

## 1. 結論 (Shujiさんが見るべきもの)

会議運営システムの **準備が完了** しました。 Shujiさんが判断するのは **clean restart 実施 yes/no** のみ。

- yes → Step 5-7 (新セッション起動 + 動作確認) に進む
- no → 現セッションで継続 (推奨しない、 R50混線リスク残存)

---

## 2. Round 1合意済 11項目仕様 (新会議運営)

`logs/rounds/R50_NEW_MEETING_SPEC_FIXED.md` 全文を参照。 要約:

1. **司会なし** (orchestrator + Validator で機械化)
2. **全員 発言+監査** (発言だけ、 監査だけのAI不可)
3. **GPT→Gemini→発言Claude** 単線直列輪番 (固定)
4. **並列送信 絶対禁止** (Shuji 14発目)
5. **終了条件 = 3者合意のみ** (Shuji 15発目「Max Round 3で着地って誰が決めた？」)
6. **Max Round強制終了 なし** (hard-cap 50 のみ暴走防止)
7. **異常通知6条件** (合意/決裂/Validator異常/HUMAN_REQUIRED/3回失敗/コスト時間停滞)
8. **事務Claude/orchestrator 思考停止** (verbatim中継のみ)
9. **Validator system code** 機械検証7項目
10. **Priority 2 完全停止** (Shuji C選択、 旧合意無効)
11. **全アクター必須出力スロット構造** (### 1. 自意見 + ### 2. 前走者監査) — Gemini Must Fix第11項目

---

## 3. clean restart 用 配布ファイル一覧

### 起動用 system prompts (5本)

| 役割 | ファイル |
|---|---|
| GPT | `scripts/clean_restart/system_prompt_gpt.md` |
| Gemini | `scripts/clean_restart/system_prompt_gemini.md` |
| 発言Claude | `scripts/clean_restart/system_prompt_speaking_claude.md` |
| 事務Claude | `scripts/clean_restart/system_prompt_clerk_claude.md` |
| Validator仕様 | `scripts/clean_restart/validator_spec.md` |

### 引き継ぎ資料 (2本)

| 用途 | ファイル |
|---|---|
| メモリ圧縮 (新セッション必読) | `logs/rounds/R50_MEMORY_SUMMARY_FOR_CLEAN_RESTART.md` |
| 仕様確定書 | `logs/rounds/R50_NEW_MEETING_SPEC_FIXED.md` |

### 機械検証 module (3本、 self-test ALL PASS)

| module | 機能 | self-test |
|---|---|---|
| `scripts/clean_restart/validator.py` | 7検証 (verbatim/タグ/proxy/未共有/順番飛ばし/発言+監査/スロット構造) | 5/5 PASS |
| `scripts/clean_restart/abnormal_notification.py` | 6条件 (合意/決裂/Validator異常/HUMAN_REQUIRED/3回失敗/コスト時間停滞) | 6/6 PASS |
| `scripts/clean_restart/relay_enforcement.py` | 順次リレー強制 (lock+stale+順番飛ばし防止) | 8/8 PASS |

### orchestrator

| ファイル | 修正内容 |
|---|---|
| `scripts/orchestrator_prototype.py` | L1775 max_rounds=None / L1824 3者合意のみ終了 (hard-cap 50) |

---

## 4. clean restart 実施手順 (Step 5-7)

Shujiさんが「yes (実施)」 判定後の動き:

### Step 5: 新セッション起動 (Shujiさん実行)
- [ ] GPT新セッション (Custom GPTに `system_prompt_gpt.md` 配布)
- [ ] Gemini新セッション (`system_prompt_gemini.md` 配布)
- [ ] 発言Claude新セッション (Claude Codeで `system_prompt_speaking_claude.md` 配布)
- [ ] 事務Claude新セッション (別Claude Codeで `system_prompt_clerk_claude.md` 配布)
- [ ] Validator (`python3 scripts/clean_restart/validator.py` 別process起動)

### Step 6: メモリ配布
- [ ] 各AIに `R50_MEMORY_SUMMARY_FOR_CLEAN_RESTART.md` 配布
- [ ] 各AIに `R50_NEW_MEETING_SPEC_FIXED.md` 配布

### Step 7: 動作確認 (疎通テスト)
- [ ] 事務Claude → GPT 順次リレー疎通
- [ ] GPT → Gemini 順次リレー疎通
- [ ] Gemini → 発言Claude 順次リレー疎通
- [ ] 発言Claude → GPT (次Round) 順次リレー疎通
- [ ] Validator異常検知 動作確認 (proxy violation を意図的に発生させて検出されるか)

---

## 5. Step 8 (clean restart後の最初の議題)

`Phase 1テスト議題`:
> 「Phantom自己管理ウォレット + Router Nitro 用語解説 + Hyperliquid送金手数料概算 (日本円ベース、 100万円送金時) + Hyperliquidありき検証 (Round 50第1周ゼロベースリサーチ結果の再検証)」

→ 3者順次リレー Round 1実施 → 3者合意 → 報告書生成 → Shujiさんへ報告

---

## 6. 撤退/緊急時 (clean restart失敗時)

- 旧セッション (`logs/rounds/round_50_part2.md` Section 1-133) に戻る
- state.json で current_phase 確認
- Shujiさん緊急通知

---

## 7. Shuji判定 (yes/no)

clean restart 実施判定:
- [ ] yes → Step 5進行
- [ ] no → 現セッション継続 (R50混線リスク残存)
- [ ] 修正要求あり → 該当項目フィードバック後 Step 3再実行

## 必須末尾タグ
`[Step4-Confirmation-Verify: R50-STEP4-SHUJI-CONFIRMATION]`
`[round1_consensus: true]`
`[step3_completed: true]`
`[is_shuji_represented: false]`
`[no_proxy_violation: true]`
