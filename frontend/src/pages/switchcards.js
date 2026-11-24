        import {workspace} from '../workspace.js';
        import {el} from '../dom.js';

        const page = {
  "title": "班组备播与闭台交接",
  "module": "班组备播卡",
  "caption": "班组备播卡",
  "detail": "发卡额须覆盖该档整班预测；同一电池扣掉公用余量后并发发卡不能超额。撤卡释放额度且重试不重复退，已交接卡片仍占额。",
  "path": "/switchcards",
  "columns": [
    {
      "name": "code",
      "label": "编号"
    },
    {
      "name": "reserve",
      "label": "备用评估"
    },
    {
      "name": "source",
      "label": "实际时钟源"
    },
    {
      "name": "approved_wh",
      "label": "锁定备用 Wh"
    },
    {
      "name": "state",
      "label": "状态"
    }
  ],
  "layout": "flip",
  "view": "table",
  "actions": [
    {
      "name": "issue_switch",
      "label": "签发班组备播卡",
      "path": "/switchcards/issue-switch",
      "fields": [
        {
          "name": "code",
          "label": "班组备播卡",
          "kind": "text",
          "initial": "SW-24"
        },
        {
          "name": "reserve",
          "label": "备用评估单",
          "kind": "text",
          "initial": "RV-24"
        },
        {
          "name": "source",
          "label": "值守时钟源",
          "kind": "text",
          "initial": "本地时钟"
        },
        {
          "name": "approved_wh",
          "label": "预留用量 Wh",
          "kind": "float",
          "initial": 190
        }
      ],
      "help": "锁定电量须覆盖该档整班预测，并在电池容量扣除公用余量后的可分额度内。",
      "roles": [
        "reviewer"
      ],
      "success": "已写入"
    },
    {
      "name": "withdraw",
      "label": "撤回备播卡",
      "path": "/switchcards/withdraw",
      "fields": [
        {
          "name": "card",
          "label": "班组备播卡",
          "kind": "text",
          "initial": "SW-24"
        }
      ],
      "help": "已签发卡片撤卡即释放额度；重复提交幂等，不会重复退电量。已交接卡片不能撤。",
      "roles": [
        "reviewer"
      ],
      "success": "已撤卡"
    },
    {
      "name": "handover",
      "label": "确认闭台交接",
      "path": "/switchcards/handover",
      "fields": [
        {
          "name": "card",
          "label": "班组备播卡",
          "kind": "text",
          "initial": "SW-24"
        },
        {
          "name": "note",
          "label": "交接班回执",
          "kind": "text",
          "initial": "WR-77 闭台交接"
        }
      ],
      "help": "写入纸本号后关闭当次卡片。",
      "roles": [
        "operator",
        "reviewer"
      ],
      "success": "已写入"
    }
  ]
};

        export const {title} = page;
        export const key = "switchcards";
        export async function render(root, role) {
          await workspace(root, role, page);

        }
