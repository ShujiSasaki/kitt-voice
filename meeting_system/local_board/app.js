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
};
const STATUS_TOOLTIP = {
  idle: '待機中',
  ai_processing: '議論中',
  paused_by_shuji: 'Shuji割込中',
  consensus_reached: '合意成立',
};

let activeRoomId = null;
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
async function submitWithRetry(body, maxRetries = 3) {
  const clientMsgId = (crypto.randomUUID && crypto.randomUUID()) ||
    `${Date.now()}_${Math.random().toString(36).slice(2)}`;
  let lastError;
  for (let i = 0; i < maxRetries; i++) {
    try {
      const r = await authFetch(`${API}/rooms/${activeRoomId}/submit`, {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({
          actor: 'shuji', body,
          client_msg_id: clientMsgId,
        }),
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
async function refreshSidebar() {
  const data = await fetchJSON(`${API}/rooms/overview`);
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

    if (data.global?.active_room_id === room.room_id) {
      btn.setAttribute('aria-current', 'true');
    } else {
      btn.removeAttribute('aria-current');
    }
  }

  for (const btn of Array.from(sidebar.querySelectorAll('.room-icon-btn'))) {
    if (!existing.has(btn.dataset.roomId)) btn.remove();
  }

  if (!activeRoomId && data.rooms.length) {
    await activateRoom(data.rooms[0].room_id);
  }
}

// ===== Header status (R56で 簡潔サマリ + 詳細<details>折りたたみ) =====
async function refreshRoomState() {
  if (!activeRoomId) return;
  const s = await fetchJSON(`${API}/rooms/${activeRoomId}/state`);
  document.getElementById('active-room-title').textContent =
    s.project_name || s.room_id;

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

  document.getElementById('submit-btn').disabled = (s.status === 'ai_processing');
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

  let prevMsg = lastRenderedMsgByRoom[activeRoomId] || null;
  for (const msg of data.messages) {
    if (tl.querySelector(`[data-msg-id="${CSS.escape(msg.msg_id)}"]`)) continue;
    maybeInsertDateSeparator(tl, msg, prevMsg);
    tl.appendChild(renderMessage(msg, prevMsg));
    lastMsgIdByRoom[activeRoomId] = msg.msg_id;
    prevMsg = msg;
  }
  lastRenderedMsgByRoom[activeRoomId] = prevMsg;
  tl.scrollTop = tl.scrollHeight;
}

// ===== R56: renderMessage (新tmpl-msg準拠) =====
function renderMessage(msg, prevMsg = null) {
  const tmpl = document.getElementById('tmpl-msg');
  const frag = tmpl.content.cloneNode(true);
  const article = frag.querySelector('.msg');
  article.dataset.actor = msg.actor || 'unknown';
  article.dataset.msgId = msg.msg_id;

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

  // bubble本体
  const body = frag.querySelector('.msg-body');
  body.innerHTML = renderMarkdownSafe(msg.body);

  // 証跡 (折りたたみ)
  frag.querySelector('.raw-markdown code').textContent = msg.raw || msg.body || '';
  frag.querySelector('.validator-log code').textContent =
    JSON.stringify(msg.validator || {}, null, 2);
  frag.querySelector('.tag-list code').textContent =
    JSON.stringify(msg.tags || {}, null, 2);

  // meta-bottom (時刻 + Validator + 巡数 + 既読)
  let tsShort = msg.ts_short || '';
  if (!tsShort && msg.ts_iso) {
    const d = new Date(msg.ts_iso);
    if (!isNaN(d.getTime())) {
      const h = d.getHours(), m = String(d.getMinutes()).padStart(2, '0');
      const ampm = h >= 12 ? 'PM' : 'AM';
      const hh12 = h % 12 || 12;
      tsShort = `${hh12}:${m} ${ampm}`;
    }
  }
  if (!tsShort) tsShort = msg.ts || '';
  frag.querySelector('.msg-ts').textContent = tsShort;

  const v = msg.validator || {pass: true};
  const validatorEl = frag.querySelector('.msg-validator');
  validatorEl.textContent = v.pass ? '✓PASS' : '✗FAIL';
  validatorEl.classList.add(v.pass ? 'pass' : 'fail');

  const loopEl = frag.querySelector('.msg-loop');
  if (msg.loop) loopEl.textContent = `${msg.loop}巡`;
  else loopEl.remove();

  const readEl = frag.querySelector('.msg-read');
  if (msg.actor === 'shuji') readEl.textContent = '✓✓既読 (3/3)';
  else readEl.remove();

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

// ===== room activate =====
async function activateRoom(roomId) {
  activeRoomId = roomId;
  await authFetch(`${API}/rooms/${roomId}/activate`, {method: 'POST'});
  document.getElementById('timeline').innerHTML = '';
  lastMsgIdByRoom[roomId] = '';
  lastRenderedMsgByRoom[roomId] = null;
  await refreshRoomState();
  await refreshTimeline();
}

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

  // R56: Quick action chip → composer prefill
  const chip = e.target.closest('.quick-chip');
  if (chip) {
    const action = chip.dataset.action;
    const prefillMap = {
      'propose-reply':  '【返信を提案】',
      'propose-topic': '【話題を提案】',
      'analyze-mood':  '【ムードを分析】',
    };
    const inp = document.getElementById('shuji-input');
    if (inp) {
      const cur = inp.value.trim();
      inp.value = cur ? `${cur}\n${prefillMap[action]} ` : `${prefillMap[action]} `;
      inp.focus();
    }
    return;
  }

  // R56: header settings - 詳細toggle
  if (e.target.closest('#header-settings-btn')) {
    const d = document.getElementById('header-details');
    if (d) d.open = !d.open;
    return;
  }

  // R56: composer icon stub (機能Phase 2)
  const iconId = e.target.closest('[id^="composer-"]')?.id;
  if (iconId && iconId !== 'composer-add-btn') {
    showToast(`${iconId.replace('composer-', '').replace('-btn', '')} 機能はPhase 2予定`);
    return;
  }
  if (iconId === 'composer-add-btn') {
    showToast('添付機能はPhase 2予定');
    return;
  }
});

// ===== Submit / Interrupt / Notify =====
document.getElementById('submit-btn').addEventListener('click', async () => {
  if (!activeRoomId) return;
  const inp = document.getElementById('shuji-input');
  const text = inp.value.trim();
  if (!text) return;
  try {
    const j = await submitWithRetry(text);
    if (j.ok) inp.value = '';
    else alert(j.error || '送信失敗');
  } catch (e) {
    alert(`送信エラー: ${e.message}`);
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

document.getElementById('shuji-input').addEventListener('keydown', (e) => {
  if ((e.metaKey || e.ctrlKey) && e.key === 'Enter') {
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
