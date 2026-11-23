// 用私服自身的 offline/src/growth.js 与 Python 侧推算对拍，证明"复用游戏逻辑"。
const path = require('path');
const growth = require(path.join('H:/magia_server/_re/src/offline/src/growth.js'));
const cards = require(path.join('H:/magia_server/magia_save_editor/data/cards.json')).cards;

const out = {};
const ids = Object.keys(cards).slice(0, 60);
for (const id of ids) {
  const master = cards[id];
  const samples = [];
  let cap;
  try { cap = growth.maxLevel(master.rank); } catch (e) { continue; }
  for (const level of [1, Math.floor(cap / 2), cap]) {
    try { samples.push({ level, stats: growth.stats(master, level) }); } catch (e) { /* skip */ }
  }
  out[id] = samples;
}
process.stdout.write(JSON.stringify(out));
