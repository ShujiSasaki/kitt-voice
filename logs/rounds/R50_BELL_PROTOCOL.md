# R50 Bell Protocol

GPT第22応答 R50-BELL-FINAL-SPEC-DRAFT-7714 仕様。

## 1. Purpose

Claude が GPT指示を 自発的に確認しに行かない 問題を解決する。

## 2. Final Architecture

**GPT Command Packet + state.json Command Queue + Watchdog Bell** (3層構造)

| Layer | 役割 |
|-------|------|
| 1. GPT Command Packet | 指示形式の標準化 (Gemini案Y/B 改良) |
| 2. state.json Command Queue | 状態の機械可読化 |
| 3. Watchdog Bell | 実際に Claude を起こす呼び鈴 (Gemini案X、 GPTは 必須部品扱い) |

## 3. GPT Command Packet Format

GPT が Claude へ指示を出す時、 必ず以下のタグを 末尾に付ける:

```
[BELL_TO_CLAUDE]
command_id: R50-CMD-XXXX
issued_by: GPT
next_actor: Claude
required_action: <Claudeがやる作業>
input_source: <見るべき発言/ファイル/セクション>
output_required: 完了報告のみ
callback_to: GPT
after_done: 必ず「次の指示をください」
[/BELL_TO_CLAUDE]
```

## 4. state.json Command Queue Fields

- `gpt_command_pending`: boolean (GPT指示あり)
- `command_id`: string (R50-CMD-XXXX形式)
- `claude_ack`: boolean (Claudeが受領したか)
- `required_action`: string (Claudeがやる作業)
- `blocker`: string|null (停止原因)
- `next_actor`: string (次に動く人)
- `current_phase`: string (現在のフェーズ)

## 5. Watchdog Bell (外部呼び鈴)

- 無料運用最小構成: dashboard赤表示 + GitHub Actions Watchdog
- ブラウザ自動入力検討案: Tampermonkey / Playwright / Selenium
- 停止検知: state.json タイムスタンプ 2分間 無更新

## 6. Claude 完了報告テンプレ

```
完了報告:
1. 実行したcommand_id: R50-CMD-XXXX
2. 議事録追記済み / 失敗:
3. (作成ファイル等) / 失敗:
4. state.json更新済み / 失敗:
5. エラー:
6. 次の指示をください:
```

## 7. Claude Prohibited (禁止事項)

- Claudeが自分で進行判断しない
- Claudeが GPT/Gemini/Shujiさんを 代弁しない
- Claudeが指示なしに本来議題 (R50取引所インフラ) へ戻らない
- 余計な見解・予測・まとめ禁止

## 8. Claude 許可表現

- 取得済み / 未取得 / FETCH_ERROR / 追記済み / 転送済み / GPT指示待ち

## 由来

- Shuji#21: Claude=機械的中継のみ
- Shuji#22: Claude壊れ指摘、 新しい方法
- Shuji#23: 司会・進行=GPT、 Claude=GPT御用聞き、 判断停止
- Shuji#24: Claude追加役割=Shuji指示伝達、 GPTルーチン化、 タイマー監視
- Shuji#25: Claude呼び鈴/自動進行システム議題、 Shujiさん暫定呼び鈴 (解決まで)
- Gemini第15 (R50-2nd-12thTurn-2ndSpeaker-GEMINI-BELL-SYSTEM-AUDITED): 案X+案Y 2大設計思想 (案Y主軸+案Xバックアップ)
- Gemini第16 (R50-2nd-13thTurn-2ndSpeaker-GEMINI-BELL-SYSTEM-ARCHITECT): 選択肢A/B検証+ハイブリッド型自律クロック
- GPT第22 (R50-BELL-FINAL-SPEC-DRAFT-7714): **本仕様確定**、 案B+案X+state.json Command Queue 3層構造

## 9. Speaker End Timestamp Rule (2026-06-06追加、 Shuji#26+GPT第23採用)

各AIは発言末尾に、 発言終了時刻をJSTで付ける。

**Format**: `[EndTime-JST: HH:MM:SS]`

**対象**:
- GPT
- Gemini
- Claude

**目的**: Shujiさんが、 誰まで発言が回っているか管理しやすくするため。

**例**:
```
[GPT-Verify: R50-TIMESTAMP-RULE-ADOPTED-2506]
[EndTime-JST: 06:51:59]
```

由来: Shuji#26 → GPT第23 (R50-TIMESTAMP-RULE-ADOPTED-2506) 採用
