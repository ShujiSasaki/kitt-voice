/* meeting_system/local_board/app.js
 * 3者合意:
 *   - SSE経由でリアルタイム更新
 *   - AI処理中はShuji送信ボタンgrayout (Gemini Must Fix 1)
 *   - DOMPurifyサニタイズ (Gemini Must Fix 4)
 *   - 通知 ON/OFF/STRICT 切替
 *   - 左サイドバー (Discord/X風) ↔ 右タイムライン (LINE/X風)
 *   - 合意成立時の緑グロー演出
 */
'use strict';

const API = '/api';
const ACTOR_LABEL = {
  gpt: 'GPT', gemini: 'Gemini', claude: 'Claude',
  shuji: 'Shuji', validator: 'Validator',
};
const STATUS_DOT_CLASS = {
  idle: 'bg-gray-500',
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
  const r = await fetch(url, opts);
  if (!r.ok) throw new Error(`${url} → ${r.status}`);
  return r.json();
}

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
    shape.style.backgroundColor = room.color || '#888888';

    const badge = btn.querySelector('.unread-badge');
    badge.textContent = room.unread_count || 0;
    badge.classList.toggle('hidden', (room.unread_count || 0) === 0);

    const dot = btn.querySelector('.status-dot');
    dot.className = `status-dot absolute -bottom-1 -right-1 w-3.5 h-3.5 rounded-full
                     ring-2 ring-gray-900 ${STATUS_DOT_CLASS[room.status] || 'bg-gray-500'}`;
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
      shape.classList.add('ring-white');
    } else {
      btn.removeAttribute('aria-current');
      shape.classList.remove('ring-white');
    }
  }

  for (const btn of Array.from(sidebar.querySelectorAll('.room-icon-btn'))) {
    if (!existing.has(btn.dataset.roomId)) btn.remove();
  }

  if (!activeRoomId && data.rooms.length) {
    await activateRoom(data.rooms[0].room_id);
  }
}

async function refreshRoomState() {
  if (!activeRoomId) return;
  const s = await fetchJSON(`${API}/rooms/${activeRoomId}/state`);
  document.getElementById('active-room-title').textContent =
    s.project_name || s.room_id;
  document.getElementById('status-current').textContent = s.status || 'idle';
  document.getElementById('next-actor').textContent =
    (s.next_actor || '-').toUpperCase();
  document.getElementById('loop-progress').textContent = s.total_loops || 0;
  document.getElementById('consensus-status').textContent =
    s.is_consensus_established ? '成立' : '未成立';
  document.getElementById('consensus-status').className =
    s.is_consensus_established ? 'text-green-600 font-bold' : 'text-red-600';

  const turn = s.current_turn_in_loop || 0;
  document.getElementById('dot-gpt').className =
    `w-3 h-3 rounded-full ${turn >= 1 || s.next_actor === 'gemini' || s.next_actor === 'claude' ? 'bg-actor-gpt' : (s.next_actor === 'gpt' ? 'bg-gray-300 animate-pulse' : 'bg-gray-300')}`;
  document.getElementById('dot-gemini').className =
    `w-3 h-3 rounded-full ${turn >= 2 || s.next_actor === 'claude' ? 'bg-actor-gemini' : (s.next_actor === 'gemini' ? 'bg-gray-300 animate-pulse' : 'bg-gray-300')}`;
  document.getElementById('dot-claude').className =
    `w-3 h-3 rounded-full ${turn === 0 && s.total_loops > 0 ? 'bg-actor-claude' : (s.next_actor === 'claude' ? 'bg-gray-300 animate-pulse' : 'bg-gray-300')}`;

  document.getElementById('submit-btn').disabled = (s.status === 'ai_processing');
}

async function refreshTimeline() {
  if (!activeRoomId) return;
  const since = lastMsgIdByRoom[activeRoomId] || '';
  const data = await fetchJSON(
    `${API}/rooms/${activeRoomId}/timeline?since=${encodeURIComponent(since)}`,
  );
  const tl = document.getElementById('timeline');
  const hint = document.getElementById('empty-hint');
  if (hint) hint.classList.add('hidden');

  for (const msg of data.messages) {
    if (tl.querySelector(`[data-msg-id="${CSS.escape(msg.msg_id)}"]`)) continue;
    tl.appendChild(renderMessage(msg));
    lastMsgIdByRoom[activeRoomId] = msg.msg_id;
  }
  tl.scrollTop = tl.scrollHeight;
}

function renderMessage(msg) {
  const tmpl = document.getElementById('tmpl-msg');
  const frag = tmpl.content.cloneNode(true);
  const article = frag.querySelector('.msg');
  article.dataset.actor = msg.actor || 'unknown';
  article.dataset.msgId = msg.msg_id;

  const avatarAbbr = ACTOR_LABEL[msg.actor] || '?';
  frag.querySelector('.msg-avatar').textContent = avatarAbbr.slice(0, 3);
  frag.querySelector('.msg-actor').textContent = avatarAbbr;
  frag.querySelector('.msg-ts').textContent = msg.ts || '';

  const v = msg.validator || {pass: true};
  const validatorEl = frag.querySelector('.msg-validator');
  validatorEl.textContent = v.pass ? '✓PASS' : '✗FAIL';
  validatorEl.classList.add(v.pass ? 'pass' : 'fail');

  const loopEl = frag.querySelector('.msg-loop');
  if (msg.loop) {
    loopEl.textContent = `${msg.loop}巡目`;
  } else {
    loopEl.remove();
  }

  const readEl = frag.querySelector('.msg-read');
  if (msg.actor === 'shuji') {
    readEl.textContent = '✓✓既読 (3/3)';
  } else {
    readEl.remove();
  }

  frag.querySelector('.msg-body').innerHTML = renderMarkdownSafe(msg.body);
  frag.querySelector('.raw-markdown code').textContent = msg.raw || msg.body || '';
  frag.querySelector('.validator-log code').textContent =
    JSON.stringify(msg.validator || {}, null, 2);
  frag.querySelector('.tag-list code').textContent =
    JSON.stringify(msg.tags || {}, null, 2);

  const auditCount = (msg.audits || []).length;
  const tb = frag.querySelector('.thread-btn');
  if (auditCount > 0) {
    tb.classList.remove('hidden');
    tb.querySelector('.thread-count').textContent = `(${auditCount})`;
    tb.dataset.parentMsgId = msg.msg_id;
  }
  return frag;
}

async function activateRoom(roomId) {
  activeRoomId = roomId;
  await fetch(`${API}/rooms/${roomId}/activate`, {method: 'POST'});
  document.getElementById('timeline').innerHTML = '';
  lastMsgIdByRoom[roomId] = '';
  await refreshRoomState();
  await refreshTimeline();
}

async function loadThread(parentMsgId, container) {
  const data = await fetchJSON(`${API}/thread/${encodeURIComponent(parentMsgId)}`);
  const colorMap = {gpt: 'green', gemini: 'purple', claude: 'amber',
                    shuji: 'lime', validator: 'red'};
  const kindBadge = {must_fix: 'bg-red-100 text-red-700',
                     agree: 'bg-green-100 text-green-700',
                     reinforce: 'bg-blue-100 text-blue-700'};
  const kindLabel = {must_fix: 'Must Fix', agree: '同意', reinforce: '補強'};
  container.innerHTML = data.items.map(it => `
    <div class="thread-item flex gap-2">
      <div class="flex-shrink-0 w-7 h-7 rounded-full bg-actor-${escapeHtml(it.actor)}
                  text-white text-[10px] font-bold flex items-center justify-center">
        ${escapeHtml((ACTOR_LABEL[it.actor] || '?').slice(0,3))}
      </div>
      <div class="flex-1 bg-${colorMap[it.actor] || 'gray'}-50 rounded-xl px-3 py-2">
        <div class="flex items-center gap-2 mb-1">
          <span class="text-[11px] font-semibold text-actor-${escapeHtml(it.actor)}">${escapeHtml(it.actor)}</span>
          <span class="text-[10px] text-gray-500">${escapeHtml(it.ts || '')}</span>
          <span class="text-[10px] ${kindBadge[it.kind] || 'bg-gray-100 text-gray-700'} px-1.5 rounded">
            ${escapeHtml(kindLabel[it.kind] || it.kind || '')}
          </span>
        </div>
        <div class="text-xs text-gray-800">${escapeHtml(it.body || '')}</div>
      </div>
    </div>`).join('');
}

document.addEventListener('click', async (e) => {
  const roomBtn = e.target.closest('.room-icon-btn');
  if (roomBtn && roomBtn.dataset.roomId) {
    return activateRoom(roomBtn.dataset.roomId);
  }

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
  }
});

document.getElementById('submit-btn').addEventListener('click', async () => {
  if (!activeRoomId) return;
  const inp = document.getElementById('shuji-input');
  const text = inp.value.trim();
  if (!text) return;
  try {
    const r = await fetch(`${API}/rooms/${activeRoomId}/submit`, {
      method: 'POST', headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({actor: 'shuji', body: text}),
    });
    const j = await r.json();
    if (j.ok) inp.value = '';
    else alert(j.error || '送信失敗');
  } catch (e) {
    alert(`送信エラー: ${e.message}`);
  }
});

document.getElementById('interrupt-btn').addEventListener('click', async () => {
  if (!activeRoomId) return;
  if (!confirm('AI処理を強制割込しますか?')) return;
  await fetch(`${API}/rooms/${activeRoomId}/interrupt`, {method: 'POST'});
});

document.getElementById('notify-level').addEventListener('change', async (e) => {
  await fetch(`${API}/notification`, {
    method: 'POST', headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({level: e.target.value}),
  });
});

document.getElementById('shuji-input').addEventListener('keydown', (e) => {
  if ((e.metaKey || e.ctrlKey) && e.key === 'Enter') {
    document.getElementById('submit-btn').click();
  }
});

try {
  const sse = new EventSource(`${API}/events`);
  sse.onmessage = () => {
    refreshSidebar().catch(()=>{});
    refreshRoomState().catch(()=>{});
    refreshTimeline().catch(()=>{});
  };
} catch (e) {
  console.warn('SSE接続失敗、 polling fallback', e);
}

(async () => {
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
