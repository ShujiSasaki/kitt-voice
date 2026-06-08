# R50 Memory Summary for Clean Restart

**作成日時 (JST)**: 2026-06-08
**Verify Token**: `[Memory-Summary-Verify: R50-MEMORY-SUMMARY-FOR-CLEAN-RESTART]`
**目的**: clean restart 後の新セッション (GPT/Gemini/発言Claude/事務Claude/Validator) に必須情報を圧縮して引き継ぐ

---

## 1. プロジェクト概要

- **Owner**: Shujiさん (sasakishuji316@gmail.com)
- **作業ディレクトリ**: `/Users/shuji/Desktop/kitt-voice`
- **目的**: BTC自動売買システム + 3者AI意思決定システム構築
- **Phase**: Round 50 後半、 Priority 2 (送金経路) は完全停止 → 会議運営システム作成優先

## 2. Shujiさんプロフィール (非エンジニア配慮)

- 専門用語は噛み砕いて説明 (Phantom/Router Nitro等は事前解説必要)
- 「Claudeが全部やる」 ことに価値を感じる (手順書だけ渡して終わりにしない)
- 不要な確認質問を望まない (自分で判断して実行)
- 本音ベース、 嘘禁止

## 3. 過去Claude仮想会議の歴史と教訓

- Round 30-47の一部 = Claude単独捏造 (Wise送金=規約違反を見落とし)
- Round 49以降 = 本物4者会議 (GPT/Gemini/Claude/Shuji)
- Round 50第1周 = ゼロベース全選択肢リサーチ (Hyperliquid+Wise前提廃止)
- Round 50後半 = Priority 2議論 + 自動化欠如指摘 + 5人会議化決定
- **教訓**: 並列送信禁止、 順次リレー徹底、 スロット構造義務化

## 4. 会議運営11項目仕様 (Round 1で3者合意確定)

1. 司会なし
2. 全員 発言+監査
3. GPT→Gemini→発言Claude 単線直列輪番
4. 並列送信禁止
5. 終了条件 = 3者合意のみ
6. Max Round強制終了なし
7. 異常通知6条件 (合意/決裂/Validator異常/HUMAN_REQUIRED/3回失敗/コスト停滞)
8. 事務Claude/orchestrator 思考停止
9. Validator system code 検証7項目
10. Priority 2旧合意無効 + Shuji C選択で完全停止 + 会議運営優先
11. **全アクター必須出力スロット構造の規定** (### 1. 自意見 + ### 2. 前走者監査)

## 5. trigger運用

- 過渡期: 「進めて」
- 本番: trigger不要 (orchestrator自動)
- 廃止: 「gptに次の指示を仰いで」

## 6. Priority 2 (送金経路) 状態

- **consensus_candidate=false** (旧 true 無効化)
- **Shuji C選択 = 完全停止**
- Phantom/Router Nitro/手数料/Hyperliquid前提検証は **新体制で再議論予定** (Phase 1テスト議題候補)

## 7. 5人会議体制

| 役割 | 担当 |
|---|---|
| 発言/監査 | GPT (整合性・戦略) |
| 発言/監査 | Gemini (物理限界・客観監査) |
| 発言/監査 | 発言Claude (実装・技術) |
| 事務 | 事務Claude (思考停止、 verbatim中継、 別セッション) |
| 会議監査 | Validator (system code/script、 補助Claude) |

## 8. 実装ファイル (clean restart後参照可)

- 議事録: `logs/rounds/round_50_part2.md` (Section 1-133)
- 仕様: `logs/rounds/R50_NEW_MEETING_SPEC_FIXED.md`
- system prompts: `scripts/clean_restart/system_prompt_*.md`
- Validator仕様: `scripts/clean_restart/validator_spec.md`
- メモリサマリー: 本ファイル
- orchestrator: `scripts/orchestrator_prototype.py` (修正必要、 Max Round撤回 + 異常通知6条件 + Validator統合 + スロット構造検証)
- state.json: `logs/state.json` (current_phase + フラグ管理)

## 9. clean restart前後の手順

### 前 (現セッション)
1. 本サマリー完成 (本ファイル)
2. 5 system prompts完成
3. Validator仕様完成
4. orchestrator修正 (次タスク)
5. Shujiさん確認

### restart
6. Shujiさんが各AIで新セッション起動 + system prompt配布
7. 事務Claudeセッション起動
8. orchestrator起動

### 後
9. 最初のテスト議題実施 (Phase 1 = Phantom/Router Nitro/手数料/Hyperliquid前提検証 - 新体制で)
10. 3者合意 → 報告書生成 → Shujiさん最終承認

## 10. 禁止事項 (新セッションでも遵守必須)

- Shujiさん承認の代弁
- 並列送信 (Shujiさん発言含む)
- Max Round強制終了
- 司会権限の行使
- 事務Claudeの議題思考
- 「gptに次の指示を仰いで」 trigger
- Priority 2再開 (Shuji C選択により完全停止中)
- 実送金・実運用 (Shujiさん承認なしで一切実行不可)

## 必須末尾タグ
`[Memory-Summary-Verify: R50-MEMORY-SUMMARY-FOR-CLEAN-RESTART]`
`[round1_consensus: true]`
`[memory_items_count: 11]`
`[priority2_consensus_candidate: false]`
`[priority2_fully_stopped: true (Shuji C選択)]`
`[meeting_operations_build_first: true]`
`[is_shuji_represented: false]`
`[no_proxy_violation: true]`
