/* meeting_system/local_board/app.js
 * R56 (R56-UI-DISCORD-DM-STYLE Loop 2) 確定UI:
 *   - Discord/Messenger DM風 dark theme
 *   - 左AI / 右Shuji 吹き出し配置
 *   - 連続発言時 sender-label省略
 *   - 日付セパレータ
 *   - Quick action chip → composer prefill
 *   - composer icon (+/カメラ/画像/絵文字/マイク) UI配置 (機能Phase 2)
 *
 * R50承継 (CSS変更のみ、 サーバー無影響):
 *   - SSE経由でリアルタイム更新
 *   - AI処理中はShuji送信ボタンgrayout
 *   - DOMPurifyサニタイズ
 *   - Basic auth + CSRF token + Replay protection
 */
'use strict';

const API = '/api';
const ACTOR_LABEL = {
  gpt: 'GPT', gemini: 'Gemini', claude: 'Claude',
  shuji: 'Shuji', validator: 'Validator',
};
const STATUS_DOT_CLASS = {
  idle: 'bg-dm-text-dim',
  ai_processing: 'bg-yellow-400 animate-pulse',
  paused_by_shuji: 'bg-orange-500',
  consensus_reached: 'bg-green-500',
  max_loops_reached: 'bg-red-500',  // R66
};
const STATUS_TOOLTIP = {
  idle: '待機中',
  ai_processing: '議論中',
  paused_by_shuji: 'Shuji割込中',
  consensus_reached: '合意成立',
  max_loops_reached: 'ループ上限到達・自動停止 (▶再開で続行)',  // R66
};

let activeRoomId = null;
let processingRoomId = null;   // UI-P0: worker処理中room (typing表示用)
let currentNextActor = null;   // UI-P0: 閲覧中roomの次actor
let lastMsgIdByRoom = {};
let previousConsensusByRoom = {};
let lastRenderedMsgByRoom = {};   // R56: 連続発言判定 + 日付セパレータ用

const AUTH_KEY = 'meeting_auth_b64';
let authB64 = localStorage.getItem(AUTH_KEY) || '';
let csrfToken = '';

// ===== R50承継: Auth + CSRF =====
async function fetchCsrf() {
  const r = await fetch(`${API}/csrf-token`, {
    headers: authB64 ? {'Authorization': `Basic ${authB64}`} : {},
  });
  if (r.status === 401) {
    localStorage.removeItem(AUTH_KEY);
    authB64 = '';
    throw new Error('auth_required');
  }
  const j = await r.json();
  csrfToken = j.token;
  return csrfToken;
}

async function initAuth() {
  try {
    await fetchCsrf();
    if (authB64) localStorage.setItem(AUTH_KEY, authB64);
    return true;
  } catch (e) {
    if (e.message === 'auth_required') {
      const user = prompt('Username:');
      const pass = prompt('Password:');
      if (user && pass) {
        authB64 = btoa(`${user}:${pass}`);
        try {
          await fetchCsrf();
          localStorage.setItem(AUTH_KEY, authB64);
          return true;
        } catch (e2) {
          alert('認証失敗');
          return false;
        }
      }
    }
    return false;
  }
}

async function authFetch(url, opts = {}) {
  const headers = new Headers(opts.headers || {});
  if (authB64) headers.set('Authorization', `Basic ${authB64}`);
  const method = (opts.method || 'GET').toUpperCase();
  if (method !== 'GET' && method !== 'HEAD') {
    if (!csrfToken) await fetchCsrf();
    headers.set('X-CSRF-Token', csrfToken);
  }
  let r = await fetch(url, {...opts, headers});
  if (r.status === 403 && method !== 'GET' && method !== 'HEAD') {
    await fetchCsrf();
    headers.set('X-CSRF-Token', csrfToken);
    r = await fetch(url, {...opts, headers});
  }
  return r;
}

// ===== Toast =====
function showToast(msg, durationMs = 3000) {
  const t = document.createElement('div');
  t.textContent = msg;
  t.style.cssText =
    'position:fixed;bottom:90px;left:50%;transform:translateX(-50%);' +
    'background:rgba(0,0,0,0.85);color:#F5F5F5;padding:8px 16px;' +
    'border-radius:8px;z-index:9999;font-size:13px;border:1px solid #2A2A2A;';
  document.body.appendChild(t);
  setTimeout(() => t.remove(), durationMs);
}

// ===== R50承継: Replay-protected submit =====
async function submitWithRetry(body, opts = {}, maxRetries = 3) {
  const clientMsgId = (crypto.randomUUID && crypto.randomUUID()) ||
    `${Date.now()}_${Math.random().toString(36).slice(2)}`;
  const payload = {
    actor: 'shuji', body,
    client_msg_id: clientMsgId,
  };
  if (opts && opts.attachments) payload.attachments = opts.attachments;
  let lastError;
  for (let i = 0; i < maxRetries; i++) {
    try {
      const r = await authFetch(`${API}/rooms/${activeRoomId}/submit`, {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify(payload),
      });
      if (r.ok) return r.json();
      if (r.status === 409 || r.status === 400) return r.json();
      lastError = new Error(`HTTP ${r.status}`);
    } catch (e) {
      lastError = e;
    }
    if (i < maxRetries - 1) {
      const delay = 1000 * Math.pow(2, i);
      showToast(`再送中... (${i + 1}/${maxRetries})`);
      await new Promise(rs => setTimeout(rs, delay));
    }
  }
  throw lastError;
}

// ===== Markdown sanitize =====
function escapeHtml(s) {
  return String(s ?? '').replace(/[&<>"']/g, c =>
    ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
}

function renderMarkdownSafe(raw) {
  try {
    const html = marked.parse(raw || '');
    return DOMPurify.sanitize(html);
  } catch (e) {
    return escapeHtml(raw || '');
  }
}

async function fetchJSON(url, opts) {
  const r = await authFetch(url, opts);
  if (!r.ok) throw new Error(`${url} → ${r.status}`);
  return r.json();
}

// ===== Sidebar (R55合意 room list、 R56で dark theme色適用) =====
// R65.1: UI自動更新 — server の ui_version (app.js mtime) が変わったら full reload。
// iOS PWA が index.html/app.js を強キャッシュして更新が届かない問題の恒久対策。
let uiVersion = null;
function checkUiVersion(v) {
  if (!v) return false;
  if (uiVersion === null) { uiVersion = v; return false; }
  if (uiVersion !== v) {
    location.replace('/?u=' + Date.now());  // query付き navigation でキャッシュ回避
    return true;
  }
  return false;
}

async function refreshSidebar() {
  const data = await fetchJSON(`${API}/rooms/overview`);
  if (checkUiVersion(data.global?.ui_version)) return;
  const sidebar = document.getElementById('sidebar');
  const tmpl = document.getElementById('tmpl-room-icon');
  const existing = new Set();

  for (const room of data.rooms) {
    existing.add(room.room_id);
    let btn = sidebar.querySelector(`[data-room-id="${CSS.escape(room.room_id)}"]`);
    if (!btn) {
      const frag = tmpl.content.cloneNode(true);
      btn = frag.querySelector('.room-icon-btn');
      btn.dataset.roomId = room.room_id;
      sidebar.appendChild(btn);
    }
    const shape = btn.querySelector('.room-icon-shape');
    const glyph = btn.querySelector('.room-icon-glyph');
    glyph.textContent = room.icon || '💬';
    shape.style.backgroundColor = room.color || '#4F46E5';

    const badge = btn.querySelector('.unread-badge');
    badge.textContent = room.unread_count || 0;
    badge.classList.toggle('hidden', (room.unread_count || 0) === 0);

    const dot = btn.querySelector('.status-dot');
    dot.className = `status-dot absolute -bottom-1 -right-1 w-3 h-3 rounded-full
                     ring-2 ring-dm-header ${STATUS_DOT_CLASS[room.status] || 'bg-dm-text-dim'}`;
    dot.title = STATUS_TOOLTIP[room.status] || room.status;

    const tooltip = btn.querySelector('.tooltip');
    tooltip.textContent = `${room.title} · ${room.current_loop}巡目 ${room.next_actor || ''}`;

    if (room.is_consensus_established && !previousConsensusByRoom[room.room_id]) {
      shape.classList.remove('consensus-reached');
      void shape.offsetWidth;
      shape.classList.add('consensus-reached');
    }
    previousConsensusByRoom[room.room_id] = !!room.is_consensus_established;

    // R65: selected = クライアント側の閲覧中room (server globalの先頭固定強調は廃止)
    if (activeRoomId === room.room_id) {
      btn.setAttribute('aria-current', 'true');
    } else {
      btn.removeAttribute('aria-current');
    }

    // R65: processing = worker処理中room (「リレー中」バッジ + 琥珀パルス)
    btn.classList.toggle('is-processing', !!room.is_processing);
    const procBadge = btn.querySelector('.processing-badge');
    if (procBadge) procBadge.classList.toggle('hidden', !room.is_processing);

    // R66: max_loops到達 = 「⚠️上限」バッジ
    const mlBadge = btn.querySelector('.maxloops-badge');
    if (mlBadge) mlBadge.classList.toggle('hidden', room.status !== 'max_loops_reached');

    // UX改善: FIFO待機列 = 「待機#N」バッジ (処理中バッジと同位置、 排他)
    const qBadge = btn.querySelector('.queued-badge');
    if (qBadge) {
      const qp = room.queue_position;
      qBadge.classList.toggle('hidden', !qp || !!room.is_processing);
      if (qp) qBadge.textContent = `待機${qp}`;
    }
  }

  // UX改善: グローバル状態行 (ヘッダ) — 「今システムが何をしているか」一目表示
  processingRoomId = data.global?.processing_room_id || null;  // UI-P0: typing表示用
  updateTypingIndicator();
  lastOverview = data;       // UI-P1: 部屋一覧パネル用
  renderRoomList();          // 開いていれば最新化
  const grsDot = document.getElementById('grs-dot');
  const grsText = document.getElementById('grs-text');
  if (grsDot && grsText) {
    const proc = data.global?.processing_room_id;
    const q = data.global?.router_queue || [];
    const lock = data.global?.chrome_lock;
    // 同時1件ロック: 手動操作(relay_worker以外)がChromeを握っている間は行列待ち。
    const manualLock = lock && lock.held &&
      !String(lock.holder || '').startsWith('relay_worker');
    if (manualLock) {
      grsDot.style.backgroundColor = '#F59E0B';
      grsDot.classList.remove('animate-pulse');
      const rem = Math.round((lock.ttl_remaining || 0) / 60);
      grsText.textContent = `🔒 Claude in Chrome 手動使用中 — 待ち` +
        (q.length ? `${q.length}部屋` : '') + (rem ? ` (最大${rem}分で自動解放)` : '');
    } else if (proc) {
      const pr = data.rooms.find(r => r.room_id === proc);
      const label = pr ? pr.title : proc;
      grsDot.style.backgroundColor = '#22C55E';
      grsDot.classList.add('animate-pulse');
      grsText.textContent = `リレー処理中: ${label}` +
        (q.length ? ` ・待ち${q.length}部屋` : '');
    } else if (q.length) {
      grsDot.style.backgroundColor = '#0EA5E9';
      grsDot.classList.remove('animate-pulse');
      grsText.textContent = `待機列 ${q.length}部屋 — まもなく開始`;
    } else {
      grsDot.style.backgroundColor = '#6B7280';
      grsDot.classList.remove('animate-pulse');
      grsText.textContent = '全部屋待機中 (submitで自動開始)';
    }
  }

  for (const btn of Array.from(sidebar.querySelectorAll('.room-icon-btn'))) {
    if (!existing.has(btn.dataset.roomId)) btn.remove();
  }

  if (!activeRoomId && data.rooms.length) {
    // P1-②: 前回の閲覧部屋を復元 (無ければ先頭room)
    let stored = null;
    try { stored = localStorage.getItem('grl_active_room'); } catch (e) {}
    const target = data.rooms.some(r => r.room_id === stored)
      ? stored : data.rooms[0].room_id;
    await activateRoom(target);
  }
}

// ===== Header status (R56で 簡潔サマリ + 詳細<details>折りたたみ) =====
async function refreshRoomState() {
  if (!activeRoomId) return;
  const s = await fetchJSON(`${API}/rooms/${activeRoomId}/state`);
  document.getElementById('active-room-title').textContent =
    s.project_name || s.room_id;
  // UX改善: 送信先の部屋を入力欄に常時表示 (部屋誤送信防止)
  const inputEl = document.getElementById('shuji-input');
  if (inputEl) inputEl.placeholder = `${s.project_name || s.room_id} へ送信...`;
  // UI-P0: typing indicator (「○○が入力中…」、R65 is_processing流用)
  currentNextActor = s.next_actor || null;
  updateTypingIndicator();

  // R56: ヘッダ簡潔サマリ
  const statusJa = STATUS_TOOLTIP[s.status] || s.status || '—';
  const nextActorUp = (s.next_actor || '-').toUpperCase();
  const summary = `${statusJa} · 次: ${nextActorUp} · ${s.total_loops || 0}巡目` +
    (s.is_consensus_established ? ' · 合意成立' : '');
  document.getElementById('header-status-summary').textContent = summary;

  // 折りたたみ詳細
  document.getElementById('status-current').textContent = s.status || 'idle';
  document.getElementById('next-actor').textContent = nextActorUp;
  document.getElementById('loop-progress').textContent = s.total_loops || 0;
  const cs = document.getElementById('consensus-status');
  cs.textContent = s.is_consensus_established ? '成立' : '未成立';
  cs.className = s.is_consensus_established ? 'text-green-400 font-bold' : 'text-red-400';

  const turn = s.current_turn_in_loop || 0;
  const dot = (id, cond) => {
    const el = document.getElementById(id);
    if (cond === 'active')      el.className = 'w-2.5 h-2.5 rounded-full bg-dm-border animate-pulse';
    else if (cond === 'done')   el.className = 'w-2.5 h-2.5 rounded-full bg-actor-' + id.replace('dot-','');
    else                        el.className = 'w-2.5 h-2.5 rounded-full bg-dm-border';
  };
  dot('dot-gpt',    s.next_actor === 'gpt' ? 'active' : (turn >= 1 || s.total_loops > 0 ? 'done' : 'idle'));
  dot('dot-gemini', s.next_actor === 'gemini' ? 'active' : (turn >= 2 || s.total_loops > 0 ? 'done' : 'idle'));
  dot('dot-claude', s.next_actor === 'claude' ? 'active' : (turn === 0 && s.total_loops > 0 ? 'done' : 'idle'));

  // R58 Must Fix B: relay_worker 3状態ランプ
  const lamp = document.getElementById('relay-lamp');
  if (lamp) {
    const rwState = s.relay_worker_state || 'off';
    const color = rwState === 'running' ? 'bg-yellow-400 animate-pulse'
                : rwState === 'done'    ? 'bg-green-400'
                                        : 'bg-dm-text-dim';
    lamp.className = 'w-2.5 h-2.5 rounded-full flex-shrink-0 ' + color;
    lamp.title = `relay_worker: ${rwState}` +
      (typeof s.relay_worker_heartbeat_age_sec === 'number'
        ? ` (heartbeat ${s.relay_worker_heartbeat_age_sec}s)` : '');
  }

  // R58 Must Fix C → 修正 (2026-06-12 Shuji指摘「再開を押さないと発言できない」):
  // 停止状態 (合意成立/外部待ち/判断待ち/割込/上限) では常に送信可能。
  // 新しいsubmitは新議題として自動で会議を開始するので、再開ボタンは不要。
  // ロックするのは「この部屋でAIが現に処理中」の時だけ。
  const submitBtn = document.getElementById('submit-btn');
  const workerRunning = s.relay_worker_state === 'running';
  const aiProcessing = s.status === 'ai_processing';
  const stopStates = new Set(['consensus_reached', 'external_wait', 'blocked',
                              'paused_by_shuji', 'max_loops_reached']);
  const stopped = stopStates.has(s.status) || s.is_consensus_established;
  const shouldLock = !stopped && (aiProcessing || workerRunning);
  submitBtn.disabled = shouldLock;
  submitBtn.title = shouldLock
    ? (aiProcessing ? 'AI処理中' : '自動relay動作中 (送信は完了後)')
    : '送信';

  // R61 D + E: 再開ボタン + stall_reason表示
  ensureResumeBar(s);
}

// R61 D + E → UI刷新 (2026-06-12): 停止時は入力欄直上の固定スリムバナー
// (旧: コンテンツに被るフローティングピル+絵文字 — 主流アプリ非準拠のため廃止)
const RESUME_BANNER_INFO = {
  consensus_reached: {dot: '#22C55E', text: '合意成立 — 新しい議題はそのまま送信できます', btn: '続きを再開'},
  external_wait:     {dot: '#F59E0B', text: '外部作業待ち — 新しい送信でも再開します', btn: '再開'},
  blocked:           {dot: '#F97316', text: '判断待ちで停止中 — 回答をそのまま送信できます', btn: '再開'},
  paused_by_shuji:   {dot: '#F97316', text: '割込で停止中 — メッセージをそのまま送信できます', btn: '再開'},
  max_loops_reached: {dot: '#EF4444', text: 'ループ上限で停止 — 新しい指示の送信でも再開します', btn: '続きを再開'},
};

function ensureResumeBar(s) {
  let bar = document.getElementById('resume-bar');
  const stallStatuses = new Set([
    'external_wait', 'blocked', 'consensus_reached', 'paused_by_shuji',
    'max_loops_reached',  // R66漏れ修正: 上限停止でもバナー表示
  ]);
  const showBar = stallStatuses.has(s.status) || s.is_consensus_established;
  if (!showBar) {
    if (bar) bar.remove();
    return;
  }
  const key = s.is_consensus_established ? 'consensus_reached' : s.status;
  const info = RESUME_BANNER_INFO[key] || {dot: '#9CA3AF', text: '停止中'};
  if (!bar) {
    bar = document.createElement('div');
    bar.id = 'resume-bar';
    bar.className =
      'flex items-center gap-2.5 px-3 py-2 bg-dm-header border-t border-dm-border text-sm';
    const dot = document.createElement('span');
    dot.className = 'resume-dot w-2 h-2 rounded-full flex-shrink-0';
    const txt = document.createElement('span');
    txt.className = 'resume-text flex-1 min-w-0 text-dm-text truncate';
    const btn = document.createElement('button');
    btn.type = 'button';
    btn.className =
      'resume-btn bg-dm-bubble-shuji text-black text-sm font-bold px-4 py-1.5 ' +
      'rounded-lg active:scale-95 transition flex-shrink-0';
    btn.textContent = '再開';
    btn.addEventListener('click', async () => {
      if (!activeRoomId) return;
      btn.disabled = true;
      try {
        const r = await authFetch(`${API}/rooms/${activeRoomId}/resume_relay`, {
          method: 'POST',
          headers: {'Content-Type': 'application/json'},
          body: JSON.stringify({}),
        });
        const j = await r.json();
        if (j.ok) {
          showToast('会議を再開しました');
          bar.remove();
          refreshRoomState();
        } else {
          showToast(`再開失敗: ${j.error || ''}`);
        }
      } catch (e) {
        showToast(`再開error: ${e.message}`);
      } finally {
        btn.disabled = false;
      }
    });
    bar.append(dot, txt, btn);
    const footer = document.querySelector('footer');
    footer.parentNode.insertBefore(bar, footer);
  }
  bar.querySelector('.resume-dot').style.backgroundColor = info.dot;
  bar.querySelector('.resume-text').textContent = info.text;
  bar.querySelector('.resume-btn').textContent = info.btn || '再開';
}

// ===== R56: 日付セパレータ insert =====
function maybeInsertDateSeparator(timelineEl, msg, prevMsg) {
  const curIso = msg.ts_iso || msg.ts;
  if (!curIso) return;
  const cur = new Date(curIso);
  if (isNaN(cur.getTime())) return;
  if (prevMsg) {
    const prevIso = prevMsg.ts_iso || prevMsg.ts;
    const prev = new Date(prevIso);
    if (!isNaN(prev.getTime()) && cur.toDateString() === prev.toDateString()) return;
  }
  const tmpl = document.getElementById('tmpl-date-sep');
  const frag = tmpl.content.cloneNode(true);
  const yyyy = cur.getFullYear();
  const mm = String(cur.getMonth() + 1).padStart(2, '0');
  const dd = String(cur.getDate()).padStart(2, '0');
  frag.querySelector('.date-label').textContent = `${yyyy}/${mm}/${dd}`;
  timelineEl.appendChild(frag);
}

// ===== R56: timeline =====
async function refreshTimeline() {
  if (!activeRoomId) return;
  const since = lastMsgIdByRoom[activeRoomId] || '';
  const data = await fetchJSON(
    `${API}/rooms/${activeRoomId}/timeline?since=${encodeURIComponent(since)}`,
  );
  const tl = document.getElementById('timeline');
  const hint = document.getElementById('empty-hint');
  if (hint) hint.classList.add('hidden');

  // R59 fix: スクロール強制戻り防止 (Shuji報告 2026-06-10)
  // 追加前に「ユーザーが最下部付近にいるか」を記録し、
  // (a) 新メッセージあり かつ (b) 元々最下部付近 のときだけ自動スクロール
  const nearBottom =
    tl.scrollHeight - tl.scrollTop - tl.clientHeight < 120;

  let appended = false;
  let prevMsg = lastRenderedMsgByRoom[activeRoomId] || null;
  for (const msg of data.messages) {
    if (tl.querySelector(`[data-msg-id="${CSS.escape(msg.msg_id)}"]`)) continue;
    maybeInsertDateSeparator(tl, msg, prevMsg);
    tl.appendChild(renderMessage(msg, prevMsg));
    lastMsgIdByRoom[activeRoomId] = msg.msg_id;
    prevMsg = msg;
    appended = true;
  }
  lastRenderedMsgByRoom[activeRoomId] = prevMsg;
  if (appended) {
    if (nearBottom) {
      tl.scrollTop = tl.scrollHeight;
      markRead();  // UX2: 最下部で閲覧中 = 既読更新
    } else {
      // R59: 上スクロール読書中は自動スクロールしない代わりに新着バッジ表示 (GPT R21提案)
      ensureNewMsgBadge(tl).classList.remove('hidden');
    }
  }
}

function ensureNewMsgBadge(tl) {
  let btn = document.getElementById('new-msg-badge');
  if (btn) return btn;
  btn = document.createElement('button');
  btn.id = 'new-msg-badge';
  btn.textContent = '↓ 新着あり';
  btn.className =
    'hidden fixed bottom-24 left-1/2 -translate-x-1/2 z-40 ' +
    'bg-dm-bubble-shuji text-black text-sm font-bold px-4 py-2 ' +
    'rounded-full shadow-lg';
  btn.addEventListener('click', () => {
    tl.scrollTop = tl.scrollHeight;
    btn.classList.add('hidden');
  });
  tl.addEventListener('scroll', () => {
    if (tl.scrollHeight - tl.scrollTop - tl.clientHeight < 120) {
      btn.classList.add('hidden');
      markRead();  // UX2: 最下部到達 = 既読更新
    }
  });
  document.body.appendChild(btn);
  return btn;
}

// ===== UI-P0: アバター (actor色 + 略号) =====
const ACTOR_AVATAR = {
  gpt:       {label: 'GP', color: '#10A37F'},
  gemini:    {label: 'GE', color: '#8E75D9'},
  claude:    {label: 'CL', color: '#D97706'},
  validator: {label: 'SY', color: '#DC2626'},
};

// ===== UI-P0: 相対時刻 ("たった今" / "N分前" / 今日=HH:MM / 昨日 / M/D) =====
function parseMsgTs(msg) {
  const raw = msg.ts_iso || msg.ts || '';
  if (!raw) return null;
  let d = new Date(raw);
  if (isNaN(d.getTime())) {
    d = new Date(String(raw).replace(' JST', '').replace(' ', 'T'));
  }
  return isNaN(d.getTime()) ? null : d;
}

function relativeTime(d) {
  if (!d) return '';
  const diffSec = (Date.now() - d.getTime()) / 1000;
  const hm = `${d.getHours()}:${String(d.getMinutes()).padStart(2, '0')}`;
  if (diffSec < 60) return 'たった今';
  if (diffSec < 3600) return `${Math.floor(diffSec / 60)}分前`;
  const now = new Date();
  if (d.toDateString() === now.toDateString()) return hm;
  const yest = new Date(now.getTime() - 86400000);
  if (d.toDateString() === yest.toDateString()) return `昨日 ${hm}`;
  return `${d.getMonth() + 1}/${d.getDate()} ${hm}`;
}

// 表示中の相対時刻を60秒ごとに更新
setInterval(() => {
  document.querySelectorAll('.msg-ts[data-epoch]').forEach(el => {
    const t = Number(el.dataset.epoch);
    if (t) el.textContent = relativeTime(new Date(t));
  });
}, 60_000);

// ===== R56: renderMessage (新tmpl-msg準拠) =====
function renderMessage(msg, prevMsg = null) {
  const tmpl = document.getElementById('tmpl-msg');
  const frag = tmpl.content.cloneNode(true);
  const article = frag.querySelector('.msg');
  article.dataset.actor = msg.actor || 'unknown';
  article.dataset.msgId = msg.msg_id;

  // UI-P0: アバター (Shuji自身は非表示=LINE流)
  const avatar = frag.querySelector('.msg-avatar');
  const av = ACTOR_AVATAR[msg.actor];
  if (av) {
    avatar.textContent = av.label;
    avatar.style.backgroundColor = av.color;
  }

  // UI-P0: システムカード判定 (📋まとめ/⚠️警告/⏺完了報告)
  const headText = (msg.body || msg.summary || '').trimStart();
  if (headText.startsWith('📋')) article.dataset.card = 'summary';
  else if (headText.startsWith('⚠') || headText.startsWith('⛔')) article.dataset.card = 'warn';
  else if (headText.startsWith('⏺')) article.dataset.card = 'report';

  // 連続発言判定 (5分以内 + 同actor)
  const sameAuthor = prevMsg && prevMsg.actor === msg.actor && (() => {
    const a = new Date(prevMsg.ts_iso || prevMsg.ts || 0);
    const b = new Date(msg.ts_iso || msg.ts || 0);
    if (isNaN(a.getTime()) || isNaN(b.getTime())) return true;
    return (b - a) < 5 * 60 * 1000;
  })();
  if (sameAuthor) article.dataset.sameAuthor = 'true';

  // sender-label (吹き出し上、 opacity-60)
  const senderLabel = frag.querySelector('.msg-sender-label');
  if (sameAuthor) {
    senderLabel.remove();
  } else {
    senderLabel.textContent = ACTOR_LABEL[msg.actor] || msg.actor || '?';
  }

  // R59 Q2: PWA表示は <pwa_summary> 200字、 全文は「証跡▼」 展開で
  const body = frag.querySelector('.msg-body');
  const summary = (msg.summary || '').trim();
  const hasFullBody = msg.body && msg.body.length > (summary.length || 0);
  if (summary && hasFullBody) {
    // 短縮表示モード
    body.innerHTML = renderMarkdownSafe(summary);
    body.dataset.fullBody = msg.body;  // 証跡で使う
    body.dataset.shortMode = '1';
  } else {
    body.innerHTML = renderMarkdownSafe(msg.body || summary);
  }
  addCodeCopyButtons(body);  // UI-P1: コードコピー

  // UI-P1: 長文折りたたみ「もっと見る」 (X/LINE風)
  if (body.dataset.shortMode !== '1' && (body.textContent || '').length > 600) {
    body.classList.add('collapsed');
    const more = document.createElement('button');
    more.type = 'button';
    more.className = 'more-btn text-[11px] font-bold mt-1 opacity-80 hover:opacity-100';
    more.textContent = '▼ もっと見る';
    more.addEventListener('click', () => {
      const collapsed = body.classList.toggle('collapsed');
      more.textContent = collapsed ? '▼ もっと見る' : '▲ 閉じる';
    });
    body.after(more);
  }

  // R59 Q3: consensus_value ラベル表示 (blocked/external_wait のみ目立たせる)
  const cv = msg.consensus_value;
  if (cv && cv !== 'true' && cv !== 'false') {
    const badge = document.createElement('span');
    badge.className = 'inline-block text-[10px] px-1.5 py-0.5 rounded ml-1 mt-1 ' +
      'bg-orange-500/30 text-orange-200 font-semibold';
    badge.textContent = cv === 'blocked' ? '⏸ 判断待ち' : '⌛ 外部待ち';
    body.appendChild(badge);
  }

  // R57 Phase F: 画像attachments 表示
  const atts = Array.isArray(msg.attachments) ? msg.attachments : [];
  atts.forEach(a => {
    if (!a || !a.url) return;
    const ct = (a.content_type || '').toLowerCase();
    if (!ct.startsWith('image/')) return;
    const wrap = document.createElement('div');
    wrap.className = 'msg-attachment mt-2';
    const img = document.createElement('img');
    img.src = a.url;
    img.alt = a.filename || 'attachment';
    img.loading = 'lazy';
    img.className = 'rounded-2xl max-w-full max-h-72 cursor-zoom-in';
    img.addEventListener('click', () => openImageModal(a.url));
    wrap.appendChild(img);
    body.appendChild(wrap);
  });

  // 証跡 (折りたたみ) — R59 Q2: 展開時 short mode を full body に置換するイベント
  const evidence = frag.querySelector('.msg-evidence');
  if (evidence && body.dataset.shortMode === '1') {
    evidence.addEventListener('toggle', () => {
      if (evidence.open && body.dataset.shortMode === '1') {
        body.innerHTML = renderMarkdownSafe(body.dataset.fullBody || msg.body);
        body.dataset.shortMode = '0';
        addCodeCopyButtons(body);  // UI-P1: 全文展開後もコピーボタン付与
      }
    });
  }
  frag.querySelector('.raw-markdown code').textContent = msg.raw || msg.body || '';
  frag.querySelector('.validator-log code').textContent =
    JSON.stringify(msg.validator || {}, null, 2);
  frag.querySelector('.tag-list code').textContent =
    JSON.stringify(msg.tags || {}, null, 2);

  // meta-bottom (時刻 + Validator + 巡数 + 既読)
  // UI-P0: 相対時刻表示 (data-epochで60秒毎に自動更新)
  const tsEl = frag.querySelector('.msg-ts');
  const tsDate = parseMsgTs(msg);
  if (tsDate) {
    tsEl.textContent = relativeTime(tsDate);
    tsEl.dataset.epoch = String(tsDate.getTime());
    tsEl.title = msg.ts || tsDate.toLocaleString();  // hover/長押しで絶対時刻
  } else {
    tsEl.textContent = msg.ts || '';
  }

  const v = msg.validator || {pass: true};
  const validatorEl = frag.querySelector('.msg-validator');
  validatorEl.textContent = v.pass ? '✓PASS' : '✗FAIL';
  validatorEl.classList.add(v.pass ? 'pass' : 'fail');

  const loopEl = frag.querySelector('.msg-loop');
  if (msg.loop) loopEl.textContent = `${msg.loop}巡`;
  else loopEl.remove();

  // R58 Must Fix A: 既読(n/3) 実値表示 (全 actor で受信者0-3)
  const readEl = frag.querySelector('.msg-read');
  const rc = typeof msg.read_count === 'number' ? msg.read_count : null;
  const rt = typeof msg.read_total === 'number' ? msg.read_total : 3;
  if (rc !== null) {
    readEl.textContent = `✓✓既読 (${rc}/${rt})`;
    if (rc === 0) readEl.style.opacity = '0.4';
    else if (rc < rt) readEl.style.opacity = '0.7';
    else readEl.style.opacity = '1.0';
  } else if (msg.actor === 'shuji') {
    readEl.textContent = '✓✓既読 (3/3)';  // fallback
  } else {
    readEl.remove();
  }

  // 監査スレッド button
  const auditCount = (msg.audits || []).length;
  const tb = frag.querySelector('.thread-btn');
  if (auditCount > 0) {
    tb.classList.remove('hidden');
    tb.querySelector('.thread-count').textContent = `(${auditCount})`;
    tb.dataset.parentMsgId = msg.msg_id;
  }
  return frag;
}

// ===== UX2: 既読管理 (SNS標準: 部屋を開くと未読の先頭へジャンプ) =====
function markRead() {
  if (!activeRoomId) return;
  const last = lastMsgIdByRoom[activeRoomId];
  if (last) try { localStorage.setItem('grl_read_' + activeRoomId, last); } catch (e) {}
}

function insertUnreadDivider(beforeNode) {
  document.getElementById('unread-divider')?.remove();
  const d = document.createElement('div');
  d.id = 'unread-divider';
  d.className = 'flex items-center gap-2 my-2 text-[11px] text-red-400 select-none';
  d.innerHTML =
    '<div class="flex-1 h-px bg-red-400/40"></div>ここから未読' +
    '<div class="flex-1 h-px bg-red-400/40"></div>';
  beforeNode.parentNode.insertBefore(d, beforeNode);
}

// ===== room activate =====
async function activateRoom(roomId) {
  activeRoomId = roomId;
  // P1-② (2026-06-12): 閲覧中roomを永続化 — 次回起動時に同じ部屋を開く
  // (旧: 起動毎に先頭roomへ自動activate → 意図しない部屋へのsubmit誤送信リスク)
  try { localStorage.setItem('grl_active_room', roomId); } catch (e) {}
  // 2026-06-16 fix: 未読ジャンプ用の既読位置を refreshTimeline の前に確保する。
  // refreshTimeline は空タイムラインを「最下部」と誤判定して markRead で全既読化
  // するため、後で読むと常に最新=既読になり未読先頭ジャンプが効かなかった。
  let lastRead = null;
  try { lastRead = localStorage.getItem('grl_read_' + roomId); } catch (e) {}

  await authFetch(`${API}/rooms/${roomId}/activate`, {method: 'POST'});
  document.getElementById('timeline').innerHTML = '';
  lastMsgIdByRoom[roomId] = '';
  lastRenderedMsgByRoom[roomId] = null;
  await refreshRoomState();
  await refreshTimeline();

  // UX2: 未読の先頭へ自動スクロール (「ここから未読」divider付き、 LINE/Discord標準)
  const tl = document.getElementById('timeline');
  let target = null;
  if (lastRead) {
    const nodes = Array.from(tl.querySelectorAll('.msg'));
    const idx = nodes.findIndex(n => n.dataset.msgId === lastRead);
    if (idx >= 0 && idx < nodes.length - 1) target = nodes[idx + 1];
  }
  if (target) {
    insertUnreadDivider(target);
    // iOS Safari: レイアウト確定後にコンテナ相対でスクロール (scrollIntoViewは
    // 画像読込で位置がずれる/ページ全体が飛ぶことがあるため自前計算)
    const jump = () => {
      const r = target.getBoundingClientRect();
      const c = tl.getBoundingClientRect();
      tl.scrollTop += (r.top - c.top) - 8;
    };
    requestAnimationFrame(() => requestAnimationFrame(jump));
  } else {
    tl.scrollTop = tl.scrollHeight;
  }
  markRead();
}

// ===== UI-P1: コードブロックのコピーボタン (ChatGPT風) =====
function addCodeCopyButtons(scope) {
  scope.querySelectorAll('pre').forEach(pre => {
    if (pre.querySelector('.code-copy-btn')) return;
    const codeText = pre.innerText;
    const btn = document.createElement('button');
    btn.className = 'code-copy-btn';
    btn.type = 'button';
    btn.textContent = 'コピー';
    btn.addEventListener('click', async (e) => {
      e.stopPropagation();
      try {
        await navigator.clipboard.writeText(codeText);
        btn.textContent = '✓';
        setTimeout(() => { btn.textContent = 'コピー'; }, 1500);
      } catch (_) {}
    });
    pre.style.position = 'relative';
    pre.appendChild(btn);
  });
}

// ===== UI-P0: タイピングインジケータ (LINE/ChatGPT風) =====
function updateTypingIndicator() {
  const el = document.getElementById('typing-indicator');
  if (!el) return;
  const actor = currentNextActor;
  const show = !!(processingRoomId && processingRoomId === activeRoomId
                  && actor && ACTOR_AVATAR[actor]);
  el.classList.toggle('hidden', !show);
  if (show) {
    const av = ACTOR_AVATAR[actor];
    const avEl = el.querySelector('.typing-avatar');
    avEl.textContent = av.label;
    avEl.style.backgroundColor = av.color;
    el.querySelector('.typing-text').textContent =
      `${ACTOR_LABEL[actor] || actor}が入力中`;
  }
}

// ===== UI-P0: 送信失敗バー (alert廃止、 再試行ボタン付き) =====
function showSendError(message) {
  let bar = document.getElementById('send-error-bar');
  if (!bar) {
    bar = document.createElement('div');
    bar.id = 'send-error-bar';
    bar.className = 'flex items-center gap-2 px-3 py-1.5 text-xs bg-red-900/60 text-red-200';
    const txt = document.createElement('span');
    txt.className = 'send-error-text flex-1 truncate';
    const retry = document.createElement('button');
    retry.textContent = '再試行';
    retry.className = 'px-2 py-0.5 rounded-full bg-red-500 text-white font-bold';
    retry.addEventListener('click', () => {
      bar.remove();
      document.getElementById('submit-btn').click();
    });
    const close = document.createElement('button');
    close.textContent = '✕';
    close.className = 'px-1 opacity-70';
    close.addEventListener('click', () => bar.remove());
    bar.append(txt, retry, close);
    const footer = document.querySelector('footer');
    footer.parentNode.insertBefore(bar, footer);
  }
  bar.querySelector('.send-error-text').textContent = `⚠ 送信失敗: ${message}`;
}

// ===== UI-P1: LINE風 部屋一覧 (☰ → 全画面リスト: プレビュー+相対時刻+状態+未読) =====
let lastOverview = null;

function renderRoomList() {
  const panel = document.getElementById('room-list-panel');
  if (!lastOverview || panel.classList.contains('hidden')) return;
  const wrap = document.getElementById('room-list-items');
  const tmpl = document.getElementById('tmpl-room-row');
  wrap.innerHTML = '';
  for (const room of lastOverview.rooms) {
    const frag = tmpl.content.cloneNode(true);
    const row = frag.querySelector('.room-row');
    row.dataset.roomId = room.room_id;
    const icon = frag.querySelector('.room-row-icon');
    icon.textContent = room.icon || '💬';
    icon.style.backgroundColor = room.color || '#4F46E5';
    frag.querySelector('.room-row-title').textContent = room.title || room.room_id;
    const st = frag.querySelector('.room-row-status');
    if (room.is_processing) {
      st.textContent = 'リレー中'; st.classList.add('bg-amber-400', 'text-black');
    } else if (room.queue_position) {
      st.textContent = `待機${room.queue_position}`; st.classList.add('bg-sky-600', 'text-white');
    } else if (room.status === 'max_loops_reached') {
      st.textContent = '上限'; st.classList.add('bg-red-500', 'text-white');
    } else if (room.is_consensus_established) {
      st.textContent = '合意'; st.classList.add('bg-green-600', 'text-white');
    } else {
      st.remove();
    }
    const d = room.last_msg_ts ? new Date(room.last_msg_ts) : null;
    frag.querySelector('.room-row-time').textContent =
      (d && !isNaN(d.getTime())) ? relativeTime(d) : '';
    frag.querySelector('.room-row-preview').textContent =
      room.last_msg_preview || (room.topic_title || '');
    const ub = frag.querySelector('.room-row-unread');
    if (room.unread_count) {
      ub.textContent = room.unread_count > 99 ? '99+' : room.unread_count;
      ub.classList.remove('hidden');
    }
    row.addEventListener('click', async () => {
      document.getElementById('room-list-panel').classList.add('hidden');
      await activateRoom(room.room_id);
    });
    wrap.appendChild(frag);
  }
}

document.getElementById('room-list-btn')?.addEventListener('click', () => {
  document.getElementById('room-list-panel').classList.remove('hidden');
  renderRoomList();
});
document.getElementById('room-list-close')?.addEventListener('click', () => {
  document.getElementById('room-list-panel').classList.add('hidden');
});

// ===== UI-P1: テーマ切替 (auto=システム追従 / light / dark) =====
function applyTheme(mode) {
  if (mode === 'light' || mode === 'dark') {
    document.documentElement.dataset.theme = mode;
  } else {
    delete document.documentElement.dataset.theme;
  }
  const btn = document.getElementById('theme-btn');
  if (btn) {
    btn.title = `テーマ: ${mode === 'auto' ? 'auto (システム追従)' : mode}`;
    btn.dataset.mode = mode;  // 手動mode中はアクセント色 (CSS)
  }
}
applyTheme(localStorage.getItem('grl_theme') || 'auto');
document.getElementById('theme-btn')?.addEventListener('click', () => {
  const cur = localStorage.getItem('grl_theme') || 'auto';
  const next = cur === 'auto' ? 'light' : cur === 'light' ? 'dark' : 'auto';
  try { localStorage.setItem('grl_theme', next); } catch (e) {}
  applyTheme(next);
});

// ===== UI-P1: 部屋内検索 + actorフィルタ (クライアント側、 0円) =====
let searchQuery = '';
let actorFilter = '';

function applySearchFilter() {
  const q = searchQuery.toLowerCase();
  document.querySelectorAll('#timeline .msg').forEach(m => {
    const matchActor = !actorFilter || m.dataset.actor === actorFilter;
    const matchText = !q || (m.textContent || '').toLowerCase().includes(q);
    m.classList.toggle('filtered-out', !(matchActor && matchText));
  });
  const active = !!(q || actorFilter);
  document.querySelectorAll('#timeline .date-separator').forEach(d =>
    d.classList.toggle('filtered-out', active));
}

document.getElementById('search-btn')?.addEventListener('click', () => {
  const bar = document.getElementById('search-bar');
  const opened = bar.classList.toggle('hidden');
  if (opened) {  // 閉じた → フィルタ解除
    searchQuery = ''; actorFilter = '';
    document.getElementById('search-input').value = '';
    document.querySelectorAll('.filter-chip').forEach(c =>
      c.classList.toggle('active', !c.dataset.filter));
    applySearchFilter();
  } else {
    document.getElementById('search-input').focus();
  }
});

document.getElementById('search-input')?.addEventListener('input', (e) => {
  searchQuery = e.target.value.trim();
  applySearchFilter();
});

document.getElementById('actor-filters')?.addEventListener('click', (e) => {
  const chip = e.target.closest('.filter-chip');
  if (!chip) return;
  actorFilter = chip.dataset.filter || '';
  document.querySelectorAll('.filter-chip').forEach(c =>
    c.classList.toggle('active', c === chip));
  applySearchFilter();
});

// ===== UX改善: 📋最新の合意まとめへジャンプ =====
document.getElementById('jump-summary-btn')?.addEventListener('click', () => {
  const bodies = Array.from(document.querySelectorAll('#timeline .msg-body'));
  const target = bodies.reverse().find(n => n.textContent.trim().startsWith('📋'));
  if (target) {
    target.closest('.msg')?.scrollIntoView({behavior: 'smooth', block: 'start'});
  } else {
    const tl = document.getElementById('timeline');
    if (tl) tl.scrollTop = tl.scrollHeight;  // まとめ無し → 最下部へ
  }
});

// ===== 監査スレッド (dark theme対応) =====
async function loadThread(parentMsgId, container) {
  const data = await fetchJSON(`${API}/thread/${encodeURIComponent(parentMsgId)}`);
  const kindBadge = {
    must_fix: 'bg-red-900/50 text-red-300',
    agree:    'bg-emerald-900/50 text-emerald-300',
    reinforce:'bg-blue-900/50 text-blue-300'
  };
  const kindLabel = {must_fix: 'Must Fix', agree: '同意', reinforce: '補強'};
  container.innerHTML = data.items.map(it => `
    <div class="thread-item flex gap-2">
      <span class="actor-pill">${escapeHtml((ACTOR_LABEL[it.actor] || '?'))}</span>
      <div class="flex-1">
        <div class="flex items-center gap-2 mb-0.5">
          <span class="text-[10px] opacity-60">${escapeHtml(it.ts || '')}</span>
          <span class="text-[10px] ${kindBadge[it.kind] || 'bg-white/10'} px-1.5 rounded">
            ${escapeHtml(kindLabel[it.kind] || it.kind || '')}
          </span>
        </div>
        <div class="text-xs opacity-90">${escapeHtml(it.body || '')}</div>
      </div>
    </div>`).join('');
}

// ===== Click delegation =====
document.addEventListener('click', async (e) => {
  // room icon
  const roomBtn = e.target.closest('.room-icon-btn');
  if (roomBtn && roomBtn.dataset.roomId) {
    return activateRoom(roomBtn.dataset.roomId);
  }

  // thread toggle
  const threadBtn = e.target.closest('.thread-btn');
  if (threadBtn) {
    const container = threadBtn.nextElementSibling;
    const expanded = threadBtn.getAttribute('aria-expanded') === 'true';
    threadBtn.setAttribute('aria-expanded', String(!expanded));
    container.classList.toggle('hidden', expanded);
    if (!expanded && container.dataset.loaded !== 'true') {
      await loadThread(threadBtn.dataset.parentMsgId, container);
      container.dataset.loaded = 'true';
    }
    return;
  }

  // R56: header settings - 詳細toggle
  if (e.target.closest('#header-settings-btn')) {
    const d = document.getElementById('header-details');
    if (d) d.open = !d.open;
    return;
  }

  // R56-r2: composer + button → popup toggle (📷/🖼️ を + 内に集約)
  if (e.target.closest('#composer-add-btn')) {
    e.stopPropagation();
    const btn = document.getElementById('composer-add-btn');
    const popup = document.getElementById('composer-add-popup');
    if (!popup) return;
    const open = popup.classList.contains('hidden');
    popup.classList.toggle('hidden', !open);
    btn.setAttribute('aria-expanded', open ? 'true' : 'false');
    return;
  }

  // R57-r57-PhaseF: popup item (📷撮影 / 🖼️画像選択) 実機能 — file picker起動
  const popupItem = e.target.closest('#composer-camera-btn, #composer-image-btn');
  if (popupItem) {
    const isCamera = popupItem.id === 'composer-camera-btn';
    const input = document.getElementById(
      isCamera ? 'file-input-camera' : 'file-input-library',
    );
    if (input) input.click();
    const popup = document.getElementById('composer-add-popup');
    const btn = document.getElementById('composer-add-btn');
    if (popup) popup.classList.add('hidden');
    if (btn) btn.setAttribute('aria-expanded', 'false');
    return;
  }

  // R56-r2: 外側クリックで popup 閉じる
  const popup = document.getElementById('composer-add-popup');
  if (popup && !popup.classList.contains('hidden')) {
    popup.classList.add('hidden');
    const btn = document.getElementById('composer-add-btn');
    if (btn) btn.setAttribute('aria-expanded', 'false');
  }
});

// ===== Submit / Interrupt / Notify =====
document.getElementById('submit-btn').addEventListener('click', async () => {
  if (!activeRoomId) return;
  const inp = document.getElementById('shuji-input');
  const sbtn = document.getElementById('submit-btn');
  const text = inp.value.trim();
  if (!text || sbtn.disabled) return;
  // UI-P0: 送信中スピナー + 二重送信防止
  sbtn.disabled = true;
  sbtn.classList.add('sending');
  try {
    const j = await submitWithRetry(text);
    if (j.ok) {
      inp.value = '';
      inp.style.height = 'auto';  // UX2: 送信後に入力欄の高さをリセット
      document.getElementById('send-error-bar')?.remove();
    } else {
      showSendError(j.error || '不明なエラー');  // 入力内容は保持
    }
  } catch (e) {
    showSendError(e.message);
  } finally {
    sbtn.disabled = false;
    sbtn.classList.remove('sending');
  }
});

document.getElementById('interrupt-btn').addEventListener('click', async () => {
  if (!activeRoomId) return;
  if (!confirm('AI処理を強制割込しますか?')) return;
  await authFetch(`${API}/rooms/${activeRoomId}/interrupt`, {method: 'POST'});
});

document.getElementById('notify-level').addEventListener('change', async (e) => {
  await authFetch(`${API}/notification`, {
    method: 'POST', headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({level: e.target.value}),
  });
});

// UX2: 入力欄オートリサイズ (入力内容に合わせて高さ可変、 最大=画面の35%)
const _composer = document.getElementById('shuji-input');
_composer.addEventListener('input', () => {
  _composer.style.height = 'auto';
  _composer.style.height =
    Math.min(_composer.scrollHeight, Math.floor(window.innerHeight * 0.35)) + 'px';
});

// UX2: Enter送信はデスクトップのみ (Shift+Enter=改行)。
// タッチ端末は Enter=改行 (LINE等のSNS標準)。日本語IME変換中は送信しない。
const _isTouch = window.matchMedia('(pointer: coarse)').matches;
_composer.addEventListener('keydown', (e) => {
  if (e.isComposing) return;
  if ((e.metaKey || e.ctrlKey) && e.key === 'Enter') {
    e.preventDefault();
    document.getElementById('submit-btn').click();
    return;
  }
  if (e.key === 'Enter' && !e.shiftKey && !_isTouch) {
    e.preventDefault();
    document.getElementById('submit-btn').click();
  }
});

// ===== SSE (R50承継、 指数バックオフ) =====
function setupSSE() {
  let attempts = 0;
  const connect = () => {
    try {
      const sse = new EventSource(`${API}/events`);
      sse.onopen = () => { attempts = 0; };
      sse.onmessage = () => {
        refreshSidebar().catch(()=>{});
        refreshRoomState().catch(()=>{});
        refreshTimeline().catch(()=>{});
      };
      sse.onerror = () => {
        sse.close();
        if (attempts < 3) {
          attempts++;
          const delay = 1000 * Math.pow(2, attempts - 1);
          showToast(`再接続中... (${attempts}/3)`);
          setTimeout(connect, delay);
        } else {
          showToast('SSE接続失敗、 polling継続');
        }
      };
    } catch (e) {
      console.warn('SSE失敗', e);
    }
  };
  connect();
}

// ===== R57 Phase F: 画像upload + modal =====
async function uploadAndSendImage(file) {
  if (!activeRoomId) {
    showToast('会議室を選択してください');
    return;
  }
  if (!file) return;
  if (!file.type.startsWith('image/')) {
    showToast(`画像ではないファイル: ${file.type}`);
    return;
  }
  try {
    const csrf = await fetchCsrf();
    const fd = new FormData();
    fd.append('file', file);
    const r = await fetch(`${API}/rooms/${activeRoomId}/upload`, {
      method: 'POST',
      headers: {
        ...(authB64 ? {'Authorization': `Basic ${authB64}`} : {}),
        'X-CSRF-Token': csrf,
      },
      body: fd,
    });
    if (!r.ok) {
      const j = await r.json().catch(() => ({error: r.statusText}));
      showToast(`upload失敗: ${j.error || r.statusText}`);
      return;
    }
    const meta = await r.json();
    // upload成功 → message送信 (添付付き)
    const text = `📷 ${meta.filename}`;
    const j = await submitWithRetry(text, {
      attachments: [{
        url: meta.url,
        filename: meta.filename,
        content_type: meta.content_type,
        size_bytes: meta.size_bytes,
      }],
    });
    if (j.ok) {
      showToast('画像送信成功');
    } else {
      showToast(`送信失敗: ${j.error || '不明'}`);
    }
  } catch (e) {
    showToast(`upload error: ${e.message}`);
  }
}

function openImageModal(url) {
  let modal = document.getElementById('img-modal');
  if (!modal) {
    modal = document.createElement('div');
    modal.id = 'img-modal';
    modal.className = 'fixed inset-0 z-50 bg-black/85 flex items-center justify-center p-4';
    modal.innerHTML =
      '<button class="absolute top-4 right-4 text-white text-3xl font-bold" aria-label="閉じる">×</button>' +
      '<img id="img-modal-img" class="max-w-full max-h-full rounded-2xl object-contain" />';
    modal.addEventListener('click', (e) => {
      if (e.target === modal || e.target.tagName === 'BUTTON') {
        modal.remove();
      }
    });
    document.body.appendChild(modal);
    // UI-P2: ピンチズーム (iOS gestureイベント) + ダブルタップでズーム切替
    const img = modal.querySelector('#img-modal-img');
    let zoom = 1;
    const setZoom = (z) => {
      zoom = Math.min(4, Math.max(1, z));
      img.style.transform = `scale(${zoom})`;
    };
    img.style.transition = 'transform .12s';
    img.addEventListener('dblclick', () => setZoom(zoom > 1 ? 1 : 2.5));
    let lastTap = 0;
    img.addEventListener('touchend', (e) => {  // iOSのダブルタップ検出
      const now = Date.now();
      if (now - lastTap < 300 && e.touches.length === 0) setZoom(zoom > 1 ? 1 : 2.5);
      lastTap = now;
    });
    let gestureBase = 1;
    img.addEventListener('gesturestart', (e) => { e.preventDefault(); gestureBase = zoom; });
    img.addEventListener('gesturechange', (e) => { e.preventDefault(); setZoom(gestureBase * e.scale); });
  }
  const imgEl = document.getElementById('img-modal-img');
  imgEl.style.transform = 'scale(1)';
  imgEl.src = url;
}

document.addEventListener('change', (e) => {
  const inp = e.target.closest('#file-input-camera, #file-input-library');
  if (!inp) return;
  const file = inp.files && inp.files[0];
  if (file) uploadAndSendImage(file);
  inp.value = '';  // reset so same file can be re-selected
});

// ===== AI育成リング (2026-06-24 PWA統合) =====
async function loadAiGrowthStatus() {
  const content = document.getElementById('ai-growth-content');
  if (!content) return;
  try {
    const s = await fetchJSON(`${API}/ai_growth/status`);
    if (s.error) {
      content.innerHTML = `<div class="text-red-400">エラー: ${s.error}</div>`;
      return;
    }
    const cycle = s.cycle || {};
    const def = s.defense || {};
    const off = s.offense || {};
    const cau = s.caution || {};
    const recent = s.recent_signals || [];

    const bar = Math.floor((cycle.progress_pct || 0) / 5);
    const barStr = '█'.repeat(Math.min(bar, 20)) + '░'.repeat(Math.max(20 - bar, 0));

    const verdict = (v) => v ? '✅' : '❌';
    const cautionVerdict = cau.caution_passed ? '✅' : '⚠️';

    // ⚔ 攻め層: 仮想損益を行で
    const pnlRow = (h) => {
      const p = off[`pnl_${h}h`] || {};
      const evald = p.evaluated || 0;
      if (evald > 0) {
        const avg = p.sum / evald;
        const cls = avg >= 0 ? 'text-green-400' : 'text-red-400';
        return `<div class="flex justify-between gap-2 py-0.5"><span class="text-dm-text-dim text-sm">${h}h後 平均</span><span class="text-sm ${cls}">$${avg >= 0 ? '+' : ''}${avg.toFixed(2)} <span class="text-dm-text-dim">(${p.wins}/${p.losses})</span></span></div>`;
      } else {
        return `<div class="flex justify-between gap-2 py-0.5"><span class="text-dm-text-dim text-sm">${h}h後 平均</span><span class="text-sm text-dm-text-dim">未到達</span></div>`;
      }
    };
    let pnl = pnlRow(1) + pnlRow(4) + pnlRow(24);

    let warns = '';
    if ((cau.warnings || []).length > 0) {
      warns = `<div class="mt-2 text-sm text-yellow-400">⚠️ ${cau.warnings.join('<br>⚠️ ')}</div>`;
    }

    let recentList = '';
    if (recent.length > 0) {
      recentList = '<div class="p-3 bg-dm-header rounded">'
        + '<div class="text-sm font-bold mb-2">📜 直近判定 (新しい順)</div>'
        + recent.slice().reverse().map(r => {
          const ts = (r.ts || '').slice(11, 16);
          const sig = r.signal || '';
          const sigEmoji = sig === 'long' ? '⬆️' : sig === 'short' ? '⬇️' : sig === 'force_stopped' ? '🛑' : '⏸️';
          return `<div class="flex justify-between gap-2 py-1 border-b border-dm-border last:border-0">
            <span class="text-sm">${ts} ${sigEmoji} ${r.regime}</span>
            <span class="text-sm text-dm-text-dim">$${(r.btc_price || 0).toFixed(0)}</span>
          </div>`;
        }).join('')
        + '</div>';
    }

    // 行: ラベル + 値 を flex で 確実に並べる (折り返し回避)
    const row = (label, value, valueClass = '') =>
      `<div class="flex justify-between gap-2 py-0.5"><span class="text-dm-text-dim text-sm">${label}</span><span class="text-sm ${valueClass}">${value}</span></div>`;

    content.innerHTML = `
      <div class="text-xs text-dm-text-dim">更新: ${(s.updated_at || '').slice(11, 19)} (model ${s.model_version})</div>

      <div class="mt-2 p-3 bg-dm-header rounded">
        <div class="text-sm font-bold mb-1">📊 サイクル進捗</div>
        <div class="text-base">${cycle.total} / ${cycle.target_max}件 <span class="text-dm-text-dim">(${cycle.progress_pct}%)</span></div>
        <div class="text-xs font-mono text-dm-text-dim mt-1 overflow-hidden whitespace-nowrap">${barStr}</div>
      </div>

      <div class="p-3 bg-dm-header rounded">
        <div class="text-sm font-bold mb-2">🛡 守り層 ${verdict(def.defense_passed)}</div>
        ${row('危ない場面でやる', def.dangerous_yarei_count + '件', def.dangerous_yarei_count > 0 ? 'text-red-400' : '')}
        ${row('ストップバグ', def.stop_rule_bugs + '件', def.stop_rule_bugs > 0 ? 'text-red-400' : '')}
        ${row('自動ループ', def.auto_loop_detected + '件')}
        ${row('内容崩壊', def.auto_collapse_detected + '件')}
      </div>

      <div class="p-3 bg-dm-header rounded">
        <div class="text-sm font-bold mb-2">⚔ 攻め層</div>
        ${pnl}
        ${row('勝率(24h)', ((off.win_rate_24h || 0) * 100).toFixed(1) + '%')}
      </div>

      <div class="p-3 bg-dm-header rounded">
        <div class="text-sm font-bold mb-2">😨 臆病チェック ${cautionVerdict}</div>
        ${row('no_trade率', ((cau.no_trade_rate || 0) * 100).toFixed(1) + '%')}
        ${row('強制ストップ率', ((cau.force_stopped_rate || 0) * 100).toFixed(1) + '%')}
        ${row('応答長', (cau.avg_response_length || 0).toFixed(0) + '字')}
        ${warns}
      </div>

      ${recentList}
    `;
  } catch (e) {
    content.innerHTML = `<div class="text-red-400">取得失敗: ${e.message}</div>`;
  }
}

document.getElementById('ai-growth-btn')?.addEventListener('click', () => {
  document.getElementById('ai-growth-modal').classList.remove('hidden');
  loadAiGrowthStatus();
});
document.getElementById('ai-growth-refresh')?.addEventListener('click', () => {
  loadAiGrowthStatus();
});

// ===== Init =====
(async () => {
  const ok = await initAuth();
  if (!ok) {
    showToast('認証必要、 再読み込みで再試行', 10000);
    return;
  }
  setupSSE();
  try {
    const cfg = await fetchJSON(`${API}/notification`);
    document.getElementById('notify-level').value = cfg.level || 'normal';
  } catch (e) {}
  await refreshSidebar();
  setInterval(() => {
    refreshSidebar().catch(()=>{});
    refreshRoomState().catch(()=>{});
    refreshTimeline().catch(()=>{});
  }, 5000);
})();
