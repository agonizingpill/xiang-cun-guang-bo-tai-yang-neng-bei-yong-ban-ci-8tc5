import {request} from '../api.js';
import {el, display} from '../dom.js';
import {status, titleBlock} from '../widgets.js';

export const title = '备播额度看板';
export const key = 'board';

function batteryCard(entry) {
  const head = el('header', {class: 'board-head'},
    el('h3', {}, entry.battery + ' · ' + entry.meter),
    el('span', {class: 'chip'}, '整班 ' + entry.shift_hours + ' 小时'));
  const summary = el('dl', {class: 'board-summary'},
    el('dt', {}, '电池容量 Wh'), el('dd', {}, display(entry.capacity_wh)),
    el('dt', {}, '公用余量 Wh'), el('dd', {}, display(entry.margin_wh)),
    el('dt', {}, '已锁电量 Wh'), el('dd', {}, display(entry.locked_wh)),
    el('dt', {}, '还能分 Wh'),
    el('dd', {class: entry.allocatable_wh <= 0 ? 'neg' : 'ok'}, display(entry.allocatable_wh)));
  const rows = entry.slots.map(slot => el('tr', {},
    el('td', {}, slot.airslot + ' ' + slot.title),
    el('td', {}, display(slot.hour)),
    el('td', {}, display(slot.prediction_wh)),
    el('td', {}, display(slot.locked_wh)),
    el('td', {}, display(slot.card_states))));
  const table = el('div', {class: 'scroll'}, el('table', {},
    el('thead', {}, el('tr', {},
      el('th', {scope: 'col'}, '节目档'),
      el('th', {scope: 'col'}, '起播小时'),
      el('th', {scope: 'col'}, '整班预测 Wh'),
      el('th', {scope: 'col'}, '已锁 Wh'),
      el('th', {scope: 'col'}, '卡片状态'))),
    el('tbody', {}, rows)));
  return el('article', {class: 'record board-card'}, head, summary, table);
}

export async function render(root) {
  root.replaceChildren(titleBlock('班组备播卡', title,
    '按电池汇总各档已锁电量、公用余量与还能分多少；已交接卡片仍占额，已撤卡释放额度。'));
  const panel = el('section', {class: 'ledger', 'aria-label': title}, status('加载中…'));
  root.append(el('div', {class: 'work stack'}, panel));
  try {
    const rows = await request('/switchcards/board');
    if (!rows.length) {
      panel.replaceChildren(status('暂无电池，请先在电池台账登记。'));
      return;
    }
    panel.replaceChildren(el('h2', {}, title), el('div', {class: 'records grid'}, rows.map(batteryCard)));
  } catch (error) {
    panel.replaceChildren(status(error.message, 'error'));
  }
}
