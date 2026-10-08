import { readFileSync } from 'node:fs';
import { execFile } from 'node:child_process';

// No React/Ink dependencies: all UI primitives come from the public widget SDK.
export default function register(sdk) {
  const config = JSON.parse(readFileSync(new URL('./thesystem-runs.json', import.meta.url), 'utf8'));
  const program = `${config.home}/plugins/thesystem-runs/awareness.py`;
  const { h, Box, Text, Dialog, React } = sdk;
  const baseArgs = ['--home', config.home, '--workspace', config.workspace];

  function Panel({ t, cols }) {
    const [snapshot, setSnapshot] = React.useState(null);
    const [error, setError] = React.useState(false);
    const [page, setPage] = React.useState(0);
    const [detail, setDetail] = React.useState(null);
    const refresh = React.useRef(null);
    React.useEffect(() => {
      let alive = true, pending = false, child = null;
      const fetch = () => {
        if (pending || !alive) return;
        pending = true;
        child = execFile('python3', [program, 'snapshot', ...baseArgs], { timeout: 5000, maxBuffer: 512 * 1024 }, (err, stdout) => {
          pending = false;
          if (!alive) return;
          if (err) { setError(true); return; }
          try { setSnapshot(JSON.parse(stdout)); setError(false); }
          catch { setError(true); }
        });
      };
      refresh.current = fetch;
      fetch();
      const timer = setInterval(fetch, 2000);
      return () => { alive = false; clearInterval(timer); child?.kill(); refresh.current = null; };
    }, []);
    const width = Math.max(18, Math.min(74, cols - 2));
    const limit = Math.max(8, width - 6);
    const short = value => String(value || '').slice(0, limit).padEnd(limit);
    const rows = snapshot?.runs || [];
    const pages = Math.max(1, Math.ceil(rows.length / 2));
    const current = Math.min(page, pages - 1);
    const shown = rows.slice(current * 2, current * 2 + 2);
    const dismiss = id => execFile('python3', [program, 'dismiss', ...baseArgs, '--id', id],
      { timeout: 5000 }, err => { if (err) setError(true); else { setDetail(null); refresh.current?.(); } });
    const blocks = [h(Text, { key: 'heading', bold: true, color: t.color.label },
      short(`Orchestrator | ${String(rows.length).padStart(3)} runs | ${current + 1}/${pages}`))];
    if (!snapshot && !error) blocks.push(h(sdk.ShimmerRows, { key: 'loading', rows: 4, width: limit }));
    else {
      for (let slot = 0; slot < 2; slot++) {
        const row = shown[slot];
        if (!row) {
          blocks.push(h(Text, { key: `empty-${slot}`, color: t.color.muted }, short(slot === 0 ? (error ? 'Monitor unavailable; retrying' : 'No orchestrator runs') : '')));
          blocks.push(h(Text, { key: `space-${slot}` }, short('')));
          continue;
        }
        const label = row.possibly_stale ? 'possibly stale' : row.status === 'running' ? row.stage : row.status;
        const color = row.possibly_stale ? t.color.error : row.status === 'pre-done' ? t.color.ok : row.status === 'running' ? t.color.primary : t.color.error;
        blocks.push(h(Box, { key: `${row.id}-title`, onClick: () => setDetail(detail === row.id ? null : row.id) },
          h(Text, { color, bold: true }, short(`${row.task} | ${label}`))));
        blocks.push(h(Box, { key: `${row.id}-body`, onClick: row.status !== 'running' ? () => dismiss(row.id) : undefined },
          h(Text, { color: t.color.muted }, short(detail === row.id ? row.evidence :
            `${row.run} | ${row.status === 'running' ? 'click title: evidence' : 'click: dismiss result'}`))));
      }
    }
    blocks.push(h(Box, { key: 'paging', onClick: () => { setPage((current + 1) % pages); setDetail(null); } },
      h(Text, { color: error ? t.color.error : t.color.muted }, short(error ? 'Read error — showing last snapshot' :
        snapshot?.truncated ? 'Scan limit reached | click: next page' : snapshot?.skipped ? `${snapshot.skipped} unreadable records | click: next page` : 'Click: next page | /thesystem-runs: hide'))));
    return h(Dialog, { width }, h(Box, { flexDirection: 'column' }, ...blocks));
  }
  const app = sdk.defineWidgetApp({
    id: 'thesystem-runs', help: 'Live orchestrator runs; click a finished result to dismiss it',
    mode: 'ambient', zone: 'dock-bottom', width: 74,
    init: () => ({}), reduce: state => state,
    render: ({ t, cols }) => h(Panel, { t, cols }),
  });
  sdk.openWidget(app, app.init(''));
}
