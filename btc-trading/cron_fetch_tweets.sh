#!/bin/bash
# X新規投稿取得 (ローカルcron用)
# danjer: 1時間毎 → crontab: 0 * * * * /path/to/cron_fetch_tweets.sh hourly
# 他全員: 週1回  → crontab: 0 9 * * 1 /path/to/cron_fetch_tweets.sh weekly

MODE="${1:-hourly}"
DIR="$(cd "$(dirname "$0")" && pwd)"
LOG="$DIR/cron_fetch_tweets.log"

echo "$(date '+%Y-%m-%d %H:%M') [$MODE] start" >> "$LOG"

cd "$DIR"
node -e "
const { Storage } = require('@google-cloud/storage');
const storage = new Storage();
const BUCKET = 'btc-research-0549297663';
const BEARER = 'AAAAAAAAAAAAAAAAAAAAANRILgAAAAAAnNwIzUejRCOuH5E6I8xnZz4puTs=1Zv7ttfk8LF81IUq16cHjhLTvJu4FA33AGWWjCpTnA';

const ACCOUNTS = {
  smile_danjer: { interval: 'hourly' },
  '4HpO4Q9Dz3CWkhV': { interval: 'weekly' },
  CryptoHayes: { interval: 'weekly' },
  '_Checkmatey_': { interval: 'weekly' },
  BobLoukas: { interval: 'weekly' },
  LynAldenContact: { interval: 'weekly' },
  PeterLBrandt: { interval: 'weekly' },
};

async function getGuestToken() {
  const res = await fetch('https://api.twitter.com/1.1/guest/activate.json', { method: 'POST', headers: { 'Authorization': 'Bearer ' + BEARER }, signal: AbortSignal.timeout(10000) });
  return (await res.json()).guest_token;
}

async function getUserId(handle, gt) {
  const v = JSON.stringify({ screen_name: handle });
  const f = JSON.stringify({ hidden_profile_subscriptions_enabled: true, responsive_web_graphql_timeline_navigation_enabled: true, responsive_web_graphql_skip_user_profile_image_extensions_enabled: false });
  const res = await fetch('https://twitter.com/i/api/graphql/IGgvgiOx4QZndDHuD3x9TQ/UserByScreenName?variables=' + encodeURIComponent(v) + '&features=' + encodeURIComponent(f), { headers: { 'Authorization': 'Bearer ' + BEARER, 'x-guest-token': gt, 'content-type': 'application/json' }, signal: AbortSignal.timeout(10000) });
  const d = await res.json();
  return d?.data?.user?.result?.rest_id || null;
}

async function getUserTweets(userId, gt) {
  const v = JSON.stringify({ userId, count: 100, includePromotedContent: false, withVoice: true, withV2Timeline: true });
  const f = JSON.stringify({ rweb_tipjar_consumption_enabled: true, responsive_web_graphql_exclude_directive_enabled: true, verified_phone_label_enabled: false, creator_subscriptions_tweet_preview_api_enabled: true, responsive_web_graphql_timeline_navigation_enabled: true, responsive_web_graphql_skip_user_profile_image_extensions_enabled: false, communities_web_enable_tweet_community_results_fetch: true, c9s_tweet_anatomy_moderator_badge_enabled: true, articles_preview_enabled: true, responsive_web_edit_tweet_api_enabled: true, graphql_is_translatable_rweb_tweet_is_translatable_enabled: true, view_counts_everywhere_api_enabled: true, longform_notetweets_consumption_enabled: true, responsive_web_twitter_article_tweet_consumption_enabled: true, tweet_awards_web_tipping_enabled: false, freedom_of_speech_not_reach_fetch_enabled: true, standardized_nudges_misinfo: true, tweet_with_visibility_results_prefer_gql_limited_actions_policy_enabled: true, rweb_video_timestamps_enabled: true, longform_notetweets_rich_text_read_enabled: true, longform_notetweets_inline_media_enabled: true, responsive_web_enhance_cards_enabled: false });
  const res = await fetch('https://twitter.com/i/api/graphql/x3B_xLqC0yZawOB7WQhaVQ/UserTweets?variables=' + encodeURIComponent(v) + '&features=' + encodeURIComponent(f), { headers: { 'Authorization': 'Bearer ' + BEARER, 'x-guest-token': gt, 'content-type': 'application/json' }, signal: AbortSignal.timeout(15000) });
  const data = await res.json();
  const tweets = [];
  for (const inst of (data?.data?.user?.result?.timeline_v2?.timeline?.instructions || [])) {
    for (const entry of (inst.entries || [])) {
      const r = entry?.content?.itemContent?.tweet_results?.result;
      if (!r?.legacy) continue;
      const l = r.legacy;
      tweets.push({ status_id: l.id_str, text: l.full_text, created_at: l.created_at, media: (l.entities?.media || []).map(m => ({ type: m.type, url: m.media_url_https })) });
    }
  }
  return tweets;
}

(async () => {
  const mode = '${MODE}';
  const gt = await getGuestToken();
  if (!gt) { console.error('No guest token'); process.exit(1); }

  for (const [handle, config] of Object.entries(ACCOUNTS)) {
    if (mode !== config.interval) continue;
    try {
      const userId = await getUserId(handle, gt);
      if (!userId) { console.log(handle + ': user not found'); continue; }

      let latestId = '0';
      try {
        const [file] = await storage.bucket(BUCKET).file('tweets/' + handle + '_tweets.json').download();
        const ex = JSON.parse(file.toString());
        if (ex.tweets?.length > 0) latestId = ex.tweets.reduce((m, t) => t.status_id > m ? t.status_id : m, '0');
      } catch (e) {}

      const newTweets = await getUserTweets(userId, gt);
      const genuinelyNew = newTweets.filter(t => t.status_id > latestId);
      if (genuinelyNew.length === 0) { console.log(handle + ': 0 new'); continue; }

      // fxtwitter画像補完
      for (const tw of genuinelyNew) {
        try {
          const r = await fetch('https://api.fxtwitter.com/' + handle + '/status/' + tw.status_id, { signal: AbortSignal.timeout(5000) });
          if (r.ok) { const fx = await r.json(); const m = fx.tweet?.media; if (m?.photos?.length) tw.media = { photos: m.photos.map(p => ({ url: p.url, width: p.width, height: p.height })) }; if (m?.videos?.length) { tw.media = tw.media || {}; tw.media.videos = m.videos.map(v => ({ url: v.url })); } if (fx.tweet?.created_at) tw.created_at = fx.tweet.created_at; }
        } catch (e) {}
      }

      let existing = { handle, tweets: [] };
      try { const [file] = await storage.bucket(BUCKET).file('tweets/' + handle + '_tweets.json').download(); existing = JSON.parse(file.toString()); } catch (e) {}
      existing.tweets = [...existing.tweets, ...genuinelyNew];
      existing.tweets.sort((a, b) => a.status_id.localeCompare(b.status_id));
      existing.fetched_count = existing.tweets.length;
      existing.last_updated = new Date().toISOString();
      await storage.bucket(BUCKET).file('tweets/' + handle + '_tweets.json').save(JSON.stringify(existing, null, 2), { contentType: 'application/json' });
      console.log(handle + ': +' + genuinelyNew.length + ' (total: ' + existing.tweets.length + ')');
    } catch (e) { console.error(handle + ': ' + e.message); }
    await new Promise(r => setTimeout(r, 1000));
  }
})();
" >> "$LOG" 2>&1

echo "$(date '+%Y-%m-%d %H:%M') [$MODE] done" >> "$LOG"
