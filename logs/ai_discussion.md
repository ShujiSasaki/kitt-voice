## 原因判断

- `UserTweetsAndReplies` / `SearchTimeline` の **404はfeatures不足ではない可能性が高い**です。  
  GraphQLのfeatures不足なら通常は `400/403` 系になります。  
  `404` は主に以下です。

  1. `queryId` と `operationName` の組み合わせ不一致  
  2. そのoperationが現行Webクライアントで無効化/差し替え済み  
  3. main.jsから取ったqueryIdが、実際の画面遷移で使われていない  
  4. ABテスト/ログイン状態/地域で別operationを使っている

- `UserTweets` が動くのに843件で止まるのは、プロフィールタイムラインAPI側の取得上限、またはリプライ除外によるもの。  
  30万件全量取得には `UserTweets` 一本は不適切です。

- `v1.1 statuses/user_timeline.json` の `200 + content-length:0 + backoff-policy` は実質使えない状態です。  
  ここに時間を使わない方がいいです。

---

## 次にやるべき順番

### 1. Playwrightで実ブラウザ通信を捕捉する

最優先です。  
main.jsからqueryIdを推測するのをやめて、実際にX Webが投げているリクエストをそのまま取ります。

捕捉対象URL:

```txt
/i/api/graphql/*/UserTweets
/i/api/graphql/*/UserTweetsAndReplies
/i/api/graphql/*/SearchTimeline
```

実際に開くページ:

```txt
https://x.com/{screen_name}
https://x.com/{screen_name}/with_replies
https://x.com/search?q=from%3A{screen_name}&src=typed_query&f=live
```

保存するもの:

- URL内の `queryId`
- `operationName`
- `variables`
- `features`
- `fieldToggles`
- request headers
  - `authorization`
  - `x-csrf-token`
  - `cookie`
  - `x-twitter-active-user`
  - `x-twitter-auth-type`
  - `x-client-transaction-id` も一応保存

重要:  
ブラウザ上で `/with_replies` が正常に表示されるなら、その通信を完全コピーすれば `UserTweetsAndReplies` は再現できる可能性があります。  
ブラウザでもAPIが出ていない/404なら、そのoperationは諦めます。

---

### 2. `UserTweetsAndReplies` が再現できるか確認

Playwrightで捕捉したリクエストを Node fetch でそのまま再送します。

判定:

- 再送で200になる  
  → 今のスクリプトのqueryId/features/fieldToggles/headersが間違い。
- 再送でも404  
  → operation自体がその環境で使えない。`SearchTimeline` 方式へ移行。
- ブラウザでは200、Nodeでは404/403  
  → header不足。特に `x-client-transaction-id`、CSRF、cookie、User-Agent差分を見る。

---

### 3. 全量取得は `SearchTimeline` の日別分割を本命にする

30万件を取るなら、基本方針はこれです。

検索クエリ:

```txt
from:{screen_name} since:YYYY-MM-DD until:YYYY-MM-DD
```

画面は「最新」タブ相当:

```txt
f=live
```

GraphQL variablesの `product` は通常:

```json
"Latest"
```

日単位で足りない場合はさらに分割します。

優先順:

```txt
年単位 → 月単位 → 日単位 → 必要なら時間単位
```

ただし、X検索が `since_time:` / `until_time:` を現在も受け付けるかは要検証です。  
まずは日別で十分か確認してください。

---

### 4. cursor処理を正しく実装する

GraphQL Timelineは単純な配列ではありません。  
以下を必ず処理します。

見る場所:

```txt
data.search_by_raw_query.search_timeline.timeline.instructions
```

処理するinstruction:

```txt
TimelineAddEntries
TimelineReplaceEntry
TimelineTerminateTimeline
```

tweet抽出:

```txt
entry.content.itemContent.tweet_results.result
```

またはwrapperを剥がす:

```txt
TweetWithVisibilityResults.result
```

bottom cursor抽出:

```txt
entry.content.operation.cursorType == "Bottom"
```

または:

```txt
entry.entryId startsWith "cursor-bottom"
```

停止条件:

- bottom cursorが無い
- `TimelineTerminateTimeline` が来た
- 同じcursorが再出現
- 新規tweet_idが0件のページが連続
- rate limit / backoff

禁止:

- 「20ページで終了」など固定ページ数で止めること  
  → 取得漏れの原因になります。

---

### 5. SQLite保存を先に入れる

30万件なら、JSON一括保存ではなく最初からSQLiteにしてください。

最低限のschema:

```sql
CREATE TABLE IF NOT EXISTS accounts (
  user_id TEXT PRIMARY KEY,
  screen_name TEXT,
  name TEXT,
  created_at TEXT,
  raw_json TEXT
);

CREATE TABLE IF NOT EXISTS tweets (
  tweet_id TEXT PRIMARY KEY,
  user_id TEXT,
  screen_name TEXT,
  created_at TEXT,
  full_text TEXT,
  conversation_id TEXT,
  in_reply_to_status_id TEXT,
  is_retweet INTEGER,
  is_quote INTEGER,
  raw_json TEXT,
  fetched_at TEXT
);

CREATE TABLE IF NOT EXISTS media (
  media_key TEXT PRIMARY KEY,
  tweet_id TEXT,
  type TEXT,
  url TEXT,
  local_path TEXT,
  downloaded INTEGER DEFAULT 0,
  raw_json TEXT
);

CREATE TABLE IF NOT EXISTS crawl_jobs (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  screen_name TEXT,
  since_date TEXT,
  until_date TEXT,
  cursor TEXT,
  status TEXT,
  last_error TEXT,
  updated_at TEXT,
  UNIQUE(screen_name, since_date, until_date)
);

CREATE TABLE IF NOT EXISTS request_log (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  operation_name TEXT,
  query_id TEXT,
  screen_name TEXT,
  since_date TEXT,
  until_date TEXT,
  cursor TEXT,
  status_code INTEGER,
  rate_remaining TEXT,
  rate_reset TEXT,
  backoff_policy TEXT,
  created_at TEXT
);
```

`tweets.tweet_id` を主キーにして、重複は `INSERT OR IGNORE` / `UPSERT` で処理します。

---

### 6. 中断再開対応

`crawl_jobs` に状態を持たせます。

状態例:

```txt
pending
running
done
rate_limited
failed
```

1ページ取得するたびに保存:

- 現在のcursor
- 最後に成功した日時
- 取得件数
- エラー内容

再開時:

```sql
SELECT * FROM crawl_jobs
WHERE status IN ('pending', 'running', 'rate_limited', 'failed')
ORDER BY since_date;
```

`running` のまま落ちたjobは起動時に `pending` に戻します。

---

### 7. rate limit / backoff対応

レスポンスヘッダーを必ず見る。

見るヘッダー:

```txt
x-rate-limit-limit
x-rate-limit-remaining
x-rate-limit-reset
backoff-policy
```

`backoff-policy` がある場合は従うべきです。

今回の例:

```txt
backoff=1234;serial-duration=30000;serial-delay=500;no-retry=true
```

意味としては、少なくとも直後の連打は避けるべきです。

実装方針:

- 同時並列は最初は1にする
- 1リクエストごとに1〜3秒sleep
- `429` または `backoff-policy` 検出時は `x-rate-limit-reset` まで待つ
- `no-retry=true` なら即時リトライしない
- アカウント7件をラウンドロビンせず、まず1アカウントで安定確認

---

### 8. 画像取得

Tweet JSON内のmediaから取ります。

主な場所:

```txt
legacy.entities.media
legacy.extended_entities.media
```

画像URL:

```txt
media_url_https
```

保存時は `?name=orig` を付ける。

例:

```txt
https://pbs.twimg.com/media/xxxxx.jpg?name=orig
```

保存先例:

```txt
media/{screen_name}/{tweet_id}_{media_key}.jpg
```

DBには画像ダウンロード成否を保存。  
画像取得はtweet取得と分離した別ジョブにした方が安全です。

---

## 取得漏れ検証

最低限これをやってください。

### A. `UserTweets` 843件との突合

現在取れている `UserTweets` の843件が、SearchTimeline方式のDBに全て入っているか確認。

```sql
SELECT tweet_id FROM usertweets_recent
EXCEPT
SELECT tweet_id FROM tweets;
```

0件であるべきです。

---

### B. 日別jobの完了確認

```sql
SELECT screen_name, since_date, until_date, status
FROM crawl_jobs
WHERE status != 'done';
```

未完了がないこと。

---

### C. 日別件数の異常検知

```sql
SELECT screen_name, substr(created_at, 1, 10) AS d, COUNT(*)
FROM tweets
GROUP BY screen_name, d
ORDER BY screen_name, d;
```

突然0件の日、異常に少ない日を再クロール対象にします。

---

### D. 境界重複チェック

`since/until` の境界漏れ対策として、隣接日を1日オーバーラップさせて取得し、tweet_idで重複排除するのが安全です。

例:

```txt
2020-01-01〜2020-01-03
2020-01-02〜2020-01-04
```

重複はDB主キーで排除。

---

## 実装方針まとめ

次の順で進めるのがよいです。

1. Playwrightで実ブラウザのGraphQL通信を捕捉  
2. 捕捉した `UserTweetsAndReplies` をNode fetchで完全再現  
3. 再現できなければ `SearchTimeline` に切り替え  
4. SQLite schemaを先に作る  
5. `SearchTimeline` の日別jobを作成  
6. cursorごとにtweets/media/job状態をSQLite保存  
7. rate limit/backoffを見て低速・再開可能にする  
8. `UserTweets` 843件との突合で取得漏れ検証  
9. 画像ダウンロードは別キューで後処理

結論として、今は `UserTweetsAndReplies` のfeaturesを手探りで増やす段階ではありません。  
まずPlaywrightで実リクエストを捕捉し、再現できなければ `SearchTimeline` 日別分割 + SQLite中断再開方式に移行するのが最短です。
以下、技術レビューとしての結論です。

## まず原因分析：Claude Codeが詰まった本質

詰まりポイントは主にこれです。

1. **GraphQL URLだけ再現しても足りなかった**
   - `authorization`
   - `x-csrf-token`
   - cookie
   - `x-twitter-active-user`
   - `x-twitter-auth-type`
   - `features` の完全一致  
   が必要だった。

2. **featuresをJSON.stringifyで再構成したことでURLエンコードが実ブラウザとズレた**
   - XのGraphQLは `variables/features/fieldToggles` の差分にかなり敏感。
   - 実ブラウザで観測したURLをベースにする方針は正しい。

3. **ページネーション・rate limit・認証更新の運用設計がまだ弱い**
   - ここから先は「取れるか」ではなく「数日安定して漏れなく取れるか」が問題。

---

# 質問への回答

## 1. auth_tokenの一般的な有効期限は？途中で切れた場合の対処は？

`auth_token` の正確な有効期限は公開されていません。一般には数週間〜数か月保持されることもありますが、以下でいつでも無効化され得ます。

- ログアウト
- パスワード変更
- セキュリティ判定
- IP/UA/挙動の変化
- X側のセッション再発行
- 長時間アクセスや異常なGraphQLアクセス

今回の6時間程度なら通常は持つ可能性が高いですが、保証はできません。

### 実装すべき対処

HTTPステータスごとに明確に分岐してください。

```text
200: 正常。保存して次cursorへ。
401: 認証切れ。即停止。cookie再取得待ち。
403: 認可/制限/ヘッダー不一致。即停止または長時間backoff。
429: rate limit。長時間sleepして同一cursorから再開。
5xx: 一時障害。指数backoff。
```

### 中断再開の最低条件

SQLiteに以下を保存しておくべきです。

```sql
accounts(
  screen_name,
  user_id,
  last_cursor,
  last_success_at,
  finished,
  error_code,
  error_message
)

tweets(
  tweet_id PRIMARY KEY,
  user_id,
  screen_name,
  created_at,
  full_text,
  raw_json,
  collected_at
)

cursors(
  screen_name,
  cursor,
  page_no,
  fetched_at,
  status_code,
  new_tweet_count
)
```

途中で `401/403` になったら、プロセスは落とさずに以下で止めるのが良いです。

```text
AUTH_REQUIRED状態にして停止
↓
Playwrightで再ログイン、cookie再取得
↓
同じaccount + last_cursorから再開
```

---

## 2. 7アカウント30万件を最速で取得する戦略は？

結論から言うと、**同一cookieでの並列化は推奨しません**。

理由は以下です。

- GraphQLのrate limitはIP単位だけでなく、アカウント、cookie、Bearer、endpoint、挙動単位で見られる可能性がある。
- 並列化すると一時的には速く見えても、429/403/アカウントロックで総時間が悪化する可能性が高い。
- IP分散やcookie複数で制限を迂回する設計はリスクが高く、安定取得の観点でも推奨しない。

### 現実的に最速かつ安全寄りの戦略

#### A. まず1アカウント完走させる

`smile_danjer` を最後まで完走させて、以下を測定してください。

- 1ページあたり平均件数
- 429発生有無
- cursor stall有無
- 最終ページ到達条件
- DB重複率
- 実tweet/reply/RT比率

この実測値がない状態で30万件の計画を立てると危険です。

#### B. delayを固定18秒ではなく、動的制御にする

例：

```text
通常: 18〜25秒にランダムjitter
429: 15〜30分sleep
403: 1〜6時間停止または手動確認
5xx: 1分, 2分, 5分, 10分...
```

固定18秒は機械的すぎるので、少し揺らした方が安定します。

```python
sleep = random.uniform(18, 27)
```

#### C. アカウント単位で順次処理

おすすめ順：

```text
1. smile_danjer 完走
2. 件数が少ないアカウントで再現性確認
3. 大きいアカウントを順次処理
```

#### D. 並列化するなら最大2並列まで、ただし別セッションでなくても危険

どうしても試すなら、

- 1並列で基準rateを測る
- 2並列にして429/403率を見る
- すぐ戻せるようにする

ただし、同一cookieで複数アカウント同時取得は避けた方が良いです。

### 推奨結論

```text
最速化よりも、中断再開 + 漏れ検証 + rate limit耐性を優先。
まず1アカウント完走。
その後、1 worker運用で数日回す。
必要なら慎重に2 worker検証。
```

---

## 3. x-client-transaction-idは使い回しで問題ないか？毎リクエスト変えるべきか？

結論：**使い回しで今200が返っていても、毎リクエスト同一IDに依存するのは危険です。**

`x-client-transaction-id` はX Webクライアント側で生成されるリクエスト識別子に近い扱いです。サーバー側が常に厳密検証しているとは限りませんが、以下のリスクがあります。

- 同一ID連発が異常挙動として見られる可能性
- あるタイミングで検証が厳しくなる可能性
- endpointやqueryId変更時に失敗する可能性

### 優先順位

#### ベスト

Playwrightで実ブラウザ通信を継続的に捕捉し、最新のヘッダー・URL・featuresを使う。

#### 次善

一定間隔でPlaywrightを開き、GraphQLリクエストを1回発生させて、そのときの以下を更新。

- `x-client-transaction-id`
- GraphQL queryId
- features
- fieldToggles
- headers

#### 最低限

現在のIDを使い続けるが、`403/400` が出たら即座にPlaywrightで再捕捉する。

### 実装方針

設定に以下を持たせると良いです。

```json
{
  "graphql_template_source": "captured_browser",
  "captured_at": "2026-05-11T00:00:00Z",
  "headers": {
    "x-client-transaction-id": "...",
    "x-twitter-active-user": "yes",
    "x-twitter-auth-type": "OAuth2Session"
  },
  "features_raw": "...",
  "field_toggles_raw": "..."
}
```

そして、以下の場合は再捕捉。

```text
400
401
403
404
GraphQL errors
空ページ連続
cursorが進まない
```

---

## 4. プロフィール投稿数とDB件数が一致しない場合の正しい検証方法は？

プロフィールの投稿数とDB件数を完全一致させる検証は危険です。

理由：

- プロフィールの投稿数はRTを含む場合がある。
- 削除済み投稿がカウントに残る/残らない差がある。
- 非公開化、凍結、制限、地域制限の影響がある。
- リプライ、RT、引用、通常投稿の扱いが画面/APIで異なる可能性がある。
- GraphQL timelineにはpin、module、広告、conversation itemなどtweet以外のentryが混ざる。
- 古い投稿がSearchには出るがUserTweetsAndRepliesには出ない、または逆もあり得る。

### 正しい検証は「件数一致」ではなく「取得範囲と差分検査」

DB側でtweet種別を分類してください。

```text
normal_tweet
reply
retweet
quote
retweet_with_comment
deleted_or_unavailable
unknown
```

判定例：

```text
retweeted_status_result がある → retweet
in_reply_to_status_id_str がある → reply
quoted_status_result がある → quote
```

### 検証SQL例

#### 総件数

```sql
SELECT COUNT(*) FROM tweets WHERE screen_name = ?;
```

#### 種別別

```sql
SELECT tweet_type, COUNT(*)
FROM tweets
WHERE screen_name = ?
GROUP BY tweet_type;
```

#### 日別件数

```sql
SELECT DATE(created_at) AS d, COUNT(*)
FROM tweets
WHERE screen_name = ?
GROUP BY d
ORDER BY d;
```

#### 重複確認

```sql
SELECT tweet_id, COUNT(*)
FROM tweets
GROUP BY tweet_id
HAVING COUNT(*) > 1;
```

#### 時系列の穴確認

```sql
SELECT MIN(created_at), MAX(created_at), COUNT(*)
FROM tweets
WHERE screen_name = ?;
```

### 完了判定

UserTweetsAndRepliesの完了判定はプロフィール件数ではなく、cursorで判断すべきです。

```text
Bottom cursorが存在しない
または
次cursorで取得しても新規tweet_idが0件
かつ
cursorが前回と同一
かつ
複数回確認済み
```

ただし、1回の空ページで終了判定するのは危険です。

おすすめ：

```text
空ページまたは新規0件が3回連続
かつ cursor変化なし
なら終了候補
```

---

## 5. SearchTimeline日別分割との併用で取得漏れを防ぐべきか？

結論：**併用すべき。ただしSearchTimelineを主系統にしない方が良いです。**

主系統：

```text
UserTweetsAndReplies GraphQL + cursor
```

副系統：

```text
SearchTimeline 日別または月別分割
```

SearchTimelineは検証・補完用に使うのが良いです。

### 理由

SearchTimelineには以下の特性があります。

- 検索インデックス依存
- 古い投稿が不完全な場合がある
- rate limitが別途厳しい可能性
- `from:user since: until:` の結果が完全とは限らない
- リプライやRTを含めるかどうかでクエリ差が出る

### 推奨する使い方

#### 1. UserTweetsAndRepliesで全件取得

まずcursorで最後まで走らせる。

#### 2. DBで日別件数を作る

```sql
SELECT DATE(created_at), COUNT(*)
FROM tweets
WHERE screen_name = ?
GROUP BY DATE(created_at);
```

#### 3. SearchTimelineで日別または月別に照合

クエリ例：

```text
from:smile_danjer since:2020-01-01 until:2020-01-02
```

リプライ確認：

```text
from:smile_danjer filter:replies since:2020-01-01 until:2020-01-02
```

RT確認：

```text
from:smile_danjer filter:nativeretweets since:2020-01-01 until:2020-01-02
```

引用は検索で完全に取れるとは限らないので補助扱い。

#### 4. Search側に存在してDBにないtweet_idを差分取得

差分が出たら、

- TweetDetail
- SearchTimeline再取得
- UserTweetsAndReplies該当期間の近辺再取得

で補完。

### 重要

SearchTimelineの件数とプロフィール件数を一致させるのではなく、**tweet_id集合の差分**で検証してください。

```text
UserTweetsAndReplies_IDs
vs
SearchTimeline_IDs
```

---

# 次に実装すべき手順

短く言うと、次はこれです。

## Step 1: smile_danjerを完走させる

今のジョブは止めずに最後まで走らせる。

記録するもの：

```text
総ページ数
総tweet_id数
重複数
429/403/401発生回数
最終cursor
最終ページの状態
1ページ平均件数
RT/Reply/Normal比率
```

---

## Step 2: cursor終了判定を厳密化

終了条件を以下にする。

```text
Bottom cursorなし
または
同一cursor + 新規0件が3回連続
```

1回の空ページで終わらせない。

---

## Step 3: HTTPエラー別リカバリを実装

```text
401: AUTH_REQUIREDで停止。cookie再取得後再開。
403: ヘッダー再捕捉。長時間停止。
429: 15〜30分sleepして同一cursor再開。
5xx: 指数backoff。
400/404: GraphQL URL/features/queryId再捕捉。
```

---

## Step 4: x-client-transaction-id再捕捉機構を入れる

最低限、以下のときPlaywrightで再捕捉。

```text
403
400
404
GraphQL errors
空ページ連続
cursor stall
```

可能ならアカウント開始ごとに再捕捉する。

---

## Step 5: SQLiteにraw_jsonと分類カラムを保存

追加推奨カラム：

```sql
tweet_type TEXT,
is_retweet INTEGER,
is_reply INTEGER,
is_quote INTEGER,
conversation_id TEXT,
in_reply_to_status_id TEXT,
retweeted_status_id TEXT,
quoted_status_id TEXT
```

---

## Step 6: 検証用SQLを作る

最低限：

```text
日別件数
種別別件数
重複tweet_id
min/max created_at
cursor履歴
ページごとの新規件数
```

---

## Step 7: SearchTimelineは完走後の差分検証に使う

いきなり併用して主処理を複雑にしない。

順番：

```text
UserTweetsAndReplies完走
↓
日別件数作成
↓
SearchTimelineで月別/日別照合
↓
tweet_id差分だけ補完
```

---

# 最終方針

おすすめ運用はこれです。

```text
1 worker
18〜27秒jitter
429は15〜30分backoff
401/403は停止してcookie/headers再捕捉
1アカウント完走ごとにPlaywrightでheaders再捕捉
SearchTimelineは完走後の漏れ検証用
```

並列化やIP分散より、まずは **確実に完走・再開・検証できる取得器** にするべきです。今回の規模なら、数日かかっても安定性優先の方が最終的に早いです。
結論：**UserTweetsAndReplies 1本勝負は危険。SearchTimeline日別を最初から検証・補完系に入れるべき**です。  
ただし、**SearchTimelineだけを主系統にするとRT/Repost漏れリスクが残る**ので、現実的には以下のハイブリッドが安全です。

---

## 1. UserTweetsAndReplies vs SearchTimeline

### UserTweetsAndReplies 1本勝負は危険か？

危険です。懸念は妥当です。

リスクは主にこれです。

- cursorが途中で `TimelineTerminateTimeline` になる
- 古い投稿まで必ず辿れる保証がない
- GraphQL operation ID / features がX側更新で変わる
- ページング中の重複・欠落検知がしづらい
- プロフィール表示件数との差分原因が追いづらい

なので、**UserTweetsAndRepliesを唯一の真実にするのは避けるべき**です。

### ではSearchTimeline日別を主系統にすべきか？

部分的には賛成です。

`from:user since:YYYY-MM-DD until:YYYY-MM-DD` を日別に回す方式は、

- 日単位で完了管理できる
- 中断再開しやすい
- 漏れ検証しやすい
- cursor破損時に日単位でリトライできる
- 件数が多い日は時間単位に分割できる

という点でかなり強いです。

ただし弱点があります。

- `from:user` がRT/Repostを安定して含むとは限らない
- 検索インデックス側の欠落・非表示・ランキング影響がある
- deleted/protected/suspendedは返らない
- 古い投稿や大量日で途中打ち切りの可能性はSearchにもある

したがっておすすめはこれです。

```text
主系統A: SearchTimeline 日別取得
  - original tweet / reply の取得と検証に使う

主系統B: UserTweetsAndReplies
  - RT/Repost含むプロフィール時系列の取得に使う
  - Searchで拾えない活動を補完する

検証:
  - 日別Search結果とUserTweetsAndReplies結果をtweet_idで突合
  - 片方にしかないIDをmissing候補として保存
```

---

## 2. rate limit / 間隔について

### 18-27秒は遅すぎるか？

はい、初期値としては保守的すぎます。

実測で、

```text
30ページ / 9分 = 約18秒/request
429なし
```

なら、次は **6-10秒間隔** くらいまで落としてよいです。

おすすめ設定：

```text
通常時:
  6-10秒 jitter

429発生時:
  x-rate-limit-reset があればそこまで待機
  なければ 15分 sleep
  その後 12-20秒に戻す

連続429:
  30分 → 60分 backoff

timeout / 5xx:
  同じcursorで3回までretry
  cursorは進めない
```

### X GraphQLの正確なrate limitは？

**公式にはありません。**

公式rate limitがあるのはX API v1.1/v2の公開APIで、Web内部GraphQL endpointとは別物です。

内部GraphQLについては、

- endpoint別の公式req/15minはない
- `x-rate-limit-limit`
- `x-rate-limit-remaining`
- `x-rate-limit-reset`

が返る場合はそれを使う  
返らない場合は実測制御するしかないです。

実装では endpoint単位でrate bucketを分けるべきです。

```text
SearchTimeline bucket
UserTweetsAndReplies bucket
UserByScreenName bucket
TweetDetail bucket
```

---

## 3. Playwright再捕捉について

### reactive方式で十分か？

基本的には十分です。

今のcaptured headers/featuresで200が返っているなら、定期的にPlaywrightを起動するproactive方式は過剰です。

おすすめはこれです。

```text
通常:
  保存済みheaders/features/operationIdでGraphQL実行

再捕捉条件:
  403
  404
  operation not found
  persistedQueryNotFound
  features mismatch
  guest token/auth token error
  連続して同じendpointが失敗

その時だけ:
  Playwright起動
  Xを開く
  Networkから最新GraphQL requestをcapture
  headers/features/variablesテンプレートを更新
```

つまり **reactive recapture** でよいです。

ただし、capture情報はSQLiteにバージョン付きで保存してください。

```sql
graphql_captures(
  id,
  endpoint_name,
  operation_name,
  operation_id,
  features_json,
  headers_json,
  captured_at,
  valid_until,
  status
)
```

---

## 4. 追加質問への回答

### Q1. UserTweetsAndRepliesはRTも返すか？

多くの場合、プロフィール上に表示されるRepost/RTは `UserTweets` / `UserTweetsAndReplies` 系に出ます。

ただし保証はできません。

RT/RepostはJSON上ではだいたい以下の形で判定します。

```text
tweet.legacy.retweeted_status_result
socialContext: "... reposted"
```

または tweet object 内に元tweetがネストされます。

なので実装では、

```text
is_retweet = retweeted_status_result があるか
retweeted_tweet_id = 元tweetのrest_id
activity_tweet_id = Repost自体のrest_id
```

を両方保存すべきです。

SearchTimelineの `from:user` はRTを安定して拾う用途には不向きです。  
RT込みの完全取得を狙うなら、UserTweetsAndReplies系は残した方がいいです。

---

### Q2. SearchTimelineの `from:user` は削除済みツイートを返すか？

基本的に返しません。

削除済み、非公開化、凍結、閲覧制限、法的制限、センシティブ制限などで現在アクセス不能なものは取得できません。

検索インデックスに一時的に残る可能性はありますが、再現性のある取得対象としては扱えません。

---

### Q3. ronpochi 11.5万件の完走見積もり

1ページあたり20件返る前提だと、

```text
115,000 / 20 = 5,750 requests
```

間隔別の概算：

```text
6秒間隔   : 約9.6時間
10秒間隔  : 約16時間
18秒間隔  : 約28.8時間
27秒間隔  : 約43.1時間
```

1ページ10件しか実効保存できない場合は倍です。

```text
6秒間隔   : 約19時間
10秒間隔  : 約32時間
18秒間隔  : 約57.5時間
27秒間隔  : 約86時間
```

なので、ronpochi級は現実的には、

```text
速め設定: 12-24時間
保守設定: 2-4日
429多発: それ以上
```

くらいで見ておくべきです。

30万件全体なら、20件/pageで15,000 requests。

```text
6秒間隔  : 約25時間
10秒間隔 : 約42時間
18秒間隔 : 約75時間
27秒間隔 : 約112時間
```

実際はretry、空ページ、日別Searchの追加があるので、**2-6日程度**が現実的です。

---

### Q4. PlaywrightでスクロールしながらDOM抽出する方が確実では？

大量取得ではおすすめしません。

理由：

- DOMは仮想リストで過去要素が消える
- スクロール位置復元が難しい
- 重複・欠落検出が難しい
- 速度が遅い
- UI変更に弱い
- tweet_idやRT構造を正確に取るには結局network JSONを見る方がよい
- 途中でおすすめ投稿、広告、固定投稿、会話文脈が混ざる可能性がある

PlaywrightはDOM抽出ではなく、

```text
GraphQL request capture用
ログイン/session更新用
動作確認用
```

に使うのがよいです。

---

## 5. Claude Codeが詰まった主原因

おそらく詰まり原因はこれです。

```text
1. UserTweetsAndRepliesだけで完走させようとした
2. cursor終了時の不完全判定が曖昧
3. SearchTimelineによる日別検証が後回し
4. rate limit方針が固定値で遅すぎる
5. SQLiteにpage/cursor/run状態を十分保存していない
6. 取得済み件数と期待件数の差分検証が弱い
```

特に重要なのは、**「ページを取る」処理と「完走したと判断する」処理を分けること**です。

---

## 6. 次の実装手順

短く具体的に言うと、次はこれで進めるべきです。

### Step 1: SQLite schemaを固める

最低限これを作る。

```sql
accounts
tweets
tweet_sources
fetch_runs
fetch_pages
fetch_buckets
graphql_captures
rate_limit_events
```

重要なのは `fetch_pages` に raw JSON と cursor を保存すること。

```sql
fetch_pages(
  id,
  account_id,
  source,
  bucket_key,
  request_url,
  request_variables_json,
  cursor_in,
  cursor_out,
  status_code,
  response_json,
  tweet_count,
  fetched_at,
  error
)
```

---

### Step 2: cursor処理をtransaction化する

1ページ取得ごとに、

```text
BEGIN
  response_json保存
  tweets upsert
  tweet_sources upsert
  next_cursor保存
COMMIT
```

失敗したらcursorを進めない。

---

### Step 3: SearchTimeline日別取得を実装

query:

```text
from:SCREEN_NAME since:YYYY-MM-DD until:YYYY-MM-DD
```

mode:

```text
Latest
```

完了条件：

```text
TimelineTerminateTimeline
または
next cursorなし
または
取得tweetのcreated_atがsince境界より古い
```

1日で件数が多すぎる場合は時間単位に分割。

---

### Step 4: UserTweetsAndRepliesも並行実装

目的は、

```text
RT/Repost補完
プロフィール時系列補完
Search漏れ検出
```

Searchとtweet_idを突合する。

---

### Step 5: adaptive rate limitにする

初期値：

```text
GraphQL page request: 6-10秒 jitter
concurrency: 1
```

429時：

```text
reset headerあり: resetまでsleep
reset headerなし: 15分sleep
その後 12-20秒に戻す
```

---

### Step 6: 漏れ検証を実装

日別に以下を出す。

```text
date
search_count
timeline_count
intersection_count
search_only_count
timeline_only_count
min_created_at
max_created_at
completed_flag
```

`timeline_only` が多い日はSearch側の漏れ。  
`search_only` が多い日はUserTweetsAndReplies側の漏れ。

---

## 最終方針

おすすめ構成はこれです。

```text
取得主軸:
  SearchTimeline 日別

RT/Repost補完:
  UserTweetsAndReplies

GraphQL更新対応:
  Playwright reactive recapture

rate limit:
  6-10秒 jitter開始、429でbackoff

保存:
  SQLiteにpage単位raw JSON + tweet正規化保存

再開:
  bucket単位、cursor単位で再開

検証:
  日別でSearchTimelineとUserTweetsAndRepliesを突合
```

つまり、**SearchTimelineを最初から入れるべき**です。  
ただし、**SearchTimelineだけではRT/Repostが危ないので、UserTweetsAndRepliesを捨てずに補完系として使う**のが一番安全です。
結論:

1. **UserTweetsAndRepliesジョブは止めない**
2. **次はSearchTimeline日別取得スクリプトを実装**
3. **日別推奨。月別は検証・スキップ補助用に限定**
4. **画像URLはGraphQL/API内の`extended_entities.media`を主軸。fxtwitterは原則不要**

---

## A. 今のUserTweetsAndRepliesジョブを止めるか

**止めない。完走させる。**

理由:

- すでに830件/30ページまで進んでいるので、ここで止めるのはもったいない。
- `UserTweetsAndReplies`はRT・Reply補完に使える。
- 実測で以下が取れる:
  - 1ページ実効件数
  - RT / Reply / Normal比率
  - cursorがどこで止まるか
  - GraphQLレスポンス構造の実例
- SearchTimelineの取得漏れ検証用ベースラインにもなる。

ただし注意:

- **同じアカウント・同じ認証でSearchTimelineを並行実行しない。**
- 並行リクエストはrate limitや一時BANのリスクを上げる。
- 実装作業は並行してよいが、実際の取得実行は片方ずつが安全。

推奨:

```text
今のUserTweetsAndReplies: 続行
SearchTimeline: 別スクリプトとして実装開始
実行: UserTweetsAndReplies完走後にSearchTimeline開始
```

---

## B. 次に実装すべきスクリプト

優先順位はこれ。

### 1. SQLite raw page保存の共通基盤

まずこれが必要。

最低限のテーブル:

```sql
CREATE TABLE IF NOT EXISTS raw_pages (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  source TEXT NOT NULL,              -- SearchTimeline / UserTweetsAndReplies
  query TEXT,
  user_id TEXT,
  since_date TEXT,
  until_date TEXT,
  cursor_in TEXT,
  cursor_out TEXT,
  status_code INTEGER,
  fetched_at TEXT NOT NULL,
  raw_json TEXT NOT NULL,
  error TEXT
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_raw_pages_unique
ON raw_pages(source, query, since_date, until_date, cursor_in);
```

tweet正規化用:

```sql
CREATE TABLE IF NOT EXISTS tweets (
  tweet_id TEXT PRIMARY KEY,
  author_id TEXT,
  screen_name TEXT,
  created_at TEXT,
  full_text TEXT,
  is_retweet INTEGER,
  is_reply INTEGER,
  is_quote INTEGER,
  conversation_id TEXT,
  raw_json TEXT,
  first_seen_source TEXT,
  updated_at TEXT
);
```

media用:

```sql
CREATE TABLE IF NOT EXISTS media (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  tweet_id TEXT NOT NULL,
  media_key TEXT,
  type TEXT,
  media_url TEXT,
  expanded_url TEXT,
  raw_json TEXT,
  UNIQUE(tweet_id, media_url)
);
```

---

### 2. SearchTimeline日別取得スクリプト

次に作るべき本体はこれ。

形式:

```text
from:smile_danjer since:YYYY-MM-DD until:YYYY-MM-DD
```

注意点:

- `until`は排他的。
- 1日取得なら `since:2020-01-01 until:2020-01-02`
- `Latest`相当で取得する。
- cursorを保存して中断再開可能にする。
- page単位でraw JSONを必ず保存。
- tweet抽出・media抽出は後段で再処理可能にする。

---

### 3. 検証SQL

SearchTimeline実装と同時に、簡単な検証SQLも作るべき。

例:

日別件数:

```sql
SELECT date(created_at) AS d, COUNT(*)
FROM tweets
GROUP BY d
ORDER BY d;
```

source別重複確認:

```sql
SELECT tweet_id, COUNT(*)
FROM tweets
GROUP BY tweet_id
HAVING COUNT(*) > 1;
```

SearchTimelineに無くUserTweetsAndRepliesにあるtweet:

```sql
SELECT tweet_id, first_seen_source, created_at, full_text
FROM tweets
WHERE first_seen_source = 'UserTweetsAndReplies';
```

本当は`tweet_sources`テーブルを別に持つと検証しやすい。

```sql
CREATE TABLE IF NOT EXISTS tweet_sources (
  tweet_id TEXT NOT NULL,
  source TEXT NOT NULL,
  query TEXT,
  since_date TEXT,
  until_date TEXT,
  page_id INTEGER,
  PRIMARY KEY(tweet_id, source, query, since_date, until_date)
);
```

---

## C. 日別 vs 月別

**最終取得は日別推奨。**

月別はおすすめしない。

理由:

- SearchTimelineは内部上限やcursor打ち切りがあり得る。
- 月単位だと、件数が多い月で途中打ち切りになっても気づきにくい。
- 取得漏れ検証が難しくなる。
- `from:user since:2020-01-01 until:2020-02-01`で全部返る保証はない。

6年分の日別、約2,190日は現実的か？

**現実的。**

6〜10秒jitterなら、1日1ページだけでも:

```text
2,190日 × 約8秒 = 約17,520秒 = 約4.9時間
```

実際は複数ページの日もあるので、数日〜1週間程度のバッチと見れば現実的。

推奨方式:

```text
基本: 日別
空の日: 1ページで終了
多い日: cursorで最後まで取得
429: backoffして再開
失敗日: SQLiteに残して後でretry
```

月別を使うなら:

- 事前の粗い活動期間確認
- 空白期間の推定
- 件数のざっくり把握

に限定。

ただし、月別で「0件だったから完全に投稿なし」と断定するのは避ける。

---

## D. 実測データを待つべきか

**待たなくてよい。**

UserTweetsAndRepliesの完走結果は有用だが、SearchTimeline実装方針は変わらない。

理由:

- UserTweetsAndRepliesはユーザータイムライン系なので、古い投稿やRT、replyの扱いに限界がある。
- SearchTimeline日別は取得漏れ検証しやすい。
- 830件/30ページの結果を待っても、SearchTimelineが不要になることはない。

したがって:

```text
UserTweetsAndReplies: 走らせる
SearchTimeline: 今すぐ実装する
方式決定: 待たない
実行開始: UserTweetsAndReplies完走後が安全
```

---

## E. 画像URLの取得方法

**GraphQL/APIレスポンス内の`extended_entities.media`を使う。fxtwitterは原則不要。**

tweet JSONに含まれる主な場所:

```text
legacy.extended_entities.media
legacy.entities.media
```

写真ならだいたい:

```json
{
  "type": "photo",
  "media_url_https": "https://pbs.twimg.com/media/xxxxx.jpg",
  "expanded_url": "https://twitter.com/.../status/.../photo/1"
}
```

保存時は`media_url_https`をそのまま保存し、ダウンロード時に必要なら:

```text
https://pbs.twimg.com/media/xxxxx.jpg?format=jpg&name=orig
```

のようにorig化する。

動画/GIFの場合は:

```text
video_info.variants
```

からbitrate最大のmp4を選ぶ。

fxtwitterを使うべきケースは限定的:

- GraphQL JSONにmediaが無い
- card由来の外部画像が欲しい
- 何らかの理由で動画URL抽出に失敗した
- 取得済みtweet JSONが壊れている

通常の画像取得にfxtwitterを挟むと:

- 追加リクエストが増える
- rate limitとは別のブロック要因が増える
- HTML/外部サービス依存になる
- 再現性が下がる

ので、主経路にしない。

---

## 実装順序の最終案

### Step 1

今の`UserTweetsAndReplies`は継続。

ただし今後のページは必ずSQLiteにraw保存する。

```text
source = UserTweetsAndReplies
cursor_in
cursor_out
raw_json
fetched_at
```

---

### Step 2

SQLite保存基盤を共通化。

```text
save_raw_page()
upsert_tweet()
upsert_media()
record_tweet_source()
```

を作る。

---

### Step 3

SearchTimeline日別スクリプトを実装。

入力:

```text
screen_name = smile_danjer
start_date = 2020-01-01
end_date = today
```

処理:

```text
for each day:
  query = "from:smile_danjer since:YYYY-MM-DD until:YYYY-MM-DD"
  cursor = resume cursor if exists
  while True:
    request SearchTimeline
    save raw page
    extract tweets
    save tweets/media
    if no next cursor: break
    sleep 6-10 sec jitter
```

429時:

```text
sleep 15min → retry
再429なら 30min → 60min
状態をSQLite保存して終了可能にする
```

403/404時:

```text
Playwrightで再捕捉
guest/auth headers/token更新
同じcursorから再開
```

---

### Step 4

検証SQLを走らせる。

見るべきもの:

```text
日別tweet件数
SearchTimeline vs UserTweetsAndRepliesの差分
RT件数
Reply件数
画像付きtweet件数
cursor打ち切り疑惑のある日
```

---

## Claude Codeが詰まった原因の推定

主因はおそらくこれ。

```text
UserTweetsAndRepliesを主取得経路にしようとして、
cursor終端・RT混入・reply混入・古い投稿到達性の不確実性を
コード側で吸収しようとしたため。
```

UserTweetsAndRepliesは便利だが、完全収集の主軸にはしにくい。

正しい分担は:

```text
SearchTimeline日別:
  通常投稿・reply含む検索ベースの主取得

UserTweetsAndReplies:
  RT補完、差分検証、SearchTimeline漏れ検出

Playwright:
  token/header更新専用

SQLite raw_pages:
  再解析・中断再開・検証用の証跡
```

---

## 最終結論

```text
1. UserTweetsAndRepliesは止めない。完走させる。
2. 次はSearchTimeline日別スクリプトを実装する。
3. 月別ではなく日別。2,190日程度なら現実的。
4. 画像URLはextended_entities.mediaから取る。fxtwitterはfallbackのみ。
5. 実測結果は待たずに実装開始。ただし実行はrate limit回避のため片方ずつ。
```
合意。

ただし条件付きで、SearchTimelineの**捕捉済み実ブラウザ通信一式**をそのまま使うこと。

- `queryId`
- `operationName`
- `variables`
- `features`
- `fieldToggles`
- `headers`
- `cookies/auth`

SearchTimelineで**429が返っていたなら、URL/API自体は到達できている**可能性が高いです。  
先ほどの404は、UserTweetsAndReplies同様に **古いqueryId/features/headers不一致** が原因の可能性が高いです。

次は `x_captured_requests.json` のSearchTimelineリクエストを正として実装でOK。
結論: **今すぐ有効なのは「既知status_idの補完系」をGraphQLと並列に回すこと**。未知IDの発見はGraphQL/Searchが主力のまま。

| 手段 | 並列可否 | 速度/rate limit | 取得範囲 | 結論 |
|---|---:|---|---|---|
| 1. oEmbed | ◎ | 比較的速いが非公式制限あり | **既知URL/IDのみ**。本文/著者/埋め込みHTML程度 | ID検証・削除/非公開判定に使う。発見には使えない |
| 2. fxtwitter API | ◎ | 不安定・制限不明 | **既知IDのみ**。本文/メディア補完向き | 補助として有効。一次ソース扱いは避ける |
| 3. Wayback CDX | ◎ | 遅めだが独立 | アーカイブ済みURLからID発見可。網羅性低い | 低優先でID発掘ジョブとして回す価値あり |
| 4. Google検索 | △ | CAPTCHA/制限強い | ID発見可だが漏れ多い | 自動化は非推奨。やるならCustom Search等で少量 |
| 5. gallery-dl | △ | X側制限に依存 | 主にメディア/タイムライン | 同じcookieならGraphQL枠を食う可能性大。今は不要 |
| 6. Syndication API | ◎ | 非公式制限あり | **既知IDのみ**。tweet detail補完 | oEmbed/fxtwitterと同じ補完レーンで有効 |
| 7. 別Xアカウント | ◎ | 最も効果大 | Search/UserTimelineを別枠で回せる可能性 | 所有アカウントでcookie完全分離。最優先の追加並列手段 |
| 8. その他 | ○ | まちまち | 公式API、既存DB、外部アーカイブ | 公式APIが使えるなら最安定 |

次の実装順:

1. **別Xアカウントを追加**
   - Playwright context/cookie/storageStateを完全分離。
   - SQLiteに `account_id`, `endpoint`, `cursor`, `rate_limit_until` を持たせる。
   - SearchTimeline 6アカウント分を別アカウントへ分散。

2. **既知status_id補完ワーカーを追加**
   - 入力: SQLiteの `tweets.status_id` または CDX等で拾ったID。
   - 並列で `oEmbed` / `Syndication` / `fxtwitter` を叩く。
   - GraphQL cookieを使わないので現在処理と独立。

3. **Wayback CDXを低速ID発掘として常時実行**
   - `https://web.archive.org/cdx?url=x.com/{user}/status/*`
   - 取れたstatus_idを `tweet_ids_discovered` に保存。
   - GraphQL/補完ワーカーに流す。

4. **gallery-dlは後回し**
   - 同じX cookieを使うならrate limit競合リスクあり。
   - メディア欠損確認用に限定。

5. **取得漏れ検証**
   - 各ユーザーごとに `max_id/min_id`, ページcursor, 件数推移を保存。
   - Search結果、UserTweetsAndReplies結果、Wayback ID、補完API結果をSQLiteで突合。
   - `status_id UNIQUE` で重複排除。

最短の追加並列構成:

```text
A: 現在の UserTweetsAndReplies GraphQL 継続
B: SearchTimeline GraphQL を別Xアカウントcookieで並列化
C: Wayback CDXでstatus_id発掘
D: oEmbed/Syndication/fxtwitterで既知ID補完
```

優先度は **7 > 6/1/2 > 3 > 5 > 4**。
原因はほぼ **Node.js fetch が Chromium の実ブラウザ通信として見えていないための SearchTimeline 側の soft 404** です。

UserTweets は通るが SearchTimeline だけ 404 になるなら、`features` や Bearer の問題ではなく、SearchTimeline がより厳しく以下を見ている可能性が高いです。

- Chromium の TLS / HTTP2 fingerprint
- header order / priority / pseudo headers
- `sec-fetch-*`, `sec-ch-ua-*`, `referer`, `origin`
- `x-client-transaction-id` が URL / method / 時刻 / セッション状態に紐づく
- SearchTimeline 特有の bot 判定

つまり **Playwright で200、同じ値をNode fetchで404** は自然です。  
Node fetch で完全再現する方向は捨てた方が早いです。

---

## 解決方針

### 1. SearchTimeline は Node fetch で叩かない

Playwright のブラウザ内で取得してください。

優先順はこれです。

### A. 最も安定: UIスクロールしてGraphQL responseを捕捉

```js
page.on('response', async res => {
  const url = res.url();
  if (url.includes('/i/api/graphql/') && url.includes('/SearchTimeline')) {
    const status = res.status();
    const text = await res.text();

    // status, url, body をSQLiteに保存
  }
});
```

その上で検索ページを開く。

```js
await page.goto('https://x.com/search?q=from%3Asmile_danjer&f=live', {
  waitUntil: 'domcontentloaded'
});
```

ページ下部までスクロールして、X公式クライアントに次ページを発火させる。

```js
await page.mouse.wheel(0, 3000);
await page.waitForTimeout(1500);
```

これなら `x-client-transaction-id` や fingerprint は公式Webクライアントが生成します。

---

### B. 次善: `page.evaluate()` 内の fetch を使う

Node fetch ではなく Chromium 内で fetch します。

```js
const result = await page.evaluate(async (url) => {
  const r = await fetch(url, {
    method: 'GET',
    credentials: 'include'
  });

  return {
    status: r.status,
    text: await r.text()
  };
}, capturedUrl);
```

ただし SearchTimeline は `x-client-transaction-id` がURLごとに必要な可能性があるため、ページ内fetchでも404になる場合があります。  
その場合は A の「公式UIにスクロールさせる方式」に寄せてください。

---

## 実装手順

### 1. Playwrightで検索ページを開く

```txt
https://x.com/search?q=from%3Asmile_danjer&f=live
```

### 2. `SearchTimeline` response を全部保存

SQLiteに最低限これを保存。

```sql
CREATE TABLE IF NOT EXISTS graphql_responses (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  endpoint TEXT,
  url TEXT UNIQUE,
  status INTEGER,
  body TEXT,
  fetched_at TEXT
);

CREATE TABLE IF NOT EXISTS tweets (
  tweet_id TEXT PRIMARY KEY,
  user_id TEXT,
  screen_name TEXT,
  text TEXT,
  created_at TEXT,
  raw_json TEXT,
  fetched_at TEXT
);

CREATE TABLE IF NOT EXISTS cursors (
  query TEXT PRIMARY KEY,
  bottom_cursor TEXT,
  last_tweet_id TEXT,
  updated_at TEXT
);
```

### 3. レスポンスから tweet と cursor を抽出

SearchTimeline の中の以下を走査。

- `instructions`
- `entries`
- `content.itemContent.tweet_results.result`
- `content.value` が `Bottom` cursor

保存済み `tweet_id` は `INSERT OR IGNORE`。

### 4. ページネーションはまずスクロールで行う

```js
let noNewCount = 0;
let lastCount = 0;

while (noNewCount < 5) {
  await page.mouse.wheel(0, 4000);
  await page.waitForTimeout(2000);

  const count = await getSavedTweetCount();

  if (count === lastCount) {
    noNewCount++;
  } else {
    noNewCount = 0;
    lastCount = count;
  }
}
```

### 5. 中断再開

再開時は同じ検索URLを開いて、既存 `tweet_id` を重複除外しながら続行。  
cursor直叩きは SearchTimeline では壊れやすいので、まずはUIスクロール再開でよいです。

---

## 取得漏れ検証

最低限これを確認してください。

1. `SearchTimeline` の 200 レスポンス数
2. 各レスポンスの tweet 件数
3. bottom cursor が変化しているか
4. tweet_id の重複率
5. 連続 N 回 tweet 増加なしで終了していないか
6. UI上の最古ツイート日時とSQLite内の最古日時が一致するか

---

## rate limit 対策

- スクロール間隔は 1.5〜4秒でランダム化
- 429 / 403 / 404 が増えたら即停止
- 同一cookieで並列取得しない
- GraphQL raw response は必ず保存して再解析可能にする

---

## 結論

SearchTimeline は Node.js fetch で再現しようとしない方がよいです。  
原因は URL や features ではなく、**Chromium実通信 + X公式クライアント生成ヘッダー/transaction/fingerprint への依存** です。

次の実装は、

1. Playwrightで検索ページを開く  
2. `SearchTimeline` responseを捕捉  
3. SQLiteへ raw response / tweet / cursor 保存  
4. ページネーションはUIスクロール  
5. tweet_id重複除外で中断再開  

この方針が最短です。
### 原因見立て
`auth_token` だけを `context.addCookies()` しても、X がログイン済み判定しない可能性が高いです。最低でも `ct0`、`auth_token`、できれば `twid`、`guest_id` 系を含む実ブラウザの cookie セットが必要です。`ct0` は CSRF トークンとして GraphQL 呼び出しにも関係します。

---

## 1. PlaywrightでXにcookieを注入する正しい方法

`addCookies()` でも可能ですが、**auth_token単体では不足**です。

推奨は以下の順です。

### 推奨
1. `launchPersistentContext()` で実ブラウザプロファイルを作る  
2. 手動で X にログイン  
3. `storageState()` を保存  
4. 以後は `storageState` を読み込んで実行

```js
const context = await chromium.launchPersistentContext('./x-profile', {
  headless: false,
});
```

または保存済み state を使う。

```js
const browser = await chromium.launch();
const context = await browser.newContext({
  storageState: 'x-storage.json',
});
```

`addCookies()` を使うなら最低限：

```js
await context.addCookies([
  {
    name: 'auth_token',
    value: '...',
    domain: '.x.com',
    path: '/',
    httpOnly: true,
    secure: true,
    sameSite: 'None',
  },
  {
    name: 'ct0',
    value: '...',
    domain: '.x.com',
    path: '/',
    secure: true,
    sameSite: 'Lax',
  },
]);
```

`.twitter.com` ではなく、アクセス先が `https://x.com` なら `.x.com` に入れること。

---

## 2. 検索結果0件時、先にhomeを開くべきか

はい。必ず最初に `https://x.com/home` を開いてログイン確認してください。

確認項目：

```js
await page.goto('https://x.com/home', { waitUntil: 'domcontentloaded' });

const url = page.url();
if (url.includes('/login') || url.includes('/i/flow/login')) {
  throw new Error('not logged in');
}

const ct0 = (await context.cookies()).find(c => c.name === 'ct0');
if (!ct0) throw new Error('ct0 missing');
```

その後に search へ遷移。

```js
await page.goto('https://x.com/search?q=CryptoHayes&src=typed_query&f=live');
```

検索ページ直行より、home経由の方がログイン状態・CSRF・初期JS状態が安定します。

---

## 3. response.json() が空になる原因

主な原因はこれです。

1. ログイン未認識で GraphQL が正常に呼ばれていない  
2. 取得した response が `SearchTimeline` ではなく、別API、preflight、画像、空レスポンス  
3. 429 / rate limit / challenge / login redirect  
4. `content-type` が JSON ではなく HTML  
5. 304 / 204 / bodyなしレスポンス  
6. ServiceWorker / cache絡みで body が取れない  
7. GraphQL は 200 だが中身が `{ errors: [...] }`

まず `json()` ではなく `text()` で保存して確認してください。

```js
page.on('response', async res => {
  const url = res.url();
  if (!url.includes('/i/api/graphql/') || !url.includes('SearchTimeline')) return;

  console.log('status', res.status(), url);
  console.log('content-type', res.headers()['content-type']);

  const text = await res.text();
  console.log(text.slice(0, 500));

  // SQLite/ファイルにraw保存推奨
});
```

---

## 次の実装手順

1. Playwright persistent profileで一度手動ログイン  
2. `x-storage.json` または profile dir を保存  
3. 起動時に `/home` を開いてログイン確認  
4. `ct0` cookie存在確認  
5. searchへ遷移  
6. `SearchTimeline` responseを `text()` でraw保存  
7. SQLiteに `raw_response`, `cursor`, `query`, `fetched_at` を保存  
8. 0件でも cursor と raw JSON を保存して、空ページ打ち切り判定を検証  
9. 429/challenge/login redirect時は停止して再開可能にする  

結論：今の詰まりは **TLS問題ではなく、Playwright側のログインセッション不完全が本命**です。
1. **別バケットの可能性が高い**  
   はい。`SearchTimeline` と `UserTweetsAndReplies` は別GraphQL operationなので、rate limitも別扱いの可能性が高いです。  
   `UserTweetsAndReplies` が正常でも、`SearchTimeline` だけ429は普通にあり得ます。

2. **30分で回復しないなら数時間〜24時間を見るべき**  
   X Web GraphQLの制限は公式APIの15分窓と違い不透明です。  
   目安は：
   - まず **2〜6時間停止**
   - それでも429なら **翌日まで停止**
   - テスト連発後なら **24時間待つのが安全**

3. **429 bodyは実際に読むべき。形式は固定と思わない**  
   多くはJSONで例えば以下系です。

   ```json
   {
     "errors": [
       { "message": "Rate limit exceeded" }
     ]
   }
   ```

   ただし空body、HTML、別形式もあり得ます。  
   Playwrightでは必ずこれを保存してください。

   ```ts
   page.on('response', async (res) => {
     if (res.url().includes('SearchTimeline')) {
       const status = res.status()
       const headers = res.headers()
       let body = ''
       try { body = await res.text() } catch {}
       console.log({ status, headers, body: body.slice(0, 1000) })
     }
   })
   ```

4. **page.evaluate()内fetchは技術的には可能。ただし解決策ではない**  
   公式Web画面と同じcookie/csrf/bearerでGraphQL fetchは可能です。  
   ただし同じ `SearchTimeline` を叩くなら **同じrate limitに当たる** ので、429回避にはなりません。  
   むしろ追加リクエストで悪化します。今はやらない方がいいです。

5. **今日は止めて明日再開が妥当**  
   今日テストで連発したなら累積制限の可能性が高いです。  
   明日まで待って、再開時は以下にしてください。

   - `SearchTimeline` は1リクエストごとに **30〜90秒待機**
   - 429が出たら即停止、SQLiteに `blocked_at` 保存
   - cursorをSQLite保存して中断再開
   - response body/headers/statusを全件保存
   - 同一cursor再試行を連発しない
   - 取得件数、最古tweet_id、cursor遷移を保存して取得漏れ検証

結論：  
**SearchTimelineだけ制限中。今日は止める。明日、低頻度・cursor保存・429即停止で再開。`page.evaluate(fetch)`での回避はしない。**
問題あり。主因は **UserTweetsAndRepliesだけでは全量取得できない可能性が高い** のと、**SearchTimelineの429対策が弱い** ことです。

## 指摘

### 1. 取得率17%はまだ「正常進行」ではなく、設計不足の可能性あり
UserTweetsAndReplies はプロフィールタイムライン取得なので、古い投稿まで無限に取れる保証がありません。  
ronpochi で 110ページ / 約13,000件取れているのは良いですが、プロフィール表示 115,000 に対してはまだ大きく不足しています。

**結論:**  
残り5アカウントを順次 UserTweetsAndReplies するだけでは、最終的に大幅な取得漏れが残る可能性が高いです。  
SearchTimeline による年月日分割取得を本線にするべきです。

---

### 2. SearchTimelineの再開間隔 30-90秒は短い
昨日429が出ているなら、単純に30-90秒で再開するとまた429になる可能性が高いです。

必要なのは以下です。

- 429時に `x-rate-limit-reset` があればそこまで停止
- なければ 15分、30分、60分の指数バックオフ
- アカウント単位ではなく、GraphQL operation 単位で rate limit 管理
- SearchTimeline と UserTweetsAndReplies を同時に強く回さない

**30-90秒間隔は通常リクエスト間隔としては可。ただし429復帰間隔としては短い。**

---

### 3. cursor保存が最重要
タイムアウトリトライで継続できているのは良いですが、以下がないと中断時に取り直しになります。

SQLiteに最低限これを保存してください。

```sql
account
operation
cursor
last_tweet_id
min_created_at
max_created_at
page_count
status
updated_at
```

UserTweetsAndReplies も SearchTimeline も **ページごとにcursor永続化**。  
成功したページだけコミット。失敗ページは再試行。

---

### 4. PlaywrightはDOMではなくGraphQL responseを捕捉する
Playwrightで画面スクロール依存にすると漏れます。  
必ず `page.on("response")` または `waitForResponse` で以下を拾う。

- `UserTweetsAndReplies`
- `SearchTimeline`
- `TweetDetail` 必要なら

レスポンスJSONから tweet id / cursor を抽出し、DOM表示件数は信用しない。

---

### 5. oEmbed補完は本文補完であって、取得漏れ解消ではない
oembed 44,998件完了は良いですが、これは既知URL/IDの補完です。  
未取得ツイートの発見にはならないので、取得率改善には SearchTimeline が必要です。

---

## 次の実装手順

### Step 1. ronpochi UserTweetsAndRepliesは完走させる
ただし、以下を記録。

- 最終bottom cursor
- 最終ページのtweet件数
- 最古tweet日時
- 最古tweet_id
- 終了理由  
  - cursorなし
  - 空ページ
  - 連続重複
  - 429
  - timeout上限

「完了」とだけ記録しないこと。

---

### Step 2. 残り5アカウントのUserTweetsAndRepliesを走らせる前に、共通cursor保存を入れる
今のまま順次実行すると、途中停止時に復旧が面倒になります。

SQLiteに `crawl_state` を追加。

```sql
CREATE TABLE IF NOT EXISTS crawl_state (
  account TEXT NOT NULL,
  operation TEXT NOT NULL,
  query TEXT,
  cursor TEXT,
  since_date TEXT,
  until_date TEXT,
  page_count INTEGER DEFAULT 0,
  item_count INTEGER DEFAULT 0,
  last_tweet_id TEXT,
  min_created_at TEXT,
  max_created_at TEXT,
  status TEXT,
  error TEXT,
  updated_at TEXT,
  PRIMARY KEY(account, operation, query, since_date, until_date)
);
```

---

### Step 3. SearchTimelineは日付分割で再開する
雑に `from:USER` で全期間検索しない。  
日付窓で分割する。

例:

```text
from:ronpochi since:2024-01-01 until:2024-02-01
```

件数が多いアカウントは月単位ではなく週単位または日単位にする。

推奨:

| 投稿密度 | window |
|---|---|
| ronpochi | 1日〜3日 |
| danjer | 3日〜7日 |
| Checkmatey | 3日〜7日 |
| BobLoukas | 7日 |
| LynAlden | 7日 |
| PeterBrandt | 7日 |
| CryptoHayes | 14日〜30日 |

1 window 内で cursor が尽きるまでページング。  
同じwindowで重複率が高くなったら終了。

---

### Step 4. 429対策を実装してからSearchTimeline再開
429時の処理。

```text
if x-rate-limit-reset exists:
    sleep until reset + 60 sec
else:
    sleep 15min
    next 429 => 30min
    next 429 => 60min
```

通常時のSearchTimeline間隔は以下。

```text
1ページごとに 45-120秒 jitter
window切替時に 2-5分 sleep
アカウント切替時に 5-10分 sleep
```

UserTweetsAndRepliesとSearchTimelineを同時に高頻度で走らせない。

---

### Step 5. 取得漏れ検証を入れる
DB件数だけでは不十分です。アカウントごとに以下を出す。

```sql
SELECT
  account,
  COUNT(*) AS total,
  MIN(created_at) AS oldest,
  MAX(created_at) AS newest,
  COUNT(DISTINCT tweet_id) AS unique_ids
FROM tweets
GROUP BY account;
```

さらに日別件数。

```sql
SELECT
  account,
  substr(created_at, 1, 10) AS day,
  COUNT(*) AS cnt
FROM tweets
GROUP BY account, day
ORDER BY account, day;
```

日別で突然0件の期間があるならSearchTimelineで再取得対象にする。

---

## 優先順位

今やるべき順番はこれです。

1. ronpochi UserTweetsAndReplies 完走  
2. `crawl_state` 追加  
3. UserTweetsAndReplies のcursor永続化確認  
4. SearchTimeline の429バックオフ実装  
5. ronpochi で SearchTimeline 日付分割テスト  
6. 取得漏れ検証SQLを出力  
7. 残りアカウントへ横展開

## 判断

現在の進捗自体は悪くないですが、**このまま残り5アカウントのUserTweetsAndRepliesを流すだけだと、最終取得率はおそらく20〜40%程度で頭打ち**になります。  
SearchTimelineの日付分割、cursor保存、429バックオフ、日別漏れ検証を先に固めるべきです。
結論：**SearchTimelineでnew 0件なのは正常寄り。未取得の主因はSearchTimeline対象外/保存対象外のRT(Repost)イベントの可能性が高い**です。まず「投稿本体」と「プロフィール上のタイムラインイベント」を分けて検証すべきです。

---

### 1. `from:user` はリプライも返すか？

基本は返りますが、**SearchTimelineは完全性が弱い**です。

検証用に分けて実行してください。

```txt
from:CryptoHayes since:2024-06-01 -filter:replies
from:CryptoHayes since:2024-06-01 filter:replies
```

リプライ漏れ確認には `filter:replies` は必要です。  
ただし、既に `UserTweetsAndReplies` で取れているなら新規0件でも不自然ではありません。

---

### 2. プロフィール2,563件のうちRT割合を確認する方法

Playwrightで **UserTweets / プロフィールPostsタブのGraphQL raw** を保存し、timeline item単位で分類してください。

見るべき判定材料：

- `socialContext` に `reposted`
- `retweeted_status_result`
- `full_text LIKE 'RT @%'`
- timeline itemの表示投稿authorがCryptoHayesではない
- `tweet_id`のauthor != 対象ユーザー だが、timeline上ではCryptoHayesがrepost

SQLite例：

```sql
SELECT
  SUM(CASE WHEN raw LIKE '%retweeted_status_result%' 
            OR raw LIKE '%reposted%' 
            OR full_text LIKE 'RT @%' THEN 1 ELSE 0 END) AS rt_like,
  COUNT(*) AS total
FROM timeline_entries
WHERE screen_name = 'CryptoHayes';
```

重要：`tweets` テーブルだけではなく、**timeline_entries/eventテーブル**で数えること。

---

### 3. DB 1,554件がオリジナル+リプライ全部で、残り約1,000件がRTの可能性は？

あります。

特に以下ならその可能性が高いです。

- `SearchTimeline from:user` でnew 0件
- `UserTweetsAndReplies` でもオリジナル/リプライは取得済み
- プロフィール件数との差分が大きい
- 保存時に `author_id = CryptoHayes` のtweetだけ保存している

RT/Repostは「CryptoHayesが書いたtweet」ではなく、**CryptoHayesのタイムライン上のrepostイベント**です。  
元tweetのauthorは別人なので、author filterで落としている可能性があります。

---

### 4. RTを取得する方法

優先順：

#### A. GraphQL `UserTweets` を取る

プロフィールの **Postsタブ** 相当。  
`UserTweetsAndReplies` ではなく `UserTweets` をPlaywrightで捕捉。

保存時はtweetだけでなく、こういうeventとして保存する。

```sql
CREATE TABLE IF NOT EXISTS timeline_events (
  user_id TEXT,
  source TEXT,
  cursor TEXT,
  sort_index TEXT,
  event_type TEXT, -- tweet, reply, quote, repost
  tweet_id TEXT,
  original_author_id TEXT,
  reposted_by_user_id TEXT,
  raw_json TEXT,
  fetched_at TEXT,
  PRIMARY KEY(user_id, source, sort_index, tweet_id)
);
```

#### B. SearchTimelineで試す

```txt
from:CryptoHayes include:nativeretweets since:2024-06-01
```

ただし、SearchTimelineのRT取得は不安定なので補助扱い。

#### C. 公式APIが使えるなら user tweets

API v2なら retweets除外を指定しなければ取れる可能性あり。

```txt
GET /2/users/:id/tweets
```

ただしプラン制限あり。

---

### 次の実装手順

1. Playwrightで `UserTweets` GraphQLを捕捉する  
2. response rawをSQLiteに全保存する  
3. tweet保存とは別に `timeline_events` を作る  
4. itemごとに `tweet/reply/quote/repost` 分類する  
5. `author_id = target` だけで捨てない  
6. cursorをDB保存して中断再開対応  
7. bottom cursorが消えるまで取得  
8. 最後に件数比較する

検証SQL：

```sql
SELECT event_type, COUNT(*)
FROM timeline_events
WHERE user_id = ?
GROUP BY event_type;
```

差分確認：

```sql
SELECT COUNT(DISTINCT tweet_id)
FROM timeline_events
WHERE user_id = ?;
```

今回の詰まり原因は、**SearchTimeline不足ではなく、RT/Repostをtweetとしてではなくeventとして保存していない設計問題**の可能性が高いです。
指摘すべき点は主に2つです。

1. **ronpochi の UTAR完了は「全件完了」ではない**
   - `UserTweetsAndReplies` は全履歴を保証していない。
   - 今回の ronpochi は **2019-10〜2020-09 だけで止まっている**ので、UTARカーソルの終端を「取得完了」と扱うのは危険。
   - 以後、UTAR完了は「UTARで到達可能な範囲の完了」とラベルを分けるべき。

2. **SearchTimeline 429 は実装で無理に突破できない**
   - 429は枠枯渇なので、連打・再試行・並列化で悪化する。
   - 対策は「枠管理」「分割」「中断再開」「無駄リクエスト削減」。
   - 回避ではなく、**消費量を制御して数日単位で確実に進める設計**にする必要がある。

---

## Claude Code が詰まった原因

### 原因1: rate limit 状態を永続管理していない
SearchTimelineで429になった後も、プロセス再起動やテスト連発で同じ枠を削り続けている可能性が高い。

必要なのは、GraphQL operationごとの rate bucket 管理。

最低限保存するもの:

```sql
CREATE TABLE IF NOT EXISTS rate_limits (
  key TEXT PRIMARY KEY,
  limit_count INTEGER,
  remaining INTEGER,
  reset_at INTEGER,
  updated_at INTEGER
);
```

key例:

```text
SearchTimeline:<auth_user_id>
UserTweetsAndReplies:<auth_user_id>
```

レスポンスヘッダに以下があれば必ず保存。

```text
x-rate-limit-limit
x-rate-limit-remaining
x-rate-limit-reset
```

429時は `x-rate-limit-reset` まで完全停止。ヘッダが無い場合は最低30〜60分停止。

---

### 原因2: SearchTimeline のクエリ範囲が広すぎる
ronpochi のように 10万件級を一発で取ろうとすると、カーソル上限・重複・429・途中打ち切りで詰まりやすい。

SearchTimeline は必ず期間分割すべき。

例:

```text
from:ronpochi since:2020-10-01 until:2020-11-01
from:ronpochi since:2020-11-01 until:2020-12-01
...
```

高投稿アカウントは月単位でも多すぎるので、以下のように自動分割。

- 月単位で開始
- ページ数が多い、または取得件数が多い場合は週単位へ分割
- 週でも多い場合は日単位へ分割
- 1ジョブの最大ページ数を決める。例: 30〜50ページ

---

### 原因3: cursor/job の中断再開が弱い
429やPlaywright落ちで再開時に同じページを何度も踏むと、rate limitを無駄に消費する。

必要なジョブテーブル:

```sql
CREATE TABLE IF NOT EXISTS search_jobs (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  account TEXT NOT NULL,
  since_date TEXT NOT NULL,
  until_date TEXT NOT NULL,
  query TEXT NOT NULL,
  cursor TEXT,
  status TEXT NOT NULL DEFAULT 'pending',
  page_count INTEGER DEFAULT 0,
  fetched_count INTEGER DEFAULT 0,
  last_tweet_id TEXT,
  min_created_at TEXT,
  max_created_at TEXT,
  retry_after INTEGER,
  error TEXT,
  updated_at INTEGER
);
```

status:

```text
pending
running
rate_limited
done
failed
split_required
```

429時は:

```text
status = rate_limited
retry_after = reset_at + jitter
cursor = 現在のcursorを保存
```

再開時はそのcursorから続行。

---

## SearchTimeline 429 を乗り越える方針

### やること

#### 1. SearchTimeline を一旦止める
今は枠が枯れているので、まず完全停止。

- 最低30〜60分停止
- 可能ならヘッダの `x-rate-limit-reset` まで停止
- UTARとは別枠の可能性があるが、SearchTimelineはSearchTimelineだけで管理する

---

#### 2. Playwrightでヘッダを必ず記録する
GraphQLレスポンスを捕捉して、SearchTimelineのヘッダをDBに保存。

Playwright側で見る対象:

```text
/graphql/.../SearchTimeline
```

保存するもの:

- URL
- operationName
- queryId
- variables
- cursor
- status code
- x-rate-limit-limit
- x-rate-limit-remaining
- x-rate-limit-reset
- response body raw json

raw保存テーブルも用意した方がよい。

```sql
CREATE TABLE IF NOT EXISTS raw_graphql_responses (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  operation TEXT,
  account TEXT,
  job_id INTEGER,
  cursor TEXT,
  status_code INTEGER,
  headers_json TEXT,
  body_json TEXT,
  created_at INTEGER
);
```

後からパースミスや取得漏れ検証ができる。

---

#### 3. SearchTimeline は1ワーカーに絞る
現時点では並列化禁止。

推奨:

```text
SearchTimeline worker = 1
UTAR worker = 1
ページ間隔 = 10〜30秒 + jitter
429時 = resetまで停止
```

テスト連発も禁止。  
同じクエリを手動確認で何度も叩かない。

---

#### 4. ronpochi は 2020-10 以降を月単位ジョブにする
現在の欠落は明確。

ronpochi用の初期ジョブ:

```text
from:ronpochi since:2020-10-01 until:2020-11-01
from:ronpochi since:2020-11-01 until:2020-12-01
...
from:ronpochi since:2026-05-01 until:2026-05-13
```

各ジョブは `Latest` 検索を使う。  
Top検索は漏れや並び替えが出やすいので避ける。

---

#### 5. ページ上限・重複検出で自動分割
1ジョブで以下の条件に当たったら、その期間を半分に割る。

- 50ページ到達
- cursorが進まない
- 連続3ページで新規tweetが少ない
- 同じtweet_idが大量に再出現
- 取得件数が多すぎる
- レスポンスは200だがentriesが空になる

例:

```text
2021-01-01〜2021-02-01 が重い
=> 2021-01-01〜2021-01-16
=> 2021-01-16〜2021-02-01
```

---

## 取得漏れ検証

### 1. 月別件数を出す
まずDBから月別件数を可視化。

```sql
SELECT
  account,
  substr(created_at, 1, 7) AS ym,
  COUNT(*) AS cnt
FROM tweets
GROUP BY account, ym
ORDER BY account, ym;
```

ronpochi は今こうなるはず。

```text
2019-10〜2020-09 に集中
2020-10以降がゼロまたは極小
```

SearchTimeline完了後、ゼロ月が残っていないか確認。

---

### 2. ジョブ単位で min/max created_at を保存
SearchTimelineの各期間ジョブで以下を保存。

```text
期間
取得件数
最古tweet日時
最新tweet日時
ページ数
終了理由
```

終了理由は重要。

```text
done_no_cursor
done_empty_entries
rate_limited
split_required
duplicate_cursor
error
```

`done_empty_entries` が本当に空なのか、rate limitや検索上限で空になっただけなのかを後で確認できる。

---

### 3. プロフィール件数との比較は参考値に留める
プロフィールの `115,000` は完全な正解ラベルではない。

理由:

- RTを含む可能性
- 削除済みを含まない/含む差
- 非公開化・凍結・検索除外
- repliesを含むかの違い
- X側の内部カウントとの差

なので検証指標は以下に分ける。

```text
DB総数
オリジナルtweet数
reply数
RT数
quote数
月別件数
SearchTimelineジョブ完了率
UTAR到達範囲
```

CryptoHayesのようにプロフィール2,563件に対してDB2,105件なら、残りがRT中心という仮説は妥当。ただし `retweeted_status` や legacy.retweeted_status_result の有無で確認する。

---

## 次の具体的な実装手順

### Step 1: SearchTimelineを止める
ronpochi SearchTimelineは今すぐ停止。

```text
次回再開 = x-rate-limit-reset 以降
ヘッダ不明なら最低60分後
```

---

### Step 2: rate_limits テーブルを追加
GraphQLレスポンスごとに rate limit ヘッダを保存。

429時は全SearchTimelineジョブを止める。

---

### Step 3: search_jobs テーブルを追加
期間分割ジョブをDB管理する。

最初は ronpochi の 2020-10以降だけでよい。

---

### Step 4: ronpochi の月次ジョブを投入
例:

```text
2020-10-01〜2020-11-01
2020-11-01〜2020-12-01
...
2026-05-01〜2026-05-13
```

クエリ:

```text
from:ronpochi since:YYYY-MM-DD until:YYYY-MM-DD
```

---

### Step 5: SearchTimeline workerを1本だけ動かす
条件:

```text
remaining > 1 のときだけ実行
429なら reset まで停止
ページ間隔 10〜30秒 jitter
同じcursor再試行は最大1回
```

---

### Step 6: 1ページごとに即SQLite保存
tweet保存は必ず冪等にする。

```sql
INSERT OR IGNORE INTO tweets (...)
```

cursorとjob状態も同じトランザクションで保存。

```text
tweets保存
raw_json保存
job.cursor更新
job.page_count更新
rate_limit更新
COMMIT
```

これで中断再開できる。

---

### Step 7: 月別欠落レポートを出す
ronpochiから先に検証。

```text
2019-10〜2020-09: UTAR由来
2020-10〜現在: SearchTimeline由来
```

ゼロ月・極端に少ない月があれば、日単位に再分割。

---

## CryptoHayesについて

CryptoHayesはこのままUTARを完走でよいです。

ただし完了判定は以下で分ける。

```text
UTAR cursor exhausted
DB件数
非RT件数
RT件数
プロフィール件数との差分
```

プロフィール2,563に対してDB2,105なら、残り458件。  
大半がRTなら実質取得率はかなり高い可能性あり。

次にやる確認SQL:

```sql
SELECT
  account,
  COUNT(*) AS total,
  SUM(CASE WHEN is_retweet = 1 THEN 1 ELSE 0 END) AS retweets,
  SUM(CASE WHEN is_reply = 1 THEN 1 ELSE 0 END) AS replies,
  SUM(CASE WHEN is_quote = 1 THEN 1 ELSE 0 END) AS quotes
FROM tweets
WHERE account = 'CryptoHayes'
GROUP BY account;
```

---

## 結論

SearchTimelineの429は「突破」ではなく「枠を浪費しない設計」に変えるべきです。

優先順位はこれです。

1. SearchTimeline停止、resetまで待つ  
2. rate limitヘッダをSQLiteに保存  
3. search_jobsで期間分割、cursor保存  
4. ronpochi 2020-10以降を月次SearchTimelineで取得  
5. 429時は完全停止、再開はDB状態から  
6. 月別件数で取得漏れ検証  
7. 重い月は週/日単位に自動分割  

今の状態でSearchTimelineを手動テスト連発すると、さらに数日単位で遅れます。まず rate limit 管理と job/cursor 永続化を入れてから再開してください。
方針は概ね賛成。  
ただし「Playwrightスクロールが最速」ではなく、**まず実測で SearchTimeline の実効 rate limit を特定し、その上で Playwright + response capture を本線にする**のが妥当。

結論としては、今詰まっている原因はおそらく以下の複合です。

---

## 1. 429の原因について

### あり得る原因

#### A. SearchTimeline の実効 limit が 50req/15min ではない
十分あり得る。  
X GraphQL は endpoint / operation / auth状態 / account / IP / query内容 で制限が違う可能性がある。

`SearchTimeline` だけ実効 10req/15min 程度でも不思議ではない。

#### B. 公式Webクライアントの自動リクエストで消費している
これもあり得る。

検索ページを開くと、SearchTimeline以外にも以下が飛ぶ可能性がある。

- SearchTimeline 初回ロード
- Top / Latest 切替や補助クエリ
- Typeahead / recommendations
- HomeTimeline系
- UserByScreenName
- Notifications / badge
- analytics系
- prefetch

特にページリロードや新規context作成を繰り返すと、想定以上に消費する。

#### C. classic rate limit ではなく abuse / temporary block
`x-rate-limit-reset` まで待っても429が継続する場合、単純な15分枠ではなく、

- IP単位制限
- account単位制限
- query単位制限
- bot判定
- search backend側の一時制限

の可能性がある。

なので、**429レスポンスの headers と body を保存して分類する必要がある。**

---

## 2. 月単位分割について

月単位67ジョブ固定は、今の状況だと遅いし硬すぎる。

前回の月単位案は「漏れ検証しやすい分割」の意味では有効だが、429が強いなら最初から67ヶ月を機械的に回すのは悪手。

おすすめはこれ。

### 改善案: 動的window分割

1. まず大きめの期間で検索する  
   例: 6ヶ月単位 or 1年単位

2. 取得件数が多い / cursorが深い / 途中で429になる window だけ分割  
   例: 1年 → 3ヶ月 → 1ヶ月 → 1週間

3. 取得件数が少ないwindowは大きいまま処理

つまり、

```text
2020-10〜2021-10
2021-10〜2022-10
...
```

から始めて、密度が高い期間だけ細かくする。

月単位固定より速く、漏れ検証もしやすい。

---

## 3. Playwrightスクロール + response捕捉について

これは現状では本線にしてよい。

ただし、DOMから取るのではなく、あなたの案通り、

> 検索ページを開きっぱなしにして、スクロールで発生する GraphQL response を捕捉してSQLite保存

が正しい。

DOM仮想リストの問題は response capture なら回避できる。

---

## 4. ただし「公式クライアントがrate limitを自動管理」は過信しない

公式Webクライアントは確かに人間っぽいペースで追加ロードするが、rate limitを完全に最適化してくれるわけではない。

実際には、

- 429が出たらUI上では単に追加ロードが止まる
- 内部で再試行してさらに消費する場合がある
- prefetchで余計なGraphQLを打つ場合がある

なので、こちら側で network response を監視して、429時にスクロール停止・reset待機する制御が必要。

---

## 次の実装手順

### Step 1: Playwrightでrate limit実測

検索ページを1つだけ開く。

```text
https://x.com/search?q=from%3Aronpochi%20since%3A2020-10-01%20until%3A2020-11-01&src=typed_query&f=live
```

Playwrightで全responseを監視し、URLに以下を含むものだけ記録。

```text
/i/api/graphql/
/SearchTimeline/
```

保存する項目:

```sql
timestamp
url
operation_name
status
x-rate-limit-limit
x-rate-limit-remaining
x-rate-limit-reset
response_body_hash
response_body_json
cursor_bottom
tweet_count
```

429も必ずbodyごと保存。

---

### Step 2: スクロール制御

最初はかなり遅くする。

例:

```text
1スクロール
↓
5〜10秒待つ
↓
SearchTimeline responseを確認
↓
remainingが減っていれば記録
↓
429ならresetまで停止
```

いきなり連続スクロールしない。

実験目的は速度ではなく、まず実効limit特定。

---

### Step 3: 429時の処理

429を見たら即停止。

`x-rate-limit-reset` がある場合:

```text
sleep(reset_epoch - now + 30秒)
```

ない場合:

```text
15分停止
それでも429なら30分
それでも429なら1〜2時間
```

この結果で classic rate limit か abuse block か判定する。

---

### Step 4: SQLite保存を先に完成させる

スクロール実装より先に、保存層を固めるべき。

最低限この3テーブル。

#### tweets

```sql
CREATE TABLE IF NOT EXISTS tweets (
  tweet_id TEXT PRIMARY KEY,
  user_id TEXT,
  screen_name TEXT,
  created_at TEXT,
  full_text TEXT,
  raw_json TEXT NOT NULL,
  first_seen_at TEXT DEFAULT CURRENT_TIMESTAMP
);
```

#### requests

```sql
CREATE TABLE IF NOT EXISTS requests (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  job_id INTEGER,
  timestamp TEXT DEFAULT CURRENT_TIMESTAMP,
  operation_name TEXT,
  url TEXT,
  status INTEGER,
  rate_limit_limit INTEGER,
  rate_limit_remaining INTEGER,
  rate_limit_reset INTEGER,
  cursor_bottom TEXT,
  tweet_count INTEGER,
  raw_response TEXT
);
```

#### jobs

```sql
CREATE TABLE IF NOT EXISTS jobs (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  query TEXT NOT NULL,
  since_date TEXT,
  until_date TEXT,
  status TEXT DEFAULT 'pending',
  last_cursor TEXT,
  last_tweet_id TEXT,
  last_error TEXT,
  updated_at TEXT DEFAULT CURRENT_TIMESTAMP
);
```

重要なのは、**responseを受け取った瞬間にSQLiteへ保存すること。**  
後でパース失敗してもraw_jsonから復旧できるようにする。

---

### Step 5: 中断再開

中断再開は cursor ベースと window ベースの両方を持つ。

- window: `since/until`
- cursor: SearchTimelineのbottom cursor
- dedupe: tweet_id primary key

再開時は、

1. 未完了jobを読む
2. 同じ検索URLを開く
3. 可能ならlast_cursor相当まで進める
4. 既存tweet_idはINSERT OR IGNORE
5. 取得済み重複が続いたら次cursorへ進む

SearchTimelineはcursor直接指定URLが使いづらい可能性があるので、完全なcursor resumeは難しい。  
その場合でも、window単位で再走してdedupeする設計にしておけば復旧可能。

---

## 取得漏れ検証

漏れ検証は必須。

### 検証方法

#### 1. window境界を1日重複させる

例:

```text
2020-10-01〜2020-11-01
2020-10-31〜2020-12-01
```

境界日のツイートが両方に出るか確認する。

#### 2. tweet_id重複率を見る

重複がゼロすぎる場合、境界漏れの可能性がある。  
適度なoverlapを入れて、重複が発生することを確認する。

#### 3. created_atの時系列連続性を見る

各window内で、

```text
最新 → 過去
```

に進んでいるか確認。

極端な日付ジャンプがあれば、そのwindowを細分化。

#### 4. 同じwindowを2回走らせる

サンプルで同じ期間を再取得して差分を見る。

```text
1回目: 120件
2回目: 123件
差分: 3件
```

のようならSearchTimelineが不安定なので、その期間は再走・細分化する。

---

## 追加の重要指摘

ronpochi個人の過去ツイート取得が目的なら、SearchTimelineだけでなく、プロフィール側のGraphQLも比較すべき。

候補:

```text
UserTweets
UserTweetsAndReplies
```

検索より profile timeline の方が、

- query負荷が軽い
- cursor構造が素直
- 検索インデックス漏れの影響が少ない
- rate limitが別枠の可能性がある

ので、`from:ronpochi` 検索より安定する可能性がある。

次にやるべき実験は、

```text
SearchTimeline
UserTweets
UserTweetsAndReplies
```

の3つで headers を比較すること。

---

## 最終判断

あなたの提案は正しい。

ただし実装方針はこうするべき。

```text
DOMスクレイピングではなく、
Playwrightで公式検索/プロフィールページを開き、
GraphQL responseを捕捉し、
SQLiteに即保存し、
rate limit headerを実測しながら、
429時はresetまで停止する。
```

月単位67ジョブ固定は後回し。  
まずは1ページ開きっぱなしの状態で、

```text
実効limit
remainingの減り方
reset挙動
429継続時間
SearchTimelineとUserTweetsの差
```

を測る。

その結果を見て、window分割幅とスクロール間隔を決めるのが次の一手。
1. **概算は正しいが理論値**
   - 49回 × 約20件 = **980件/15分**
   - 10万件 ÷ 980 × 15分 ≒ **25.5時間**
   - ただし実際は重複・削除済み・空レス・エラー・cursor打ち切りがあるので、**30〜50時間程度を見込むべき**。
   - 初回ページロード分も保存できるなら、最大は **50req × 約20件 = 1000件/15分**。

2. **開きっぱなしのprefetchリスクはある**
   - X Webは以下でSearchTimelineを勝手に消費する可能性あり。
     - ページ初回表示
     - 下端に近づいた時の先読み
     - タブ復帰・focus
     - reload / reconnect
     - UI操作による再検索
   - 対策:
     - Playwrightで**全GraphQLレスポンスを必ず監視・保存**
     - `SearchTimeline`のrequest数をSQLiteに記録
     - rate limit残数・reset時刻をレスポンスヘッダから保存
     - 1ブラウザ1検索タブに固定
     - 勝手に発生したSearchTimelineも「消費済み」として扱う

3. **広すぎるsinceはcursor打ち切りリスクあり。期間分割すべき**
   - `since:2020-10-01` のように広い範囲だと、X側が全件をcursorで返し切らず、途中で止まる可能性がある。
   - 特に検索結果が多いクエリでは危険。
   - 推奨:
     - `since:YYYY-MM-DD until:YYYY-MM-DD` で**日単位または時間単位に分割**
     - 件数が多い日はさらに **6時間 / 1時間単位**へ分割
     - 各windowごとにcursor最終到達まで取得
     - SQLiteに `query_window`, `cursor`, `last_tweet_id`, `done` を保存して中断再開
     - 境界漏れ防止に前後数分〜1時間のoverlapを入れ、tweet_idで重複排除

結論:  
**25時間は理論上正しいが、実装は「期間分割 + GraphQL全保存 + rate limit管理 + SQLite中断再開」が必須。**
1. **検索除外アカウントの全件取得方法**
   - `SearchTimeline` / `from:... since:...` は使えません。検索除外ならDOMにもAPIにも出ません。
   - 取得経路は基本的に以下だけです。
     - プロフィールのGraphQL Timeline  
       `UserTweets` / `UserTweetsAndReplies`
     - Playwrightでプロフィール/with_repliesを開いて、同じGraphQL responseを捕捉
     - 本人提供のXデータアーカイブ
     - 契約API/データ提供系
   - 公開プロフィール経由で遡れる範囲が実質上限です。検索で補完は不可です。

2. **UserTweetsAndRepliesが途中で止まった場合、別cursor開始は可能か**
   - 任意日時・任意tweet_idから開始するcursor指定は基本不可です。
   - cursorはGraphQLが返す不透明トークンなので、できるのは：
     - 最初から開始
     - 直前に保存した`bottom cursor`から再開
   - 途中で2019-10〜2020-09だけ取れて止まるなら、疑うべきは：
     - `bottom cursor`ではなく`top cursor`を使っている
     - `TimelineAddEntries`以外、`TimelineReplaceEntry`や`TimelinePinEntry`を処理していない
     - `cursorType: Bottom`抽出漏れ
     - rate limit / 429 / empty responseを終端扱いしている
     - `UserTweets`と`UserTweetsAndReplies`を混同
     - `rest_id`違い、旧ハンドル/別ユーザー参照

3. **Playwrightでプロフィール(with_replies)をスクロールし続けてresponse captureする方式は有効か**
   - 有効です。DOMではなくGraphQL responseを保存してください。
   - ただし、内部的には同じTimeline APIなので、rate limit・cursor打ち切り・ログイン状態の影響は受けます。
   - 実装方針：
     1. Playwrightでログイン済みcontextを使用
     2. `https://x.com/{screen_name}/with_replies` を開く
     3. `page.on("response")`で`UserTweets` / `UserTweetsAndReplies`を含むGraphQLレスポンスを捕捉
     4. raw JSONをSQLiteへ保存
     5. tweet_idでdedupe保存
     6. `Bottom cursor`も保存
     7. スクロール継続
     8. 新規tweet_idがN回連続で増えない、または同一cursor反復で停止
     9. 429/空レスポンス時は停止ではなくbackoff

次の実装手順はこれです。

```text
1. Search取得処理はronpochi用には捨てる
2. Playwright response captureを主取得経路にする
3. GraphQL raw response、tweet、cursorをSQLite保存
4. Bottom cursor単位で中断再開できるようにする
5. 429/失敗/空レスポンスを終端扱いしない
6. tweet_id件数、最古日時、cursor遷移、重複率で取得漏れ検証する
```

結論：  
検索除外なら検索APIでは無理です。プロフィールTimeline GraphQLをPlaywrightで捕捉し、cursorとraw responseを保存しながら遡る方式が現実的です。
原因特定は「抽出0件」と「通信0件」を分けて潰してください。

## 1. 5 responsesの中身を先に可視化する

`INSERT OR IGNORE` の結果ではなく、GraphQLレスポンスから抽出できた tweet_id 自体をログに出す。

見る項目:

```txt
response_no
status
url operationName
request cursor
response body hash
tweet_id count
unique tweet_id count
min created_at
max created_at
bottom cursor 有無
DB既存数
DB未登録数
```

判定:

- `unique tweet_id > 0` かつ `DB未登録数 = 0`
  - 単に全件既存。抽出は正常。
- `unique tweet_id = 0`
  - extractTweetsがまだ壊れている。
- `bottom cursor なし`
  - そのレスポンスはページネーション継続不能。
- `bottom cursor あり` なのにスクロールで次リクエストなし
  - UIスクロール/Playwright側の問題。

---

## 2. responseではなくrequestも記録する

スクロール後に本当にGraphQL requestが出ているかを見る。

```js
page.on('request', req => {
  if (req.url().includes('UserTweetsAndReplies')) {
    const post = req.postDataJSON?.();
    console.log('[REQ]', {
      url: req.url(),
      cursor: post?.variables?.cursor,
      count: post?.variables?.count,
    });
  }
});

page.on('response', async res => {
  if (res.url().includes('UserTweetsAndReplies')) {
    console.log('[RES]', res.status(), res.url());
  }
});
```

重要なのは `variables.cursor`。

- 初回だけ `cursor: undefined/null`
- 次ページは `cursor: "..."`
- スクロール後も cursor付きrequestが出ないなら、ページネーション未発火。

---

## 3. DOM上の記事数とスクロール位置を記録する

スクロールが効いているか確認。

```js
async function dumpDomState(label) {
  const s = await page.evaluate(() => ({
    scrollTop: document.scrollingElement.scrollTop,
    scrollHeight: document.scrollingElement.scrollHeight,
    clientHeight: document.scrollingElement.clientHeight,
    articleCount: document.querySelectorAll('article').length,
    firstText: document.querySelector('article')?.innerText?.slice(0, 100),
    lastText: [...document.querySelectorAll('article')].at(-1)?.innerText?.slice(0, 100),
  }));
  console.log(label, s);
}
```

スクロール前後で見る。

```js
await dumpDomState('before');

for (let i = 0; i < 20; i++) {
  await page.mouse.wheel(0, 3000);
  await page.waitForTimeout(1500);
  await dumpDomState(`scroll ${i}`);
}
```

判定:

- `scrollTop` が増えない  
  → スクロール対象が違う、またはページが固定されている。
- `scrollTop` は増えるが `articleCount/lastText` が変わらない  
  → UIロードが発火していない。
- `articleCount/lastText` が変わるが GraphQL requestなし  
  → 初期レスポンス内のデータだけを仮想DOMで表示している可能性。
- DOMは増えるが extract 0  
  → GraphQL抽出ではなくDOM抽出も併用検討。

---

## 4. 5 responses内のtweet_idと日付範囲を直接出す

`extractTweets` の結果ではなく、生JSONから `rest_id` と `legacy.created_at` を再帰的に拾って確認する。

```js
function collectTweets(obj, out = []) {
  if (!obj || typeof obj !== 'object') return out;

  if (
    obj.__typename === 'Tweet' &&
    obj.rest_id &&
    obj.legacy?.created_at
  ) {
    out.push({
      id: obj.rest_id,
      created_at: obj.legacy.created_at,
      full_text: obj.legacy.full_text?.slice(0, 80),
      user_id: obj.core?.user_results?.result?.rest_id,
      screen_name: obj.core?.user_results?.result?.legacy?.screen_name,
    });
  }

  for (const v of Object.values(obj)) {
    if (v && typeof v === 'object') collectTweets(v, out);
  }

  return out;
}
```

ログ:

```js
const tweets = collectTweets(json);
const ids = [...new Set(tweets.map(t => t.id))];

console.log({
  total: tweets.length,
  unique: ids.length,
  minDate: tweets.map(t => new Date(t.created_at)).sort()[0],
  maxDate: tweets.map(t => new Date(t.created_at)).sort().at(-1),
  sample: tweets.slice(0, 5),
});
```

これで仮説3「oembed分13,403件が全部含まれている」はほぼ否定できます。初期GraphQL 5件に13,403 tweet全部が入ることは通常ありません。

---

## 5. DB重複の確認

`INSERT OR IGNORE` の前に必ず差分を見る。

```sql
SELECT COUNT(*) FROM tweets WHERE tweet_id IN (...);
```

またはJS側で:

```js
const existing = await getExistingTweetIds(ids);
console.log({
  responseUnique: ids.length,
  existing: existing.length,
  newIds: ids.filter(id => !existing.has(id)).length,
});
```

`new 0` だけでは原因不明です。

---

## 6. 一番有力な原因

現状だと一番怪しいのはこれです。

> 初回5 responsesには既存tweetしか含まれており、スクロールによる cursor付き `UserTweetsAndReplies` request が発火していない。

つまり問題は `extractTweets` よりも pagination 未発火側。

---

## 7. 次の実装手順

1. `UserTweetsAndReplies` の request/response を全ログ化する。  
   特に `variables.cursor`、tweet_id数、日付範囲、bottom cursor。

2. DOM状態をスクロールごとに出す。  
   `scrollTop`, `scrollHeight`, `articleCount`, `lastText`。

3. 5 responsesから bottom cursor を抽出する。

4. UIスクロールで次requestが出ない場合、Playwright内で直接GraphQL POSTする方式に切り替える。  
   つまり、ブラウザセッションのcookie/authを使って、captured requestの `variables.cursor` だけ差し替えて次ページ取得。

5. SQLiteには以下を保存する。
   - `tweet_id`
   - `created_at`
   - `raw_json`
   - `source = graphql`
   - `cursor`
   - `fetched_at`

6. 中断再開用に `crawl_state` テーブルを作る。
   - `user_id`
   - `screen_name`
   - `last_cursor`
   - `last_tweet_created_at`
   - `updated_at`

7. rate limit対策として、1 cursorごとに `2〜5秒 sleep`、429/403時は停止して `last_cursor` 保存。

まずは「5 responses内の unique tweet_id 数・日付範囲・bottom cursor」と「スクロール後の cursor付きrequest有無」を出せば原因は確定できます。
問題あり。特に ronpochi の進め方が非効率すぎます。

### 指摘

1. **ronpochi の Playwright スクロール継続は危険**
   - `50 responses / 17新規` はほぼ重複巡回。
   - このまま DOM スクロールで 11.5万件を狙うのは現実的でない。
   - SearchTimeline 不可でも、**プロフィールの GraphQL `UserTweets` / `UserTweetsAndReplies` の cursor 抽出**は試すべき。

2. **「プロフィール件数 = 取得目標件数」と見なすのは危険**
   - X の表示件数は削除済み、非公開化、RT、返信、制限表示、凍結期間などを含みうる。
   - `CryptoHayes 106%` はその兆候。重複キー、RT/返信混入、プロフィール件数の意味を再確認。

3. **ronpochi の oldest: 2026-03-26 は浅すぎる**
   - まだ直近を回っているだけ。
   - 既存 DB がどの期間を持っているか見て、**未取得期間に直接降りる戦略**が必要。

4. **UTAR完了の定義が不明**
   - cursor が尽きたのか、rate limit で止まったのか、取得率で打ち切ったのかを保存すべき。
   - 「完了」は `bottom cursorなし` または `既知最古日到達 + gap検証済み` で判定。

---

### 次の実装手順

1. **ronpochi はスクロール停止**
   - まず 200〜300 response だけ追加で保存して、GraphQL operation 名を確認。
   - `UserTweets`, `UserTweetsAndReplies`, `ProfileTimeline` 系 response から `bottom cursor` を抽出。

2. **Playwrightは認証取得専用に寄せる**
   - browser でログイン済み cookie / bearer / csrf / x-client-transaction-id を取得。
   - 以後は Node/Python の HTTP で GraphQL を直接叩く。
   - Playwright DOM スクロールは最終手段。

3. **SQLite に cursor 状態を保存**
   - `account`, `endpoint`, `cursor`, `oldest_tweet_id`, `oldest_created_at`, `new_count`, `dup_count`, `status`, `updated_at`
   - 中断再開はこの cursor から再開。

4. **取得漏れ検証を入れる**
   - account ごとに `created_at` を日単位または週単位で集計。
   - 件数が急に 0 になる期間、tweet_id の大きな断絶を検出。
   - UTAR完了アカウントも gap チェックする。

5. **rate limit 処理**
   - endpoint/account 単位で 429 を記録。
   - `x-rate-limit-reset` が取れるならそこまで sleep。
   - 取れない場合は指数バックオフ。
   - 429中に同 endpoint を叩き続けない。

6. **ronpochi 用の方針**
   - SearchTimeline不可でも、プロフィール GraphQL cursor が取れるならそれでバックフィル。
   - cursor が取れない場合のみ Playwright スクロール継続。
   - ただしその場合も response 全保存、cursor候補抽出、重複率90%以上なら停止。

結論：今の最大の詰まりは **ronpochi を DOM スクロールで総当たりしていること**。まず GraphQL cursor 化と SQLite cursor 再開管理に切り替えるべきです。
結論：**Premium/Premium+加入で取得率23%が大きく改善する可能性は低い**です。

1. **GraphQL rate limit緩和**
   - 公式には **Premium/Premium+でWeb GraphQLのrate limitが緩和される保証なし**。
   - GraphQL制限は非公開で、アカウント状態・IP・セッション・行動量依存。

2. **X API Basicが付くか**
   - **付かない**。
   - X Premium/Premium+ と X API Basic は別契約。
   - API BasicはDeveloper Platform側で別途課金が必要。

3. **UserTweetsAndRepliesのcursor打ち切り緩和**
   - **期待薄**。
   - 166ページ程度で止まるのはrate limitより、Timeline側の取得窓・ランキング・可視性制限・古い投稿の打ち切りの可能性が高い。
   - Premium加入で解除される根拠なし。

4. **検索除外アカウントが検索可能になるか**
   - **基本ならない**。
   - SearchTimelineで除外される状態は、検索インデックス・可視性制御側の問題。
   - Premiumで検索除外が解除される保証なし。

5. **サブスクで有利になる点**
   - 可能性があるのは限定的：
     - Web閲覧上限が多少有利になる可能性
     - CAPTCHA/一時制限が減る可能性
     - アカウント信頼度が少し上がる可能性
   - ただし **GraphQL全件取得・cursor延長・検索除外解除には直結しない**。

次の実装方針：

- Premium購入より先に、**取得漏れ検証と再開可能なSQLite保存**を整備。
- `UserTweetsAndReplies`で取れる範囲を保存。
- cursor終了位置、最古tweet日時、取得件数をアカウント別に記録。
- 取得漏れは以下で補完：
  - 個別tweet ID周辺の会話取得
  - 日付範囲を分けた検索
  - 別セッション/別IP/低速Playwright再試行
  - SearchTimeline不可アカウントはGraphQL timeline依存で割り切り
- Premiumは検証するなら **1アカウントだけ短期加入してA/B比較**。  
  期待値は低い。
結論：Claudeが詰まった主因は、**UserTweetsAndReplies 1本で過去全件を取れる前提が崩れている**ことです。  
XのWeb GraphQLタイムラインは、cursorがあっても過去方向に無限取得できず、だいたい一定ページで打ち切られる挙動があります。  
今後は **「タイムラインを深掘り」ではなく「複数経路で tweet_id を発見し、SQLiteで重複排除しながら蓄積」** に切り替えるべきです。

---

## 1. 現実的にやる価値が高いもの

### A. SearchTimeline の日付分割取得

対象：ronpochi以外の6アカウント。

これは最優先です。

`from:user since:YYYY-MM-DD until:YYYY-MM-DD` のように期間を細かく区切り、各期間で SearchTimeline を最後までページングします。

理由：

- UserTweetsAndReplies の166〜170ページ上限を回避できる可能性が高い
- SearchTimelineはrate limitがあるが、待てば進む
- 年/月/週/日単位で分割すれば、1クエリあたりの上限にも引っかかりにくい
- 取得漏れ検証がしやすい

方針：

- 最初は月単位
- 1期間で上限到達っぽい場合は週単位へ分割
- さらに多い期間は日単位へ分割
- `from:account since:... until:...`
- 必要なら `filter:replies` あり/なし、`exclude:retweets` あり/なしを分ける

注意：

- ronpochiは検索除外ならこの方法は使えない
- 50req/15minは守る
- rate limitをSQLiteに保存して中断再開する

---

### B. Playwrightで「DOMスクロール」ではなく「GraphQLレスポンス捕捉」

今のPlaywrightスクロールは遅い理由が明確です。

- DOM上に表示される投稿が少ない
- 仮想スクロールで古い要素が消える
- 同じレスポンスを何度も処理している
- UI操作起点なので重複が多い

改善案：

- PlaywrightでXにログイン済み状態を使う
- `page.on("response")` でGraphQLレスポンスを捕捉
- `SearchTimeline`, `UserTweets`, `UserTweetsAndReplies`, `TweetDetail`, `UserMedia` などのJSONだけ保存
- DOMからtweetを読むのは最後の手段にする

つまり、**ブラウザに正規UI操作をさせ、ネットワークJSONを取る**形です。  
Node fetchで直接GraphQLを叩くより成功率が高いです。

---

### C. UserTweets / UserMedia / UserHighlightsTweets など別GraphQL endpoint

やる価値ありです。

既に試したのは `UserTweetsAndReplies` なので、以下は別途試す価値があります。

| endpoint | 期待値 |
|---|---|
| UserTweets | repliesなしの通常投稿。AndRepliesと重複多いが差分が出る可能性あり |
| UserMedia | 画像・動画付き投稿。全件ではないが追加取得源になる |
| UserHighlightsTweets | ハイライトのみ。件数は少ない |
| Likes | 対象ユーザーの投稿取得には基本不要 |
| TweetDetail | 会話・スレッド芋づる用 |

ただし、これらもWeb GraphQLなので、過去全件保証はありません。

---

### D. TweetDetailからの芋づる取得

やる価値あり。特に「返信」「スレッド」が多いアカウントには効きます。

使い方：

1. 既に取得済みtweetの `conversation_id` / `in_reply_to_status_id` / URLを保存
2. `TweetDetail` を開く
3. 会話内にある対象ユーザーの未取得tweetを拾う
4. 新しいtweet_idが見つかったらSQLiteに保存

期待できるもの：

- スレッド内の未取得投稿
- 会話ツリーに残っている返信
- SearchTimelineやUserTweetsから漏れた投稿

限界：

- tweet_idの発見源が必要
- 全履歴の網羅にはならない
- 会話が巨大だとまたページング制限に当たる

---

### E. 公式データダウンロード機能

対象アカウント本人が協力できるなら最強です。

- Xの「アーカイブをダウンロード」
- 本人のみ可能
- ほぼ全投稿が含まれる可能性が高い
- retweet/reply/media情報も取れる場合あり

ronpochiが本人協力可能なら、これが一番現実的です。

---

### F. 既存ツール gallery-dl / snscrape系

試す価値はありますが、過期待は禁物です。

| ツール | 評価 |
|---|---|
| gallery-dl | X対応はあるが、内部的にはWeb/API依存。画像・動画取得には有用 |
| yt-dlp | 基本的に動画向け。tweet全件取得には不向き |
| snscrape | X側変更で壊れていることが多い |
| twint | ほぼ古い。現状では期待薄 |

やるなら：

- 1アカウントだけ小さく検証
- 取得tweet_idだけSQLiteに入れる
- 既存実装より新規が増えるか確認

---

## 2. 補助的に使えるもの

### G. Syndication API

`cdn.syndication.twimg.com/tweet-result?id=...`

これは **tweet_idが既に分かっている場合のhydrate用** です。

できること：

- IDからtweet本文・ユーザー・メディア情報を取れることがある
- ログインなしでも取れる場合がある
- 削除済み・非公開・制限投稿は無理

できないこと：

- ユーザーの過去投稿一覧取得
- cursor pagination
- tweet_idの発見

つまり、**発見済みIDの補完用**です。

---

### H. Google/Bing/Internet Archive等の外部インデックス

追加発見源としてはありです。

検索例：

- `site:x.com/account/status account`
- `site:twitter.com/account/status account`
- Internet Archive CDX APIで `twitter.com/account/status/*`

期待できるもの：

- 古いtweet URL
- 外部サイトに引用されたtweet
- 一部のstatus ID

限界：

- 網羅性は低い
- 本文までは残っていないことが多い
- Google Cacheはほぼ期待できない
- Internet Archiveもアカウントによる差が大きい

用途：

- tweet_idを発見
- Syndication API / TweetDetail / Playwrightでhydrate
- SQLiteにsource=`external_index`として保存

---

### I. フォロワーや他ユーザーのリプライから発見

理屈上は可能です。

例：

- `to:target`
- `"@target" since:... until:...`
- 対象ユーザーへの返信を検索
- そのconversationをTweetDetailで開く
- 対象ユーザー本人の投稿を拾う

ただし効率は低いです。

使えるケース：

- 対象ユーザーが会話中心
- 元tweetがSearchTimelineから漏れている
- 他人の返信経由でconversation_idが見つかる

限界：

- SearchTimeline依存
- ronpochiが検索除外なら厳しい
- 対象本人の全投稿発見にはならない

---

## 3. 期待薄・やらなくてよいもの

### J. TweetDeck / X Pro API

正直、私は最新のX Pro内部APIを実運用で検証していません。  
ただし、現実的には大きな期待はしない方がいいです。

理由：

- 現在のX ProもWeb GraphQL/内部API依存の可能性が高い
- 過去全件取得APIではない
- 検索やカラム表示もrate limitや検索制限の影響を受ける
- サブスクで取得上限が根本的に増えるとは限らない

補助的にUI差分を見る程度ならありですが、主戦力にはしない方がよいです。

---

### K. X Spaces / Communities API

通常投稿の過去取得にはほぼ関係ありません。

- Spacesは音声イベント
- Communitiesはコミュニティ内投稿
- 対象アカウントの通常timeline全件取得には使えない

優先度は低いです。

---

### L. UserTweetsAndRepliesのcursor手動操作

ほぼ無理です。

理由：

- cursorは不透明な内部トークン
- 日付やtweet_idから任意位置へジャンプする設計ではない
- 改ざんしても失敗する可能性が高い
- 成功しても再現性が低い

やるべきこと：

- cursorを手動生成するのではなく、取得したcursorをSQLiteに保存
- 中断再開に使う
- 過去方向ジャンプはSearchTimelineの日付分割で代替する

---

### M. 複数ブラウザセッション並列化

慎重に扱うべきです。

同じログインアカウントで並列化しても、rate limitは共有される可能性が高いです。  
むしろ以下の問題が出ます。

- 429増加
- セッションロック
- 一時制限
- 重複増加
- 状態管理が複雑化

やるなら：

- 取得対象アカウント単位で低並列
- SQLiteで完全重複排除
- rate limitを共有管理
- まずは1ブラウザ1ワーカーで安定化

---

## 4. 避けた方がよいもの

### N. 別IP / VPN / プロキシでの回避

推奨しません。

理由：

- rate limit回避目的に見える
- アカウント制限リスクが高い
- 結果が不安定
- 再現性がない
- セキュリティ・規約面の問題がある

GCPインフラがあっても、IPを増やして突破する方向ではなく、**rate limitを保存して待つ設計**にすべきです。

---

### O. モバイルアプリAPI Android/iOS

これも推奨しません。

理由：

- リバースエンジニアリング寄りになる
- 認証・署名・証明書・バージョン依存が強い
- 短期的に動いても保守不能になりやすい
- アカウント制限リスクが高い

「やったことない/わからない」部分もありますが、少なくとも今回の目的には主戦力にしない方がよいです。

---

### P. Node.js fetchでGraphQL直接実行を深追い

現状、TLS fingerprintやブラウザ文脈差で404になっているなら、ここを深追いしない方がよいです。

代替：

- Playwrightで正規ページを開く
- UI操作でX自身にGraphQLを発火させる
- `page.on("response")` でJSONだけ捕捉する

この方が安定します。

---

## 5. 優先順位まとめ

### 最優先

1. SearchTimelineの日付分割取得  
2. PlaywrightでGraphQLレスポンス捕捉  
3. SQLiteでtweet_id重複排除・cursor・rate limit保存  
4. UserTweets / UserMedia / TweetDetail追加  
5. 取得漏れ検証用の月別ヒストグラム作成  

### 次点

6. gallery-dl等の既存ツール検証  
7. Internet Archive / 外部検索からtweet_id発見  
8. Syndication APIで発見済みIDをhydrate  
9. フォロワー返信・conversation経由の芋づる  

### 条件付きで有効

10. 本人の公式Xアーカイブ取得  
11. X Pro/TweetDeck差分調査  

### 非推奨

12. VPN/プロキシ  
13. モバイルアプリAPI  
14. cursor改ざん  
15. Node fetch直叩きの深追い  

---

## 6. SQLite設計案

最低限この4テーブルを作るべきです。

### tweets

```sql
CREATE TABLE IF NOT EXISTS tweets (
  tweet_id TEXT PRIMARY KEY,
  user_screen_name TEXT,
  user_id TEXT,
  created_at TEXT,
  text TEXT,
  conversation_id TEXT,
  in_reply_to_status_id TEXT,
  is_retweet INTEGER,
  is_quote INTEGER,
  source TEXT,
  raw_json TEXT,
  first_seen_at TEXT,
  last_seen_at TEXT
);
```

### crawl_jobs

```sql
CREATE TABLE IF NOT EXISTS crawl_jobs (
  job_id TEXT PRIMARY KEY,
  account TEXT,
  method TEXT,
  query TEXT,
  since_date TEXT,
  until_date TEXT,
  cursor TEXT,
  status TEXT,
  new_count INTEGER DEFAULT 0,
  total_count INTEGER DEFAULT 0,
  retry_count INTEGER DEFAULT 0,
  next_run_at TEXT,
  updated_at TEXT
);
```

### rate_limits

```sql
CREATE TABLE IF NOT EXISTS rate_limits (
  key TEXT PRIMARY KEY,
  remaining INTEGER,
  reset_at TEXT,
  updated_at TEXT
);
```

### discovered_ids

```sql
CREATE TABLE IF NOT EXISTS discovered_ids (
  tweet_id TEXT PRIMARY KEY,
  source TEXT,
  discovered_at TEXT,
  hydrated INTEGER DEFAULT 0
);
```

---

## 7. 取得漏れ検証

やるべき検証は3つです。

### 1. 月別件数ヒストグラム

```sql
SELECT
  user_screen_name,
  substr(created_at, 1, 7) AS ym,
  COUNT(*) AS count
FROM tweets
GROUP BY user_screen_name, ym
ORDER BY user_screen_name, ym;
```

これで急に0件になる月、異常に少ない月を見つける。

---

### 2. Search日付窓の完了管理

各 `from:user since:X until:Y` について、

- 最後までcursorを辿ったか
- rate limitで止まっただけか
- 上限到達っぽいか
- 新規件数が何件か

を `crawl_jobs` に残す。

---

### 3. 重複率の監視

PlaywrightスクロールやTweetDetail芋づるは重複が多いので、

- response件数
- parse件数
- 新規tweet_id件数
- 重複率

をログに出す。

例：

```text
account=ronpochi method=playwright_scroll responses=52 parsed=1800 new=17 duplicate_rate=99.0%
```

新規率が低い方法は停止する。

---

## 8. 次の実装手順

短く言うと、次です。

1. SQLiteに `tweets`, `crawl_jobs`, `rate_limits`, `discovered_ids` を作る  
2. PlaywrightでSearchTimelineを開き、GraphQLレスポンスをJSON保存する  
3. ronpochi以外を `from:user since:YYYY-MM-DD until:YYYY-MM-DD` で月単位取得  
4. 1ヶ月で上限到達した期間だけ週単位・日単位に分割  
5. 429/rate limitは `reset_at` を保存して自動再開  
6. UserTweets / UserMedia / TweetDetailも同じ保存パイプラインに流す  
7. ronpochiはSearchが使えないので、UserMedia、TweetDetail芋づる、外部ID発見、本人アーカイブを優先  
8. 月別ヒストグラムで取得漏れを確認  
9. 新規率が低いPlaywrightスクロールは最後の補助に回す  

この方針が一番現実的です。
### 反論1: 1ページ開きっぱなしで検索クエリ変更できるか

結論: **技術的には可能だが、rate limit節約にはならない**。

方法は2つあります。

1. **検索ボックスをPlaywrightで操作**
   ```js
   await page.fill('input[data-testid="SearchBox_Search_Input"]', query);
   await page.keyboard.press('Enter');
   ```
   SPA遷移なのでフルリロードは避けられるが、**SearchTimeline GraphQLは必ず1回以上発火**する。

2. **`page.goto("https://x.com/search?q=...&src=typed_query&f=live")`**
   安定性はこちらが上。毎回ページ遷移だが実装が単純。

`page.evaluate()`でReact内部状態だけを書き換えてURLを変えずに検索、は**非推奨**。Xの内部store/routerに依存しすぎて壊れやすい。  
また、どのみち検索条件を変えた時点でSearchTimelineリクエストは発生するので、**rate limit削減にはならない**。

68ヶ月分で68リクエストなら許容範囲。問題は各月内のpagination数。  
なので方針は:

- 月単位 or 週単位に分割
- 各クエリでcursorを最後まで進める
- 50req/15minに合わせてtoken bucket制御
- SQLiteに `query`, `cursor`, `last_tweet_id`, `done` を保存して中断再開

---

### 反論2: gallery-dlはTLS fingerprint問題を回避できるか

おそらく**完全な回避にはならない**。

gallery-dlは基本的にPythonのHTTPクライアント、主に `requests` 系で動く。  
つまりPlaywright/ChromeのTLS fingerprintではない。Node fetchで404になるSearchTimeline問題がTLS fingerprint由来なら、gallery-dlも同じ壁に当たる可能性がある。

ただし試す価値はある。

理由:

- gallery-dl側が別endpointを使っている可能性がある
- cookie認証込みでUserTimeline系を取れる可能性がある
- 実装済みのpagination/cursor処理を流用できる可能性がある

検証は小さくでよい。

```bash
gallery-dl --cookies-from-browser chrome "https://x.com/ronpochi"
gallery-dl -v --cookies-from-browser chrome "https://x.com/ronpochi"
```

見る点:

- どのendpointを叩いているか
- 404/429/403が出るか
- 取得件数がPlaywrightより多いか
- cursorが最後まで進むか

ただし本命は引き続き**PlaywrightでGraphQL response捕捉**。

---

### 反論3: ronpochi本人アーカイブ

同意。現実的ではないので優先度低。  
他人アカウントなら選択肢から外してよい。

---

## 追加質問への回答

### 1. 1ページ開きっぱなしで検索クエリ変更できるか

できるが、推奨はこれ。

```js
await page.goto(`https://x.com/search?q=${encodeURIComponent(query)}&src=typed_query&f=live`);
```

または検索ボックス操作。

```js
await page.fill('input[data-testid="SearchBox_Search_Input"]', query);
await page.keyboard.press('Enter');
```

`page.evaluate()`で内部JS状態を直接変更するのは不安定。  
そして**どの方法でもSearchTimelineリクエストは消費する**。

---

### 2. UserTweetsAndRepliesが166ページで打ち切られる原因

rate limitではなく、可能性が高いのは**API側/Timeline側の取得上限**。

典型原因:

- UserTweetsAndRepliesは全履歴保証APIではない
- cursorが一定深度で終端扱いになる
- 古い投稿/返信がtimeline indexから落ちている
- reply/repost/filteringで表示対象が間引かれる
- 同じcursorが返ってループ防止で止まる
- `bottom` instructionが消える

判定方法:

- 429ならrate limit
- 200でcursorなし/同一cursor/entries空ならAPI側終端
- response内の `instructions` と `entries` をSQLiteに保存して確認

対策:

- UserTweetsAndReplies一本に期待しない
- `from:ronpochi since:YYYY-MM-DD until:YYYY-MM-DD` のSearchTimeline日付分割
- 既知tweetのTweetDetailから会話・引用・返信を芋づる
- 取得IDの重複排除と日付別件数検証

---

### 3. Playwrightスクロールペースを上げてよいか

よい。  
ただし制御対象は**スクロール間隔ではなくGraphQL実リクエスト数**。

3秒スクロールでも、データが必要な時だけGraphQLが発火する。  
ただし深掘り中は連続発火して50req/15minを超える可能性がある。

実装はこうする。

- `page.on("response")` でGraphQLレスポンスを捕捉
- SearchTimeline/UserTweetsAndReplies/TweetDetailごとにreq数をカウント
- token bucketで `45req/15min` くらいに抑える
- 429が出たら `x-rate-limit-reset` まで停止
- 同一cursor連発、entries空ならそのクエリ終了

スクロール自体は:

```js
await page.mouse.wheel(0, 3000);
await page.waitForTimeout(3000);
```

でよい。  
ただしGraphQL発火が多すぎる場合は待機を入れる。

---

## 次の実装手順

1. PlaywrightでSearchTimeline response捕捉を実装  
2. SQLiteに保存  
   - `tweets`
   - `queries`
   - `cursors`
   - `graphql_responses`
3. 検索クエリを月単位で生成  
   ```txt
   from:ronpochi since:2019-01-01 until:2019-02-01
   ```
4. 各月を `f=live` で開く  
5. スクロールしながらGraphQL responseからtweet ID/cursorを抽出  
6. cursorなし、entries空、同一cursorで月終了  
7. 45req/15minでrate limit制御  
8. 取得後に月別件数を検証  
9. 欠けが大きい月だけ週単位に再分割  
10. 既知tweetからTweetDetail芋づるで補完
Traceback (most recent call last):
  File "/Users/shuji/Desktop/kitt-voice/tools/ask_gpt.py", line 8, in <module>
    response = client.responses.create(
        model="gpt-5.5",
    ...<10 lines>...
        input=prompt
    )
  File "/usr/local/lib/python3.14/site-packages/openai/resources/responses/responses.py", line 920, in create
    return self._post(
           ~~~~~~~~~~^
        "/responses",
        ^^^^^^^^^^^^^
    ...<45 lines>...
        stream_cls=Stream[ResponseStreamEvent],
        ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
    )
    ^
  File "/usr/local/lib/python3.14/site-packages/openai/_base_client.py", line 1332, in post
    return cast(ResponseT, self.request(cast_to, opts, stream=stream, stream_cls=stream_cls))
                           ~~~~~~~~~~~~^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "/usr/local/lib/python3.14/site-packages/openai/_base_client.py", line 1105, in request
    raise self._make_status_error_from_response(err.response) from None
openai.BadRequestError: Error code: 400 - {'error': {'message': 'This content was flagged for possible cybersecurity risk. If this seems wrong, try rephrasing your request. To get authorized for security work, join the Trusted Access for Cyber program: https://chatgpt.com/cyber', 'type': 'invalid_request', 'param': None, 'code': 'cyber_policy'}}
結論: **「走行中にバッチ投入」がおすすめ**です。  
ただし **1 JSONごとにDBへINSERTしない**。`100〜1000件単位`でまとめて投入し、SQLite側は `UNIQUE(tweet_id)` + `INSERT OR IGNORE/UPSERT` に任せるのが良いです。

## 理由

### 完了後投入の問題
- 数万JSONになると、ファイル走査・パース・失敗時再実行が重い
- 途中で取得が落ちた場合、「どこまでDB化したか」が不明瞭
- 後続の取得漏れ検証が遅れる

### 走行中投入の問題
- 1件ずつ重複チェックするとSQLite負荷が高い
- gallery-dlの書き込み中ファイルを読んでしまうリスク
- DBロックが起きる可能性

なので、**走行中に別プロセスでバッチ投入**が最適です。

---

## 推奨構成

```text
gallery-dl
  ↓ JSON出力
json_ingester.py
  ↓ 100〜1000件ごとにtransaction
SQLite
```

SQLite設定:

```sql
PRAGMA journal_mode=WAL;
PRAGMA synchronous=NORMAL;
PRAGMA temp_store=MEMORY;
PRAGMA busy_timeout=5000;
```

テーブル例:

```sql
CREATE TABLE IF NOT EXISTS tweets (
  tweet_id TEXT PRIMARY KEY,
  account TEXT,
  created_at TEXT,
  url TEXT,
  raw_json TEXT NOT NULL,
  inserted_at TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS ingested_files (
  path TEXT PRIMARY KEY,
  size INTEGER,
  mtime REAL,
  ingested_at TEXT DEFAULT CURRENT_TIMESTAMP
);
```

投入は:

```sql
INSERT OR IGNORE INTO tweets (...)
VALUES (...);
```

または更新もしたいなら:

```sql
INSERT INTO tweets (...)
VALUES (...)
ON CONFLICT(tweet_id) DO UPDATE SET
  raw_json = excluded.raw_json;
```

---

## 実装手順

1. **gallery-dlはそのまま走らせる**
   - 取得処理とDB投入処理を分離する
   - X側へのアクセス数を増やさないのでrate limitには影響しない

2. **JSON投入ワーカーを別プロセスで起動**
   - 出力ディレクトリを定期スキャン
   - `.json` のみ対象
   - サイズ・mtimeが数秒変化していないファイルだけ読む  
     例: `mtime < now - 5秒`

3. **100〜1000ファイル単位でSQLite transaction**
   - 1ファイル1コミットは禁止
   - 例: 500件ごとに `BEGIN; ... COMMIT;`

4. **`ingested_files` に投入済みファイルを記録**
   - 再起動時は未投入ファイルだけ処理
   - 中断再開が簡単になる

5. **tweetsテーブルは `tweet_id PRIMARY KEY`**
   - 重複チェックはPython側で頑張らずSQLiteに任せる
   - `INSERT OR IGNORE` で十分

6. **取得漏れ検証をDBベースで実施**
   - account別件数
   - min/max created_at
   - tweet_id重複数
   - gallery-dlのログ上の取得件数との差分
   - 日付レンジごとの空白期間確認

---

## 判断基準

今回すでに10分で3,274件なら、数万件規模になります。  
この規模なら **完了後まとめて投入でも不可能ではない**ですが、運用上は走行中バッチ投入の方が安全です。

おすすめ設定:

```text
投入間隔: 30〜60秒ごと
バッチサイズ: 500件
SQLite: WAL有効
重複処理: tweet_id PRIMARY KEY + INSERT OR IGNORE
再開管理: ingested_files
```

これでDB負荷を抑えつつ、ファイル数膨張・中断時のやり直し・取得漏れ検証の遅延を避けられます。
最有力は **取得ではなく保存/再開ロジック側** です。  
「Playwrightでは見える」「APIでは取れる」「DBに入っていない」なら、cookie期限切れより **DB投入前後で落としている** 可能性が高いです。

## 考えられる原因

### 1. cursor / resume が古い位置から再開している
一番怪しいです。

- 保存済み cursor が 2025-09/10 付近
- 次回実行時に最新ページからではなく、その cursor 以降、つまり古い方向だけを継続
- その結果、2025-10以降の最新側を一度も見に行かない

X GraphQL の timeline cursor は基本的に「下へ、古い方へ」進むので、**head sync と backfill を分ける必要があります**。

### 2. DB import 側のフィルタで「新しすぎるツイート」を捨てている
全7アカウントで同じ時期に止まるなら、日付条件のバグも濃厚です。

例:

```python
if created_at > cutoff:
    skip
```

のような条件が逆になっている。

2025-10 付近は現在から約6〜7ヶ月前なので、  
`now - 180days` などの cutoff が誤って効いている可能性があります。

### 3. 重複スキップで最新分が落ちている可能性
ありえます。

特に以下は危険です。

- tweet_id ではなく URL / text / media URL で dedupe
- JS Number で tweet_id を扱って精度落ち
- SQLite に入れる前に `already_seen_user` や `last_seen_at` で雑に停止
- 1件でも既存ツイートを見つけたらページ全体/以降を打ち切る

ただし、全アカウントで同じ境界なら、単純な重複より **cursor/resume または cutoff 条件** の方が怪しいです。

### 4. gallery-dl の cookie 期限切れ
可能性は低いです。

cookie切れなら普通は、

- 401/403
- guest扱い
- 途中で空になる
- rate limit
- protected / sensitive が取れない

のような症状になります。  
「APIでは取れるがDBに入っていない」なら cookie より保存側。

### 5. メタデータ保存形式の問題
可能性は中程度。

gallery-dl の raw metadata には 2026年5月分があるのに DB にないなら、  
**metadata → SQLite import の parser/schema 問題** です。

特に確認するべき点:

- `created_at` のパース失敗
- timezone 比較ミス
- tweet_id を INTEGER/REAL/文字列で混在
- quoted/reply/retweet の JSON パス変更
- `legacy` / `tweet_results.result` / `note_tweet` など新形式未対応

## 次にやるべき確認

1. **API raw JSON / gallery-dl metadata に 2026年5月ツイートが存在するか確認**
   - 存在する → DB import バグ
   - 存在しない → fetch/cursor/cookie/rate limit 側

2. SQLiteで確認

```sql
SELECT account, MAX(created_at), MAX(tweet_id)
FROM tweets
GROUP BY account;
```

3. resume/cursor テーブルを確認

```sql
SELECT * FROM cursors;
SELECT * FROM checkpoints;
```

4. 一度だけ cursor を無視して、各アカウントを最新ページから取得する

- cursorなし
- count多め
- 最新100〜300件のみ
- 既存DBに upsert

5. insert直前にログを出す

```text
fetched tweet_id, created_at
skip reason
inserted/ignored reason
```

## 結論

優先順位はこれです。

1. **古い cursor/checkpoint から再開して最新側を見ていない**
2. **cutoff/date filter が逆で、直近6ヶ月を skip している**
3. **DB投入時の dedupe / upsert / parser で落としている**
4. gallery-dl cookie期限切れ
5. metadata形式問題

まず cursor をリセットして「最新から100件だけ取得→DB upsert」してください。  
それで入るなら原因は resume/pagination です。
## 結論

最も有望なのは **SearchTimeline を日付分割して Python / gallery-dl 経由で回す方法**です。  
`UserTweetsAndReplies` の cursor 打ち切りはサーバ側の上限なので、cursor 手動操作や gallery-dl の範囲指定では突破できない可能性が高いです。

ただし、**ronpochi は SearchTimeline から除外されているため別問題**です。  
ronpochi の全件取得は、現状の公開 GraphQL 経路だけでは保証困難です。やるなら Playwright で profile timeline をネットワークレスポンスから直接吸う「低速・長時間・再開可能」方式が現実的です。

---

## 未試行項目の評価

### 1. gallery-dl の SearchTimeline モード

有望です。  
gallery-dl は検索 URL を渡すことで Twitter/X search extractor として動く可能性があります。

例：

```bash
gallery-dl \
  --cookies-from-browser firefox \
  "https://x.com/search?q=from%3Adanjer%20since%3A2025-10-01%20until%3A2025-10-08&f=live"
```

`f=live` を必ず使う。Top 検索だと欠落しやすいです。

クエリ例：

```text
from:danjer since:2025-10-01 until:2025-10-08
from:BobLoukas since:2025-10-01 until:2025-10-08
```

必要なら replies 用に追加確認：

```text
from:danjer filter:replies since:2025-10-01 until:2025-10-08
```

ただし、`from:user` だけで replies も含まれることが多いので、まず差分検証してください。

---

### 2. gallery-dl の `--range`, `--chapter-range`

打開策にはなりません。

これらは「取得されたアイテムの何番目から何番目を保存するか」の制御であり、X 側の GraphQL cursor 上限や日付範囲を変えるものではありません。

使うべきなのは gallery-dl の range ではなく、SearchTimeline の検索クエリ側の：

```text
since:YYYY-MM-DD until:YYYY-MM-DD
```

です。

---

### 3. gallery-dl の cursor キャッシュ手動操作

期待薄です。

理由：

- cursor はサーバ発行
- query / account / session / feature flags に依存
- 打ち切りは client 側 cache ではなく server 側 pagination limit の可能性が高い
- cache clear で最新分が取れるのは、開始位置がリセットされるだけ

つまり、cursor を書き換えても「170ページ以降」が出る可能性は低いです。

---

### 4. Python requests で SearchTimeline を直接叩く

有望です。

Node.js fetch の 404 は TLS fingerprint よりも、以下の不一致の可能性が高いです。

- bearer token
- `x-csrf-token`
- `auth_token` cookie
- `ct0` cookie
- `x-twitter-active-user`
- `x-twitter-client-language`
- GraphQL の `features`
- `variables`
- URL encoding

まずは gallery-dl が SearchTimeline で通るか確認し、通るなら gallery-dl の実装を参考に Python 化するのが早いです。

もし Python `requests` でも不安定なら、次点で：

```bash
pip install curl_cffi
```

を使い、Chrome impersonation で叩く。

```python
from curl_cffi import requests

s = requests.Session(impersonate="chrome")
```

---

### 5. 手動 cookie 指定

可能です。  
`--cookies-from-browser` ではなく、Netscape cookies.txt を渡せます。

```bash
gallery-dl --cookies ./cookies_x_profile1.txt "https://x.com/search?q=..."
```

または config に指定。

複数ブラウザプロファイルを切り替えることで、認証状態の差分検証にも使えます。  
ただし rate limit は厳密に SQLite に記録して、429 を踏んだら待機してください。

---

## 推奨する実装手順

### Step 1: gallery-dl SearchTimeline が使えるか最短確認

まず 1 アカウント、短い期間で確認。

```bash
gallery-dl \
  --cookies-from-browser firefox \
  "https://x.com/search?q=from%3Adanjer%20since%3A2025-10-01%20until%3A2025-10-02&f=live"
```

見るべき点：

- tweet が出るか
- replies が含まれるか
- pagination が最後まで行くか
- 429 が出るか
- 保存 JSON に tweet ID / created_at があるか

これが通るなら、6アカウント分は SearchTimeline 日付分割で進めるべきです。

---

### Step 2: Python で SearchTimeline 収集器を作る

gallery-dl をそのまま大量実行してもよいですが、全件取得を狙うなら Python で制御した方がよいです。

必要機能：

- query: `from:user since:YYYY-MM-DD until:YYYY-MM-DD`
- GraphQL SearchTimeline 呼び出し
- bottom cursor 保存
- rate limit 検知
- SQLite 保存
- 中断再開
- 日付範囲の自動分割

---

### Step 3: 日付範囲を自動分割する

SearchTimeline は 50 req / 15min が厳しいので、雑に長期間を投げない方がよいです。

初期 window 目安：

| アカウント | 初期 window |
|---|---:|
| CryptoHayes | 30日 |
| danjer | 3〜7日 |
| BobLoukas | 3〜7日 |
| Checkmatey | 2〜5日 |
| LynAlden | 7日 |
| PeterBrandt | 3〜7日 |
| ronpochi | Search 不可なので対象外 |

ルール：

- 1 window 内で cursor ページ数が多すぎる場合、期間を半分に割る
- 40 request 近く使っても終端に届かない window は分割
- 取得件数 0 の window も完了として記録
- 期間境界は 1日 overlap させて重複排除

例：

```text
2025-10-01〜2025-10-08
↓ 多すぎる
2025-10-01〜2025-10-04
2025-10-04〜2025-10-08
```

---

## SQLite 設計

最低限これでよいです。

```sql
CREATE TABLE IF NOT EXISTS tweets (
  id TEXT PRIMARY KEY,
  user_screen_name TEXT,
  user_id TEXT,
  created_at TEXT,
  full_text TEXT,
  raw_json TEXT NOT NULL,
  source TEXT NOT NULL,
  first_seen_at TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS jobs (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  user_screen_name TEXT NOT NULL,
  since_date TEXT NOT NULL,
  until_date TEXT NOT NULL,
  source TEXT NOT NULL,
  cursor TEXT,
  status TEXT NOT NULL DEFAULT 'pending',
  page_count INTEGER DEFAULT 0,
  item_count INTEGER DEFAULT 0,
  attempts INTEGER DEFAULT 0,
  last_error TEXT,
  updated_at TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_jobs_unique
ON jobs(user_screen_name, since_date, until_date, source);
```

`tweets.id` を primary key にして、重複は `INSERT OR IGNORE` で潰す。

---

## rate limit 対応

SearchTimeline は 50 req / 15min 前提で制御。

実装ルール：

- 1 credential ごとに request counter を持つ
- 429 が出たら `x-rate-limit-reset` を読む
- reset header がなければ 15分 sleep
- 1 window で無理に粘らず、分割して後回し
- cursor は job に保存して中断再開

疑似ロジック：

```text
while jobs pending/running:
  job = next_job()
  while job has cursor or first page:
    if rate_limit_near:
      sleep_until_reset()

    res = call_search_timeline(job.query, job.cursor)

    if 429:
      save cursor
      sleep_until_reset()
      continue

    save tweets
    save bottom cursor

    if no bottom cursor:
      mark done
      break

    if page_count > 40:
      split job date range
      mark split
      break
```

---

## 取得漏れ検証

SearchTimeline は完全性保証が弱いので、検証を必ず入れるべきです。

### 検証1: window 再実行

完了した window をもう一度実行して、新規 ID が出ないか確認。

```text
new_ids == 0 なら一旦 OK
new_ids > 0 なら window をさらに分割
```

### 検証2: 日別件数チェック

SQLite で日別件数を出す。

```sql
SELECT
  user_screen_name,
  substr(created_at, 1, 10) AS d,
  COUNT(*) AS cnt
FROM tweets
GROUP BY user_screen_name, d
ORDER BY user_screen_name, d;
```

極端に 0 の日が続く場所を再取得対象にする。

### 検証3: UserTweetsAndReplies との突合

既に取得済みの `UserTweetsAndReplies` データと SearchTimeline の union を作る。

確認：

- SearchTimeline にしかない ID
- UserTweetsAndReplies にしかない ID
- 日付境界の欠落
- replies / retweets / quotes の差

### 検証4: overlap window

例えば実際の job はこうする。

```text
2025-10-01〜2025-10-08
2025-10-07〜2025-10-15
```

1日 overlap させ、重複は tweet ID で排除。  
境界欠落を防げます。

---

## ronpochi の扱い

ronpochi は SearchTimeline 除外なら、SearchTimeline 戦略では無理です。

候補は以下。

### A. Playwright + network capture

DOM から読むのではなく、GraphQL response を intercept して保存する。

```python
page.on("response", handle_response)
```

対象 URL：

```text
UserTweets
UserTweetsAndReplies
TweetDetail
```

保存対象：

- tweet ID
- legacy.created_at
- legacy.full_text
- user result
- raw JSON

DOM パースより速く、重複にも強いです。

ただし、profile timeline が同じ 170ページ制限で止まるなら、これも限界があります。

---

### B. Playwright DOM スクロールを最適化

ronpochi だけは低速前提でやる。

改善点：

- tweet ID を DOM の URL `/status/{id}` から抽出
- ID 重複率が高い場合はスクロール量を増やす
- `created_at` が目標期間に入ったら保存
- 連続 N 回、新規 ID なしなら一時停止
- SQLite に last_position / newest_oldest_seen を保存
- ブラウザ context は persistent にする

ただし 100,000件規模だと時間がかかります。

---

### C. 外部データソースを検討

全件保証が必要なら、ronpochi については以下が必要になる可能性が高いです。

- X paid API の full-archive search 相当
- 本人提供の archive
- 既存の外部アーカイブ
- 別の検索インデックス

公開 GraphQL だけで ronpochi 100,000件を保証するのは厳しいです。

---

## 優先順位

### 最優先

1. gallery-dl で SearchTimeline URL が動くか確認  
2. 動くなら 6アカウントを SearchTimeline 日付分割で回収  
3. SQLite job 管理、cursor 管理、rate limit 管理を入れる  
4. window 再実行で欠落検証  

### 並行

5. Python direct SearchTimeline 実装  
6. Node.js fetch は一旦捨てる  
7. 必要なら `curl_cffi` を使う  

### ronpochi

8. SearchTimeline は諦める  
9. Playwright network capture 方式に切り替える  
10. それでも cursor 上限で止まるなら、外部アーカイブ/API が必要  

---

## 具体的な次の一手

まずこれを実行してください。

```bash
gallery-dl \
  --cookies-from-browser firefox \
  --write-metadata \
  "https://x.com/search?q=from%3Adanjer%20since%3A2025-10-01%20until%3A2025-10-03&f=live"
```

成功したら、次にこれ。

```bash
gallery-dl \
  --cookies-from-browser firefox \
  --write-metadata \
  "https://x.com/search?q=from%3Adanjer%20filter%3Areplies%20since%3A2025-10-01%20until%3A2025-10-03&f=live"
```

この2つの ID 差分を見る。

- 1本目だけで replies も含まれる → `from:user since until` で進める
- replies が不足 → 通常検索 + `filter:replies` の2系統で回す
- どちらも取れない → Python direct / curl_cffi 実装へ進む

この検証が通れば、ronpochi 以外の約13万件欠落はかなり現実的に埋められます。
合意。方針は妥当です。`gallery-dl SearchTimeline` が実際に通ったので、このルートで欠落期間を埋めるのが最短です。

注意点だけ：

1. **`until` は排他的**
   - `since:2025-10-01 until:2025-10-08` は 10/1〜10/7 分。
   - 週分割時に境界漏れしないようにする。

2. **検索結果の上限対策**
   - 週単位で件数が多いアカウントは取り切れない可能性あり。
   - 完了後、日別件数を見て不自然に少ない週は **日単位に再分割**。

3. **取得漏れ検証**
   - SQLite投入後に以下を確認：
     - account別・日別件数
     - 既存DBとの重複tweet_id
     - 期間の空白日
     - gallery-dlログ上の途中終了/rate limit/error

4. **SQLite保存**
   - `tweet_id` を UNIQUE / PRIMARY KEY にしてUPSERT。
   - metadata JSONもできればraw保存。
   - ingestは冪等にする。

5. **中断再開**
   - `account, since, until, status, count, started_at, finished_at, error` のようなジョブ管理テーブルを作る。
   - 成功済み週はスキップ可能にする。

6. **rate limit**
   - gallery-dlの30秒待機に任せてOK。
   - ただし複数アカウント並列実行は避ける。まずは直列。

7. **ronpochi**
   - SearchTimeline不可なら別ルート。
   - 候補は UserTweets GraphQL / Playwrightスクロール / 既存アーカイブ比較。
   - 同じSQLiteスキーマに正規化して投入する。

次の実装手順：

1. 6アカウント分の週次ジョブリスト生成  
2. gallery-dl実行ラッパー作成  
3. 成功/失敗/件数をSQLiteに記録  
4. metadata ingestでtweetsテーブルへUPSERT  
5. account別・日別集計で欠落チェック  
6. 不足週だけ日単位で再取得  

このまま進めてよいです。
1. **SearchTimelineの日付分割は効果あり。ただし補完用途**
   - 古い方向でUserTweets/UserTweetsAndRepliesのcursorが詰まるなら、`SearchTimeline`を`since/until`で月・週・日単位に割るのは有効。
   - ただしSearchは完全保証ではない。インデックス漏れ、削除、非公開化、古い投稿の検索非ヒットがある。
   - 実装は `from:account since:YYYY-MM-DD until:YYYY-MM-DD` を基本に、件数が多い月は週→日に再分割。
   - `Latest`相当のSearchTimelineを使い、cursor重複・空ページ・rate limitを検知して中断再開可能にする。

2. **RT/Repost割合の推定方法**
   - まず現在DBの83,901件を分類する。
     - RT/Repost: `retweeted_status_result` / `retweeted_status_id` / socialContext等で判定
     - Reply: `in_reply_to_status_id`あり
     - Original: それ以外
   - アカウント別・年別にRT率を出す。
   - 未取得の古い期間は、SearchTimelineでサンプル取得して同じ分類をする。
   - 可能なら検索クエリで補助:
     - RTのみ: `from:user filter:nativeretweets`
     - RT除外: `from:user -filter:nativeretweets`
   - ただし検索演算子も完全ではないので、最終判定は取得JSONの構造で分類するべき。

3. **83,901件が実質50%近く取得できている可能性はある**
   - プロフィール件数313,000がRT込みなら、RT率50〜60%の場合:
     - 非RT総数は約125,000〜156,000件
   - 83,901件がすべて非RT相当なら、取得率は約54〜67%。
   - ただし83,901件にもRTが含まれているなら、比較前にRTを除外する必要あり。
   - したがって「実質50%近く」は十分あり得るが、DB内のRT率を出さないと確定できない。

次の実装順:

1. `created_at`を文字列ではなく`created_at_ms`またはSnowflake由来時刻で正規化保存。  
2. SQLiteに `tweet_id UNIQUE`, `user_id`, `created_at_ms`, `is_rt`, `is_reply`, `is_original` を追加。  
3. 既存83,901件をRT/Reply/Originalに再分類。  
4. アカウント別・年別の取得件数とRT率を集計。  
5. 2018年以前をSearchTimelineで月単位取得。多い月は週/日に分割。  
6. cursor、query、since/until、最終tweet_idをSQLiteに保存して中断再開。  
7. 各期間で重複除去後、Snowflake順で取得漏れを検証。
原因は「取得ロジック」ではなく、**SearchTimelineの共有rate limit 50req/15minを3並列で奪い合っていること**と、**UserTweetsAndReplies系タイムラインが深掘りに向かないこと**です。戦略は以下に寄せるべきです。

---

## 1. 並列 vs 直列

**基本は直列、またはglobal rate limiter付き1〜2並列。**

今の3並列は速くならず、各ジョブが待たされるだけです。

推奨:

```text
SearchTimeline worker: 1本
rate limit: 50req/15min を全ジョブ共有
ジョブ単位: account + since/until の日付範囲
```

優先順位:

1. 既知の古い未取得期間
2. 日別ヒストグラムで空白が出た中間期間
3. 再検証用の短期間ジョブ

やること:

- 3並列を停止
- `danjer`, `Checkmatey`, `BobLoukas` をキュー化
- 1ジョブずつSearchTimelineを消化
- rate limit到達時は15分待機
- cursor/last query/date rangeをSQLiteに保存して中断再開可能にする

---

## 2. 欠落期間の特定

**日別件数ヒストグラムは必須。先に作るべきです。**

SQL例:

```sql
SELECT
  account,
  date(created_at) AS day,
  COUNT(*) AS cnt
FROM tweets
GROUP BY account, day
ORDER BY account, day;
```

見るべきもの:

- 完全な0件の日
- 前後平均より極端に少ない日
- 連続して件数が落ちている月
- 既に取得済みと思っていた2020-03〜2025-09の空白

次に月別も作る:

```sql
SELECT
  account,
  substr(created_at, 1, 7) AS month,
  COUNT(*) AS cnt
FROM tweets
GROUP BY account, month
ORDER BY account, month;
```

取得ジョブはこう切る:

```text
from:ACCOUNT since:2020-03-01 until:2020-04-01
from:ACCOUNT since:2020-04-01 until:2020-05-01
...
```

件数が多い月は週単位、日単位に分割。

---

## 3. ronpochi戦略

ronpochiは別扱いです。

現状:

- SearchTimeline不可
- UserTweetsAndRepliesは約170ページで打ち切り
- 欠落10万件規模

この場合、UserTweetsAndRepliesを深掘りしても全件は無理です。Webのプロフィールタイムラインは深い過去まで保証されません。

試す順番:

### A. Playwrightでログイン済み検索UIを直接確認

ブラウザ上で以下が通るか確認:

```text
from:ronpochi since:2020-01-01 until:2020-02-01
```

通るなら、gallery-dlではなくPlaywright/GraphQL SearchTimelineで取得する価値あり。

### B. GraphQL SearchTimelineをPlaywrightから叩く

PlaywrightでXにログインし、NetworkからSearchTimeline GraphQLを捕捉。

保存対象:

- query
- variables
- features
- cursor
- response JSON

実装方針:

```text
日付範囲を月/週/日単位に分割
SearchTimeline GraphQLをcursorで最後まで回す
raw JSONをSQLiteに保存
tweet idでdedupe
```

### C. それでもSearchTimelineに出ない場合

ronpochiの古い投稿は、公開検索インデックスから取れない可能性が高いです。

その場合の現実的な選択肢:

- X有料APIのfull-archive search
- 本人アーカイブ
- 外部アーカイブ
- 既存DB/過去クロールデータ
- 取得対象から分離して「検索不可」と明記

つまり、ronpochiは他6アカウントと同じ完了基準にしない方がいいです。

---

## 4. 完了判定

プロフィール件数313,000件との一致は使わない方がいいです。

理由:

- RT/返信/削除/非公開化/検索非掲載が混ざる
- X側のプロフィール件数は取得可能件数と一致しない
- SearchTimelineに出ない投稿がある

実用的な完了基準:

### アカウントごとに以下を満たしたら十分取得済み

1. 日別/月別ヒストグラムに unexplained gap がない
2. `since/until` 分割検索を全期間で実行済み
3. 各ジョブがcursor終端まで到達している
4. 同じ期間を再実行しても新規追加がほぼ0
5. 取得済みtweet idの重複率が高くなり、新規発見率が低い

目安:

```text
再取得1周で新規追加率 < 0.5% なら完了扱い
重要期間だけ再取得して新規追加率 < 0.1% なら確定
```

SQLiteに `jobs` テーブルを作るとよいです。

```sql
CREATE TABLE IF NOT EXISTS fetch_jobs (
  id INTEGER PRIMARY KEY,
  account TEXT,
  source TEXT,
  query TEXT,
  since TEXT,
  until TEXT,
  status TEXT,
  last_cursor TEXT,
  request_count INTEGER DEFAULT 0,
  inserted_count INTEGER DEFAULT 0,
  started_at TEXT,
  finished_at TEXT,
  updated_at TEXT,
  error TEXT
);
```

---

## 5. 時間見積もり

rate limitが本当に、

```text
50req / 15min = 200req/hour
```

なら、理論値はこうです。

SearchTimeline 1ページあたり仮に20〜50件として:

```text
残り23万件 / 20件 = 11,500req = 約57.5時間
残り23万件 / 50件 = 4,600req = 約23時間
```

ただし実運用では、

- rate limit待ち
- cursor失敗
- 重複
- 検索結果の薄い期間
- ingest遅延
- 再取得検証

があるので、現実的には:

```text
他6アカウントのSearchTimeline補完: 3〜7日
ronpochi含む完全補完: 不明。検索不可ならAPI/アーカイブなしでは無理
```

---

## 次の実装手順

短期でやる順番はこれです。

1. **3並列を止める**
2. SearchTimeline用の**単一キュー + global rate limiter**に変更
3. SQLiteに `fetch_jobs` を作り、`account/since/until/cursor/status` を保存
4. 日別/月別ヒストグラムを生成
5. 空白・低件数期間を自動でジョブ化
6. `since/until` 月単位で取得、件数が多い月だけ週/日単位に分割
7. 各ジョブはcursor終端まで回す
8. 完了後、同じ期間を再実行して新規追加率を測る
9. ronpochiは別レーンに分離し、PlaywrightでSearchTimeline GraphQL可否を確認
10. ronpochiが検索不可なら「通常手段では取得不能」として完了基準から除外

最重要は、**先にヒストグラムで欠落期間を可視化し、SearchTimelineを日付分割ジョブとして管理すること**です。並列数を増やすより、cursor終端・中断再開・再検証を固めた方が確実です。
反論は妥当。**今は独自SearchTimeline実装より gallery-dl ラッパーが速い**です。  
方針変更: **取得本体=gallery-dl、制御/検証/保存=自前**。

## 回答

### 1. rate limit 30秒待機は変更できるか
通常リクエスト間隔は設定可能。

例:

```bash
gallery-dl \
  -o extractor.twitter.sleep-request=20 \
  "https://x.com/search?q=from%3AUSER%20since%3A2024-01-01%20until%3A2024-01-02&f=live"
```

ただし注意:

- `50req/15min = 18秒` は理論値
- SearchTimelineのlimitは認証状態/endpoint/他アクセスと共有される可能性あり
- 429後の待機を無理に短縮するのは危険

推奨はまず **20〜25秒**。429が出るなら30秒以上に戻す。

---

### 2. gallery-dlのcreated_atフォーマットは統一されているか
**信用しない方がいい**です。

gallery-dl側に正規化済み日時フィールドがある場合でも、raw metadataにはX由来の形式が残る可能性があります。

想定混在:

```text
Wed Oct 10 20:19:24 +0000 2018
2024-01-01T12:34:56+00:00
2024-01-01 12:34:56
```

DB投入時に必ず自前で正規化するべき。

---

### 3. ヒストグラム前にcreated_at正規化が必要か
**必要。最優先。**

日別ヒストグラムは `created_at_utc` から作る。

SQLite例:

```sql
tweets(
  tweet_id TEXT PRIMARY KEY,
  user_id TEXT,
  screen_name TEXT,
  raw_created_at TEXT,
  created_at_utc TEXT,
  created_at_epoch INTEGER,
  raw_json TEXT,
  source_job_id TEXT,
  fetched_at TEXT
)
```

正規化失敗したものは別テーブルへ退避:

```sql
parse_errors(
  tweet_id TEXT,
  raw_created_at TEXT,
  raw_json TEXT,
  reason TEXT
)
```

---

## 次の実装手順

1. **gallery-dl単一キュー化**
   - 3並列停止
   - `jobs` テーブルで `since/until/status/retry_count` 管理
   - ronpochiは別DBまたは別queue

2. **1日単位でgallery-dl実行**
   - query:
     ```text
     from:USER since:YYYY-MM-DD until:YYYY-MM-DD
     ```
   - `f=live` を使う
   - `sleep-request=20〜25` から開始

3. **metadata/raw JSONを必ず保存**
   - gallery-dl出力をそのままSQLiteへ投入
   - `tweet_id UNIQUE` で重複排除

4. **created_at正規化**
   - DB投入時にUTC ISO + epochへ変換
   - 失敗レコードは捨てずに `parse_errors`

5. **日別ヒストグラム生成**
   - `created_at_epoch` ベース
   - 件数0/極端に少ない日を再取得対象にする

6. **完了判定**
   - プロフィール件数では判定しない
   - 再取得時の新規tweet率を見る
   - 例: 直近再取得で新規率 `<0.1%` なら一旦完了候補

7. **Playwright**
   - 本取得には使わない
   - Cookie更新/ログイン確認専用にする

結論: **今はgallery-dl採用で正解。ただしDB投入前の日時正規化と日別欠落検証は自前必須。**
結論: **sleepを伸ばすだけでは解決しにくい**です。まず429の中身確認。その後、検索範囲分割が現実的です。

### 1. `-o sleep-request=`を長くすべき？
少しは有効ですが、今回の主因解決には弱いです。

- `sleep-request`は「通常リクエスト間隔」を空けるだけ
- すでにcursor付き2ページ目で429固定なら、待っても同じcursorで詰まり続ける可能性あり
- 設定するなら `10-30秒` 程度  
  例:

```bash
-o sleep-request=15
```

ただし、**14分待ちを繰り返して進まないならsleep調整だけでは不足**です。

---

### 2. `--verbose`で確認すべき？
はい。最優先です。

確認したいもの:

- 429時のURL / GraphQL operation
- cursorが毎回同じか
- `x-rate-limit-limit`
- `x-rate-limit-remaining`
- `x-rate-limit-reset`
- GraphQL error内容
- guest token / auth状態

実行例:

```bash
gallery-dl --verbose \
  "https://twitter.com/search?q=from%3Asmile_danjer%20since%3A2023-07-01%20until%3A2023-08-01&src=typed_query&f=live"
```

可能ならレスポンス保存も有効。

```bash
-o write-pages=true
```

---

### 3. 1ジョブごとに再起動、キャッシュクリア、新規セッションは？
基本おすすめしません。

理由:

- 同一IP / 同一アカウントならrate limitは回避できない可能性が高い
- キャッシュクリアでtoken再取得が増え、逆に怪しまれる
- cursor再開位置を失いやすい
- 重複取得や取得漏れ検証が難しくなる

やるなら「再起動」ではなく、**範囲分割 + archive保存 + 単一セッション**が良いです。

---

## 次の実装手順

1. 今のジョブ停止  
2. `--verbose -o write-pages=true`で1回だけ再実行  
3. 429時のheaderとcursorを確認  
4. 1ヶ月検索をやめて日単位に分割

例:

```bash
from:smile_danjer since:2023-07-01 until:2023-07-02
from:smile_danjer since:2023-07-02 until:2023-07-03
...
```

5. `download-archive`を必ず使う

```bash
--download-archive twitter-archive.sqlite3
```

6. 各日付ごとに完了/失敗/最終cursor/件数をSQLiteに保存  
7. 失敗日は後で再試行  
8. 取得漏れ検証は日単位件数、tweet_id重複、時刻範囲で確認

---

要するに、今回の詰まりは **SearchTimelineのcursor paginationが429で固定化している状態** に見えます。  
`--verbose`で確認後、**月単位ではなく日単位または数時間単位に分割して深いcursorを避ける**のが一番安全です。
1. **はい。** `gallery-dl --dump-json` は基本的に画像なしツイートも含むJSONを stdout に出します。  
   ただし replies / retweets / protected / deleted / rate limit / pagination 設定の影響は受けます。

2. **いいえ、期待しない方がいいです。**  
   `--write-metadata` の sidecar `.json` は「ダウンロード対象ファイル」に紐づくため、画像・動画なしツイートでは保存されません。  
   `posts=all` 系の設定で解決する問題ではありません。

3. **全件取得目的なら独自Python推奨。**  
   gallery-dl内部を import して流用するより、挙動を参考にして自前で組む方が安全です。  
   ただし rate limit 自体は回避できません。改善点は「中断再開・SQLite保存・検証」ができることです。

実装手順：

- Playwrightでログイン済みcookie取得
- Python `requests` でXのGraphQL `UserTweets` / `UserTweetsAndReplies` を叩く
- `Bottom` cursor をSQLiteに保存しながらページング
- tweet_id をPKにして raw JSON / text / created_at / media有無を保存
- 429時は `x-rate-limit-reset` か固定backoffで待機
- 再開時はSQLiteの最後のcursorから続行
- 検証は gallery-dl `--dump-json` の一部結果と tweet_id 集合比較

結論：  
**メタデータ全件保存には gallery-dl sidecar ではなく、`--dump-json` か独自GraphQL取得。長期運用なら独自Python。**
率直に言うと、**今の方法のまま全件取得は現実的ではない**です。  
理由は「遅い」以前に、**成功3日でもDB増加0件＝取得結果を保存できていない可能性が高い**ためです。現状では何日回しても成果が出ないリスクがあります。

## 現実的な時間見積もり

### 現状ペース
- 2時間で成功3日、failed6日、DB追加0
- danjer 305日だけでも、単純計算で **3〜9日以上**
- 5アカウント4000日超なら、日単位実行だと **40〜100日級**
- しかも failed 再試行込みだとさらに悪化

なので、**現方式のまま4000日完走は非現実的**です。

---

## まずやるべきこと

### 1. いったん fetch_all_dumpjson.py は止める
DB追加0なので、今走らせ続けても無駄になる可能性が高いです。

---

### 2. failed原因を分類する
各実行ごとに最低限これを保存してください。

- command
- returncode
- stdout bytes
- stderr last 200 lines
- elapsed sec
- timeoutかどうか
- HTTP 429 / 403 / 404 / 5xx の有無
- 出力JSON件数

`timeout=600`で死んだのか、rate limitなのか、JSON parse失敗なのかを分ける必要があります。

---

### 3. dump-jsonのパースを単独検証する
成功した3日の `dump-json` 出力ファイルを使って、まず手動で確認。

```bash
head -n 5 output.jsonl
wc -l output.jsonl
jq . output.jsonl | head
```

gallery-dl の `--dump-json` は多くの場合、**JSON Lines形式**です。  
つまり、1ファイル全体が1つのJSON配列ではなく、**1行1JSON** の可能性が高いです。

Python側はこう読むべきです。

```python
for line in f:
    if not line.strip():
        continue
    obj = json.loads(line)
```

DB追加0の原因はかなり高確率でここです。

---

## 日単位 vs 週単位

週単位に戻すべきです。

日単位は gallery-dl 起動回数が多すぎます。

ただし注意点：

- rate limit消費は「日数」ではなく「timeline pagination回数」に依存
- 週単位にしても取得ページ数が多ければrate limitは減らない
- でもプロセス起動、ログイン、初期GraphQL呼び出しのオーバーヘッドは減る

推奨：

- まず **7日単位**
- ツイート量が少ない期間は **14日単位**
- 失敗したら **二分割して再試行**
  - 14日失敗 → 7日
  - 7日失敗 → 3日
  - 3日失敗 → 1日

---

## gallery-dl継続か、独自GraphQLか

短期は **gallery-dl継続でよい** です。  
理由は、TLS問題なく動いていることが確認済みだからです。

ただし最終的には、独自GraphQL実装の方が良いです。

### gallery-dl継続のメリット
- XのGraphQL仕様変更にある程度追従してくれる
- TLS / cookie / guest token周りが既に動いている
- 実装が早い

### gallery-dlの問題
- 失敗原因がブラックボックス化しやすい
- cursor保存・中断再開が弱い
- rate limit制御しづらい
- 日付範囲指定と実取得の対応が見えにくい

### 独自GraphQLに切り替える場合
PlaywrightでXにログイン済みcookieを取得し、GraphQLを直接叩く構成が良いです。

必要要素：

- Playwrightで `auth_token`, `ct0` 取得
- `UserTweets` / `UserTweetsAndReplies` GraphQLをrequests/httpxで呼ぶ
- cursorをSQLiteに保存
- raw JSONをページ単位で保存
- tweet_idでUPSERT
- 429時は長めにsleep
- cursor単位で中断再開

ただし、今すぐ全面移行するとまた詰まる可能性があります。  
まずは gallery-dl の出力パース修正が先です。

---

## 取得漏れ検証

最低限この3つを入れてください。

### 1. 日別件数テーブル

```sql
account, date, expected_min, fetched_count, status
```

### 2. tweet_id重複排除

```sql
tweet_id PRIMARY KEY
```

### 3. raw JSON保存

正規化ミスに備えて、GraphQL/galllery-dlの生出力を保存。

```sql
raw_pages(
  account TEXT,
  start_date TEXT,
  end_date TEXT,
  source TEXT,
  raw_json TEXT,
  fetched_at TEXT
)
```

DBに入らなかった時でも、rawが残っていれば再パースできます。

---

## BTC自動売買の観点

**100%取得を待つ必要はない**です。  
83,901件、27%でも先に分析を進めるべきです。

おすすめは二系統で進めること。

1. 既存83,901件で分析・特徴量・バックテストを開始
2. 取得パイプラインは別途修正して増分取得

100%収集完了を待つと、売買ロジック開発が数週間止まります。これは悪手です。

---

## 次の具体的手順

1. `fetch_all_dumpjson.py` を停止
2. 成功済み3日のdump-jsonファイルを確認
3. JSON Linesとして再パース
4. DB追加されるか単体テスト
5. failedログに returncode/stderr/elapsed/timeout/429 を保存
6. 取得単位を7日へ戻す
7. 失敗時だけ 7日→3日→1日に分割
8. raw JSON保存テーブルを追加
9. 83,901件でBTC分析を先に開始
10. 並行して独自GraphQL実装を小さくPoCする

結論：  
**今は全件取得を継続する局面ではなく、パース修正と失敗原因分類が先です。**  
その後、週単位＋分割再試行に変えれば、数週間級には短縮できる可能性があります。
### 回答

1. **`sleep-request`最適値**
   - `50 req / 15 min = 1 req / 18 sec`
   - 設定は **18〜20秒 + jitter** が妥当。
   - 例：
     ```bash
     -o sleep-request=19
     ```
   - ただし、これは「429を避ける」設定であって、総取得時間は大きく短縮しない。  
     バーストして14分待つか、19秒ずつ待つかの違い。

2. **理論上1000件/15分出ない理由**
   主因はこれです。

   - SearchTimelineの1ページは「20ツイート保証」ではない
     - cursor
     - user object
     - tombstone
     - unavailable/deleted/protected
     - 会話スレッド
     - 重複
     - promoted / instruction
     が混じる。
   - `count=20`でも有効ツイートは数件〜十数件になることがある。
   - 検索条件が週単位でも、該当密度が低いと空ページ・重複ページが増える。
   - gallery-dlはGraphQL cursorを追うため、1週間の境界に対して効率よく二分探索しているわけではない。
   - 429後の待機、リトライ、subprocess timeoutで進捗が無駄になる可能性がある。

   なので実効は **1000件/15分ではなく、数百件/15分以下** と見るべき。

3. **同じcookie連続実行でrate limitが残るか**
   - **残る。**
   - rate limitはプロセス単位ではなく、概ね以下の単位で共有される。
     - authenticated account
     - guest token / csrf
     - cookie session
     - endpoint: `SearchTimeline`
     - 場合によりIP
   - gallery-dlを終了して再実行しても、`x-rate-limit-reset`までは消費済み。
   - 「厳しくなる」というより、**前ジョブの残り枠を引き継ぐ**。
   - 各ジョブ間で必ず固定待機するより、理想はレスポンスヘッダの
     - `x-rate-limit-remaining`
     - `x-rate-limit-reset`
     を見て待つこと。

---

### 次の実装方針

#### 1. gallery-dl運用なら暫定設定

```bash
-o sleep-request=19
-o retries=999
-o retry-codes=429,500,502,503,504
```

subprocess timeoutは **撤廃または6時間以上**。  
20分/60分 timeout はSearchTimelineには不向き。

---

#### 2. ジョブ単位を「週」ではなく「cursor checkpoint」にする

SQLiteに以下を保存。

```sql
CREATE TABLE IF NOT EXISTS search_jobs (
  id INTEGER PRIMARY KEY,
  account TEXT,
  since TEXT,
  until TEXT,
  cursor TEXT,
  status TEXT,
  last_tweet_id TEXT,
  fetched_count INTEGER DEFAULT 0,
  request_count INTEGER DEFAULT 0,
  rate_remaining INTEGER,
  rate_reset INTEGER,
  updated_at TEXT
);
```

429やプロセス停止時に、最後のcursorから再開する。

---

#### 3. 取得済みtweetは即時SQLite保存

```sql
CREATE TABLE IF NOT EXISTS tweets (
  tweet_id TEXT PRIMARY KEY,
  account TEXT,
  created_at TEXT,
  raw_json TEXT,
  fetched_at TEXT
);
```

- dump-jsonを最後にまとめてparseしない
- 1ページ取得ごとに即insert
- `INSERT OR IGNORE`で重複排除

---

#### 4. 取得漏れ検証

週ごとに以下を記録。

```sql
CREATE TABLE IF NOT EXISTS coverage (
  account TEXT,
  since TEXT,
  until TEXT,
  min_tweet_time TEXT,
  max_tweet_time TEXT,
  tweet_count INTEGER,
  cursor_exhausted INTEGER,
  checked_at TEXT,
  PRIMARY KEY(account, since, until)
);
```

検証ルール：

- `cursor_exhausted=1` まで到達したか
- 取得tweetの `created_at` が `since <= created_at < until` に収まるか
- 週の境界付近で欠けていないか
- 前後週でtweet_id重複があるか
- 空週の場合、本当に空なのか再試行対象にする

---

#### 5. 本命はgallery-dl依存をやめる

Playwrightでログイン済みcookie取得 → GraphQL `SearchTimeline`を直接叩く。

理由：

- `x-rate-limit-reset`を正確に読める
- cursorをSQLiteに保存できる
- 429時に正確にsleepできる
- ページ単位で中断再開できる
- gallery-dl subprocess timeout問題を消せる

実装順：

1. PlaywrightでXログイン済みcontextを作成
2. cookie / csrf token / bearer token取得
3. SearchTimeline GraphQL URLとvariablesを特定
4. Python `httpx` で同じheaders/cookieを使って実行
5. cursor、tweet、rate headersをSQLite保存
6. `remaining == 0` なら `reset + 5秒` までsleep
7. cursor exhaustedで週完了

---

### 結論

- `sleep-request`は **19秒**。
- ただし速度改善にはならない。429待ちを平準化するだけ。
- 同じcookieではrate limitは当然引き継がれる。
- 今のボトルネックはgallery-dlではなく **SearchTimeline 50req/15min**。
- 改善の本筋は、gallery-dl subprocess運用をやめて、GraphQL cursor・rate header・SQLite checkpointを自前管理すること。
DBを直接見られていないので確定判断は不可ですが、16:30時点の改善提案は以下です。

### まず見るべきDB差分

```sql
-- 総件数
SELECT COUNT(*) FROM tweets;

-- 直近1時間の増分
SELECT COUNT(*) FROM tweets
WHERE inserted_at >= datetime('now', '-1 hour');

-- 重複確認
SELECT tweet_id, COUNT(*) c
FROM tweets
GROUP BY tweet_id
HAVING c > 1
LIMIT 20;

-- 週単位ジョブごとの取得数
SELECT window_start, window_end, COUNT(*)
FROM tweets
GROUP BY window_start, window_end
ORDER BY window_start;
```

### 改善判断

- **1時間で件数が安定増加している**  
  → sleep-request=19、timeout=6hのまま継続でよい。今いじらない。

- **DB件数が20〜30分以上増えていない**  
  → cursor停止、rate limit、GraphQL失敗、Playwright待機失敗の可能性。  
  次回から `cursor / status_code / response size / retry count` を必ず保存。

- **重複が多い**  
  → `tweet_id UNIQUE` + `INSERT OR IGNORE` にする。  
  JSON dumpとSQLite登録を分離し、DB側で冪等化。

- **週単位で取得数が極端に多い週がある**  
  → 週単位は粗すぎる。  
  その週だけ日単位、または6時間単位に分割して再走行。

- **途中で落ちる可能性がある**  
  → `job_state` テーブルに以下を保存して中断再開可能にする。

```sql
CREATE TABLE IF NOT EXISTS job_state (
  job_key TEXT PRIMARY KEY,
  window_start TEXT,
  window_end TEXT,
  cursor TEXT,
  last_tweet_id TEXT,
  updated_at TEXT
);
```

### 次の実装手順

1. 現在の走行は止めずに完走させる。  
2. 1時間ごとに `tweets増分 / 重複数 / 最終inserted_at` を記録。  
3. JSON保存時に `cursor` と `response metadata` も一緒に保存。  
4. SQLiteは `tweet_id UNIQUE`、`INSERT OR IGNORE` 化。  
5. 取得数が多い週だけ日単位へ分割して再取得。  
6. 停止時は最後のcursorまたはwindowから再開する。  

現状、sleep-request=19はかなり安全寄りです。DB増分が安定しているなら、今は速度改善より取得漏れ検証と再開性の確保を優先した方がよいです。
判断: **切り替えるべき**です。  
今の `gallery-dl subprocess 1ジョブ1起動` は構造的に遅すぎます。残り23万件規模では不適。

ただし、期待値は注意です。  
**直接SearchTimeline実装で速くなるのは「起動・認証・ジョブ間待機の無駄」部分**で、X側のGraphQL rate limit自体は消えません。とはいえ現状13件/時は明らかに運用方式が悪いので、移行判断でよいです。

次の実装手順:

1. **gallery-dl内部を読む**
   - `SearchTimeline` の `queryId`
   - `features`
   - `variables`
   - cursor位置
   - authヘッダ/cookie構成  
   を抽出。

2. **requests/httpxで長寿命クライアント化**
   - 1プロセスでcookie/tokenを再利用
   - `x-csrf-token`
   - `authorization: Bearer ...`
   - `auth_token`, `ct0` cookie
   - 必要ならPlaywrightでログイン済みcookie更新。

3. **cursor paginationを自前管理**
   - bottom cursorをSQLiteに保存
   - 1ページ取得ごとにtweet保存 + cursor保存
   - 中断再開可能にする。

4. **SQLite保存**
   - `tweets(tweet_id primary key, user, created_at, raw_json, fetched_at)`
   - `jobs(query/user, cursor, status, last_seen_id, updated_at)`
   - 重複は `INSERT OR IGNORE`

5. **rate limit対応**
   - 429/空レスポンス時は指数バックオフ
   - account単位で待機
   - 並列数は最初1〜2で測定、無理に増やさない。

6. **取得漏れ検証**
   - ページ間でtweet_id連続性/時刻範囲を記録
   - 同一queryを再走査して差分検出
   - `cursor進んだのに新規0件` を異常扱い。

結論:  
**gallery-dlは参考実装として残し、取得本体は直接GraphQL実装へ移行。**  
まず1アカウント/1クエリでPoCして、`件/時`, `429頻度`, `cursor安定性`, `DB重複率` を測るべきです。
結論：**gallery-dl subprocess方式に戻すのが最短で現実的**です。  
404はTLSよりも **queryId / headers / x-client-transaction-id / guest-token / cookie更新などアプリ層差分**の可能性が高いです。

---

## 1. gallery-dlのsession/auth処理を直接importできるか？

**可能だが非推奨。**

理由：

- gallery-dl内部APIは安定していない
- extractorごとの状態管理が複雑
- queryId更新、guest token、csrf、headers、transaction-id生成が内部に散らばる
- importしても結局gallery-dl本体の内部仕様に依存する

やるなら「ライブラリ利用」ではなく、**gallery-dlを長期起動プロセスとして使う設計**の方が安全。

---

## 2. curl_cffiで解決するか？

**解決する可能性は低い。**

curl_cffiが効くのは主に：

- TLS fingerprint
- HTTP/2 fingerprint
- Chrome風handshake

今回：

- gallery-dlはPython requests系で200
- 独自requests / Node fetchで404

なので、TLS fingerprintよりも：

- GraphQL `queryId` が古い/違う
- `features` / `variables` の差分
- `x-client-transaction-id`
- `x-twitter-active-user`
- `x-twitter-auth-type`
- guest token
- cookie / ct0更新
- endpointパス

あたりが原因の可能性が高いです。

---

## 3. gallery-dl dump-json subprocessに戻すべきか？

**はい。現実的にはこれが最優先。**

最適化方針：

### A. URLごとに毎回起動しない

NG：

```bash
gallery-dl --dump-json URL1
gallery-dl --dump-json URL2
gallery-dl --dump-json URL3
```

OK：

```bash
gallery-dl --dump-json URL1 URL2 URL3 ...
```

またはURLリストをまとめて渡す。

---

### B. stdoutを逐次JSONLとして読む

Python側：

- `subprocess.Popen`
- stdoutを1行ずつ読む
- 1 tweet/itemごとにSQLite保存
- 途中失敗しても保存済みは残す

---

### C. SQLiteに進捗保存

最低限テーブル：

```sql
jobs(
  id INTEGER PRIMARY KEY,
  query TEXT UNIQUE,
  status TEXT,
  started_at TEXT,
  finished_at TEXT,
  last_error TEXT
);

tweets(
  tweet_id TEXT PRIMARY KEY,
  query TEXT,
  json TEXT,
  created_at TEXT
);
```

`tweet_id PRIMARY KEY` にして重複排除。

---

### D. 中断再開

再開時：

```sql
SELECT query FROM jobs WHERE status IN ('pending', 'running', 'failed');
```

取得済みtweetは `INSERT OR IGNORE`。

---

### E. 取得漏れ検証

各ジョブで記録：

- 取得件数
- 最古tweet日時
- 最新tweet日時
- gallery-dl終了コード
- stderr
- rate limit / auth error有無

可能なら同じ検索を2回走らせて、tweet_id集合差分を確認。

---

## 推奨実装順

1. **独自SearchTimeline実装はいったん停止**
2. gallery-dl `--dump-json` subprocessに戻す
3. 複数queryを1プロセスにまとめる
4. stdout逐次読み取り
5. SQLiteへ `INSERT OR IGNORE`
6. jobsテーブルで中断再開
7. stderr/returncodeを保存
8. 取得漏れ検証として再実行差分チェック
9. それでも遅ければ、gallery-dlの長期常駐ラッパー化を検討

---

要するに、今詰まっている404は **HTTPクライアント差分ではなくX GraphQL実装追従の問題**です。  
Claude Codeにやらせるなら、次は **「gallery-dl subprocess + SQLite永続化 + 再開可能ジョブキュー」** に絞るのが良いです。
### 1. 理論値の0.7%しか出ない理由

「50req/15min × 20件」は **全ページが未取得ツイート20件で埋まる場合の上限**。実測28件/時は、たぶん以下のどれか。

- **gallery-dlが取得しているのが UserMedia 系**で、画像/動画付きだけ
- 1ページ20件に見えても、実際は  
  - 既取得重複  
  - RT/引用/返信除外  
  - tombstone/削除/非公開  
  - 広告/モジュール/空entry  
  が混ざる
- **SQLiteへの新規insert数だけ見ている**ため、取得数ではなく「純増」が小さい
- 429/待機/内部sleepで **50req/15minを使い切っていない**
- pagination cursorが浅い/同じ範囲をループしている

まず見るべきは「リクエスト数」「JSON内tweet数」「新規insert数」を分けること。

---

### 2. `gallery-dl --dump-json` が画像付きだけの可能性

**まだ十分ある。むしろ最有力。**

gallery-dlは基本がメディアDLツールなので、URL指定やextractorによっては **media timeline / UserMedia 相当**になり、テキストのみツイートは落ちる可能性が高い。

検証方法は簡単。

1. danjerの既知のテキストのみツイートURLを1件選ぶ  
2. `gallery-dl --dump-json <そのtweet URL>` で出るか確認  
3. アカウントtimeline指定でそのtweet IDが出るか確認  
4. X画面/Playwrightで見える件数とgallery-dl出力IDを突合

これで「media-onlyか」はすぐ判定できる。

---

### 3. gallery-dl継続で速度改善余地はあるか

**小さい。根本改善はendpoint変更。**

gallery-dlが UserMedia を叩いている限り、50req/15minを使い切っても **有効ツイート密度が低い**ので純増は伸びない。

改善余地はこの程度。

- 429が出ていないなら並列度を少し上げる
- アカウントごとに分散実行
- 重複URLを減らす
- cursor停止/ループを検知
- SQLite insertをバッチ化

ただし、テキストのみ欠落が目的なら **gallery-dl継続では限界**。

---

## 次の実装手順

1. **計測ログ追加**
   - endpoint
   - cursor
   - HTTP status
   - rate-limit remaining/reset
   - JSON内tweet数
   - 新規insert数
   - 重複数

2. **media-only検証**
   - 既知のテキストのみtweet IDを10件用意
   - gallery-dl出力に含まれるか確認

3. **PlaywrightでGraphQL UserTweetsを直接取得**
   - gallery-dlではなくX WebのGraphQL timelineを使う
   - `UserTweets` / `UserTweetsAndReplies` を対象
   - bottom cursorでpagination
   - text-only含むtweet IDを保存

4. **SQLiteに状態保存**
   - `tweets(tweet_id unique, user_id, text, created_at, raw_json)`
   - `cursors(account, endpoint, cursor, updated_at)`
   - `request_log(endpoint, cursor, status, count, inserted, remaining)`

5. **中断再開**
   - accountごとに最後のbottom cursorを保存
   - 起動時にそこから再開
   - 同一cursor再出現なら停止

結論: **今の28件/時はrate limit問題より、取得endpoint/有効密度/重複の問題の可能性が高い。まずmedia-only判定、その後Playwright GraphQLへ切替。**
判断: **分析を並行開始すべき。取得は継続。ただし「全件取得完了待ち」はやめる。**

理由:
1. **43件/時では全件前提の計画は破綻**  
   220日は現実的でない。今の84,274件で先に傾向分析・分類・重複確認を始めるべき。

2. **ただし「rate limitだけが原因」と断定は早い**  
   50req/15minなら理論上はもっと出る。  
   ボトルネックはおそらく以下も混ざっている:
   - 重複URL/重複cursor
   - SearchTimelineの古い領域で新規ヒット率低下
   - クエリ分割不足
   - gallery-dl側のpagination効率

3. **次にやるべき実装**
   - SQLiteに `tweet_id UNIQUE` で保存継続
   - `crawl_state` テーブル追加  
     `url/query, cursor, last_seen_id, last_request_at, status`
   - 1リクエストごとに  
     `returned_count / inserted_count / duplicate_count / 429有無 / cursor` を記録
   - `inserted_count per request` が低いURLを停止または再分割
   - 日付範囲で `since/until` 分割して新規率を測る

4. **Playwrightは本取得ではなく検証用**
   - gallery-dlの取得漏れ確認
   - 特定日・特定ユーザー・特定検索語で目視/DOM比較
   - 本格取得に使うとさらに不安定化しやすい

結論:  
**今の84,274件で分析開始。取得はバックグラウンド継続。並行して「新規件数/req」を計測し、低効率URLを日付分割で改善する。全件完了を待つ判断はしない。**
前提：私の知識は 2024-06 までで、2025-2026 の新規GitHub動向をリアルタイム確認はできません。  
ただし、現状の詰まり方を見る限り、問題は「新ツール不足」より **X側のGraphQL・検索・カーソル・rate limit・bot判定の制約に正面から当たっている** ことです。

---

## 結論

現実的には次のどれかです。

1. **gallery-dl SearchTimeline を中核にして、期間分割・並列・中断再開・漏れ検証を改善する**
2. **twscrape系を検証するが、アカウント凍結・壊れやすさ前提**
3. **PlaywrightでUIではなくNetwork JSONを保存する補助ルートを作る**
4. **公式X APIはFreeでは全件取得に使えない。Pro/Enterprise以外は補助用**
5. **curl_cffiでgallery-dlの内部GraphQLを完全模倣する方向は、コストが高く不安定**

---

# 質問への回答

## 1. 2025-2026に新しい有力手法はあるか？

実践的には、大きなブレイクスルーは期待しにくいです。

現在も有効な系統は以下です。

| 方法 | 実用性 | コメント |
|---|---:|---|
| gallery-dl SearchTimeline | 高 | 遅いが安定しやすい |
| twscrape系 GraphQL | 中 | 速い可能性はあるが凍結・仕様変更リスク大 |
| Playwright + Network capture | 中 | DOMスクロールよりJSON保存が重要 |
| 公式X API v2 | 低〜高 | Free/Basicは不可。Pro/Enterpriseなら可 |
| Wayback CDX | 補助 | ID発掘用 |
| snscrape | 低 | 旧Twitter時代の方式はほぼ死んでいる前提 |
| Nitter系 | 低 | 多くが停止・不安定 |

新しい「万能な全件取得ツール」は期待せず、**複数経路でIDを発掘し、SQLiteで統合し、欠落区間を狭める設計**にした方がよいです。

---

## 2. snscrape後継、twscrapeの状況

### snscrape
ほぼ後継の本命ではないです。

理由：

- Xのログイン壁・GraphQL化・rate limit強化に弱い
- 検索HTML取得ベースの手法が成立しにくい
- メンテが止まりがち

### twscrape
候補にはなります。

特徴：

- Python async
- Xの内部GraphQLを使う系統
- アカウントセッション管理あり
- SQLiteでアカウント状態を持つ実装が多い
- gallery-dlより高速になる可能性あり

ただし注意：

- X側変更で突然壊れる
- アカウントロック・認証要求が起きやすい
- 複数アカウント運用は規約・リスク面で注意
- SearchTimelineの深い履歴取得は結局制限される可能性あり

使うなら、**本番置換ではなく、gallery-dlで遅い区間を埋める補助取得器**として試すべきです。

---

## 3. gallery-dlより速いX取得ツールはあるか？

候補はありますが、安定性ではgallery-dlがまだ強いです。

| ツール/手法 | 速度 | 安定性 | 推奨度 |
|---|---:|---:|---:|
| gallery-dl SearchTimeline | 遅い | 高 | 本線 |
| twscrape | 中〜速 | 中〜低 | 補助検証 |
| Playwright Network取得 | 中 | 中 | 欠落区間用 |
| 有料スクレイピングAPI/Apify系 | 速い場合あり | サービス次第 | 費用次第 |
| curl_cffi自作GraphQL | 速い可能性 | 低 | 非推奨 |

あなたの現状では、ツール変更より先に **gallery-dlのジョブ設計を改善する方が効果が大きい** です。

今の「週単位で一晩+460件」は遅すぎます。  
原因はおそらく：

- 欠落が少ない期間も総当たりしている
- SearchTimelineのカーソルを最後まで舐めている
- 重複が多い
- 保存済みIDによる早期打ち切りが弱い
- 期間分割が固定で密度に合っていない

---

## 4. curl_cffi + Pythonでgallery-dlのSearchTimelineを直接叩く方法

ここは注意です。  
Xの内部GraphQL認証・TLS fingerprint・`x-client-transaction-id`等を模倣して制限を回避する具体手順は推奨できません。

ただし、技術的に詰まった原因はほぼこれです。

### requests直接で404になる主な原因

同じheadersに見えても、gallery-dlと完全には同じではありません。

差分候補：

- TLS fingerprint
- HTTP/2設定
- cookie jar
- `ct0` と `x-csrf-token` の一致
- guest token
- bearer token
- GraphQL queryId/hash
- features JSON
- variables JSONの順序・エンコード
- `x-twitter-active-user`
- `x-twitter-auth-type`
- `x-twitter-client-language`
- `x-client-transaction-id`
- セッションのbot score
- リクエスト順序
- 直前に踏むべき初期化API
- SearchTimelineのoperation name変更
- X側の偽装404

特にGraphQLは、**URL・queryId・featuresが少しでもズレると404/403/400になる**ことがあります。

### 実務上のおすすめ

直接再実装ではなく、以下に寄せるべきです。

1. **gallery-dlをライブラリ/サブプロセスとして呼ぶ**
2. gallery-dlのdebug logを保存する
3. 出力JSONをSQLiteへ正規化する
4. 期間・カーソル・失敗状態を自前SQLiteで管理する
5. 遅い部分だけtwscrape/Playwrightで補完する

つまり、**gallery-dlの認証処理を再現するのではなく、gallery-dlを取得エンジンとして使う**方が早いです。

---

## 5. X API v2 Free tierは使えるか？

全件取得には使えません。

理由：

- 月1500件程度なら 313,000件には桁違いに足りない
- Free/Basicは履歴検索が弱い
- full-archive searchは通常Pro/Enterprise級
- 期間2〜5年分の穴埋めには不十分
- rate limitも厳しい

使い道があるとすれば：

- 既知IDのhydrate
- 最近投稿の検証
- 欠落判定の補助
- 少量アカウントの最新分取得

本気で公式APIだけでやるなら、必要なのは基本的に：

- Full-archive search
- user timeline
- expansions
- pagination token
- 十分な monthly post cap

つまり有料上位プランです。

---

## 6. 複数アカウントでrate limit分散できるか？

技術的には、twscrape系や自作管理で可能な場合があります。  
ただし、規約・凍結・認証チャレンジのリスクが高いです。

実務的にはこう考えるべきです。

### やるなら最低条件

- 自分が管理権限を持つアカウントのみ
- 各アカウントごとにcookie/sessionを分離
- SQLiteでrate limit状態を記録
- 429/403/ログイン要求を検知したら即停止
- 同一IP・同一挙動の高頻度アクセスを避ける
- 長時間低速で回す

### ただし推奨構成

「rate limit突破」ではなく、

- アカウントA：gallery-dl本線
- アカウントB：Playwright検証
- アカウントC：twscrape実験
- 失敗したら自動でバックオフ

のように、**取得経路の冗長化**として使う方が安全です。

---

## 7. 見落としている手法

あります。特に重要なのは以下です。

---

# 見落とし1：固定週単位ではなく adaptive window にする

週単位固定は非効率です。

やるべきは：

- 欠落が多い期間は日単位・時間単位に分割
- 欠落が少ない期間は月単位に拡大
- 取得済みIDが多いwindowは早期終了
- 0件windowは即完了
- 取得件数が上限っぽいwindowは二分割

例：

```text
2020-01-01〜2020-02-01
  ↓ 取得件数が多い
2020-01-01〜2020-01-15
2020-01-15〜2020-02-01
  ↓ まだ多い
日単位へ
```

SearchTimelineは深いページングに弱いので、**カーソルを深掘りするより期間を細かく切る**方が安定します。

---

# 見落とし2：SQLiteで window 単位の状態管理をする

最低限このテーブルを持つべきです。

```sql
CREATE TABLE IF NOT EXISTS tweets (
  tweet_id TEXT PRIMARY KEY,
  user_id TEXT,
  screen_name TEXT,
  created_at TEXT,
  text TEXT,
  raw_json TEXT,
  source TEXT,
  inserted_at TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS fetch_windows (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  screen_name TEXT,
  since TEXT,
  until TEXT,
  query TEXT,
  source TEXT,
  status TEXT,
  cursor TEXT,
  fetched_count INTEGER DEFAULT 0,
  new_count INTEGER DEFAULT 0,
  retry_count INTEGER DEFAULT 0,
  last_error TEXT,
  started_at TEXT,
  finished_at TEXT,
  updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
  UNIQUE(screen_name, since, until, source)
);

CREATE TABLE IF NOT EXISTS fetch_log (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  window_id INTEGER,
  source TEXT,
  status_code INTEGER,
  new_count INTEGER,
  duplicate_count INTEGER,
  cursor TEXT,
  error TEXT,
  created_at TEXT DEFAULT CURRENT_TIMESTAMP
);
```

重要なのは、tweet単位ではなく **window単位で中断再開できること**です。

---

# 見落とし3：取得漏れ検証を月別ヒートマップで行う

今は「84,734/313,000」という全体進捗だけですが、これでは次にどこを掘るべきか分かりません。

必要なのは：

```sql
SELECT
  screen_name,
  substr(created_at, 1, 7) AS ym,
  COUNT(*) AS count
FROM tweets
GROUP BY screen_name, ym
ORDER BY screen_name, ym;
```

これで月別件数を出して、

- 極端に少ない月
- 0件の月
- 前後月と比べて異常に少ない月
- SearchTimeline済みなのに少ない月

を優先します。

---

# 見落とし4：313,000件という母数を疑う

Xのプロフィール上の投稿数は、完全な取得可能件数とは一致しません。

含まれる可能性：

- 削除済み投稿
- 非公開化された投稿
- 凍結/制限投稿
- RT
- replies
- quote tweets
- コミュニティ投稿
- 検索に出ない投稿
- センシティブ/検索除外
- spam判定で非表示
- API/GraphQLで到達不能な古い投稿

したがって、313,000件を絶対母数にすると永遠に100%にならない可能性があります。

検証すべき母数は：

```text
取得可能な公開投稿数
≠ プロフィール表示のstatuses_count
```

です。

---

# 見落とし5：PlaywrightはDOMスクロールではなくNetwork JSON保存に使う

Playwright UIスクロールが遅いのは当然です。  
DOMから拾うのではなく、GraphQLレスポンスを保存してください。

方針：

1. Playwrightでログイン済みstorage stateを使う
2. Advanced Search URLを開く
3. Network responseのJSONだけ保存
4. tweet IDをSQLiteへINSERT OR IGNORE
5. DOMパースはしない

用途は本線ではなく、**gallery-dlが取れないwindowの検証用**です。

---

# Claude Codeが詰まった原因

おそらく原因はこれです。

## 1. UserTweetsAndRepliesの170ページ打ち切り

これは実装ミスではなく、X側のtimeline pagination制約の可能性が高いです。

- cursorが返っても中身が空になる
- 一定ページ以降ランキング/制限で出ない
- 古い投稿がtimeline endpointから落ちる
- endpoint自体が全件アーカイブ用ではない

対策：

- UserTweetsAndRepliesを全件取得の本線にしない
- SearchTimelineの日付分割へ切り替える

---

## 2. requests直接GraphQLの404

headersをコピーしても足りません。

原因候補：

- TLS fingerprint差
- HTTP/2差
- cookies/CSRF不一致
- GraphQL queryId差
- features差
- transaction id差
- bot判定
- 初期化リクエスト不足

対策：

- 直接模倣を本線にしない
- gallery-dlを呼び出して結果だけSQLite保存
- どうしても比較するならHAR/debugログで差分確認まで

---

## 3. Playwright UIスクロールの重複

XのUIは仮想リストなので、DOM取得は重複しやすいです。

対策：

- DOMではなくNetwork responseを保存
- tweet_idでdedupe
- cursor/window単位で保存

---

# 次の実装手順

## Step 1：gallery-dlを本線としてSQLite投入

gallery-dlの出力JSONをすべてSQLiteへ入れる。

必須：

- `tweet_id PRIMARY KEY`
- `raw_json`保存
- `source='gallery-dl-search'`
- `INSERT OR IGNORE`

---

## Step 2：5アカウント×月単位の欠落表を作る

月別件数を出す。

```sql
SELECT screen_name, substr(created_at,1,7) ym, COUNT(*)
FROM tweets
GROUP BY screen_name, ym;
```

件数が少ない月から優先処理。

---

## Step 3：adaptive windowキューを作る

固定週単位をやめる。

ルール：

```text
取得0件 → 完了
新規少数 → 完了
取得多数/ページ深い/重複多い → windowを半分に分割
429/403 → retry_after付きで保留
既取得率が高い → 早期終了
```

---

## Step 4：gallery-dlを非重複windowで2〜4並列

同じwindowを複数プロセスで走らせない。

```text
worker1: accountA 2019-01
worker2: accountB 2020-05
worker3: accountC 2021-11
```

ただしrate limitが出たら並列数を下げる。

---

## Step 5：twscrapeを補助検証

gallery-dlで取れない月だけ試す。

保存時は必ず：

```text
source='twscrape'
```

として区別する。

---

## Step 6：Playwright Network captureを最後の補助にする

対象：

- gallery-dlで0件だがUI検索では見える期間
- 重複だらけで進まない期間
- 特定月の検証

DOMではなくJSONレスポンス保存。

---

## Step 7：313,000件ではなく「取得可能母数」を再推定

月別・アカウント別に、

- SearchTimeline
- UserTweetsAndReplies
- Wayback ID
- Playwright Network
- 公式API少量hydrate

を突き合わせて、到達不能分を分離する。

---

# 優先度つきTODO

最短で改善するならこの順です。

1. **SQLiteにwindow管理テーブルを追加**
2. **週単位固定をやめてadaptive window化**
3. **月別欠落ヒートマップ作成**
4. **gallery-dlを2〜4並列で非重複window処理**
5. **取得済みIDが多いwindowの早期打ち切り**
6. **twscrapeを欠落月だけ試験投入**
7. **PlaywrightはNetwork JSON保存だけに使う**
8. **curl_cffi完全模倣は後回し、または捨てる**

---

## 最終判断

今のボトルネックはツール選定より、**取得計画と状態管理**です。

おすすめ構成はこれです。

```text
gallery-dl SearchTimeline
  ↓
SQLite tweets / windows / logs
  ↓
月別欠落検出
  ↓
adaptive window再投入
  ↓
twscrape補助
  ↓
Playwright Network補助
  ↓
取得漏れ検証
```

curl_cffiでgallery-dlを再実装するより、gallery-dlをそのまま取得器として使い、周辺の **キュー制御・SQLite保存・中断再開・漏れ検証** を強化する方が、成功確率は高いです。
優先度順に **3つだけ** です。

## 1. GraphQLのcursor取得ループをSQLite保存前提で実装する

最優先は「1ページ取得するたびに必ず保存して、途中停止しても再開できる」状態にすることです。

### 実装手順

1. SQLiteに最低限この3テーブルを作る。

```sql
CREATE TABLE IF NOT EXISTS tweets (
  tweet_id TEXT PRIMARY KEY,
  user_id TEXT,
  created_at TEXT,
  text TEXT,
  raw_json TEXT NOT NULL,
  fetched_at TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS cursors (
  target_user TEXT,
  timeline_type TEXT,
  cursor TEXT,
  status TEXT,
  updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (target_user, timeline_type)
);

CREATE TABLE IF NOT EXISTS raw_pages (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  target_user TEXT,
  timeline_type TEXT,
  cursor TEXT,
  response_json TEXT NOT NULL,
  fetched_at TEXT DEFAULT CURRENT_TIMESTAMP
);
```

2. X WebのGraphQL `UserTweets` / `UserTweetsAndReplies` をPlaywrightのログイン済みセッションで叩く。

対象は最低2系統：

- `UserTweets`
- `UserTweetsAndReplies`

3. 1レスポンスごとに必ず以下を保存する。

- tweets本体を `tweets` に `INSERT OR IGNORE`
- 生レスポンスを `raw_pages` に保存
- 次のbottom cursorを `cursors` に保存

4. cursorが無くなるまで回す。

疑似コード：

```ts
while (true) {
  const cursor = loadCursor(user, timelineType);

  const res = await fetchGraphQLTimeline({
    userId,
    timelineType,
    cursor,
  });

  await db.transaction(async () => {
    saveRawPage(user, timelineType, cursor, res);
    upsertTweets(extractTweets(res));
    saveCursor(user, timelineType, extractBottomCursor(res));
  });

  const nextCursor = extractBottomCursor(res);

  if (!nextCursor || nextCursor === cursor) break;

  await sleep(randomBetween(3000, 8000));
}
```

これを最初に入れる理由は、Claude Codeが詰まる典型原因が「取得・保存・再開」が分離できておらず、途中で落ちると進捗が消えることだからです。

---

## 2. rate limit / 空ページ / 重複cursor対策を入れる

次に、止まらず長時間回せるようにします。

### 実装手順

1. HTTPステータスとレスポンス内容で分岐する。

```ts
if (status === 429) {
  await sleep(15 * 60 * 1000);
  retrySameCursor();
}

if (status >= 500) {
  await sleep(backoffMs);
  retrySameCursor();
}

if (responseContainsRateLimitOrUnavailable(res)) {
  await sleep(10 * 60 * 1000);
  retrySameCursor();
}
```

2. 同じcursorが連続したら停止ではなく、記録して別ルートに回す。

```sql
CREATE TABLE IF NOT EXISTS cursor_errors (
  target_user TEXT,
  timeline_type TEXT,
  cursor TEXT,
  reason TEXT,
  created_at TEXT DEFAULT CURRENT_TIMESTAMP
);
```

3. `seen_cursor` をメモリまたはSQLiteで管理する。

```ts
if (seenCursors.has(nextCursor)) {
  saveCursorError(user, timelineType, nextCursor, "duplicate_cursor");
  break;
}
seenCursors.add(nextCursor);
```

4. リトライ回数をcursor単位で持つ。

```sql
CREATE TABLE IF NOT EXISTS retry_state (
  target_user TEXT,
  timeline_type TEXT,
  cursor TEXT,
  retry_count INTEGER DEFAULT 0,
  PRIMARY KEY(target_user, timeline_type, cursor)
);
```

5. sleepは固定値ではなくランダムにする。

```ts
await sleep(randomBetween(5000, 15000));
```

これで長時間取得時の停止率を下げます。

---

## 3. 取得漏れ検証用にSearchTimeline補完を実装する

最後に、GraphQL timelineだけで取れない投稿を埋めるため、検索補完を入れます。

### 実装手順

1. SQLiteに検索ウィンドウ管理テーブルを作る。

```sql
CREATE TABLE IF NOT EXISTS search_windows (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  target_user TEXT,
  since_date TEXT,
  until_date TEXT,
  status TEXT DEFAULT 'pending',
  fetched_count INTEGER DEFAULT 0,
  updated_at TEXT DEFAULT CURRENT_TIMESTAMP
);
```

2. 対象ユーザーの投稿期間を月単位または週単位に分割する。

例：

```txt
from:username since:2020-01-01 until:2020-02-01
from:username since:2020-02-01 until:2020-03-01
...
```

3. PlaywrightでX検索を開く。

```ts
await page.goto(
  `https://x.com/search?q=${encodeURIComponent(query)}&src=typed_query&f=live`
);
```

4. 検索結果をスクロールしながらtweet URLを回収する。

```ts
const urls = await page.locator('a[href*="/status/"]').evaluateAll(links =>
  links.map(a => a.href)
);
```

5. 取得済みの `tweets.tweet_id` と照合し、未保存tweetだけ詳細取得する。

```ts
if (!existsTweet(tweetId)) {
  const detail = await fetchTweetDetail(tweetId);
  upsertTweet(detail);
}
```

6. 1ウィンドウ完了ごとに `search_windows.status = 'done'` にする。

これで `UserTweets` / `UserTweetsAndReplies` のcursor取得で漏れた分を、日付検索で補完できます。  
まずはこの3つだけ実装してください。
結論から言うと、**今の本命は gallery-dl 継続 + SQLiteで中断再開/欠落検証を固めること**です。  
`twscrape` はまだ捨てなくてよいですが、今回の `UserTweets` エラーは「速度比較」以前に **endpoint/レスポンス形式の不整合で落ちている**可能性が高いです。

---

## 1. twscrape と gallery-dl は rate limit を共有するか？

**同じ cookie / 同じ X アカウント / 同じ GraphQL operation なら、ほぼ共有すると見てよい**です。

特に以下は共有されやすいです。

- 同じ `auth_token`
- 同じ `ct0`
- 同じ web bearer token
- 同じ GraphQL operation, 例: `SearchTimeline`

GraphQL は operation ごとに bucket が分かれることがありますが、**同一アカウントで同一 SearchTimeline を叩くなら 2倍にはなりません**。  
むしろ gallery-dl と twscrape を同時に走らせると、

- remaining を食い合う
- 429 が増える
- cursor 途中で失敗する
- account lock / cooldown が増える

可能性が高いです。

### ただし

`twscrape UserTweets` と `gallery-dl SearchTimeline` は、operation が違うなら bucket が別の可能性はあります。  
でも今回の目的が「danjer の欠落44週分の media 回収」なら、**UserTweets と SearchTimeline は取得意味が違う**ので注意です。

- `SearchTimeline`: `from:danjer filter:media since:... until:...`
- `UserTweets`: プロフィールタイムライン相当

欠落補完には SearchTimeline の日付分割の方が安定しやすいです。

---

## 2. twscrape の方が速い可能性はあるか？

**単一アカウントでは大きく速くなる可能性は低い**です。

理由:

- ボトルネックは Python の同期/非同期ではなく X 側の rate limit
- async でも同じ bucket を消費するだけ
- page size / count を増やしても X 側が返す件数に上限がある
- cursor pagination は結局ページ数が必要

ただし、次の場合は twscrape の方が速い可能性があります。

### 速くなる可能性があるケース

1. gallery-dl より sleep が保守的すぎる場合  
2. twscrape が gallery-dl と別 operation を使っていて bucket が別の場合  
3. twscrape の SearchTimeline 実装が gallery-dl より少ないリクエストで同じ量を取れる場合  
4. 複数アカウントを正当に使えて、アカウントごとに job 分割する場合

ただし今回のログ:

```txt
Unknown error. Account timeouted for 15 minutes.
Err: <class 'IndexError'>: list index out of range
No account available for queue "UserTweets"
```

これは rate limit というより、**twscrape がレスポンスの配列構造を想定して IndexError で死んでいる**ように見えます。

ありがちな原因:

- X 側の GraphQL レスポンス形式変更
- UserTweets operation の instructions 構造変更
- 空レスポンス/エラーレスポンスを正常系として parse してしまった
- cookie は通っているが追加認証/制限/soft block のレスポンスが返っている
- twscrape のバージョンが現行 X に追従できていない

なので、まず `UserTweets` ではなく **SearchTimeline 相当で小さく検証**した方がいいです。

---

## 3. Embedded Timeline / syndication API で全件取得できるか？

**全件取得はほぼ無理です。**

X Embedded Timeline / syndication 系は以下の制約があります。

- 取得件数が少ない
- 古い投稿まで深く遡れない
- cursor が限定的
- media 情報が不完全なことがある
- rate limit / guest token 制約がある
- replies / retweets / sensitive / unavailable が落ちる
- 検索条件 `since/until/filter:media` の細かい制御に向かない

用途としては、

- 最新数件の確認
- tweet id が既知の投稿の埋め込み情報取得
- 軽い存在確認

くらいです。

**44週分の欠落補完の主力にはならない**です。

---

## 4. まだ試す価値がある手法

優先度順に書きます。

---

# A. twscrape は UserTweets ではなく SearchTimeline で試す

今回のエラーは `queue "UserTweets"` です。  
gallery-dl と比較したいなら、同じ意味のクエリに寄せるべきです。

試す対象:

```txt
from:danjer filter:media since:YYYY-MM-DD until:YYYY-MM-DD
```

または必要なら:

```txt
from:danjer since:YYYY-MM-DD until:YYYY-MM-DD
```

その上で media 有無は自前で判定。

見るべき点:

- 1ページあたり何件返るか
- cursor が最後まで進むか
- gallery-dl と同じ tweet_id が取れるか
- 欠落が増えないか
- 429 / lock が出るか

`twscrape UserTweets` が壊れていても、`SearchTimeline` 側は動く可能性があります。

---

# B. rate limit 共有の実測

仮説で悩むより、ヘッダを見るのが早いです。

見るヘッダ:

```txt
x-rate-limit-limit
x-rate-limit-remaining
x-rate-limit-reset
```

検証方法:

1. gallery-dl で SearchTimeline を1ページ取得
2. 直後に twscrape で同じ SearchTimeline を1ページ取得
3. 両方の `remaining/reset` を比較
4. remaining が連続して減っていれば同一 bucket

gallery-dl だけでヘッダが見づらいなら、Playwright または mitmproxy 的に一度だけ観測するのがよいです。

---

# C. Playwright は「高速化」ではなく「診断/補完」に使う

Playwright でログイン済みブラウザを立てて、

```txt
https://x.com/search?q=from%3Adanjer%20filter%3Amedia%20since%3A2025-01-01%20until%3A2025-01-08&f=live
```

のような検索ページを開き、GraphQL `SearchTimeline` レスポンスを intercept します。

用途:

- X Web UI では結果が出ているのか確認
- gallery-dl が落としている tweet_id があるか確認
- cursor がどこで止まるか確認
- raw JSON を保存して parser の差分を見る

ただし、**Playwright でも同じアカウントなら rate limit は同じ**です。  
高速化目的ではなく、取得漏れ検証・レスポンス観察用に使うべきです。

---

# D. 日付分割をもっと細かくする

SearchTimeline は長い期間を一気に取ると、内部ランキング/検索上限/カーソル打ち切りで漏れることがあります。

44週欠落を処理するなら、週単位ではなく以下を推奨します。

```txt
1日単位
または
投稿数が多い日は 6時間単位
```

例:

```txt
from:danjer filter:media since:2025-01-01 until:2025-01-02
from:danjer filter:media since:2025-01-02 until:2025-01-03
...
```

1日単位で件数が多すぎる日はさらに:

```txt
since:2025-01-01_00:00 until:2025-01-01_06:00
since:2025-01-01_06:00 until:2025-01-01_12:00
...
```

X 検索が時刻指定を完全に安定処理するかはケース次第なので、まず日単位が無難です。

---

# E. SQLite で job / cursor / tweet を管理する

今の状態だと「一晩で +460 件」は安定していて良いです。  
次は速度より **中断再開と漏れ検証**を固めた方がいいです。

最低限のテーブル:

```sql
CREATE TABLE IF NOT EXISTS jobs (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  source TEXT NOT NULL,
  query TEXT NOT NULL,
  since_date TEXT,
  until_date TEXT,
  cursor TEXT,
  status TEXT NOT NULL DEFAULT 'pending',
  attempts INTEGER NOT NULL DEFAULT 0,
  last_error TEXT,
  updated_at TEXT
);

CREATE TABLE IF NOT EXISTS tweets (
  tweet_id TEXT PRIMARY KEY,
  user_id TEXT,
  username TEXT,
  created_at TEXT,
  text TEXT,
  raw_json TEXT NOT NULL,
  source TEXT,
  fetched_at TEXT
);

CREATE TABLE IF NOT EXISTS media (
  media_id TEXT,
  tweet_id TEXT NOT NULL,
  type TEXT,
  url TEXT,
  video_url TEXT,
  raw_json TEXT,
  PRIMARY KEY (media_id, tweet_id)
);

CREATE TABLE IF NOT EXISTS rate_limits (
  source TEXT,
  operation TEXT,
  limit_count INTEGER,
  remaining INTEGER,
  reset_at TEXT,
  observed_at TEXT
);
```

重要なのは `jobs.cursor` です。  
1ページごとに cursor を保存すれば、途中で死んでも再開できます。

---

# F. 取得漏れ検証は「重複窓」でやる

日付窓を完全に隣接させると、境界漏れが起きます。

悪い例:

```txt
2025-01-01 until 2025-01-02
2025-01-02 until 2025-01-03
```

改善:

```txt
2025-01-01 until 2025-01-03
2025-01-02 until 2025-01-04
```

のように 1日オーバーラップさせ、SQLite 側で `tweet_id` dedupe します。

検証方法:

- 同じ tweet_id が複数窓で取れるか
- 窓境界の日の投稿が片方だけになっていないか
- gallery-dl と twscrape / Playwright の tweet_id set を比較
- 取得件数が異常に少ない日を再キュー

---

# G. 2アカウント運用するなら job 分割

2つ目の正規アカウントがあるなら、速度改善の可能性はあります。

ただしやるなら:

- account A: 2024-01〜2024-06
- account B: 2024-07〜2024-12

のように job を分ける。

同じ日付範囲を両方で同時に叩くのは無駄です。

SQLite の `jobs` に `assigned_account` を持たせるとよいです。

```sql
ALTER TABLE jobs ADD COLUMN assigned_account TEXT;
```

---

## 今回の twscrape エラーへの具体対応

まずこれ。

```bash
twscrape reset_locks
```

ただし、根本解決前に連打しない方がいいです。

次に確認:

1. twscrape を最新版にする  
2. `UserTweets` ではなく `SearchTimeline/search` を試す  
3. limit 小さめ、1日分だけで試す  
4. raw response を保存できるなら保存  
5. 同じクエリを gallery-dl で実行して tweet_id を比較

もし SearchTimeline でも `IndexError` なら、今の twscrape は X の現行レスポンスに追従できていない可能性が高いです。  
その場合は無理に使わず、gallery-dl 主体に戻すのがよいです。

---

## おすすめの次手順

短く言うとこれです。

1. **gallery-dl は継続**  
   安定しているなら止めない。

2. **SQLite に tweet_id / media / job / cursor を保存**  
   中断再開と重複排除を先に完成させる。

3. **欠落44週を週単位ではなく日単位 job に分解**  
   多い日はさらに分割。

4. **twscrape は UserTweets ではなく SearchTimeline で小テスト**  
   1日分、limit 小さめで gallery-dl と tweet_id 比較。

5. **Playwright で SearchTimeline の raw GraphQL を1回観測**  
   rate limit header、cursor、レスポンス構造を見る。

6. **rate limit header を記録して bucket 共有を実測**  
   共有なら並列実行しない。

7. **2アカウントがあるなら job を日付範囲で分配**  
   SQLite で dedupe。無理に同じ範囲を叩かない。

---

## 個人的な判断

今のログを見る限り、`twscrape UserTweets` に時間を使いすぎるのは危険です。  
本線は、

```txt
gallery-dl SearchTimeline
+ 日付細分化
+ SQLite checkpoint
+ tweet_id set 差分検証
+ Playwright でGraphQL観測
```

です。

`twscrape` は「SearchTimeline で gallery-dl と同じ結果が取れるか」だけ確認し、取れるなら補助投入。  
取れない/IndexError が続くなら切ってよいと思います。
Claude側の詰まり原因はほぼ明確です。  
`twscrape UserTweets` が X の GraphQL レスポンス構造変更に追従できず、固定位置の list 参照で落ちています。なので「UserTweets をそのまま直す」より、まず取得系を複線化して、漏れ検証できる形にするのが良いです。

---

## 結論：次はこの順でやるべき

### 1. gallery-dl を一次取得系として固める
`twscrape` より今は `gallery-dl` の方が実用性が高そうです。

やること：

- `gallery-dl --dump-json` または metadata 出力で tweet JSON を保存
- SQLite に保存
- `tweet_id` を UNIQUE にする
- 1ページ/1件ごとに即コミット
- 取得済み ID は再実行時にスキップ
- cookie/account ごとの rate limit/cooldown を記録

複数 cookie があるなら「同一制限をすり抜ける」目的ではなく、許可されたアカウント単位で queue を分ける形にする。  
同じユーザー timeline を複数 cookie で同時に殴るより、対象ユーザーや日付範囲で分割した方が安全。

---

### 2. twscrape SearchTimeline は短時間だけ試す
UserTweets が壊れていても SearchTimeline は別経路なので試す価値あり。

試すクエリ：

```text
from:USERNAME
```

できれば Latest/Live 相当で取得。

さらに漏れ防止には日付分割：

```text
from:USERNAME since:2024-01-01 until:2024-02-01
from:USERNAME since:2024-02-01 until:2024-03-01
```

重要なのは SearchTimeline はランキング/検索制限/古いツイート欠落が起きやすいこと。  
なので本採用する前に、gallery-dl 結果と直近 200〜1000 件で突き合わせる。

判定基準：

- gallery-dl にある tweet_id が SearchTimeline にもあるか
- 逆に SearchTimeline にしかないものがあるか
- retweet/reply/media/tombstone がどう扱われるか
- cursor が最後まで進むか
- 日付降順が崩れないか

1〜2時間で無理なら深追いしない。

---

### 3. Playwright を「認証フロー模倣」ではなく「ネットワーク取得器」として使う
`curl_cffi` で gallery-dl の認証フロー完全模倣は、今やると沼る可能性が高いです。  
代わりに Playwright でログイン済みブラウザを使い、X の GraphQL レスポンスを intercept する方が現実的。

方針：

- Playwright で `x.com/USERNAME` を開く
- 下スクロール
- `page.on("response")` で以下を捕捉
  - `/i/api/graphql/`
  - `UserTweets`
  - `UserTweetsAndReplies`
  - `SearchTimeline`
- レスポンス JSON を raw のまま SQLite に保存
- パーサは後から改修可能にする

これにより X 側の認証/CSRF/header 変化をブラウザに任せられる。  
curl_cffi 再実装より保守性が高いです。

---

## SQLite は最初に設計しておくべき

最低限この3テーブル。

### `tweets`

```sql
CREATE TABLE IF NOT EXISTS tweets (
  tweet_id TEXT PRIMARY KEY,
  user_id TEXT,
  screen_name TEXT,
  created_at TEXT,
  text TEXT,
  json TEXT NOT NULL,
  source TEXT,
  fetched_at TEXT DEFAULT CURRENT_TIMESTAMP
);
```

### `raw_pages`

```sql
CREATE TABLE IF NOT EXISTS raw_pages (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  target TEXT,
  endpoint TEXT,
  cursor TEXT,
  next_cursor TEXT,
  status_code INTEGER,
  json TEXT,
  fetched_at TEXT DEFAULT CURRENT_TIMESTAMP
);
```

### `jobs`

```sql
CREATE TABLE IF NOT EXISTS jobs (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  target TEXT NOT NULL,
  method TEXT NOT NULL,
  cursor TEXT,
  since_date TEXT,
  until_date TEXT,
  oldest_tweet_id TEXT,
  newest_tweet_id TEXT,
  status TEXT DEFAULT 'pending',
  updated_at TEXT DEFAULT CURRENT_TIMESTAMP
);
```

ポイント：

- raw JSON を必ず保存する
- パース失敗しても raw から再処理できる
- cursor を job に残す
- tweet_id UNIQUE で重複を吸収
- 中断再開は cursor または日付範囲単位

---

## 取得漏れ検証は必須

単に「最後までスクロールできた」では信用できないです。

検証方法：

### A. 隣接ページの重なり確認

ページ境界で tweet_id が少し重複するか確認。  
まったく重複なしで古い方へ飛ぶ場合は欠落の可能性あり。

### B. created_at が単調に古くなっているか

timeline なら基本的に新しい順。  
突然 2024 → 2022 へ飛ぶなどがあれば穴を疑う。

### C. Snowflake ID から時刻推定

tweet_id は Snowflake なので時刻に変換可能。  
`created_at` と大きくズレる、または ID 範囲が飛ぶ場合はログに出す。

### D. 日付窓で再取得

1ヶ月単位や1週間単位で SearchTimeline を使い、gallery-dl/Playwright の結果と突き合わせる。

例：

```text
from:USERNAME since:2023-01-01 until:2023-02-01
```

件数が多い月はさらに週単位に分割。

### E. 2方式比較

理想は：

- gallery-dl
- Playwright GraphQL capture
- twscrape SearchTimeline

のうち2系統で直近 N 件を比較。  
一致率が低い方式は本番採用しない。

---

## rate limit 対応

必要なのは高速化より「止まっても壊れない」こと。

実装方針：

- account/cookie 単位の queue
- endpoint 単位の cooldown
- 429 や一時エラーは exponential backoff
- `x-rate-limit-remaining`
- `x-rate-limit-reset`
- 取得ページごとに cursor 保存
- 同一 account で並列リクエストしすぎない

SQLite に `rate_limits` を持っても良いです。

```sql
CREATE TABLE IF NOT EXISTS rate_limits (
  account TEXT,
  endpoint TEXT,
  remaining INTEGER,
  reset_at INTEGER,
  cooldown_until INTEGER,
  updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY(account, endpoint)
);
```

---

## 各案への評価

### 1. twscrape SearchTimeline

試す価値あり。  
ただし本命ではなく、検証用・補完用として扱う。

優先度：中

---

### 2. gallery-dl 並列化

良い。  
ただし同一対象を雑に並列化するより、対象ユーザー/日付範囲で queue 分割する。

優先度：高

---

### 3. 2025-2026 最新ツールの Web 検索

やるべき。  
ただし時間を区切る。

探す対象：

- `twscrape UserTweets IndexError`
- `twscrape X response format changed`
- `gallery-dl twitter x.com extractor issue`
- `x.com GraphQL UserTweets timeline_v2`
- `SearchTimeline cursor x.com`
- maintained fork of twscrape
- Playwright X GraphQL capture examples

ただし、未知ツールに全面移行するより、まず SQLite/raw保存/再開/検証基盤を作る方が優先。

優先度：中

---

### 4. curl_cffi で gallery-dl 認証フロー完全模倣

今は非推奨。  
これは最後の手段。

理由：

- X 側の header/feature flag/CSRF/token 変更に弱い
- gallery-dl がすでにやっている処理を再実装することになる
- 認証成功しても pagination/cursor/response parse でまた詰まる可能性が高い

やるなら先に gallery-dl の extractor をライブラリ的に呼ぶ、または subprocess で安定運用する方が早い。

優先度：低

---

## Claude に次にやってほしい具体手順

### Step 1

gallery-dl で 1ユーザー分を `--dump-json` 取得し、tweet_id / created_at / raw_json を SQLite に保存する。

### Step 2

中断再開を実装する。  
1ページごと、または1ツイートごとに commit。  
再実行時は tweet_id 重複を無視。

### Step 3

Playwright で同じユーザーの timeline を開き、GraphQL レスポンスを raw_pages に保存する。

### Step 4

gallery-dl と Playwright の tweet_id 集合を比較する。

出すレポート：

```text
gallery-dl count:
playwright count:
common:
gallery_only:
playwright_only:
newest:
oldest:
```

### Step 5

twscrape SearchTimeline を `from:USERNAME` と日付分割で試す。  
同じく tweet_id 集合比較。

### Step 6

一番漏れが少ない方式を primary にして、他方式を補完/検証用にする。

---

## 追加で試してほしいこと

- gallery-dl の raw 出力に cursor 相当が残っているか確認
- X GraphQL の `timeline_v2.timeline.instructions` を raw 保存しているか確認
- `TimelineAddEntries` の中の `TimelineTimelineItem` と `TimelineTimelineCursor` を分けて処理できるか確認
- tombstone / unavailable / protected / deleted tweet をどう保存するか決める
- replies を含めるのか、media tweet だけなのか、retweet を含めるのかを先に固定する
- `UserTweets` と `UserTweetsAndReplies` の差分を比較する
- SearchTimeline は月単位で件数が多ければ週単位に再分割する

---

## 最終方針

今はこう進めるのが一番堅いです。

```text
gallery-dl primary
+ Playwright GraphQL capture fallback/oracle
+ twscrape SearchTimeline experimental補完
+ SQLite raw保存
+ cursor/job保存
+ tweet_id突き合わせで漏れ検証
```

`curl_cffi` 再挑戦は、上記でどうしても足りない場合の最後でいいです。  
先に「取得できた/できない」ではなく、「どれだけ漏れたかを検出できる基盤」を作るべきです。
短く判断です。

## 1. 方向は正しいか？

**半分正しい。だが `x-client-transaction-id` だけが原因とは断定しない方がいい。**

直接 GraphQL が 404 になる主因候補は以下。

- `x-client-transaction-id` 欠落 / 不正
- `queryId` が古い
- `features` / `fieldToggles` が現行 Web とズレている
- cookie / `ct0` / `auth_token` / `x-csrf-token` 不一致
- `User-Agent` / `x-twitter-active-user` / `x-twitter-client-language` 不足
- SearchTimeline の endpoint / operationName / variables が現行とズレている
- X 側の anti-bot cloaking として 404 を返している

なので、**transaction-id 実装は必要条件の可能性が高いが、十分条件ではない**です。

進めるなら、まず Playwright で実際の SearchTimeline リクエストを捕捉し、Python requests で **同一 cookie・同一 headers・同一 queryId・同一 variables** を再送して成功するか確認するべきです。

---

## 2. gallery-dl のキャッシュからキーを流用できるか？

**可能性はあるが、実装依存・期限依存なので本線にしない方がいい。**

gallery-dl の `cache.sqlite3` には取得済みの JS / metadata / token 系が入っている可能性がありますが、

- cache schema が gallery-dl 内部仕様
- X の JS hash 更新で即死する
- `twitter-site-verification` や ondemand JS と整合しないと失敗する
- 複数アカウント / 複数セッションでズレる可能性

があります。

使うなら **デバッグ用・一時回避用**。  
本実装では、

- HTML から verification 取得
- 現行 JS hash 解決
- KEY_BYTE indices 抽出
- SQLite に TTL 付きキャッシュ
- 404 / 401 / 403 / 抽出失敗時に再取得

の方がよいです。

---

## 3. Playwright で捕捉した transaction-id を使い回せるか？

**基本不可。使い回し前提は危険。**

`x-client-transaction-id` は通常、

- request path
- method
- 時刻
- animation key
- verification key
- random 要素

などに依存する想定です。

そのため、**1個捕捉して全リクエストに使い回すのは失敗しやすい**です。  
前回 404 だったのは「使い古し」だけでなく、**対象 URL / queryId / variables と transaction-id の対応がズレていた**可能性もあります。

Playwright は transaction-id 再利用ではなく、以下に使うべきです。

- 正しい GraphQL endpoint の特定
- 最新 queryId の取得
- features / fieldToggles の取得
- cursor pagination の実リクエスト確認
- headers 差分確認
- 取得漏れ検証用の基準データ作成

---

# 推奨実装手順

## Step 1: Playwright で SearchTimeline を捕捉

まずブラウザ実通信を保存。

保存対象:

- URL
- method
- headers
- cookies
- queryId
- operationName
- variables
- features
- fieldToggles
- response body
- cursor
- rate-limit headers

SQLite に `captured_requests` として保存。

---

## Step 2: Python requests で完全再送テスト

Playwright で捕捉した **最新の1リクエスト** を Python requests で再送。

この時点では transaction-id も捕捉値をそのまま使ってよい。

判定:

- 成功 → headers / cookie / queryId は概ね正しい
- 404 → transaction-id 以外にも差分あり
- 401 / 403 → cookie / csrf / auth 問題
- 429 → rate limit
- 200 だが空 → variables / search query / cursor 問題

---

## Step 3: transaction-id generator を差し替え可能に実装

いきなり本体に埋め込まない。

```text
TransactionIdProvider
  - generate(method, path)
  - refresh_keys()
  - load_cache()
  - save_cache()
```

SQLite キャッシュ:

```sql
transaction_keys(
  id integer primary key,
  site_verification text,
  ondemand_js_url text,
  key_indices_json text,
  animation_key text,
  created_at integer,
  expires_at integer
)
```

404 が出たら、

1. queryId 更新確認
2. features 更新確認
3. transaction keys refresh
4. cookie refresh
5. retry

の順で切り分け。

---

## Step 4: cursor pagination を requests 側で管理

SearchTimeline response から cursor を抽出。

見るべき cursor:

- `Bottom`
- `ShowMore`
- `TimelineTimelineCursor`

保存:

```sql
search_runs(
  run_id text primary key,
  query text,
  since_cursor text,
  next_cursor text,
  status text,
  started_at integer,
  updated_at integer
)

pages(
  id integer primary key,
  run_id text,
  cursor text,
  response_hash text,
  item_count integer,
  fetched_at integer,
  status_code integer
)

tweets(
  tweet_id text primary key,
  user_id text,
  created_at text,
  text text,
  raw_json text,
  first_seen_run_id text,
  fetched_at integer
)
```

中断再開は `search_runs.next_cursor` から再開。

---

## Step 5: 取得漏れ検証

最低限これを入れる。

- page ごとの tweet_id 数
- 重複率
- cursor が進んでいるか
- 前ページ末尾 tweet_id と次ページ先頭 tweet_id の連続性
- 同一 query を Playwright と requests で数ページ比較
- gallery-dl 結果との差分比較

差分検証用テーブル:

```sql
tweet_sources(
  tweet_id text,
  source text,
  run_id text,
  seen_at integer,
  primary key(tweet_id, source, run_id)
)
```

`source = playwright / requests / gallery-dl`

---

# 結論

- **transaction-id 実装方針は妥当**
- ただし **404 の原因を transaction-id 単独に固定しない**
- gallery-dl cache 流用はデバッグ用途まで
- 捕捉した transaction-id の使い回しは不可寄り
- Playwright は「正解リクエストを観測する道具」として使う
- 本実装は `queryId/features/cursor/transaction/cookie` を全部 SQLite に保存して、失敗時に個別 refresh できる構造にするべきです。
1. **transaction-idの使い回し回数**
   - 固定保証なし。基本は**1リクエストごとに変わる前提**で扱うべきです。
   - 同じIDで複数回200が返る可能性はありますが、X側の検証が緩いだけで、将来/条件次第で403・400・429・空結果になり得ます。
   - 「何回使えるか」は環境依存なので、実測するなら低頻度で `same transaction-id + different cursor` を20〜50回試して失敗率を見る。

2. **自前生成 vs 定期捕捉**
   - 短期実装なら **Playwrightで定期捕捉** が良いです。
   - 自前生成はXの難読化JS依存で壊れやすく、保守コストが高い。
   - おすすめは：
     - PlaywrightでSearchTimelineを1回発火
     - headers/cookies/bearer/guest or auth token/transaction-idを捕捉
     - Python requestsで取得
     - 403/400/429が出たらPlaywrightで再捕捉

3. **cursor paginationで同じIDを使い続けてよいか**
   - 推奨しません。**cursorごと、つまりHTTPリクエストごとに新しいtransaction-id** が安全です。
   - ただし実務上は、同じIDで数ページ取れるなら暫定利用は可能。
   - 重要なのは、200でも取得漏れがあり得るので、以下を保存・検証すること。

次の実装手順：

```text
1. SQLiteに保存
   - query
   - cursor
   - response_json/raw
   - tweet_id
   - fetched_at
   - transaction_id
   - status_code
   - error

2. pagination
   - responseからbottom cursor抽出
   - 次リクエストへ渡す
   - cursor既出なら停止
   - tweet_id重複排除

3. 中断再開
   - queryごとの最後の未処理cursorをSQLiteに保存
   - 再起動時そこから再開

4. 取得漏れ検証
   - ページごとのtweet件数
   - 新規tweet_id数
   - cursor連続性
   - 連続0件/同一cursor/重複急増を異常扱い

5. rate limit対応
   - 429, 403, 空レスポンスで指数バックオフ
   - transaction-id再捕捉
   - cookie/tokenも必要なら再捕捉
```

結論：  
**今は自前生成せず、Playwright捕捉 + requests取得 + 失敗時再捕捉** が最短で安定です。Cursorごとは本来新しいtransaction-id推奨です。
概ね合意。詰まった主因は **gallery-dlが同一cookie/accountのSearchTimeline枠を消費していたこと**。Playwright側は `remaining=2` から始まっていたので、性能評価が歪んでいた。

ただし注意点あり。

## 注意点

1. **3 responses / 39件だけでは4,000件/時は暫定値**
   - SearchTimelineはページごとの件数が安定しない。
   - 古い期間・重複・削除済み・鍵・引用混入で効率が落ちる可能性あり。

2. **月単位クエリは広すぎる可能性**
   - X検索は深いpaginationで抜け・打ち切りが起きやすい。
   - 月で詰まるなら週単位、日単位に分割するべき。

3. **429は固定15分sleepよりreset header優先**
   - GraphQL response headerの  
     `x-rate-limit-remaining`  
     `x-rate-limit-reset`  
     を保存して、reset時刻までsleep。

4. **取得漏れ検証が必須**
   - `tweet_id UNIQUE`でSQLite保存。
   - 各クエリ範囲ごとに件数、最古tweet時刻、最新tweet時刻、cursorを記録。
   - 期間境界は `since/until` に1日程度のオーバーラップを入れて重複除去。

5. **UIスクロールだけに依存しすぎない**
   - response捕捉はOK。
   - ただしresponse内の `cursor` / `bottom cursor` / timeline instructions を保存する。
   - 再開時に同じ検索条件からスクロール再開できるようにする。

## 次の実装手順

1. **gallery-dl完全停止**
   - 同じcookie/account/IPで並行アクセスしない。

2. **Playwright SearchTimeline捕捉を本線化**
   - `SearchTimeline` responseを保存。
   - tweet本体、cursor、rate limit headerをSQLiteへ保存。

3. **SQLite設計**
   - `tweets(tweet_id PRIMARY KEY, created_at, user_id, text, raw_json)`
   - `jobs(query, since, until, status, last_cursor, min_tweet_id, max_tweet_id, fetched_count)`
   - `rate_limits(endpoint, remaining, reset_at)`

4. **検索範囲分割**
   - まず月単位で試す。
   - cursorが止まる、件数が少ない、時系列ギャップが出る場合は週/日単位へ自動分割。

5. **pagination**
   - スクロールで追加responseを発火。
   - `remaining=0` or `429` 検知で停止。
   - `x-rate-limit-reset` までsleepして再開。

6. **取得漏れ検証**
   - 各期間の取得tweetを時刻順に並べる。
   - 大きな時間ギャップ、突然のcursor終了、想定件数より少ない期間を再クロール。
   - 境界日はオーバーラップ取得して `tweet_id` で重複排除。

結論：**方針は正しい**。ただし「月単位で58時間」は楽観値。まず1〜2ヶ月分を本実装で流して、件数/時、cursor停止率、漏れ率を測ってから全量実行が安全。
原因は「PlaywrightでスクロールしていればAPI枠を消費してページングできる」という設計になっている点です。  
実際には **GraphQL cursor pagination / rate limit / reset時刻** を直接制御できておらず、UIスクロールと `noNew` 判定に依存しているため、枠を使い切れていません。

---

## Claude案への評価

### 1. 429後に別windowへ切り替える
同じアカウント・同じGraphQL endpointなら基本的に無意味です。  
rate limitはだいたい以下の単位で効きます。

- account / auth cookie
- endpoint / operationName
- IPやguest token
- bearer / client context

同じendpointならwindowを変えても429は続きます。  
有効なのは以下だけです。

- 別アカウント
- 別endpoint
- 別IP / proxy
- 別token系統

---

### 2. `noNew` 10 → 20
根本解決ではないです。  
429後ならいくらスクロールしてもresponseは来ません。

ただし、429ではなく「スクロールが浅くて次ページrequestが発火していない」ケースなら効果はあります。  
なので `noNew` 固定ではなく、以下で分岐すべきです。

- GraphQL 429を受けた → resetまで停止
- GraphQL 200だがitems 0 → cursor終端扱い
- GraphQL request自体が出ていない → scroll制御の問題
- cursorが変わっていない → pagination停止

---

### 3. 2週間window → 1ヶ月window
多少は効く可能性があります。  
ただし、単純に広げると取得漏れリスクがあります。

特にSearchTimeline系は深いpaginationで打ち切られたり、ランキング/フィルタ都合で古いtweetが抜けることがあります。  
おすすめは固定1ヶ月ではなく **動的window分割** です。

- 件数が少ない月は1ヶ月
- 件数が多い期間は1週間/3日/1日へ分割
- cursor終端まで到達できたwindowだけ完了扱い

---

### 4. 429待ち中に別アカウント/別endpointを叩く
これは有効です。  
ただし同一endpoint・同一アカウントでは無意味です。

有効な並列化は以下です。

- account AでSearchTimeline
- account BでSearchTimeline
- account AでUserMedia
- account AでTweetDetailなど別endpoint
- 別target user
- 別proxy付きaccount

---

## GPT側の改善案

### 最優先: UIスクロールをやめてGraphQL cursorを直接叩く

Playwrightはログイン済みcookieとheaders取得用に使い、取得本体は以下に寄せるべきです。

1. PlaywrightでXにログイン
2. NetworkからGraphQL endpoint, queryId, variables, featuresを取得
3. response内の `cursor` を抽出
4. `page.evaluate(fetch(...))` かNode側HTTPで同じGraphQLを直接実行
5. `cursor` を更新しながらpagination
6. 429なら `x-rate-limit-reset` までsleep
7. reset後、同じcursorから再開

UIスクロールは不安定で、request発火がXのフロント実装に依存します。  
cursor直叩きにすれば、50req/15minなら50reqをほぼ使い切れます。

---

## まず確認すべき実測ログ

今の「50req/15min」という前提が本当にそのendpointに適用されているか確認してください。

GraphQL responseごとにSQLiteかJSONLへ保存。

```text
timestamp
operationName
url
status
x-rate-limit-limit
x-rate-limit-remaining
x-rate-limit-reset
tweet_count
cursor_before
cursor_after
window_since
window_until
```

見るべき点:

- 本当にlimit=50か
- 14回目でremaining=0になっていないか
- reload時に何req消費しているか
- SearchTimeline以外のGraphQLが勝手に枠を食っていないか
- 429のreset時刻は何分後か
- 1 responseあたりtweet何件取れているか

234件/時 ÷ 28responses/時 = 約8.3件/response なので、responseあたりの取得量も低いです。

---

## 具体的な次の実装手順

### Step 1: responseロガーを入れる

Playwrightで全GraphQL responseを記録。

```js
page.on('response', async res => {
  const url = res.url();
  if (!url.includes('/graphql/')) return;

  const headers = res.headers();
  const status = res.status();

  console.log({
    time: new Date().toISOString(),
    url,
    status,
    limit: headers['x-rate-limit-limit'],
    remaining: headers['x-rate-limit-remaining'],
    reset: headers['x-rate-limit-reset'],
  });
});
```

まず「14 responseで止まる理由」を確定させる。

---

### Step 2: reloadを禁止する

429後のreloadはquotaを無駄にします。  
429を受けたら以下だけ行う。

```text
reset_epoch + 5秒までsleep
同じcursorから再開
```

ページ再読み込みは原則しない。

---

### Step 3: cursorをSQLiteに保存する

最低限このテーブルを作る。

```sql
CREATE TABLE IF NOT EXISTS windows (
  id INTEGER PRIMARY KEY,
  query TEXT NOT NULL,
  since TEXT NOT NULL,
  until TEXT NOT NULL,
  cursor TEXT,
  status TEXT NOT NULL DEFAULT 'pending',
  last_tweet_id TEXT,
  last_tweet_time TEXT,
  request_count INTEGER NOT NULL DEFAULT 0,
  updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS tweets (
  tweet_id TEXT PRIMARY KEY,
  created_at TEXT,
  user_id TEXT,
  screen_name TEXT,
  text TEXT,
  raw_json TEXT NOT NULL,
  fetched_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS requests (
  id INTEGER PRIMARY KEY,
  window_id INTEGER,
  operation_name TEXT,
  status_code INTEGER,
  rate_limit INTEGER,
  rate_remaining INTEGER,
  rate_reset INTEGER,
  cursor_before TEXT,
  cursor_after TEXT,
  tweet_count INTEGER,
  created_at TEXT NOT NULL
);
```

中断時は `windows.cursor` から再開。

---

### Step 4: GraphQLを直接paginateする

Playwrightで捕まえたSearchTimeline/UserMediaのrequestを再利用する。

疑似コード:

```text
while window not complete:
    call GraphQL with cursor
    if status == 429:
        sleep_until(rate_reset + 5)
        continue

    extract tweets
    upsert tweets into SQLite

    extract bottom cursor
    if no cursor or no new tweets:
        mark window complete
        break

    save cursor
```

UI scrollはバックアップ扱いにする。

---

### Step 5: window幅を動的にする

固定2週間/1ヶ月ではなく、密度で変える。

```text
最初は1ヶ月window
↓
1ヶ月でpaginationが深すぎる / 429前に終端へ到達しない
↓
2週間へ分割
↓
それでも深い
↓
1週間 / 3日 / 1日へ分割
```

完了条件はこれ。

```text
そのwindowの最古tweet日時 <= since
または
cursor終端
または
連続N回、新規tweet_idなし
```

単なる `noNew 10回` ではなく、cursorとtweet時刻で判定する。

---

### Step 6: responseあたり件数を増やす

GraphQL variablesの `count` を確認してください。

- `count: 20` なら40/50に上げて試す
- server側capで無視される可能性あり
- UserMedia endpointの方がSearchTimelineより件数効率が高い可能性あり
- `filter:media` が不要なら外す/必要なら維持
- queryは `from:user since:YYYY-MM-DD until:YYYY-MM-DD` を明示

目標は最低でも **15〜20 tweets/response**。  
今の8.3 tweets/responseは低いです。

---

## 取得漏れ検証

必ず二段階で検証する。

### 1. window内の完了検証

各windowで以下を保存。

```text
max_created_at
min_created_at
tweet_count
cursor終端到達有無
最終cursor
```

完了条件:

```text
min_created_at <= since
または
GraphQL cursor終端
```

`until`側から降順取得しているなら、最古tweetがsinceを超えるまで取る。

---

### 2. 日別件数ヒストグラム

取得後に日別件数を出す。

```sql
SELECT substr(created_at, 1, 10) AS day, COUNT(*)
FROM tweets
GROUP BY day
ORDER BY day;
```

急に0件や極端に少ない日があれば、その日だけ再取得。

---

### 3. 再取得比較

ランダムにwindowを選び、別条件で再取得。

例:

```text
初回: 1ヶ月window
検証: 1日window
```

差分tweet_idが出るなら、広いwindowで漏れている。

---

## 速度見込み

今は:

```text
28 responses/時 × 8.3 tweets = 234件/時
```

GraphQL直叩きでrate枠を使い切れれば、仮に本当に50req/15minなら:

```text
200 responses/時 × 8.3 tweets = 1,660件/時
```

さらにresponseあたり15件にできれば:

```text
200 responses/時 × 15 tweets = 3,000件/時
```

23万件なら:

```text
230,000 / 3,000 = 約77時間
```

複数アカウント2本なら約1.5日程度まで短縮可能。

---

## 結論

次にやるべき順番はこれです。

1. GraphQL responseのrate limit headerを全記録  
2. 429後のreloadを廃止  
3. cursorをSQLiteへ保存  
4. PlaywrightスクロールではなくGraphQL cursor直叩きに変更  
5. reset時刻までsleepして同じcursorから再開  
6. windowを密度に応じて自動分割  
7. 日別件数と再取得差分で漏れ検証  
8. 必要なら別アカウント/別endpointで並列化  

Claude案の中では「別アカウント/別endpointを叩く」は有効ですが、最優先ではありません。  
まずは **cursor直叩き + rate header制御 + SQLite中断再開** に変えるのが一番効きます。
了解。現状は **234件/時で安定稼働継続**、`page.evaluate fetch` は **rate limit空き時間に再検証**で問題ありません。

次回11時までの確認ポイント：

1. **取得漏れ検証**
   - 直近取得IDの連続性確認
   - 同一検索条件で再取得した際の差分件数確認
   - 重複率・欠損率をログ化

2. **cursor / pagination**
   - 最後に使用したcursorをSQLiteへ保存
   - ページ遷移失敗時に同じcursorから再開できることを確認
   - 空ページ・同一cursorループを検知して停止/スキップ

3. **rate limit**
   - 429 / retry-after / x-rate-limit系ヘッダを保存
   - Playwright通常取得と `page.evaluate fetch` の消費差を比較予定
   - rate limit空き時のみ再検証でOK

4. **SQLite保存**
   - `tweet_id` など一意キーでUPSERT
   - 取得時刻、検索条件、cursor、raw JSONを保存
   - コミット単位を小さめにして中断耐性を維持

5. **中断再開**
   - 最終成功cursor
   - 最終成功tweet_id
   - 最終保存時刻
   - rate limit状態  
   を再起動時に読み込む形にしておく

11時報告では以下があると判断しやすいです。

```text
稼働時間:
取得件数:
件/時:
重複件数:
新規保存件数:
最終cursor:
429回数:
失敗/再試行回数:
SQLite保存件数:
取得漏れ疑い:
```

現時点では、無理に `page.evaluate fetch` を再開せず、安定稼働ログを優先で進めてください。
page.evaluate(fetch) のテスト可能タイミングは **「ログイン済みX画面で、対象GraphQLリクエストを1回以上200で観測した直後」** がベストです。  
今429が多いなら、**429解除後の最初のwindowで count小さめにして試す**べきです。同じrate bucketを使うので、429中に試しても失敗確認にしかなりません。

## いま詰まっている原因候補

- Playwrightスクロール取得がrate limitに当たり、実効 +112件/時まで落ちている
- 80件/window取得できているが、429待ちが長く、windowあたりのリクエスト数制御が弱い
- cursor/paginationの保存・再開が不完全だと、同じページ再取得でrateを浪費する
- page.evaluate fetchを試す前に、必要なGraphQL endpoint / queryId / variables / features / cursorを確定できていない可能性

## page.evaluate(fetch) を試す条件

Playwrightで以下を満たした直後。

```js
await page.goto('https://x.com/...');
await page.waitForLoadState('domcontentloaded');
```

その後、対象GraphQLを捕捉。

```js
page.on('response', async res => {
  const url = res.url();
  if (url.includes('/i/api/graphql/') && res.status() === 200) {
    console.log('GQL OK', url);
    console.log(await res.allHeaders());
  }
});
```

対象タイムライン/search/userTweetsなどのGraphQLが **200で1回出たら**、同じURL・variables・features・cursorで `page.evaluate` から再実行できます。

```js
const result = await page.evaluate(async ({ url }) => {
  const r = await fetch(url, {
    method: 'GET',
    credentials: 'include',
    headers: {
      'accept': '*/*',
      'x-twitter-active-user': 'yes',
      'x-twitter-client-language': 'ja'
    }
  });

  return {
    status: r.status,
    headers: Object.fromEntries(r.headers.entries()),
    text: await r.text()
  };
}, { url: capturedGraphqlUrl });
```

ポイント:

- `credentials: 'include'` 必須
- X画面上で実行するのでcookie/csrfはブラウザ文脈を使える
- 429中は同じく429になる可能性が高い
- まず `count=20` など小さめで疎通確認
- 成功後にcursor付きpaginationへ移行

## 改善案

### 1. スクロール主体をやめてGraphQL cursor主体にする

Playwrightはログイン・トークン取得・初回リクエスト捕捉だけに使う。  
取得本体は以下で回す。

- 捕捉したGraphQL endpoint
- variables
- features
- bottom cursor
- rate limit headers

スクロールは重い上に重複・DOM取り漏れが出やすいです。

### 2. 429制御を明示する

429が出たら固定sleepではなく、レスポンスヘッダを見る。

見るべきもの:

- `x-rate-limit-limit`
- `x-rate-limit-remaining`
- `x-rate-limit-reset`

実装方針:

```text
remaining > 0:
  次ページ取得
remaining == 0 or 429:
  reset時刻までsleep + 30〜90秒jitter
```

`+112件/時` は429待ちが支配的なので、無駄なリクエストをゼロにする方が効きます。

### 3. SQLiteにcursor状態を保存する

最低限このテーブルを追加/確認。

```sql
CREATE TABLE IF NOT EXISTS crawl_state (
  job_key TEXT PRIMARY KEY,
  endpoint TEXT,
  variables_json TEXT,
  features_json TEXT,
  bottom_cursor TEXT,
  last_tweet_id TEXT,
  rate_reset INTEGER,
  updated_at INTEGER
);
```

各成功ページごとに保存。

```text
1ページ取得成功
→ tweets upsert
→ next bottom_cursor保存
→ commit
```

これで中断再開時に同じwindowを消費しにくくなります。

### 4. tweetsはINSERT OR IGNORE / UPSERT

```sql
CREATE TABLE IF NOT EXISTS tweets (
  tweet_id TEXT PRIMARY KEY,
  user_id TEXT,
  screen_name TEXT,
  created_at TEXT,
  text TEXT,
  raw_json TEXT,
  fetched_at INTEGER
);
```

保存は重複前提。

```sql
INSERT OR IGNORE INTO tweets (...) VALUES (...);
```

取得件数は

```text
APIから返った件数
新規insert件数
重複件数
cursor
```

を必ずログに出す。

### 5. 取得漏れ検証を入れる

各ページで以下を記録。

```text
cursor_before
cursor_after
returned_count
inserted_count
min_tweet_id
max_tweet_id
status
```

検証方法:

- DB件数増加だけでなく、API returned_count と inserted_count を分ける
- `inserted_count=0` が連続したらcursorループ疑い
- cursorが前回と同じなら即停止
- tweet_id降順が飛びすぎていないか確認
- 可能なら同一条件で2周目を軽く走らせ、追加がほぼ0になるか確認

## 次の実装手順

1. Playwrightで対象GraphQL responseを捕捉する  
2. 200レスポンスのURL、headers、variables、features、cursorをログ保存  
3. 429解除後、`page.evaluate(fetch)` で同じURLを1回だけ再実行  
4. 成功したらbottom cursorを取り出して次ページfetch  
5. 各ページ成功ごとにSQLiteへ tweets と crawl_state をcommit  
6. rate limit headersを見て、remaining 0ならresetまで待つ  
7. cursor重複・inserted 0連続・429連続を検知して停止/待機

今の状態なら、まず **429解除後の最初の200 GraphQLを捕捉 → page.evaluate fetchで同一URL再実行** が最短の確認ポイントです。
結論: **transaction-id自前生成には進まない。UIスクロール方式を本線にして堅牢化する。**

理由:
- `transaction-id`生成はXの難読化JS依存で、壊れやすい
- 直叩きGraphQLは404/403/rate limit/仕様変更の検知が難しい
- 今すでに **234件/時で再開できているUI方式** が唯一安定動作している
- Claude Codeが詰まった原因は「cursor直叩きに固執して、X側の動的検証を突破しようとしたこと」

次にやること:

1. **UIスクロール方式を正式ルートに固定**
   - Playwrightでタイムラインを開く
   - スクロールごとにDOMまたはNetwork responseからtweetを抽出
   - cursor/API直叩きは一旦捨てる

2. **SQLite保存を強化**
   - `tweets(id PRIMARY KEY, user, text, created_at, url, raw_json, collected_at)`
   - `runs(id, target, started_at, last_seen_tweet_id, scroll_count, status)`
   - tweet IDでUPSERTして重複排除

3. **中断再開**
   - 最後に保存したtweet ID / 最終URL / スクロール回数を保存
   - 再開時は同じページを開き、既知tweetが連続N件出るまでスクロール
   - そこから続行

4. **取得漏れ検証**
   - 取得済みtweet IDを時系列で並べる
   - 同一ユーザー・同一期間で件数の急落を検知
   - スクロール停止時に「新規0件がN回連続」まで粘る
   - 可能なら画面上の表示件数とDB保存件数を比較

5. **rate limit / BAN回避ではなく安定運用**
   - スクロール間隔をランダムに 3〜8秒
   - 1時間ごとに休憩
   - エラー時は指数バックオフ
   - headful優先、ログイン状態を永続化

6. **transaction-id生成は保留**
   - やるなら別ブランチで1日だけ検証
   - 本番経路には入れない
   - 壊れた時にUI方式へ即フォールバックできる設計にする

実装方針はこれで十分です。  
**今は「速くする」より「止まっても再開でき、漏れを検知できる」方向に振るべきです。**
加速は「並列数を上げる」より先に **1 responseあたり取得数を上げる** のが最優先です。現状 100件/14 responses ≒ 7件/response で効率が低いです。

### 優先実装案

1. **GraphQLレスポンス解析の取り漏れ確認**
   - `entries` 内の `tweet` / `tweetWithVisibilityResults` / quoted / retweet を全部拾えているか確認。
   - cursorだけ進んで tweet entry を捨てていないかログ化。
   - 目標: **30〜100件/response**。

2. **cursor chainを可視化**
   - `topCursor`, `bottomCursor`, `minTweetId`, `maxTweetId`, `inserted`, `duplicate`, `empty` をDBに保存。
   - 同じcursor再利用・空ページ連発・重複ループを検出。
   - 空/重複率が高い shard は即停止して別shardへ。

3. **Playwrightを減らす**
   - Playwrightはログイン・cookie取得だけ。
   - GraphQL取得は `fetch/httpx` 等で直接叩く。
   - 画像/動画/font/cssは `route.abort()`。
   - これだけでCPU待ちが減りやすい。

4. **AIMDでwindow自動調整**
   - 現在 window 6。
   - 429/403/timeoutなしが10分続く → `+1`
   - 429/403/empty急増 → `半減`
   - 例: `6 → 8 → 10 → 12` まで試す。
   - 固定windowより安全。

5. **時間範囲でshard分割**
   - cursor一本は基本直列なので遅い。
   - `since/until` や tweet ID 時間帯で日/週単位に分割。
   - shardごとに独立cursorを持たせる。
   - 例: 2020-01, 2020-02, ... を並列取得。

6. **SQLite高速化**
   - `WAL`
   - `synchronous=NORMAL`
   - `INSERT OR IGNORE` + 500〜2000件 batch transaction
   - indexは最小限。後で追加。
   - 重複チェックは `tweet_id PRIMARY KEY` に任せる。

7. **中断再開の粒度を細かく**
   - `shards` テーブル:
     - `query`
     - `since`
     - `until`
     - `bottom_cursor`
     - `status`
     - `last_seen_tweet_id`
     - `empty_count`
     - `rate_limited_until`
   - crash後は unfinished shard だけ再開。

8. **取得漏れ検証**
   - shardごとに `max_id/min_id` と件数を記録。
   - 隣接shardの境界 tweet ID に穴がないか確認。
   - 低密度区間は再クロール。
   - 既知の総件数との差分を dashboard 化。

### 目標値

今: **193件/時**  
まず狙うべき現実ライン:

- 30件/response × 60 responses/時 = **1,800件/時**
- 50件/response × 100 responses/時 = **5,000件/時**

残り22万件なら:

- 1,800件/時 → 約5日
- 5,000件/時 → 約44時間

### 次にClaude Codeへ投げる実装順

1. GraphQLレスポンスごとの `entries/tweets/cursors/inserted/duplicates` ログ追加  
2. cursor状態をSQLiteに保存  
3. Playwright取得をHTTP直接取得へ分離  
4. windowをAIMD化  
5. since/until shard分割 + shard再開テーブル追加  
6. SQLite batch insert + WAL化  

まずは **100件/14 responses の原因特定** が最重要です。ここが直れば47日問題は一気に縮みます。
### 結論：原因は「429後に先頭からやり直して同じページを再取得している」こと。  
window分割だけでは根本解決しない。**cursor保存・同一位置再開・adaptive分割**が必要。

---

## 1. 429ループを抜ける具体策

### 最優先
**429後にページリロードしない。**  
リロードすると検索結果の先頭から再スクロールになり、50 reqをほぼ重複に使う。

やるべきこと：

1. GraphQL responseから `bottom cursor` を保存  
2. SQLiteに `user/window/cursor/oldest_tweet_id/oldest_time/status` を保存  
3. 429になったらそのwindowを `rate_limited` にして停止  
4. reset後、同じcursorから再開  
5. 取得済みtweetは `tweet_id UNIQUE` でdedupe

Playwright UIスクロールだけでcursor再開が難しいなら、  
**ブラウザで取得したGraphQL requestのheaders/cookies/variablesを使って、fetchでSearchTimelineを直接叩く**方が良いです。  
UIスクロール継続より安定します。

---

## 2. window分割は速くなるか？

### 単純には速くならない
X側の制限が例えば **50 req / 15 min** なら、windowを細かくしても総req数はあまり減らない。

ただし、次の効果はある：

- 1 windowが深くなりすぎない
- 429時の巻き戻り被害が小さい
- 終了判定が明確になる
- 密度の高い期間だけ細分化できる
- 取得漏れ検証が楽になる

なので、固定で「2週間→3日」ではなく、**adaptive分割**が良いです。

### 推奨ルール

```text
window開始
  ↓
GraphQL responses が 30〜40 を超える
  または
429前に since 境界まで到達できない
  ↓
そのwindowを半分に分割してqueueへ戻す
```

例：

```text
2021-05-15〜2021-05-29
→ 2021-05-15〜2021-05-22
→ 2021-05-22〜2021-05-29
```

それでも深ければさらに分割。

最小粒度はまず **1日**。  
極端に多い日は **12時間** まで割る。

---

## 3. 429待ち14分の有効活用

### 同じ認証・同じendpointなら基本無理
同じX GraphQL SearchTimeline bucketなら、別windowを回してもまた429になります。

### 有効活用できること

- SQLiteのdedupe/index作成
- window別取得件数の集計
- 欠落検証
- 次に割るべき高密度windowのqueue生成
- 保存済みHTML/GraphQL JSONから未保存tweet再抽出
- 別rate bucketの処理  
  例：ユーザープロフィール、tweet detailなど。ただしSearchTimelineと同bucketなら不可。

### 複数セッションについて
別アカウント・別認証でrate limit bucketが分かれるなら並列化可能。  
ただしXの制限・規約内でやるべき。

---

## 4. noNewCount 10→5について

これは補助策。  
根本解決ではない。

`noNewCount`で終了すると取得漏れリスクがあります。  
終了条件は以下に寄せるべきです。

```text
oldest_tweet_time < window_since
または
GraphQL cursor が終端
または
window内で新規0が連続し、かつ最古tweetがsinceを十分下回っている
```

「新規が増えない」だけで止めるのは危険。

---

## 5. 今すぐのBobLoukas window 2対応

### 手順

1. 現在のwindow 2を停止
2. `2021-05-15〜2021-05-29` を分割

```text
2021-05-15〜2021-05-18
2021-05-18〜2021-05-21
2021-05-21〜2021-05-24
2021-05-24〜2021-05-27
2021-05-27〜2021-05-29
```

3. 各windowをSQLite queueに入れる
4. 各windowで以下を保存

```sql
user
since
until
status
last_cursor
request_count
new_tweets
oldest_tweet_time
rate_limited_at
completed_at
```

5. 30〜40 responses超えたらさらに半分に分割
6. 429時はreloadせず、cursorを保存してreset後に同cursorから再開

---

## 6. 最終方針

Claude案の評価：

| 改善案 | 評価 |
|---|---|
| 2週間→3日 | 有効。ただし固定ではなくadaptive分割が良い |
| 429後のreload停止 | 最重要。必須 |
| noNewCount 10→5 | 効果小。取得漏れリスクあり |

優先順位はこれです。

```text
1. 429後reload禁止
2. cursor保存・同一位置再開
3. windowをadaptive分割
4. SQLite queueで中断再開
5. window別の取得漏れ検証
```

この順で直すのが最短です。
### 結論：130件/時の主因
Claudeが詰まっている原因は主に3つです。

1. **SearchTimelineを固定3日windowで総当たりしている**
   - 空window、重複windowにも同じコストを払っている。
   - `new=0` が多いなら、取得よりも「探索」がボトルネック。

2. **Playwright UI操作寄りで、GraphQLレスポンス直叩き最適化が足りない**
   - ページ描画・スクロール・不要リソース待ちが無駄。
   - 本質的には `SearchTimeline` / `UserTweets` GraphQLのJSONだけ取ればよい。

3. **rate limitを“固定sleep”で扱っている可能性が高い**
   - 429後に同じwindowを再試行してループ。
   - `x-rate-limit-reset` / 実測429間隔を見て、ジョブ単位で止めるべき。

---

## 130件/時から加速する具体策

### 1. 固定3日windowをやめて「粗探索 → 細分化」にする
今の3日window総当たりは遅いです。

やるべきはこれです。

```text
30日windowで軽くprobe
  ├─ tweet 0件 → その30日をskip
  ├─ 少数 → そのまま取得
  └─ 多数 / cursorあり → 7日 → 3日 → 1日に分割
```

重要なのは、**probeでは1ページ目だけ取る**ことです。  
14日windowで429ループしたのは、おそらく深掘りpaginationまでやったからです。

#### 実装案
SQLiteに `windows` テーブルを作る。

```sql
CREATE TABLE IF NOT EXISTS fetch_windows (
  account TEXT,
  since TEXT,
  until TEXT,
  status TEXT, -- pending, probing, fetching, done, empty, rate_limited, error
  granularity_days INTEGER,
  next_cursor TEXT,
  fetched_count INTEGER DEFAULT 0,
  new_count INTEGER DEFAULT 0,
  last_error TEXT,
  updated_at TEXT,
  PRIMARY KEY(account, since, until)
);
```

これで、

- empty windowは二度と叩かない
- 429で止まっても再開可能
- new=0が続く期間を後で分析可能

になります。

---

### 2. SearchTimelineをPlaywright画面操作ではなくGraphQL JSON取得に寄せる
Playwrightはログインcookie取得・認証維持だけに使い、取得自体はGraphQLを直接叩くのが速いです。

方針：

```text
PlaywrightでXログイン済みcontext作成
↓
cookie, csrf token, bearer tokenを取得
↓
context.request.get/post で GraphQL SearchTimeline を直接呼ぶ
↓
JSONからtweet_id, created_at, text, user_idを抽出
↓
SQLiteへINSERT OR IGNORE
```

UIスクロールは最終手段にするべきです。

#### 効果
- 画像/CSS/font待ちが消える
- DOM解析不要
- cursor paginationを正確に扱える
- 429の発生箇所をログ化できる

---

### 3. cursorをSQLiteに保存して中断再開する
window単位だけでなく、**cursor単位で再開**できるようにするべきです。

```sql
CREATE TABLE IF NOT EXISTS fetch_cursors (
  account TEXT,
  endpoint TEXT,
  since TEXT,
  until TEXT,
  cursor TEXT,
  status TEXT,
  page_count INTEGER DEFAULT 0,
  fetched_count INTEGER DEFAULT 0,
  updated_at TEXT,
  PRIMARY KEY(account, endpoint, since, until, cursor)
);
```

1 window内で429になった場合、

```text
window: 2021-01-01 to 2021-01-04
next_cursor: AAA...
```

を保存しておき、次回そこから再開します。

これをやらないと、429後に同じページを何度も取り直して件数が伸びません。

---

### 4. rate limitは固定sleepではなく、アカウント単位のrate limiterにする
同じXアカウント・同じcookieなら、別ブラウザセッションを増やしても基本的にはrate limitは共有されます。

やるなら：

```text
XアカウントA: BobLoukas SearchTimeline
XアカウントB: Checkmatey / LynAlden / ronpochi UserTweets
```

ただし、同一IPで制限が共有される可能性もあります。  
2アカウント並列するなら、最低限ログに以下を残すべきです。

```text
account_cookie_id
endpoint
status_code
x-rate-limit-limit
x-rate-limit-remaining
x-rate-limit-reset
retry_after
response_time
window_since
window_until
cursor
```

XのWeb GraphQLは必ずしもrate limit headerが綺麗に出ないことがあります。  
その場合は、429時刻から実測でcooldownを決める。

例：

```text
429発生
↓
そのXアカウントのSearchTimeline queueを15〜30分停止
↓
別アカウントまたは別endpointのqueueを進める
```

---

### 5. Playwrightのroute.abortは有効だが優先度は低め
UI取得を続ける場合はやる価値があります。

```js
await page.route('**/*', route => {
  const type = route.request().resourceType();
  if (['image', 'media', 'font', 'stylesheet'].includes(type)) {
    return route.abort();
  }
  return route.continue();
});
```

ただし、XはCSS/JS依存が強いので、stylesheetを切ると壊れることがあります。  
おすすめはまず以下だけ。

```js
['image', 'media', 'font']
```

最終的にはUIではなくGraphQL JSON直取得に寄せるべきです。

---

## 並行できる別アプローチ

### A. BobLoukas本取得中に、他アカウントの「空window探索」だけ走らせる
rate limitを食いにくいように、深いpaginationはせず、1ページprobeだけする。

対象：

```text
Checkmatey
LynAlden
他の未処理アカウント
```

やること：

```text
月単位 or 30日単位でSearchTimeline 1ページだけ取得
0件ならempty登録
hitありならneeds_fetch登録
```

これにより、後で本取得するときに空振りが減ります。

---

### B. SQLite上で欠落検証を並行実行する
取得と独立して、DB分析は今すぐ並行できます。

やるべき検証：

```sql
-- 日別件数
SELECT account, substr(created_at, 1, 10) AS day, COUNT(*)
FROM tweets
GROUP BY account, day
ORDER BY account, day;

-- 月別件数
SELECT account, substr(created_at, 1, 7) AS month, COUNT(*)
FROM tweets
GROUP BY account, month
ORDER BY account, month;
```

見るべきもの：

- 0件月
- 急に件数が落ちる月
- 既存DBでは多いのに新規取得が0になる期間
- `tweet_id`連番的に大きく飛んでいる期間

保存は必ずこれ。

```sql
CREATE UNIQUE INDEX IF NOT EXISTS idx_tweets_tweet_id ON tweets(tweet_id);
CREATE INDEX IF NOT EXISTS idx_tweets_account_created ON tweets(account, created_at);
```

SQLiteはWALにする。

```sql
PRAGMA journal_mode=WAL;
PRAGMA synchronous=NORMAL;
```

複数取得プロセスを並行するなら、DB writerは1本にしてqueue経由が安全です。

---

### C. UserTweets / UserTweetsAndRepliesを別endpointとして試す
SearchTimelineだけに依存しない。

使う候補：

```text
SearchTimeline       : from:account since: until:
UserTweets           : profile timeline
UserTweetsAndReplies : replies含むprofile timeline
UserMedia            : media付きtweet
```

SearchTimelineで取れないアカウントでも、UserTweetsなら取れる可能性があります。  
特にronpochi対策では必須です。

---

## ronpochiの10万件欠落への対処

### まず認識
ronpochiが検索除外されているなら、`SearchTimeline from:ronpochi` では完全取得は難しいです。  
この場合、3日windowをいくら回しても根本解決しません。

### 優先順はこれです。

---

### 1. UserTweets / UserTweetsAndReplies GraphQLで取得可能範囲を確認
まずronpochiの `rest_id` を取得し、profile timeline系endpointを叩く。

```text
UserByScreenName
↓
rest_id取得
↓
UserTweets
↓
bottom cursorでpagination
↓
止まるまで保存
```

検証ポイント：

```text
何ページ取れるか
最古tweetの日付はどこまで行けるか
429頻度
SearchTimeline除外でもUserTweetsは動くか
```

これで10万件すべて取れる保証はありません。  
Xのprofile timelineは途中で打ち切られることがあります。

ただし、SearchTimeline不可アカウントに対する第一候補はこれです。

---

### 2. ronpochi本人のX Archiveが取れるなら、それが最強
10万件規模の完全回収が必要なら、現実的にはこれが一番確実です。

```text
X設定
→ Your account
→ Download an archive of your data
→ tweets.js / tweet.js をSQLiteへimport
```

もしronpochiが自分または協力者のアカウントなら、APIスクレイピングより圧倒的に速く、完全性も高いです。

---

### 3. 有料Full-Archive APIを検討
Search除外・10万件欠落・完全性重視なら、公式APIのFull Archive Searchが現実解です。

ただし、プラン・費用・上限確認が必要です。

---

### 4. 外部アーカイブは補助扱い
Wayback、Google/Bing index、Nitter系、第三者ミラーは補助にはなりますが、10万件完全回収には向きません。

用途は：

```text
欠落期間の存在確認
代表tweetの復元
tweet_idの手がかり取得
```

程度です。

---

## すぐやるべき実装手順

### Step 1: DBを中断再開可能にする
追加：

```text
fetch_windows
fetch_cursors
fetch_logs
```

必須：

```text
tweet_id UNIQUE
WAL mode
account + created_at index
```

---

### Step 2: SearchTimeline取得をGraphQL直叩きに変更
Playwright UIスクロールではなく、

```text
Playwright authenticated context
→ GraphQL request
→ JSON parse
→ SQLite upsert
```

にする。

---

### Step 3: 30日probe → 3日/1日fetchのadaptive windowへ変更
BobLoukasの残り461 windowsをそのまま走らせる前に、空windowを潰す。

```text
30日 probe
0件: empty
hitあり: 7日 or 3日に分割
dense: 1日に分割
```

---

### Step 4: 429時はwindow再試行ではなくaccount queue停止
429が出たら、

```text
同じcookieの同じendpointをcooldown
cursorを保存
別account / 別endpoint / offline検証へ切替
```

---

### Step 5: ronpochiはSearchTimelineを停止し、UserTweets検証へ切替
ronpochiに対してはまずこれだけ確認。

```text
UserByScreenNameでrest_id取得
UserTweetsでpagination
UserTweetsAndRepliesでpagination
最古到達日を記録
```

結果が最近数千件で止まるなら、10万件回収には

```text
X Archive
公式Full Archive API
外部アーカイブ補完
```

の判断に進むべきです。

---

## Claude提案への評価

### 1. 別ブラウザセッション並列
同じcookieなら効果は薄いです。  
別Xアカウントがあるなら有効。ただし同一IP制限の可能性あり。

優先度：中。

---

### 2. ヒストグラムで投稿なし期間をスキップ
これは正しいです。  
ただし既存DBだけでなく、30日probe結果を `empty window` として保存するべきです。

優先度：高。

---

### 3. route.abortで画像/CSS/font削減
有効ですが、根本解決ではないです。  
GraphQL直叩きの方が効果が大きい。

優先度：中〜低。

---

## 推奨方針
今やるべき順番はこれです。

```text
1. SQLiteにwindow/cursor/log管理を追加
2. SearchTimelineをGraphQL JSON直取得化
3. 30日probeでempty windowを大量skip
4. 429時はcursor保存してaccount単位cooldown
5. ronpochiはSearchTimelineを捨ててUserTweets/UserTweetsAndReplies検証
6. 2つ目のXアカウントがある場合のみ並列化
```

この順でやれば、130件/時のまま数週間走る状態から、少なくとも「空振りwindowで時間を溶かす」状態は抜けられます。
結論：**今の情報だけでは「正確な総費用」は出せません。**  
理由は、プロフィール表示件数が「返信含む全件」であり、APIで取得したい「返信除外後の投稿数」が不明だからです。

---

## 1. `from:user -filter:replies` 的に返信除外した場合の課金対象

通常の理解では、**課金はAPIレスポンスとして返されたPost/Tweet数に対して**です。  
つまり、検索条件で返信が除外され、レスポンスに返らなければ、その返信分は課金対象にならないはずです。

ただし、あなたの契約・料金ページ上の「read」の厳密定義は外部から確認できないため、**内部検索でスキャンされた件数まで課金されるかは不明**です。  
公開APIの一般的な使い方では「返却されたPost数」で見るべきです。

実装上は、X API v2なら以下のようなクエリになります。

```text
from:username -is:reply
```

リポストも除外して「本人のオリジナル投稿のみ」にするなら：

```text
from:username -is:reply -is:retweet
```

引用ポストを除外するかどうかは別途定義が必要です。

---

## 2. user timeline endpointで返信除外オプションはあるか？

あります。

X API v2 の user timeline 系：

```http
GET /2/users/:id/tweets?exclude=replies,retweets
```

返信だけ除外なら：

```http
exclude=replies
```

リポストも除外なら：

```http
exclude=replies,retweets
```

ただし重要点があります。

**user timeline endpoint だけで過去全件、特に数万〜十数万件を取得できるとは限りません。**  
多くの場合、ユーザータイムライン系APIには取得可能範囲の制限があります。大量の過去投稿を全件取るなら、通常は **Full-archive search** 相当の検索APIが必要です。

---

## 3. 現実的な正確な費用見積もり

現時点では不明です。

理由：

- 表示件数は返信込み
- 返信除外後の件数が不明
- リポスト・引用を含めるか不明
- 既にDBにある66,000件をAPIで再取得すると、その分も再課金される可能性がある
- 既存DBの66,000件がどの条件で取得済みか不明

### 上限に近い概算

プロフィール表示件数を単純合計すると：

| account | 表示件数 |
|---|---:|
| smile_danjer | 33,000 |
| _Checkmatey_ | 50,000 |
| BobLoukas | 40,000 |
| ronpochi | 115,000 |
| LynAldenContact | 33,000 |
| PeterLBrandt | 40,000 |
| CryptoHayes | 2,563 |
| **合計** | **313,563** |

単価 $0.005 / 件なら：

```text
313,563 * 0.005 = $1,567.815
```

つまり、**全表示件数が課金対象になる最悪寄りの上限は約 $1,568** です。

CryptoHayesが完了済みで除外なら：

```text
311,000 * 0.005 = $1,555
```

既存DBの66,000件を完全に再取得せずに避けられる場合の理論上限は：

```text
(313,563 - 66,000) * 0.005 = $1,237.815
```

ただしこれは、既存66,000件が今回条件の取得対象と一致し、APIで重複取得しない設計ができる場合のみです。

### 正確な費用式

```text
費用 = APIから実際に返却された未取得ではなく「返却された」Post数 * $0.005
```

重複取得してもAPIレスポンスに返れば課金対象になる前提で考えるべきです。

### 正確化する方法

各アカウントについて、まず件数だけ確認します。

```text
from:username -is:reply -is:retweet
```

この条件で counts endpoint または検索結果のページング総数を確認します。  
ただし、counts endpoint 自体の課金有無・利用可否は契約条件次第なので要確認です。

---

## 4. X APIで取得する場合の所要時間とrate limit

正確な所要時間は不明です。  
理由は、あなたのAPI契約・プラン・endpointごとのrate limitが不明だからです。

実装ではレスポンスヘッダを見る必要があります。

```http
x-rate-limit-limit
x-rate-limit-remaining
x-rate-limit-reset
```

### Full-archive search想定の概算

検索APIで `max_results=500` が使える場合：

```text
必要リクエスト数 = 取得対象Post数 / 500
```

最大表示件数313,563件を全部返すと仮定すると：

```text
313,563 / 500 = 約628リクエスト
```

返信・リポストを除外すれば実際はこれより少ないはずです。

所要時間は：

```text
ceil(必要リクエスト数 / 15分あたり許可リクエスト数) * 15分
```

例：

| rate limit | 628リクエストの所要時間 |
|---:|---:|
| 300 req / 15min | 約30〜45分 |
| 100 req / 15min | 約1.5〜2時間 |
| 50 req / 15min | 約3〜3.5時間 |
| 10 req / 15min | 約15〜16時間 |

ただしこれは例です。正確には実際のヘッダで確認してください。

---

## 5. ronpochiが検索除外アカウントの場合、X APIでも制限があるか？

不明です。

整理すると：

- **user timeline endpoint** はユーザーID指定なので、通常の検索インデックスとは別系統の可能性が高い
- ただし timeline endpoint では古い投稿全件を取れない可能性が高い
- **search endpoint / full-archive search** は検索インデックス依存なので、検索除外・可視性制限・ポリシー制限の影響を受ける可能性がある
- Xが「検索除外アカウントはAPI検索でどう扱われるか」を明確に保証しているかは不明
- protected / suspended / deleted / withheld な投稿はAPIでも取得できない

ronpochiについては、APIで小規模に検証するしかありません。

検証方法：

1. ronpochiの既知の古い投稿IDを数件用意する
2. `GET /2/tweets/:id` で直接取得できるか確認
3. `from:4HpO4Q9Dz3CWkhV -is:reply -is:retweet` で検索に出るか確認
4. user timeline endpointで直近投稿が出るか確認
5. 3つの結果を比較する

---

## 実装上の推奨手順

1. 取得条件を固定する  
   - 返信除外：`-is:reply`
   - リポスト除外：`-is:retweet`
   - 引用を含めるか除外するか決める

2. 各アカウントで件数確認  
   - 可能なら counts endpoint
   - 無理なら低件数でページング検証

3. SQLiteにアカウント別の進捗を保存  
   - `account`
   - `query`
   - `next_token`
   - `oldest_id`
   - `newest_id`
   - `completed`
   - `last_request_at`

4. 投稿保存テーブルは `tweet_id` をPRIMARY KEYにする  
   - 重複保存防止
   - ただしAPIで重複取得した分の課金は避けられない

5. ページングは `next_token` を必ず保存  
   - 中断再開可能にする
   - rate limit時は `x-rate-limit-reset` までsleep

6. 取得漏れ検証  
   - APIのcount結果とSQLite件数を比較
   - アカウント別・月別に件数比較
   - 欠落期間があればその期間だけ再取得

---

## まとめ

- 返信除外クエリなら、通常は**返却された非返信Post数だけが課金対象**と考える。
- user timeline endpointには返信除外オプションはある。
- ただし timeline endpointだけで数万件以上の全過去投稿を取れるとは限らない。
- 現時点の最大概算は約 **$1,568**。
- 返信除外後の正確な費用は、各アカウントの `from:user -is:reply -is:retweet` 件数を確認しないと出せない。
- rate limitと所要時間は契約プラン不明のため正確には不明。
- ronpochiの検索除外がAPI検索に影響するかは不明。小規模検証が必要。
