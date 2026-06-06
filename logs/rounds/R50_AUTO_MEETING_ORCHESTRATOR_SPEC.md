# R50 Auto Meeting Orchestrator Spec

## 1. Goal

Shujiさんが呼び鈴にならなくても、 議題提出から3者合意まで自動で進む。

## 2. Selected Architecture

**Local Playwright Orchestrator**

(Gemini第19監査+GPT第35採択: 案B+Playwright)

## 3. Why

Claudeは自発的にGPT指示を確認しに行けない。 外部プロセスがChromeタブと state.json を監視して、 次Actorへ自動送信する。

## 4. Components

- `scripts/orchestrator.py` (本実装、 Phase 1.5以降)
- `scripts/orchestrator_prototype.py` (Phase 1 雛形)
- `logs/state.json` (状態機械)
- `logs/queue.json` (キュー)
- `logs/rounds/round_50_part*.md` (議事録)
- `logs/rounds/R50_BELL_PROTOCOL.md` (Bell Protocol仕様)
- `logs/dashboard.html` (可視化、 将来)

## 5. State Machine

| State | Description |
|-------|-------------|
| IDLE | 待機中 (議題なし) |
| NEW_TOPIC | 新議題受信 |
| SEND_TO_GPT | GPTへプロンプト送信 |
| WAIT_GPT | GPT応答待ち (stopBtn polling) |
| LOG_GPT | GPT応答を議事録追記 |
| SEND_TO_GEMINI | Geminiへプロンプト送信 |
| WAIT_GEMINI | Gemini応答待ち |
| LOG_GEMINI | Gemini応答を議事録追記 |
| SEND_TO_CLAUDE | Claudeへプロンプト送信 (Phase 1.5+) |
| WAIT_CLAUDE | Claude応答待ち |
| LOG_CLAUDE | Claude応答を議事録追記 |
| CHECK_CONSENSUS | 3者合意検知 (Verify Token+承認文字列パース) |
| NEXT_LOOP | 次ラウンドへ |
| SHUJI_CONFIRM | Shujiさん最終確認待ち |
| ERROR | エラー状態 (Failure Handling 9参照) |

## 6. Single Lock Rule

同時実行は禁止。 `state.json` に `lock=true` の時は新処理を開始しない。

実装: `acquire_lock()` / `release_lock()` で atomic file rename を使う。

## 7. Send Success Rule

3条件全成立で Send成功とみなす:

1. `editor=0` (入力欄空)
2. `userCount +1` (user投稿数増加)
3. `stopBtn=true` または response開始

failしたら `SEND_FAILED` で 再inject+再Send。

## 8. Response Complete Rule

5条件全成立で Response完了とみなす:

1. `stopBtn=false` (生成停止)
2. assistant本文あり
3. Verify Tokenあり (`[<Actor>-Verify: ...]`)
4. NextActorあり (`[NextActor: ...]`)
5. EndTime-JSTあり (`[EndTime-JST: HH:MM:SS]`)

failしたら タイムアウト判定 (Section 9)。

## 9. Failure Handling

| Error | Handling |
|-------|----------|
| FETCH_ERROR | DOM取得失敗 → reload+再取得 |
| SEND_FAILED | Send反映失敗 (userCount未増加) → 再inject+再Send |
| VERIFY_TOKEN_MISSING | 応答末尾にVerify Tokenなし → INVALID/再要請 |
| NEXTACTOR_MISSING | NextActorタグなし → INVALID/再要請 |
| ENDTIME_MISSING | EndTime-JSTタグなし → INVALID/再要請 |
| TIMEOUT | 一定時間 (例120秒) 応答なし → reload+再送 |
| LOCK_STALE | lock=true が 一定時間以上 → 強制release |

## 10. Phase 1 Prototype Scope

まずは **「GPT→Gemini→GPT」 の2者循環** で実弾テスト。

- Claudeは議事録追記と転送だけ
- 3者完全自動は Phase 1.5
- 議題提出はShujiさんが手動 (CLIまたはWebUI 1回打鍵)

## 11. Phase 2

OpenAI / Gemini / Claude API化。 Web UI依存を減らす。

長期的には orchestrator.py が API直接呼び出し → コスト+安定性 トレードオフ後 採択。

---

由来: Shuji#27 → GPT第33 (5案A-E) → Gemini第19 (案B+Playwright GREEN承認、 3ステップロードマップ) → GPT第35 (Local Playwright Orchestrator方式採択+本仕様確定)

`[GPT-Verify: R50-AUTO-ORCHESTRATOR-PROTOTYPE-2251]`
