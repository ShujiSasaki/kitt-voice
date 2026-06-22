#!/usr/bin/env python3
"""
X/Twitterの実ブラウザ通信を捕捉してGraphQL APIのパラメータを取得
ログイン済みcookieを注入してプロフィールページの通信を記録
"""
import json, os, sys
from playwright.sync_api import sync_playwright

env = {}
with open('/Users/shuji/Desktop/kitt-voice/.env') as f:
    for line in f:
        if '=' in line:
            k, v = line.strip().split('=', 1)
            env[k] = v

CT0 = env.get('X_CT0', '')
AUTH = env.get('X_AUTH_TOKEN', '')

captured = []

def on_request(request):
    url = request.url
    if '/graphql/' in url and ('UserTweets' in url or 'SearchTimeline' in url or 'Timeline' in url):
        headers = request.headers
        captured.append({
            'url': url,
            'method': request.method,
            'headers': {k: v for k, v in headers.items() if k in [
                'authorization', 'x-csrf-token', 'cookie', 'content-type',
                'x-twitter-active-user', 'x-twitter-auth-type',
                'x-client-transaction-id', 'user-agent',
            ]},
            'post_data': request.post_data[:2000] if request.post_data else None,
        })
        # URLからqueryId, operationNameを抽出
        parts = url.split('/graphql/')
        if len(parts) > 1:
            path = parts[1].split('?')[0]
            query_id = path.split('/')[0]
            op_name = path.split('/')[1] if '/' in path else '?'
            print(f"  CAPTURED: {op_name} (queryId: {query_id})")

def on_response(response):
    url = response.url
    if '/graphql/' in url and ('UserTweets' in url or 'SearchTimeline' in url):
        print(f"  RESPONSE: {response.status} {url[:100]}")

handle = sys.argv[1] if len(sys.argv) > 1 else 'smile_danjer'
print(f"Capturing X requests for @{handle}...")

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    context = browser.new_context(
        user_agent='Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36'
    )
    # cookie注入
    context.add_cookies([
        {'name': 'auth_token', 'value': AUTH, 'domain': '.x.com', 'path': '/'},
        {'name': 'ct0', 'value': CT0, 'domain': '.x.com', 'path': '/'},
    ])

    page = context.new_page()
    page.on('request', on_request)
    page.on('response', on_response)

    # 1. プロフィールページ(ツイートタブ)
    print(f"\n--- Loading https://x.com/{handle} ---")
    page.goto(f'https://x.com/{handle}', wait_until='domcontentloaded', timeout=60000)
    page.wait_for_timeout(3000)

    # 2. 返信タブ
    print(f"\n--- Loading https://x.com/{handle}/with_replies ---")
    page.goto(f'https://x.com/{handle}/with_replies', wait_until='domcontentloaded', timeout=60000)
    page.wait_for_timeout(3000)

    # 3. 検索(最新タブ)
    print(f"\n--- Loading search: from:{handle} ---")
    page.goto(f'https://x.com/search?q=from%3A{handle}&src=typed_query&f=live', wait_until='domcontentloaded', timeout=60000)
    page.wait_for_timeout(3000)

    # スクロールして追加リクエスト捕捉
    for i in range(3):
        page.mouse.wheel(0, 2000)
        page.wait_for_timeout(2000)

    browser.close()

# 結果保存
out_path = '/Users/shuji/Desktop/kitt-voice/logs/x_captured_requests.json'
with open(out_path, 'w') as f:
    json.dump(captured, f, indent=2, ensure_ascii=False)

print(f"\n=== Captured {len(captured)} requests ===")
print(f"Saved to: {out_path}")

# サマリー
for req in captured:
    url = req['url']
    parts = url.split('/graphql/')
    if len(parts) > 1:
        path = parts[1].split('?')[0]
        print(f"  {path}: {req['method']}")
