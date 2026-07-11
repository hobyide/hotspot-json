# Daily Archives

每天 23:00（Asia/Shanghai）先归档、后清理。

归档目录格式：

```text
archive/
└── YYYY/
    └── MM/
        └── DD/
            ├── events.json
            ├── sources.json
            └── manifest.json
```

- `events.json`：当天事件 Feed 快照。
- `sources.json`：事件所引用的来源素材快照。
- `manifest.json`：归档时间、数量、Schema 版本、源路径和内容哈希摘要。

归档前必须验证事件中的全部 `source_ids` 均能在同日 `sources.json` 中找到。验证失败时不得清理当前数据。

历史归档默认保留 30 天。归档内容用于证据追溯，不得在后续清理中改写事实。
