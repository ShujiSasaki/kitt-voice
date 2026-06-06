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

## 10. Phase 1 Prototype Scope (Revised 2026-06-06 GPT第37採用)

**修正**: Phase 1から Claude を 会議運用ループから **完全に外す**。

**範囲** (GPT↔Gemini 2者循環を Playwrightが全代行):

1. **Chrome CDP接続** (ログイン済セッション流用、 Cookie管理ゼロ) ← **最短ルート**
2. GPT/Geminiタブ検出
3. Shujiさん議題提出検知
4. GPT→Gemini送信
5. Gemini応答取得
6. Verify Token / NextActor / EndTime-JST検証
7. 議事録append
8. Gemini→GPT送信
9. GPT応答取得

**Claudeの位置**: 会議運用から **除外**。 実装補助・GPT指示待ちのみ。

**議題提出**: Shujiさんが 手動 (CLIまたはWebUI 1回打鍵)

## 10.1 Phase 1 Required Safety Features (P0-P3、 Gemini第20再マッピング+GPT第39採用)

**Priority 再マッピング** (Gemini第20指示):

- **P0 最優先**: 30分stall通知 (要素取得見失い沈黙時の人間気づき経路、 **最大脆弱性対策**)
- **P1**: Dry-runモード (`DRY_RUN=True`、 実Send前ログ出力のみ、 暴走防止)
- **P2**: state.jsonバックアップ (lock_stale/破損保険)
- **P3**: 議事録自動timestamp commit (運用安定後の履歴管理)

**実装順** (GPT第39):

最優先実装 (骨格):
- Chrome CDP接続 (`http://127.0.0.1:9222`)
- GPT/Geminiタブ検出
- dry-runモード
- state.json backup
- lock取得/解除
- SIGINT安全終了

検証ロジック:
- Send成功検証 (editor=0 + userCount+1 + stopBtn=true or response開始)
- Response完了検証 (本文 + Verify Token + NextActor + EndTime-JST)
- Verify Token / NextActor / EndTime-JST 抽出

## 10.2 Critical Safety Mechanism (Gemini第20追加+GPT第39採用)

**DOM要素30秒未検出時の即時セーフティ・シャットダウン**:

```python
# 30秒以上 div[contenteditable="true"] 等 が見つからない場合
state["STATUS"] = "ERROR_SUSPENDED"
save_state(state)
# orchestrator安全停止 (プロセス自壊)
sys.exit(1)
```

**SIGINT / KeyboardInterrupt時の安全終了**:

```python
import signal

def handle_sigint(signum, frame):
    state = load_state()
    state["STATUS"] = "INTERRUPTED"
    state["lock"] = False
    state["interrupted_epoch"] = int(time.time())
    save_state(state)
    sys.exit(0)

signal.signal(signal.SIGINT, handle_sigint)
```

## 11. Phase 1.5

Phase 1が安定してから:
- Claudeを発言者として戻すか検討
- Watchdog追加
- dashboard強化
- stall通知 (Phase 1から繰上もあり)

## 13. CDP Environment Setup (GPT第42 R50-CDP-ENV-SETUP-GUIDE-5162)

CDP接続には、 Chromeを `--remote-debugging-port=9222` 付きで起動する必要がある。 **既に通常起動しているChromeには後付けで接続できない**。

### 推奨

専用プロファイルでChromeを起動し、 ChatGPT/Geminiへ一度ログインする。

### Mac起動例

```bash
open -na "Google Chrome" --args \
  --remote-debugging-port=9222 \
  --user-data-dir=/tmp/chrome-cdp-profile
```

### 接続確認

ブラウザまたは curl で:

```
http://127.0.0.1:9222/json/version
```

### 注意

- 既存Chromeを無理に操作しない (タブ閉じ・データ破損リスク)
- 必ず専用プロファイル (`--user-data-dir`) を使う
- 最初だけ ChatGPT / Gemini へ手動ログインが必要
- ログイン後に `python3 scripts/orchestrator_prototype.py --cdp-smoke-test` 再実行

### 環境変数

`CDP_ENDPOINT` で接続先URLを上書き可能 (未指定は `http://127.0.0.1:9222`)。

## 12. Phase 2

OpenAI / Gemini / Claude API化。 Web UI依存を減らす。

長期的には orchestrator.py が API直接呼び出し → コスト+安定性 トレードオフ後 採択。

---

由来: Shuji#27 → GPT第33 (5案A-E) → Gemini第19 (案B+Playwright GREEN承認、 3ステップロードマップ) → GPT第35 (Local Playwright Orchestrator方式採択+本仕様確定) → Claude第10 (発言監査3スロット+追加安全策a-d提案) → **GPT第37 (Phase 1 Claude除外+Chrome CDP+Dry-run必須+a-d採用)**

`[GPT-Verify: R50-PHASE1-CLAUDE-EXCLUDED-6824]`
