# Claude自動化 C案 スクリプト4本 仕様書

> GPT R50-2nd-2ndTurn-1stSpeaker-GPT-SHIELD-2874 で 採用確定: **「採用、 仕様→監査→実装の順」**。
> 本仕様書は 3者監査 (GPT+Gemini) 受領後 実装着手 (Shuji#11 ルール: Claude単独実装は 3者合意後)。

## 目的

3者会議 ぐるぐる ルーチン (Claude 7項目チェックリスト) を 各ターン自動実行する補助スクリプト。 Claudeが Shujiさん介入なしで 連続実行できる範囲を 最大化する。

## 共通仕様

- **言語**: Python 3.11+
- **依存**: 標準ライブラリのみ (PyGithub 等は 任意、 GitHub操作は git CLI経由)
- **配置**: `scripts/` ディレクトリ
- **実行**: `python scripts/<name>.py [args]`
- **エラー処理**: 失敗時 stderr出力+exit code非0、 Claudeが検知可能
- **冪等性**: 同じ入力で 何度実行しても 同じ結果 (重複追記防止)

---

## 1. `scripts/append_verbatim.py`

### 目的

GPT/Gemini/Shuji発言の verbatim を `logs/rounds/round_NN.md` に セクションとして追加。

### 入力

```bash
python scripts/append_verbatim.py \
  --round 50 \
  --speaker gpt|gemini|claude|shuji \
  --turn 2 \
  --order 1 \
  --verify-token "R50-2nd-2ndTurn-1stSpeaker-GPT-SHIELD-2874" \
  --content-file /tmp/verbatim.txt \
  [--challenge-tail "途中で止めないで"]
```

### 動作

1. `logs/rounds/round_50.md` の 末尾を 確認
2. 次のセクション番号 (現在末尾+1) を 自動採番
3. 以下のテンプレートで 追記:
   ```markdown

   ---

   ## NN. <Speaker> verbatim (R<Round>第<Subround>周第<Turn>ターン<Order>番手) — <Date>

   ### Verify Token: `<verify_token>`

   ### Challenge末尾3単語: 「<challenge_tail>」 (Shujiの場合のみ)

   ### 応答全文 verbatim:

   <content>
   ```
4. `logs/queue.json` の `unlogged_ai_responses` から 該当エントリを 削除

### 出力

- stdout: `Appended section NN to round_50.md (verbatim NN chars)`
- exit 0 成功 / 非0 失敗

### エッジケース

- 既に 同じ Verify Token のセクションがあれば skip (冪等性)
- ファイル末尾の 改行整合性 保持

---

## 2. `scripts/update_state.py`

### 目的

`logs/state.json` を 議事録+queue.jsonから 一括更新。 next_actor/phase/3者status を 自動計算。

### 入力

```bash
python scripts/update_state.py \
  [--round 50] \
  [--subround 2] \
  [--turn 2] \
  [--last-speaker gpt] \
  [--last-verify-token "R50-2nd-2ndTurn-1stSpeaker-GPT-SHIELD-2874"]
```

### 動作

1. `logs/state.json` を 読み込み
2. `logs/queue.json` の next_actor を 参照
3. `logs/rounds/round_50.md` の 最新セクション verify_tokenを 抽出
4. 以下を更新:
   - `current_round` / `current_subround` / `current_turn` / `current_speaker_position`
   - `next_actor` (固定順序 GPT→Gemini→Claude 自動計算)
   - 3者 `status` / `verify_tokens` / `verbatim_recorded_count`
   - `latest_commit` (`git rev-parse HEAD` で取得)
5. `logs/state.json` に 書き戻し

### 出力

- stdout: 更新された フィールド diff
- exit 0 成功 / 非0 失敗

---

## 3. `scripts/next_speaker_prompt.py`

### 目的

次の発言者 (GPT/Gemini) に 送る verbatim transmission プロンプト を 生成。 前1人+前2人 監査のための 文脈を 自動収集。

### 入力

```bash
python scripts/next_speaker_prompt.py \
  --next-speaker gemini \
  --include-previous-speakers 2
```

### 動作

1. `logs/state.json` から 現在のターン+順序を 取得
2. `logs/rounds/round_50.md` から 前2人の verbatim (該当セクション) を 抽出
3. 以下のテンプレートで プロンプト生成:
   ```
   [Claude事務局 → <Next AI> verbatim transmission]

   ぐるぐる順序: GPT → Gemini → Claude → ... 固定。
   本ターンは 第<Round>周第<Subround>第<Turn>ターン <Order>番手 = <Next AI>。

   ## 前1人 (発言者+Verify Token+概要):

   <Previous 1 summary>

   ## 前2人 (発言者+Verify Token+概要):

   <Previous 2 summary>

   ## 期待する応答形式 (3スロット強制):

   ### スロット1 前1人監査
   ### スロット2 前2人監査
   ### スロット3 自己ターン

   [Claude-Transmission: R<Round>-Turn<N>-<Order>-Forward-to-<NextAI>]
   ```
4. stdout に プロンプト出力 (Claude が browser_batch で 反対側タブに paste)

### 出力

- stdout: 生成プロンプト (1500-3000字 目安)
- stderr: ログ
- exit 0 成功

---

## 4. `scripts/verify_tokens.py`

### 目的

全 Verify Token を 議事録から 抽出+集約+重複/欠落 検知。 自浄機能。

### 入力

```bash
python scripts/verify_tokens.py [--round 50]
```

### 動作

1. `logs/rounds/round_50.md` を 読み込み
2. 正規表現で 全 Verify Token を 抽出:
   - `\[GPT-Verify: ([^\]]+)\]`
   - `\[Gemini-Verify: ([^\]]+)\]`
   - `\[Claude-Verify: ([^\]]+)\]`
   - `HMAC-SHA256\s*[\w-]*\s*Verification Token:\s*([\w-]+)`
3. 各 Token に 紐づく セクション番号+発言主+ターン+順序を 集計
4. 重複検知: 同じ Token が 複数セクションにあれば 警告
5. 欠落検知: ターン+順序の系列で Token なしのセクションがあれば 警告
6. stdout に CSV出力:
   ```csv
   section,speaker,turn,order,verify_token,duplicate_flag,missing_flag
   16,GPT,1,4,R50-1st-RESEARCH-9147,false,false
   ...
   ```

### 出力

- stdout: CSV (Verify Token集約)
- stderr: 警告 (重複/欠落)
- exit 0 成功 / 警告のみで exit 0、 致命エラーで 非0

---

## 連携フロー (Claude各ターン自動実行)

```
[Shuji発言受信]
   ↓
[次AI応答取得 (browser MCP)]
   ↓
[append_verbatim.py で 議事録追記]
   ↓
[update_state.py で state.json + queue.json 更新]
   ↓
[next_speaker_prompt.py で 反対側プロンプト生成]
   ↓
[browser_batch で paste+send]
   ↓
[verify_tokens.py で セルフチェック]
   ↓
[git commit/push]
   ↓
[Shuji報告]
```

これにより、 Claudeの 7項目チェックリスト routine が 半自動化される。 完全自動化は /loop dynamic mode 時のみ (D案ScheduleWakeup)。

---

## 3者監査 依頼

- **GPT (司会)**: 仕様の 順序+整合性 確認、 queue.jsonとの 連携 OK か
- **Gemini (技術)**: Python実装の 脆弱性 (regex injection / file race condition / token collision)、 冪等性 検証
- **Shujiさん**: 採用可否 最終判断、 もし採用なら 実装着手 Claude単独OK

---

> 本仕様書は 整理版 (Reading-friendly)、 Round 50 第2周中 Gemini技術監査 受領後 implementation着手。
