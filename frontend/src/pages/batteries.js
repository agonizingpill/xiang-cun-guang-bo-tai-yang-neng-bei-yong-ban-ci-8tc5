import {request} from '../api.js';
import {actionForm} from '../controls.js';
import {el} from '../dom.js';
import {dataView, status, titleBlock} from '../widgets.js';

const page = {
  title: '共用电池与整班额度',
  module: '电池台账',
  caption: '共用电池',
  detail: '几档连播节目共用一块电池；整班时长决定等长时窗与预测窗口，容量是各档发卡的共同上限。',
  path: '/batteries',
  columns: [
    {name: 'code', label: '电池编号'},
    {name: 'meter', label: '电表编号'},
    {name: 'shift_hours', label: '整班小时'},
    {name: 'capacity_wh', label: '电池容量 Wh'},
    {name: 'margin_wh', label: '公用余量 Wh'},
  ],
  layout: 'flip',
  view: 'table',
  actions: [
    {
      name: 'register_battery',
      label: '登记共用电池',
      path: '/batteries/register',
      fields: [
        {name: 'code', label: '电池编号', kind: 'text', initial: 'BAT-11'},
        {name: 'meter', label: '电表编号', kind: 'text', initial: 'BAT-11'},
        {name: 'shift_hours', label: '整班小时（1-6）', kind: 'int', initial: 3},
        {name: 'capacity_wh', label: '电池容量 Wh', kind: 'float', initial: 2200},
      ],
      help: '一块电池绑定一个电表；同一电池各档发卡共用容量与一份整班 MAE 余量。',
      roles: ['reviewer'],
      success: '已写入',
    },
  ],
};

export const {title} = page;
export const key = 'batteries';

export async function render(root, role) {
  const panel = el('section', {class: 'ledger', 'aria-label': page.caption});
  const refresh = async () => {
    try {
      const rows = await request(page.path);
      panel.replaceChildren(el('h2', {}, page.caption), dataView(rows, page.columns, page.view));
    } catch (error) {
      panel.replaceChildren(status(error.message, 'error'));
    }
  };
  const actions = page.actions.filter(x => x.roles.includes(role));
  root.replaceChildren(
    titleBlock(page.module, page.title, page.detail),
    el('div', {class: 'work ' + page.layout}, panel,
      actions.length ? el('section', {class: 'actions'}, actions.map(x => actionForm(x, refresh))) : null));
  await refresh();
}
