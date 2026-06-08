# R50 No-Chair Nonstop System Architecture Draft

**作成日時 (JST)**: 2026-06-07 09:35:00
**Verify Token**: `[No-Chair-Architecture-Verify: R50-NO-CHAIR-NONSTOP-SYSTEM-ARCHITECTURE-DRAFT]`
**Trigger**: Shuji 3-6発目 + Gemini Section 123判定 (orchestrator MUST EXECUTE)
**Status**: GPTレビュー前ドラフト

---

## 1. 体制 (司会なし、 システム中心)

| 役割 | 担当 | 動作 |
|---|---|---|
| 発言/監査 | GPT (発言/監査AI) | 議題思考・発言・他者監査のみ。 司会権限なし。 |
| 発言/監査 | Gemini (発言/監査AI) | 同上。 物理限界監査+客観エラー検知も担当。 |
| 発言/監査 | 発言Claude | 同上。 実装監査も担当。 |
| 事務 (機械) | **orchestrator_prototype.py** | 発言の順番リレー、 verbatim転送、 議事録自動更新、 state.json管理。 思考なし。 |
| 会議監査 (Validator) | 別Claudeセッション or system code | orchestrator のverbatim transmissionログを構造チェック。 代弁・捏造検出時にShujiさんへ通知。 |

## 2. 動作フロー

```
[Shujiさん] 議題提示
   ↓
[orchestrator_prototype.py] 自動loop開始
   - 議題を3人 (GPT/Gemini/発言Claude) に同条件で配布
   - 順番で発言取得 → 他2人へ転送
   - 議事録 (round_50_part*.md) 自動追記
   - state.json自動更新
   - Max Round 3 で強制着地 (Gemini指摘反映)
   ↓
[Validator (会議監査)] 並列実行
   - 各転送の verbatim 真正性を chunk比較
   - 代弁・捏造検出 → 即時Shujiさん通知
   ↓
[orchestrator] 合意判定
   - 3人発言 consensus_candidate=true の場合: 報告書自動生成 → Shujiさん通知
   - Max Round到達で未合意: 論点整理 → Shujiさん通知
   - 議論決裂検出: 即時停止 → Shujiさん通知
   ↓
[Shujiさん通知] (6条件のみ)
   1. 合意成立 (consensus_candidate=true、 報告書あり)
   2. Max Round到達 (論点整理あり)
   3. 議論決裂検出
   4. Validator異常検知
   5. Watchdog HUMAN_REQUIRED
   6. 3回連続技術エラー
```

## 3. Max Round制限 (Gemini指摘必須)

- 1議題あたり最大 **3往復 (3 Round)** で強制着地
- 3 Round以内に合意成立 → 報告書生成 → Shujiさん通知
- 3 Round経過しても未合意 → 論点整理 (3者の意見対立点をまとめる) → Shujiさん判断依頼
- コスト暴走防止 (トークン無限消費を物理的にブロック)

## 4. Validator/会議監査の必須要件 (GPT指示で強化)

### 優先順位 (GPT明示)
- **主検証**: **system code / script による機械検証** (Python等、 verbatim文字列の完全一致 chunk比較、 正規表現タグマッチ、 proxy パターンgrep)
- **補助監査**: 別Claudeセッション (system prompt厳格、 思考機能停止)
- **依存回避**: 同じClaude基盤だけに依存しない (system code主体で、 別AI監査はバックアップ)

### 検証対象 (4項目)
1. **verbatim一致**: Shujiさん発言/3者発言と orchestrator転送内容の文字列chunk比較
2. **タグ**: 必須タグ ([Verify], [NextActor], [EndTime-JST], [is_shuji_represented], [no_proxy_violation]) の存在 + 値範囲チェック
3. **proxy violation**: 「Shujiさんなら」 「Shujiの代弁」 「Shujiが認める」 等のパターン正規表現マッチ
4. **未共有検出**: 各Shujiさん発言が GPT/Gemini/発言Claude の **3者全員に転送されたか** を log解析で確認 (本件の根本原因対策)

### 異常検知時
- 即時 Shujiさんへ Email/KITT音声/Claude Codeチャット通知
- 該当発言の転送停止 + 修正待ち
- orchestrator自動停止 (Watchdog発動)

## 5. orchestrator中心への修正点 (事務Claude単独案からの変更)

- **旧案 (事務Claude単独)**: 別Claudeセッションが手動転送、 人間が起動する
- **新案 (orchestrator中心)**: orchestrator_prototype.py が常駐、 完全自動転送
- 理由: Gemini Section 123「APIレベル or スクリプトレベルで順序制御 (リレー) システム化が捏造・転送漏れ防止の唯一の物理的解決策」 を反映

## 6. Shujiさんの介入タイミング

- **介入する**: 議題提示時 + 報告書確認時 + 通知受領時 (6条件のみ)
- **介入しない**: 通常の3者往復、 orchestrator動作、 Validator検証、 議事録更新

## 7. 目標

- Shujiさん画面監視時間: **1日5分未満**
- 議論合意までのShujiさん待ち時間: 議題提示後、 報告書到着までブラックボックス (中身は議事録で確認可)

## 必須末尾タグ
`[No-Chair-Architecture-Verify: R50-NO-CHAIR-NONSTOP-SYSTEM-ARCHITECTURE-DRAFT]`
`[NextActor: GPT]`
`[EndTime-JST: 09:35:00 (real Bash取得予定)]`
`[gemini_max_round3_required: true]`
`[orchestrator_must_execute: true]`
`[is_shuji_represented: false]`
`[no_proxy_violation: true]`
