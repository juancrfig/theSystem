// F11 public widget contract with real snapshot/dismiss subprocesses and offline run files.
import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import os from 'node:os';
import { pathToFileURL, fileURLToPath } from 'node:url';

const root = path.dirname(path.dirname(fileURLToPath(import.meta.url)));
const waitFor = async predicate => {
  const end = Date.now() + 6000;
  while (Date.now() < end) { if (predicate()) return; await new Promise(r => setTimeout(r, 25)); }
  assert.fail('timed out waiting for real widget subprocess');
};
const flatten = node => typeof node === 'string' ? node : (node?.children || []).flatMap(flatten).join('');
const nodes = node => !node || typeof node === 'string' ? [] : [node, ...(node.children || []).flatMap(nodes)];

function fixture() {
  const folder = fs.mkdtempSync(path.join(process.env.TMPDIR || os.tmpdir(), 'awareness-widget-'));
  const home = path.join(folder, 'home'), workspace = path.join(folder, 'ws');
  fs.mkdirSync(path.join(home, 'plugins/thesystem-runs'), { recursive: true });
  fs.copyFileSync(path.join(root, 'thesystem/run_awareness.py'), path.join(home, 'plugins/thesystem-runs/awareness.py'));
  fs.copyFileSync(path.join(root, 'integrations/hermes/thesystem-runs.mjs'), path.join(folder, 'widget.mjs'));
  fs.writeFileSync(path.join(folder, 'thesystem-runs.json'), JSON.stringify({ home, workspace }));
  const record = (task, status, stage = 'finished') => {
    const file = path.join(workspace, `p/tickets/T/tasks/${task}/runs/run-1/run.json`);
    fs.mkdirSync(path.dirname(file), { recursive: true });
    fs.writeFileSync(file, JSON.stringify({ task, run: 'run-1', status, stage }));
    return file;
  };
  return { folder, record, home, workspace };
}

async function mount(f) {
  const values = [], effects = [];
  let cursor = 0, app;
  const h = (type, props, ...children) => ({ type, props: props || {}, children: children.flat() });
  const sdk = { h, Box: 'Box', Text: 'Text', Dialog: 'Dialog', ShimmerRows: 'Shimmer',
    React: {
      useState(initial) { const i = cursor++; if (!(i in values)) values[i] = initial; return [values[i], v => { values[i] = v; }]; },
      useRef(initial) { const i = cursor++; if (!(i in values)) values[i] = { current: initial }; return values[i]; },
      useEffect(callback) { const i = cursor++; if (!(i in values)) { values[i] = true; effects.push(callback()); } },
    },
    defineWidgetApp(value) { app = value; return value; },
    openWidget(value) { assert.equal(value.mode, 'ambient'); assert.equal(value.zone, 'dock-bottom'); },
  };
  const module = await import(pathToFileURL(path.join(f.folder, 'widget.mjs')).href);
  module.default(sdk);
  const render = cols => {
    cursor = 0;
    const props = { state: {}, cols, rows: 40, t: { color: { label: 'white', primary: 'cyan', error: 'red', ok: 'green', muted: 'gray' } } };
    const component = app.render(props);
    return component.type(component.props);
  };
  return { values, render, app, cleanup() { effects.forEach(effect => effect?.()); } };
}

test('stable-width dock, paging, real dismissal and run evidence unchanged', async t => {
  const f = fixture();
  t.after(() => fs.rmSync(f.folder, { recursive: true, force: true }));
  const activeFile = f.record('active', 'running', 'reviewer');
  const one = f.record('finished-1', 'pre-done'), two = f.record('finished-2', 'failed');
  const originals = [activeFile, one, two].map(p => fs.readFileSync(p, 'utf8'));
  const ui = await mount(f);
  t.after(ui.cleanup);
  assert.equal(ui.app.reduce({}, { char: 'x' }).constructor, Object);
  const before = ui.render(110);
  assert.equal(before.props.width, 74);
  assert.ok(nodes(before).some(n => n.type === 'Shimmer'));
  await waitFor(() => ui.values[0]);
  let rendered = ui.render(110);
  assert.match(flatten(rendered), /active.*possibly stale/);
  assert.match(flatten(rendered), /finished-2.*failed/);
  assert.equal(rendered.props.width, before.props.width);
  const narrow = ui.render(40);
  assert.equal(narrow.props.width, 38);
  for (const n of nodes(narrow).filter(n => n.type === 'Text')) assert.ok(flatten(n).length <= 32);
  const page = nodes(rendered).find(n => n.type === 'Box' && typeof n.props.onClick === 'function' && flatten(n).includes('Click: next page'));
  page.props.onClick();
  rendered = ui.render(110);
  assert.match(flatten(rendered), /finished-1.*pre-done/);
  const dismiss = nodes(rendered).find(n => n.type === 'Box' && typeof n.props.onClick === 'function' && flatten(n).includes('click: dismiss result'));
  dismiss.props.onClick();
  await waitFor(() => ui.values[0].runs.length === 2);
  assert.deepEqual([activeFile, one, two].map(p => fs.readFileSync(p, 'utf8')), originals);
  rendered = ui.render(110);
  assert.doesNotMatch(flatten(rendered), /finished-1.*pre-done/);
  // A read error keeps the last observed records; it does not declare a run complete.
  fs.unlinkSync(path.join(f.home, 'plugins/thesystem-runs/awareness.py'));
  ui.values[4].current();
  await waitFor(() => ui.values[1] === true);
  assert.match(flatten(ui.render(110)), /Read error/);
  assert.equal(ui.values[0].runs.length, 2);
});
