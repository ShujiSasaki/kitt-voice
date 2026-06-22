#!/usr/bin/env python3
"""
X SearchTimeline直接取得 - gallery-dl不要
長寿命セッション、cursor保存、rate limit管理、中断再開
"""
import json, time, sqlite3, sys, os, re
from datetime import datetime, timedelta
import requests

# === Config ===
env = {}
with open(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '.env')) as f:
    for line in f:
        if '=' in line:
            k, v = line.strip().split('=', 1)
            env[k] = v

CT0 = env.get('X_CT0', '')
AUTH_TOKEN = env.get('X_AUTH_TOKEN', '')
BEARER = 'AAAAAAAAAAAAAAAAAAAAANRILgAAAAAAnNwIzUejRCOuH5E6I8xnZz4puTs%3D1Zv7ttfk8LF81IUq16cHjhLTvJu4FA33AGWWjCpTnA'

# gallery-dlから抽出した設定
SEARCH_QUERY_ID = '4fpceYZ6-YQCx_JSl_Cn_A'
FEATURES = {"rweb_video_screen_enabled":False,"payments_enabled":False,"rweb_xchat_enabled":False,"profile_label_improvements_pcf_label_in_post_enabled":True,"rweb_tipjar_consumption_enabled":True,"verified_phone_label_enabled":False,"creator_subscriptions_tweet_preview_api_enabled":True,"responsive_web_graphql_timeline_navigation_enabled":True,"responsive_web_graphql_skip_user_profile_image_extensions_enabled":False,"premium_content_api_read_enabled":False,"communities_web_enable_tweet_community_results_fetch":True,"c9s_tweet_anatomy_moderator_badge_enabled":True,"responsive_web_grok_analyze_button_fetch_trends_enabled":False,"responsive_web_grok_analyze_post_followups_enabled":True,"rweb_cashtags_composer_attachment_enabled":True,"responsive_web_jetfuel_frame":True,"responsive_web_grok_share_attachment_enabled":True,"responsive_web_grok_annotations_enabled":True,"articles_preview_enabled":True,"responsive_web_edit_tweet_api_enabled":True,"graphql_is_translatable_rweb_tweet_is_translatable_enabled":True,"view_counts_everywhere_api_enabled":True,"longform_notetweets_consumption_enabled":True,"responsive_web_twitter_article_tweet_consumption_enabled":True,"tweet_awards_web_tipping_enabled":False,"responsive_web_grok_show_grok_translated_post":False,"responsive_web_grok_analysis_button_from_backend":True,"creator_subscriptions_quote_tweet_preview_enabled":False,"freedom_of_speech_not_reach_fetch_enabled":True,"standardized_nudges_misinfo":True,"tweet_with_visibility_results_prefer_gql_limited_actions_policy_enabled":True,"longform_notetweets_rich_text_read_enabled":True,"longform_notetweets_inline_media_enabled":True,"responsive_web_grok_image_annotation_enabled":True,"responsive_web_grok_imagine_annotation_enabled":True,"responsive_web_grok_community_note_auto_translation_is_enabled":False,"responsive_web_enhance_cards_enabled":False}

# === SQLite ===
DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'x_tweets.db')
conn = sqlite3.connect(DB_PATH)
conn.execute("PRAGMA journal_mode=WAL")
conn.execute("PRAGMA busy_timeout=5000")

# === Session ===
session = requests.Session()
session.headers.update({
    'Authorization': f'Bearer {BEARER}',
    'x-csrf-token': CT0,
    'x-twitter-active-user': 'yes',
    'x-twitter-auth-type': 'OAuth2Session',
    'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36',
    'Content-Type': 'application/json',
})
session.cookies.set('auth_token', AUTH_TOKEN, domain='.x.com')
session.cookies.set('ct0', CT0, domain='.x.com')

# === Tweet extraction ===
def extract_tweets(data):
    tweets = []
    def walk(obj):
        if not obj or not isinstance(obj, (dict, list)):
            return
        if isinstance(obj, list):
            for item in obj:
                walk(item)
            return
        legacy = obj.get('legacy')
        if legacy and legacy.get('id_str') and legacy.get('full_text'):
            author = ''
            core = obj.get('core', {})
            if isinstance(core, dict):
                ur = core.get('user_results', core.get('user_result', {}))
                if isinstance(ur, dict):
                    result = ur.get('result', {})
                    if isinstance(result, dict):
                        leg = result.get('legacy', {})
                        if isinstance(leg, dict):
                            author = leg.get('screen_name', '')

            media = legacy.get('extended_entities', {}).get('media', []) or legacy.get('entities', {}).get('media', [])
            tweets.append({
                'tweet_id': legacy['id_str'],
                'screen_name': author,
                'created_at': legacy.get('created_at', ''),
                'full_text': legacy['full_text'],
                'in_reply_to': legacy.get('in_reply_to_status_id_str'),
                'is_rt': 1 if 'retweeted_status_result' in obj else 0,
                'is_quote': 1 if 'quoted_status_result' in obj else 0,
                'rt_count': legacy.get('retweet_count', 0),
                'fav_count': legacy.get('favorite_count', 0),
                'media': json.dumps([{'type': m.get('type'), 'url': m.get('media_url_https')} for m in media]) if media else None,
            })
            return
        for v in obj.values():
            walk(v)
    walk(data)
    seen = set()
    return [t for t in tweets if not (t['tweet_id'] in seen or seen.add(t['tweet_id']))]

def extract_cursor(data):
    def walk(obj):
        if not obj or not isinstance(obj, (dict, list)):
            return None
        if isinstance(obj, list):
            for item in obj:
                r = walk(item)
                if r: return r
            return None
        # Bottom cursor
        eid = obj.get('entryId', '')
        if eid.startswith('cursor-bottom-') and obj.get('content', {}).get('value'):
            return obj['content']['value']
        for v in obj.values():
            r = walk(v)
            if r: return r
        return None
    return walk(data)

# === Fetch one page ===
def fetch_page(query, cursor=None):
    variables = {
        'rawQuery': query,
        'count': 20,
        'querySource': 'typed_query',
        'product': 'Latest',
    }
    if cursor:
        variables['cursor'] = cursor

    params = {
        'variables': json.dumps(variables, separators=(',', ':')),
        'features': json.dumps(FEATURES, separators=(',', ':')),
    }

    url = f'https://x.com/i/api/graphql/{SEARCH_QUERY_ID}/SearchTimeline'
    resp = session.get(url, params=params, timeout=30)

    rate_remaining = resp.headers.get('x-rate-limit-remaining')
    rate_reset = resp.headers.get('x-rate-limit-reset')

    if resp.status_code == 429:
        if rate_reset:
            wait = int(rate_reset) - int(time.time()) + 5
            if wait > 0:
                print(f'    429. Waiting {wait}s (reset: {datetime.fromtimestamp(int(rate_reset)).strftime("%H:%M")})')
                time.sleep(wait)
        else:
            print('    429. Waiting 900s')
            time.sleep(900)
        return None, None, rate_remaining, rate_reset

    if resp.status_code != 200:
        print(f'    HTTP {resp.status_code}')
        return None, None, rate_remaining, rate_reset

    data = resp.json()
    tweets = extract_tweets(data)
    next_cursor = extract_cursor(data)

    return tweets, next_cursor, rate_remaining, rate_reset

# === Fetch date range ===
def fetch_range(handle, since, until):
    query = f'from:{handle} since:{since} until:{until}'
    cursor = None
    total_new = 0
    page = 0

    while True:
        tweets, next_cursor, remaining, reset = fetch_page(query, cursor)

        if tweets is None:
            # 429 retry
            tweets, next_cursor, remaining, reset = fetch_page(query, cursor)
            if tweets is None:
                return total_new, 'rate_limited'

        # Save tweets
        new = 0
        for t in tweets:
            try:
                cur = conn.execute(
                    "INSERT OR IGNORE INTO tweets (tweet_id, screen_name, created_at, full_text, in_reply_to_status_id, is_retweet, is_quote, retweet_count, favorite_count, media_json, fetched_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (t['tweet_id'], t['screen_name'] or handle, t['created_at'], t['full_text'], t['in_reply_to'], t['is_rt'], t['is_quote'], t['rt_count'], t['fav_count'], t['media'], datetime.utcnow().isoformat())
                )
                if cur.rowcount > 0:
                    new += 1
            except:
                pass
        conn.commit()
        total_new += new
        page += 1

        # Rate limit management
        if remaining and int(remaining) <= 2:
            if reset:
                wait = int(reset) - int(time.time()) + 5
                if wait > 0:
                    print(f'    Low remaining ({remaining}). Waiting {wait}s')
                    time.sleep(wait)

        # Stop conditions
        if not next_cursor or next_cursor == cursor:
            return total_new, 'done'
        if len(tweets) == 0:
            return total_new, 'done'

        cursor = next_cursor
        time.sleep(1)  # 1秒間隔(rate limitは自動管理)

    return total_new, 'done'

# === Main ===
GAPS = {
    'smile_danjer': ('2023-07-01', '2024-05-01'),
    'BobLoukas': ('2021-05-01', '2025-03-01'),
    '_Checkmatey_': ('2020-12-01', '2025-08-01'),
    'LynAldenContact': ('2021-04-01', '2025-06-01'),
    'PeterLBrandt': ('2021-03-01', '2025-10-01'),
}

target = sys.argv[1] if len(sys.argv) > 1 else None

for handle, (start, end) in GAPS.items():
    if target and handle != target:
        continue

    print(f'\n=== {handle}: {start} → {end} ===')

    d = datetime.strptime(start, '%Y-%m-%d')
    e = datetime.strptime(end, '%Y-%m-%d')
    total_new = 0
    week_num = 0

    while d < e:
        since = d.strftime('%Y-%m-%d')
        d += timedelta(days=7)
        if d > e: d = e
        until = d.strftime('%Y-%m-%d')
        week_num += 1

        new, status = fetch_range(handle, since, until)
        total_new += new

        if week_num % 5 == 0:
            db_total = conn.execute("SELECT COUNT(*) FROM tweets WHERE screen_name=?", (handle,)).fetchone()[0]
            print(f'  [{week_num}] {since}: +{new} (total new: {total_new}, DB: {db_total})')

    db_total = conn.execute("SELECT COUNT(*) FROM tweets WHERE screen_name=?", (handle,)).fetchone()[0]
    print(f'{handle} done: DB={db_total} (+{total_new})')

conn.close()
print('\n=== Complete ===')
