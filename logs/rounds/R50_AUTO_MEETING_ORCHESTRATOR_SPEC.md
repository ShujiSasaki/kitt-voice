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

## 21. Multi-Round Consensus Test (GPT第52 R50-MULTIROUND-CONSENSUS-TEST-9346)

Real Topic Auto Relay PASSED後、 **GPT↔Gemini複数周回+合意判定** を検証。

### 目的
- Shuji介在なし複数周回成立
- Gemini異論あり/なし → GPT修正/収束判定
- 合意判定 state.json記録

### 制約
- GPT↔Gemini 2者のみ、 Claude運用ループ外
- 最大2周
- R50最終インフラ報告書題材
- Shuji承認代弁禁止、 R50正式終結なし
- `real_send_enabled` テスト中のみ true → 終了後 false

### Consensus criteria
- Gemini「重大異論なし」 or 「修正後確認へ出せる」
- GPT修正反映最終案生成
- unresolved_critical_issues 空
- state.json に `consensus_candidate=true`

### Not consensus
- Gemini重大脆弱性指摘 / タグ欠落 / 送信取得append失敗 / lock異常 / 2周以内未収束

### 初期案 (Gemini監査対象)
- DMM Bitcoin → Tier 3外し SBI VC移管枠へ
- 海外CEX Tier 3理由に日本居住者IP制限/規約変更/規制リスク明記
- 経路B 重要経路明記
- Hyperliquid 主候補だが既定路線ではない
- Wise既定路線 却下

### Output
- round_50_part2.md 各周 Gemini/GPT応答 append
- `logs/dry_run/{ts}.multi_round_consensus_test.json`
- state.json: `consensus_candidate` / `unresolved_critical_issues` / `final_report_ready`

## 20. Controlled Real Topic Auto Relay Test (GPT第51 R50-REAL-TOPIC-RELAY-TEST-6634)

Two-Agent Auto Relay Test PASSED後、 本来議題 (R50最終インフラ報告書) を題材に **制御付き自動1周テスト**。

### 目的
- Shujiさん介在なしで実議題に対しGPT→Gemini→GPT監査relay成立確認
- R50最終インフラ報告書題材
- このテスト結果だけでR50正式終結としない

### 制約
- 1往復のみ、 GPT→Gemini→GPT
- Claude運用ループ外
- `real_send_enabled` テスト中のみ `true` → 終了後 `false`
- このテストでShujiさん承認を代弁しない
- R50正式終結はShujiさん確認後

## 19. Controlled Two-Agent Auto Relay Test (GPT第50 R50-TWO-AGENT-RELAY-TEST-2907)

Phase 1 Orchestrator の Send/Fetch個別動作確認済み後、 GPT↔Gemini 2者循環を **1回だけ** 自動relay。

### 目的
- Shujiさん呼び鈴なしで 2者間自動会議1周可能か検証
- Gemini送信 → Gemini応答取得 → 議事録append → ChatGPT送信 → ChatGPT応答取得 (Verify Tokenなくても TEST_PARTIAL)

### 制約
- 本来議題進めない / テスト議題のみ / 1往復で停止
- `real_send_enabled` テスト中のみ `true` → 終了後 `false` 戻し
- 失敗時は `ERROR_SUSPENDED` ではなく `TEST_FAILED` として停止

## 18. ChatGPT Controlled Send Test (GPT第49 R50-ORCHESTRATOR-CHATGPT-SEND-TEST-6129)

Gemini単方向E2E (Send→Response→Fetch) 完了後、 ChatGPTへの制御付き実送信テスト。

### 目的
- Playwright OrchestratorがChatGPT editor入力できるか
- Send button押せるか
- 3条件Send成功検証機能 (editor_len/userCount/stopBtn or assistant)

### 制約
- 送信先はChatGPTのみ、 内容は疎通確認のみ
- 本来議題は進めない
- Geminiへの自動送信はこのテストでは行わない
- `real_send_enabled` テスト中のみ `true` → 終了後 `false` 戻し

## 17. Gemini Response Fetch Test (GPT第48 R50-ORCHESTRATOR-FETCH-GEMINI-LATEST-2678)

Controlled Gemini Send Test が成功したため、 次に Gemini 最新応答取得テスト。

### 目的
- Gemini 最新 `model-response` を取得できるか
- 応答本文を `logs/dry_run/` に保存できるか
- response complete 判定が機能するか
- Verify Token / NextActor / EndTime-JST の有無を検査できるか (missing許容)

### 制約
- 実入力禁止 / 実Send禁止 / 読み取りのみ / ChatGPT自動送信禁止

## 16. Controlled Gemini Send Test (GPT第47 R50-ORCHESTRATOR-GEMINI-SEND-TEST-7062)

Relay Dry-runが成功したため、 次に **1回だけ** 制御付きでGemini実送信を行う。

### 目的

- Playwright OrchestratorがGemini editorへ入力できるか
- Send buttonを押せるか
- Send成功検証 (editor=0 + userCount+1 + stopBtn=true or response start) が機能するか

### 制約

- 送信先はGeminiのみ
- 送信内容は疎通確認のみ
- 本来議題は進めない
- ChatGPTへの自動送信はまだ禁止
- `real_send_enabled` はテスト中のみ明示的に `true`
- **テスト終了後 `false` に戻す**

### 実装

`scripts/orchestrator_prototype.py --send-test-gemini`:
- 送信前 metrics記録
- 固定テスト文inject (TrustedHTML対策: `document.createElement('p').textContent`)
- send button click
- 3条件検証 (editor_len/userCount/stopBtn or assistant)
- 結果 `logs/dry_run/{ts}.gemini_send_test.json`

## 15. Selector Candidates Adopted (GPT第46 R50-ORCHESTRATOR-RELAY-DRY-RUN-5381)

### ChatGPT
- editor: `#prompt-textarea` / `div.ProseMirror[contenteditable=true]`
- send: `button[data-testid="send-button"]`
- stop: `button[data-testid="stop-button"]`
- assistant: `[data-message-author-role="assistant"]`
- user: `[data-message-author-role="user"]`
- turn: `[data-testid^="conversation-turn-"]`

### Gemini
- editor: `rich-textarea .ql-editor`
- send: `button[aria-label="プロンプトを送信"]`
- stop: `button[aria-label="回答を停止"]`
- user: `user-query`
- assistant: `model-response`

### Send成功条件

```
editor_len_after == 0
AND user_count_after - user_count_before == 1
AND (stop_btn_exists OR assistant_count_after > assistant_count_before)
```

### 注意: Phase 1ではまだ実入力・実Send禁止。 次は Relay Dry-run のみ。

## 14. Selector Discovery Phase (GPT第44 R50-ORCHESTRATOR-SELECTOR-DISCOVERY-3382)

CDP接続成功後、 次は ChatGPT/Gemini各タブのDOMセレクタ探索。

### 目的: 候補抽出

- editor selector (入力欄)
- send button selector (送信ボタン)
- assistant message selector (応答メッセージ)
- user message count (ユーザー投稿数)
- response count (応答数)
- stop button selector (生成停止ボタン)

### 制約

- **実Sendは禁止**
- **実入力も禁止**
- DOM読み取りのみ
- 結果は `logs/dry_run/{timestamp}.selectors.json` に保存

### 実装

`scripts/orchestrator_prototype.py --selector-discovery`:
- CDP接続
- ChatGPT/Geminiタブ検出 (URLパターンフィルタ)
- 各タブの title/url 保存
- textarea / contenteditable / button要素列挙
- editor候補 / send button候補 / stop button候補 / assistant message候補 / user message候補抽出
- `real_send_enabled=false` 維持

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
