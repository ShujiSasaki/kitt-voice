const functions = require('@google-cloud/functions-framework');
const { Storage } = require('@google-cloud/storage');

const storage = new Storage();
const BUCKET = 'btc-research-0549297663';

// Bearer Token (公開固定値)
const BEARER = 'AAAAAAAAAAAAAAAAAAAAANRILgAAAAAAnNwIzUejRCOuH5E6I8xnZz4puTs=1Zv7ttfk8LF81IUq16cHjhLTvJu4FA33AGWWjCpTnA';

const ACCOUNTS = {
  smile_danjer: { userId: null, interval: 'hourly' },
  '4HpO4Q9Dz3CWkhV': { userId: null, interval: 'weekly' },
  CryptoHayes: { userId: null, interval: 'weekly' },
  '_Checkmatey_': { userId: null, interval: 'weekly' },
  BobLoukas: { userId: null, interval: 'weekly' },
  LynAldenContact: { userId: null, interval: 'weekly' },
  PeterLBrandt: { userId: null, interval: 'weekly' },
};

// ゲストトークン取得
async function getGuestToken() {
  const res = await fetch('https://api.twitter.com/1.1/guest/activate.json', {
    method: 'POST',
    headers: { 'Authorization': `Bearer ${BEARER}` },
    signal: AbortSignal.timeout(10000),
  });
  const data = await res.json();
  return data.guest_token;
}

// ユーザーID取得
async function getUserId(handle, guestToken) {
  const variables = JSON.stringify({ screen_name: handle, withSafetyModeUserFields: true });
  const features = JSON.stringify({ hidden_profile_subscriptions_enabled: true, rweb_tipjar_consumption_enabled: true, responsive_web_graphql_exclude_directive_enabled: true, verified_phone_label_enabled: false, highlights_tweets_tab_ui_enabled: true, responsive_web_twitter_article_notes_tab_enabled: true, subscriptions_feature_can_gift_premium: true, creator_subscriptions_tweet_preview_api_enabled: true, responsive_web_graphql_skip_user_profile_image_extensions_enabled: false, responsive_web_graphql_timeline_navigation_enabled: true });
  const url = `https://twitter.com/i/api/graphql/IGgvgiOx4QZndDHuD3x9TQ/UserByScreenName?variables=${encodeURIComponent(variables)}&features=${encodeURIComponent(features)}`;

  const res = await fetch(url, {
    headers: {
      'Authorization': `Bearer ${BEARER}`,
      'x-guest-token': guestToken,
      'content-type': 'application/json',
    },
    signal: AbortSignal.timeout(10000),
  });
  const data = await res.json();
  return data?.data?.user?.result?.rest_id || null;
}

// ユーザーツイート取得 (最新100件)
async function getUserTweets(userId, guestToken, count = 100) {
  const variables = JSON.stringify({ userId, count, includePromotedContent: false, withQuickPromoteEligibilityTweetFields: true, withVoice: true, withV2Timeline: true });
  const features = JSON.stringify({ rweb_tipjar_consumption_enabled: true, responsive_web_graphql_exclude_directive_enabled: true, verified_phone_label_enabled: false, creator_subscriptions_tweet_preview_api_enabled: true, responsive_web_graphql_timeline_navigation_enabled: true, responsive_web_graphql_skip_user_profile_image_extensions_enabled: false, communities_web_enable_tweet_community_results_fetch: true, c9s_tweet_anatomy_moderator_badge_enabled: true, articles_preview_enabled: true, responsive_web_edit_tweet_api_enabled: true, graphql_is_translatable_rweb_tweet_is_translatable_enabled: true, view_counts_everywhere_api_enabled: true, longform_notetweets_consumption_enabled: true, responsive_web_twitter_article_tweet_consumption_enabled: true, tweet_awards_web_tipping_enabled: false, creator_subscriptions_quote_tweet_preview_enabled: false, freedom_of_speech_not_reach_fetch_enabled: true, standardized_nudges_misinfo: true, tweet_with_visibility_results_prefer_gql_limited_actions_policy_enabled: true, rweb_video_timestamps_enabled: true, longform_notetweets_rich_text_read_enabled: true, longform_notetweets_inline_media_enabled: true, responsive_web_enhance_cards_enabled: false });
  const url = `https://twitter.com/i/api/graphql/x3B_xLqC0yZawOB7WQhaVQ/UserTweets?variables=${encodeURIComponent(variables)}&features=${encodeURIComponent(features)}`;

  const res = await fetch(url, {
    headers: {
      'Authorization': `Bearer ${BEARER}`,
      'x-guest-token': guestToken,
      'content-type': 'application/json',
    },
    signal: AbortSignal.timeout(15000),
  });
  const data = await res.json();

  // ツイートをパース
  const tweets = [];
  const instructions = data?.data?.user?.result?.timeline_v2?.timeline?.instructions || [];
  for (const inst of instructions) {
    const entries = inst.entries || [];
    for (const entry of entries) {
      const result = entry?.content?.itemContent?.tweet_results?.result;
      if (!result?.legacy) continue;
      const legacy = result.legacy;
      tweets.push({
        status_id: legacy.id_str,
        text: legacy.full_text,
        created_at: legacy.created_at,
        media: (legacy.entities?.media || []).map(m => ({
          type: m.type,
          url: m.media_url_https,
        })),
      });
    }
  }
  return tweets;
}

// メイン: 新規ツイート取得してGCSに保存
functions.http('fetchNewTweets', async (req, res) => {
  try {
    const mode = req.query.mode || 'hourly'; // 'hourly' or 'weekly'
    const targetHandle = req.query.handle; // 特定アカウントのみ
    const results = {};

    const guestToken = await getGuestToken();
    if (!guestToken) throw new Error('Failed to get guest token');

    for (const [handle, config] of Object.entries(ACCOUNTS)) {
      if (targetHandle && handle !== targetHandle) continue;
      if (mode !== config.interval && !targetHandle) continue;

      try {
        // ユーザーID取得
        let userId = config.userId;
        if (!userId) {
          userId = await getUserId(handle, guestToken);
          if (!userId) { results[handle] = 'user not found'; continue; }
          ACCOUNTS[handle].userId = userId;
        }

        // 既存データから最新status_idを取得
        let latestId = '0';
        try {
          const [file] = await storage.bucket(BUCKET).file(`tweets/${handle}_tweets.json`).download();
          const existing = JSON.parse(file.toString());
          if (existing.tweets?.length > 0) {
            latestId = existing.tweets.reduce((max, t) =>
              t.status_id > max ? t.status_id : max, '0');
          }
        } catch (e) { /* ファイルなし */ }

        // 最新ツイート取得
        const newTweets = await getUserTweets(userId, guestToken, 100);
        const genuinelyNew = newTweets.filter(t => t.status_id > latestId);

        if (genuinelyNew.length === 0) {
          results[handle] = { new: 0 };
          continue;
        }

        // oembed APIでリッチデータ補完
        for (const tweet of genuinelyNew) {
          try {
            const oembedRes = await fetch(
              `https://publish.twitter.com/oembed?url=https://twitter.com/${handle}/status/${tweet.status_id}&omit_script=true`,
              { signal: AbortSignal.timeout(5000) }
            );
            if (oembedRes.ok) {
              const oembed = await oembedRes.json();
              const dateMatch = oembed.html?.match(/<a[^>]*>([^<]*\d{4})<\/a>\s*<\/blockquote>/);
              if (dateMatch) tweet.date = dateMatch[1].trim();
            }
          } catch (e) { /* ignore */ }
        }

        // fxtwitter APIで画像URL補完
        for (const tweet of genuinelyNew) {
          try {
            const fxRes = await fetch(
              `https://api.fxtwitter.com/${handle}/status/${tweet.status_id}`,
              { signal: AbortSignal.timeout(5000) }
            );
            if (fxRes.ok) {
              const fx = await fxRes.json();
              const media = fx.tweet?.media;
              if (media?.photos?.length > 0) {
                tweet.media = { photos: media.photos.map(p => ({ url: p.url, width: p.width, height: p.height })) };
              }
              if (media?.videos?.length > 0) {
                tweet.media = tweet.media || {};
                tweet.media.videos = media.videos.map(v => ({ url: v.url, thumbnail: v.thumbnail_url }));
              }
            }
          } catch (e) { /* ignore */ }
        }

        // GCSの既存データにマージ
        let existing = { handle, tweets: [] };
        try {
          const [file] = await storage.bucket(BUCKET).file(`tweets/${handle}_tweets.json`).download();
          existing = JSON.parse(file.toString());
        } catch (e) { /* 新規 */ }

        existing.tweets = [...existing.tweets, ...genuinelyNew];
        existing.tweets.sort((a, b) => a.status_id.localeCompare(b.status_id));
        existing.fetched_count = existing.tweets.length;
        existing.last_updated = new Date().toISOString();

        // GCSに保存
        await storage.bucket(BUCKET).file(`tweets/${handle}_tweets.json`).save(
          JSON.stringify(existing, null, 2),
          { contentType: 'application/json' }
        );

        results[handle] = { new: genuinelyNew.length, total: existing.tweets.length };
      } catch (e) {
        results[handle] = { error: e.message };
      }

      await new Promise(r => setTimeout(r, 1000)); // レート制限対策
    }

    console.log('fetchNewTweets:', JSON.stringify(results));
    res.json({ success: true, mode, results });

  } catch (err) {
    console.error('fetchNewTweets error:', err);
    res.status(500).json({ error: err.message });
  }
});
