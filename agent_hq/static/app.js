// Agent HQ: recorded status (Markdown), observed activity (transcript metadata) and the pixel office (scene.js). Renders only what the API returns; all text goes in via textContent.
'use strict';

const main = document.getElementById('main');
const nav = document.getElementById('nav');
const readAt = document.getElementById('readat');
const NR = 'not recorded';
let liveData = null;
let liveError = null;
const LIVE_MS = 5000;

function h(tag, cls, text, kids) {
  const el = document.createElement(tag);
  if (cls) el.className = cls;
  if (text !== undefined && text !== null) el.textContent = text;
  (kids || []).forEach(k => k && el.appendChild(k));
  return el;
}
const val = v => (v === null || v === undefined || v === '') ? NR : String(v);
const statusCls = s => 'st st-' + (s ? s.toLowerCase() : 'unknown');

function statusBadge(status, known) {
  const b = h('span', 'badge rec ' + statusCls(known === false ? null : status), val(status));
  b.title = 'Recorded status (TASK_BOARD.md)';
  return b;
}
function verifiedBadge(status) {
  return status === 'DONE' ? h('span', 'badge verified', 'Verified complete') : null;
}
function agentBadge(status) {
  const b = h('span', 'badge agent', 'agent says: ' + val(status));
  b.title = "Agent-reported handoff status — not task completion";
  return b;
}
function checkerBadge(hf) {
  const b = h('span', 'badge ' + (hf.checker === 'PASS' ? 'pass' : 'warn'), 'checker ' + hf.checker);
  b.title = hf.checker_problems.length ? hf.checker_problems.join('\n') : 'All six handoff parts present (check_handoff.py)';
  return b;
}
const src = s => h('code', 'src', s);
function stamp(file) {  // YYYYMMDD-HHMM prefix of a handoff file name
  const m = /^(\d{4})(\d{2})(\d{2})-(\d{2})(\d{2})/.exec(file || '');
  return m ? `${m[1]}-${m[2]}-${m[3]} ${m[4]}:${m[5]}` : NR;
}

function warningsPanel(list, title) {
  if (!list.length) return h('section', 'panel', null, [h('h2', null, title), h('p', 'muted', 'No inconsistencies found in the records.')]);
  return h('section', 'panel warnpanel', null, [
    h('h2', null, `${title} (${list.length})`),
    h('ul', 'warnlist', null, list.map(w => h('li', null, null, [
      h('span', 'badge warn', w.kind), h('span', null, ' ' + w.text + ' '), w.source ? src(w.source) : null])))
  ]);
}

function agentCard(a, slug) {
  const owned = a.owned_tasks.filter(t => !slug || t.slug === slug);
  const last = a.last_handoff && (!slug || a.last_handoff.slug === slug) ? a.last_handoff : null;
  const initials = val(a.name).split('-').map(w => w[0]).join('').toUpperCase();
  const desk = h('div', 'desk', null, [h('span', 'sprite sprite-' + val(a.name).replace(/[^a-z-]/g, ''), initials)]);
  desk.setAttribute('aria-hidden', 'true');
  return h('article', 'card agentcard', null, [
    desk,
    h('div', 'agentbody', null, [
      h('h3', null, val(a.name)),
      h('div', 'row', null, [h('span', 'chip', 'model: ' + val(a.model)),
        h('span', 'chip', a.tools.includes('Write') || a.tools.includes('Edit') ? 'can write' : 'read-only')]),
      last
        ? h('p', 'small', null, [h('span', null, 'Last handoff ' + stamp(last.file) + ' · ' + val(last.task_id) + ' '), agentBadge(last.status)])
        : h('p', 'small muted', 'No recorded handoffs' + (slug ? ' in this project' : '')),
      obsLine(a.name),
      h('p', 'small muted', `Handoffs on record: ${a.handoff_count}` + (owned.length ? ` · named in Owner of ${owned.map(t => t.id).join(', ')}` : '')),
      src(a.source),
    ])
  ]);
}
function orchestratorCard() {
  return h('article', 'card agentcard orch', null, [
    h('div', 'desk', null, [h('span', 'sprite sprite-orchestrator', 'OR')]),
    h('div', 'agentbody', null, [
      h('h3', null, 'orchestrator'),
      h('p', 'small', 'The main Claude Code session. Routes work between agents; not an agent definition.'),
      obsLine('__orchestrator'),
    ])
  ]);
}

function ago(s) {
  if (s === null || s === undefined) return NR;
  if (s < 60) return s + ' s ago';
  if (s < 3600) return Math.floor(s / 60) + ' min ago';
  if (s < 86400) return Math.floor(s / 3600) + ' h ago';
  return Math.floor(s / 86400) + ' d ago';
}
const STATE_TEXT = {
  active: 'active (written < 30 s ago)', recent: 'recent (written < 5 min ago)', idle: 'idle (written < 1 h ago)',
  dormant: 'dormant (no writes for > 1 h)', ended: 'run ended (per meta file) — not task completion',
  unknown: 'unknown (not marked finished, no recent writes)',
};
function obsBadge(state) {
  const b = h('span', 'badge obs obs-' + (state || 'unknown'), 'observed: ' + (state || 'unknown'));
  b.title = STATE_TEXT[state] || 'unknown';
  return b;
}
function toolText(tool) { return tool ? 'last tool ' + tool : 'no tool call in recent records'; }

function obsLine(name) {
  const p = h('p', 'small obsline');
  p.dataset.agent = name || '';
  return p;
}
function fillObsLines() {
  document.querySelectorAll('.obsline').forEach(p => {
    p.replaceChildren();
    if (!liveData) { p.appendChild(h('span', 'muted', liveError ? 'observed: live data unavailable (' + liveError + ')' : 'observed: waiting for live data')); return; }
    if (!liveData.available) { p.appendChild(h('span', 'muted', 'observed: transcript folder not found on this Mac')); return; }
    if (p.dataset.agent === '__orchestrator') {
      const s = liveData.sessions[0];
      if (!s) { p.appendChild(h('span', 'muted', `observed: no workspace session in the last ${liveData.window_h} h`)); return; }
      p.append(obsBadge(s.state), h('span', null, ` session ${s.id8} · ${s.tool_read === false ? 'tool not read (older than 24 h)' : toolText(s.last_tool)} · ${ago(s.age_s)}`));
      return;
    }
    const r = Object.prototype.hasOwnProperty.call(liveData.agents, p.dataset.agent) ? liveData.agents[p.dataset.agent] : null;
    if (!r) { p.appendChild(h('span', 'muted', 'observed: no sub-agent run found in the transcripts')); return; }
    p.append(obsBadge(r.state), h('span', null, ` ${r.tool_read === false ? 'tool not read (older than 24 h)' : toolText(r.last_tool)} · ${ago(r.age_s)}`));
  });
}

function livePanel() {
  const sec = h('section', 'panel livepanel', null, [h('h2', null, 'Live — observed activity')]);
  sec.id = 'livepanel';
  return sec;
}
function fillLivePanel() {
  const sec = document.getElementById('livepanel');
  if (!sec) return;
  const kids = [h('h2', null, 'Live — observed activity'),
    h('p', 'small muted', 'From transcript file times and tool names only (no message content). Observed activity is not task progress; projects cannot be told apart from metadata, so this is workspace-wide.')];
  if (!liveData) kids.push(h('p', liveError ? 'warntext' : 'muted', liveError ? 'Live data unavailable: ' + liveError : 'waiting for live data…'));
  else if (!liveData.available) kids.push(h('p', 'muted', 'No transcript folder for this workspace on this Mac: ' + liveData.source));
  else if (!liveData.sessions.length) kids.push(h('p', 'muted', `No workspace sessions in the last ${liveData.window_h} h.`));
  else {
    const rows = [];
    liveData.sessions.forEach(s => {
      rows.push(h('tr', 'sessrow', null, [h('td', null, null, [h('strong', null, 'orchestrator')]), h('td', null, 'session ' + s.id8),
        h('td', null, null, [obsBadge(s.state)]), h('td', null, s.tool_read === false ? 'not read (older than the live window)' : toolText(s.last_tool)), h('td', null, ago(s.age_s))]));
      s.subagents.forEach(r => rows.push(h('tr', null, null, [h('td', 'indent', '└ ' + (r.agent_type || (r.meta_pending ? 'sub-agent (type known when the run ends)' : NR))), h('td', null, 'run ' + r.run_id + (r.meta_pending ? ' · meta pending' : '')),
        h('td', null, null, [obsBadge(r.state)]), h('td', null, r.tool_read === false ? 'not read (older than the live window)' : toolText(r.last_tool)), h('td', null, ago(r.age_s))])));
    });
    kids.push(h('div', 'tablewrap', null, [h('table', 'htable', null, [
      h('thead', null, null, [h('tr', null, null, ['Who', 'Session / run', 'Observed state', 'Last tool', 'Last write'].map(c => h('th', null, c)))]),
      h('tbody', null, null, rows)])]));
  }
  kids.push(h('p', 'small muted', null, [h('span', null, 'Source: '), src(liveData ? liveData.source : NR),
    h('span', null, liveData ? ' · read ' + new Date().toLocaleTimeString() : '')]));
  sec.replaceChildren(...kids);
}
function fileActivityPanel(fa) {
  const rows = fa.recent_files.map(f => h('tr', null, null, [h('td', null, null, [src(f.path)]), h('td', null, ago(f.age_s))]));
  return h('section', 'panel', null, [h('h2', null, 'Recently modified files in this project'),
    h('p', 'small muted', 'File modification times only: they show that a file changed, not who changed it or whether the change is correct.'),
    h('div', 'tablewrap', null, [h('table', 'htable', null, [
      h('thead', null, null, [h('tr', null, null, [h('th', null, 'File'), h('th', null, 'Modified')])]), h('tbody', null, null, rows)])])]);
}

function officePanel(agents, projects, focus) {
  const sec = h('section', 'panel office', null, [h('h2', null, 'Office')]);
  const key = h('p', 'small muted officekey', null, [
    h('span', null, 'Lamps and motion = observed transcript writes: '),
    h('span', 'lamp lamp-active', 'active'), h('span', 'lamp lamp-recent', 'recent'), h('span', 'lamp lamp-idle', 'idle'),
    h('span', 'lamp lamp-dormant', 'dormant / run ended'), h('span', 'lamp lamp-unknown', '? unknown'), h('span', 'lamp lamp-none', 'faded = no run observed'),
    h('span', null, ' · Room boards and handoff trays = recorded Markdown (board columns: T todo, P in progress, C needs context, R in review, V revision required, B blocked, A approved, D done, each with its count). Hover for details; click a room to open it.')]);
  sec.appendChild(key);
  if (window.AgentScene) window.AgentScene.mount(sec, { agents, projects, live: liveData, focus });
  else sec.appendChild(h('p', 'muted', 'scene.js not loaded'));
  return sec;
}

function countBy(tasks) {
  const c = {}; tasks.forEach(t => { c[t.status] = (c[t.status] || 0) + 1; }); return c;
}

function renderOverview(data) {
  main.replaceChildren();
  const projects = h('section', 'panel', null, [h('h2', null, `Projects (${data.projects.length})`)]);
  const grid = h('div', 'grid');
  data.projects.forEach(p => {
    const c = countBy(p.board.tasks);
    const reg = p.registry || {};
    const a = h('a', 'card projcard', null, [
      h('h3', null, val(reg.Title || p.slug)),
      h('p', 'small muted', p.slug + ' · ' + val(reg.Domain)),
      h('div', 'row', null, [h('span', 'chip', 'registry: ' + val(reg.Status)),
        h('span', 'chip', 'board updated ' + val(p.board_updated)),
        h('span', 'chip', `${p.handoffs.length} handoffs`)]),
      h('div', 'row', null, data.statuses.filter(s => c[s]).map(s => h('span', 'badge rec ' + statusCls(s), `${s} ×${c[s]}`))),
      p.warnings.length ? h('p', 'small', null, [h('span', 'badge warn', `${p.warnings.length} inconsistenc${p.warnings.length === 1 ? 'y' : 'ies'}`)]) : null,
    ]);
    a.href = '/p/' + encodeURIComponent(p.slug);
    grid.appendChild(a);
  });
  projects.appendChild(grid);

  const roster = h('section', 'panel', null, [h('h2', null, `Agents (${data.agents.length} defined in .claude/agents/)`)]);
  roster.appendChild(h('div', 'grid agents', null, [orchestratorCard(), ...data.agents.map(a => agentCard(a, null))]));

  const allWarn = data.warnings.concat(...data.projects.map(p => p.warnings.map(w => Object.assign({}, w, { text: p.slug + ': ' + w.text }))));
  main.append(officePanel(data.agents, data.projects, null), projects, livePanel(), roster, warningsPanel(allWarn, 'Inconsistencies'));
  fillLivePanel(); fillObsLines();
}

function taskCard(t, handoffsByFile) {
  const linked = t.linked_handoffs.map(f => handoffsByFile[f] || { file: f, missing: true });
  const details = h('details', 'links', null, [h('summary', null, `${linked.length} linked handoff${linked.length === 1 ? '' : 's'}`)]);
  linked.forEach(hf => details.appendChild(hf.missing
    ? h('div', 'hrow', null, [h('span', 'badge warn', 'missing'), h('code', 'src', 'HANDOFFS/' + hf.file)])
    : h('div', 'hrow', null, [h('span', 'small', stamp(hf.file) + ' · ' + val(hf.agent) + ' '), agentBadge(hf.status), checkerBadge(hf)])));
  return h('article', 'card taskcard', null, [
    h('div', 'row between', null, [h('strong', null, val(t.id)), statusBadge(t.status, t.status_known)]),
    h('p', null, val(t.title)),
    h('p', 'small muted', 'Owner: ' + val(t.owner)),
    t.depends_on && t.depends_on !== '–' ? h('p', 'small muted', 'Depends on: ' + t.depends_on) : null,
    verifiedBadge(t.status),
    linked.length ? details : h('p', 'small muted', 'No handoff linked on the board'),
    src(t.source),
  ]);
}

function renderProject(data) {
  const p = data.project;
  main.replaceChildren();
  const byFile = {}; p.handoffs.forEach(hf => { byFile[hf.file] = hf; });
  const reg = p.registry || {};
  const head = h('section', 'panel', null, [
    h('h2', null, val(reg.Title || p.slug)),
    h('div', 'row', null, [h('span', 'chip', p.slug), h('span', 'chip', 'domain: ' + val(reg.Domain)),
      h('span', 'chip', 'registry: ' + val(reg.Status)), h('span', 'chip', 'board updated ' + val(p.board_updated)),
      h('span', 'chip', 'state updated ' + val(p.state_updated)), src(p.board.source)])
  ]);

  const known = data.statuses.concat(p.board.tasks.filter(t => !t.status_known).length ? ['UNRECOGNISED'] : []);
  const lanes = h('div', 'lanes');
  known.forEach(s => {
    const tasks = p.board.tasks.filter(t => s === 'UNRECOGNISED' ? !t.status_known : t.status === s);
    const lane = h('div', 'lane' + (tasks.length ? '' : ' empty'), null, [h('h3', statusCls(s === 'UNRECOGNISED' ? null : s), `${s} · ${tasks.length}`)]);
    tasks.forEach(t => lane.appendChild(taskCard(t, byFile)));
    lanes.appendChild(lane);
  });
  const board = h('section', 'panel', null, [h('h2', null, `Task board (${p.board.tasks.length} tasks)`), lanes]);

  const rows = p.handoffs.slice().reverse().map(hf => h('tr', null, null, [
    h('td', null, stamp(hf.file)), h('td', null, val(hf.agent)), h('td', null, val(hf.task_id)),
    h('td', null, null, [agentBadge(hf.status)]), h('td', null, null, [checkerBadge(hf)]),
    h('td', null, val(hf.next_agent)), h('td', 'small', val(hf.task_board_update)), h('td', null, null, [src(hf.source)])]));
  const table = h('table', 'htable', null, [
    h('thead', null, null, [h('tr', null, null, ['Time (file name)', 'Agent', 'Task', 'Agent-reported', 'Checker', 'Next', 'Proposed board update', 'Source'].map(c => h('th', null, c)))]),
    h('tbody', null, null, rows)]);
  const log = h('section', 'panel', null, [h('h2', null, `Handoff log (${p.handoffs.length}, newest first)`), h('div', 'tablewrap', null, [table])]);

  const roster = h('section', 'panel', null, [h('h2', null, 'Agents in this project'),
    h('div', 'grid agents', null, [orchestratorCard(), ...data.agents.map(a => agentCard(a, p.slug))])]);

  main.append(head, officePanel(data.agents, [p], p.slug), board, warningsPanel(p.warnings, 'Inconsistencies'), livePanel(), fileActivityPanel(data.file_activity), log, roster);
  fillLivePanel(); fillObsLines();
}

function renderNav(slugs, current) {
  nav.replaceChildren();
  const all = h('a', 'navlink' + (current ? '' : ' on'), 'Overview'); all.href = '/';
  nav.appendChild(all);
  slugs.forEach(s => { const a = h('a', 'navlink' + (s === current ? ' on' : ''), s); a.href = '/p/' + encodeURIComponent(s); nav.appendChild(a); });
}

async function load() {
  const m = /^\/p\/([a-z0-9-]+)$/.exec(location.pathname);
  const slug = m ? m[1] : null;
  try {
    const ro = await fetch('/api/overview', { cache: 'no-store' });
    if (!ro.ok) throw new Error('overview: HTTP ' + ro.status);
    const ov = await ro.json();
    renderNav(ov.projects.map(p => p.slug), slug);
    if (slug) {
      const r = await fetch('/api/project/' + encodeURIComponent(slug), { cache: 'no-store' });
      if (!r.ok) throw new Error('project ' + slug + ': HTTP ' + r.status);
      renderProject(await r.json());
    } else {
      renderOverview(ov);
    }
    readAt.textContent = 'records read ' + new Date().toLocaleTimeString();
  } catch (e) {
    main.replaceChildren(h('section', 'panel warnpanel', null, [h('h2', null, 'Could not read the workspace records'), h('p', null, String(e))]));
    readAt.textContent = 'read failed';
  }
}

async function pollLive() {
  try {
    const r = await fetch('/api/live', { cache: 'no-store' });
    if (!r.ok) throw new Error('HTTP ' + r.status);
    liveData = await r.json();
    liveError = null;
  } catch (e) {
    liveData = null;
    liveError = String(e.message || e);
  }
  fillLivePanel(); fillObsLines();
  if (window.AgentScene) window.AgentScene.setLive(liveData, liveError);
}

document.getElementById('refresh').addEventListener('click', load);
load().then(pollLive);
setInterval(pollLive, LIVE_MS);
