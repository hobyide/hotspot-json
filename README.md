# Entertainment Hotspot JSON

自动聚合国内外电视剧、网剧、短剧、综艺、明星和娱乐圈热点，并以可追溯、带证据引用的 JSON 格式供其他脚本读取。

本项目不再采用“搜索一下直接写文章”的模式，而是执行：

`固定信源池 → 原始素材落库 → URL/正文指纹去重 → 同一事件聚合 → 事实表 → 引用核验 → 风险检查 → 事件 Feed`

## 数据地址

### 主要读取地址

- 事件热点：`https://raw.githubusercontent.com/hobyide/hotspot-json/main/data/latest.json`
- 原始素材库：`https://raw.githubusercontent.com/hobyide/hotspot-json/main/data/sources.json`
- 数据清单：`https://raw.githubusercontent.com/hobyide/hotspot-json/main/data/manifest.json`
- 运行状态：`https://raw.githubusercontent.com/hobyide/hotspot-json/main/data/status.json`

### 分类兼容地址

- 剧集热点：`https://raw.githubusercontent.com/hobyide/hotspot-json/main/data/drama.json`
- 综艺热点：`https://raw.githubusercontent.com/hobyide/hotspot-json/main/data/variety.json`
- 明星热点：`https://raw.githubusercontent.com/hobyide/hotspot-json/main/data/celebrity.json`
- 娱乐事件：`https://raw.githubusercontent.com/hobyide/hotspot-json/main/data/entertainment-events.json`

写作程序应先读取 `data/latest.json` 中的事件，再根据事件的 `source_ids` 到 `data/sources.json` 查找证据素材。不得只根据标题或 URL 补写事实。

## 自动化时间

- 时区：`Asia/Shanghai`
- 每 6 小时抓取一次：00:00、06:00、12:00、18:00
- 每天 23:00 执行归档和过期清理
- 单轮抓取全部失败时，不用空数组覆盖上一版有效数据
- 只在数据发生实质变化时提交 GitHub

## 固定信源池

抓取优先级：

1. 官方 API、RSS、Atom
2. 固定网页解析
3. 搜索 API
4. 浏览器式搜索补源

信源分为四层：

- Tier 1：节目组、平台、电视台、制作公司、经纪公司、明星或工作室、品牌、法院、警方等官方一手来源
- Tier 2：微博、百度、抖音、B站、Google Trends、YouTube、TMDB 等热点或趋势来源
- Tier 3：白名单影视娱乐行业媒体
- Tier 4：仅用于补源的搜索结果

平台热榜主要用于发现热点和计算热度，不能单独证明事件事实。

## 原始素材库

`data/sources.json` 中每个来源至少保存：

```json
{
  "source_id": "S20260711_EXAMPLE",
  "title": "原始标题",
  "url": "原文地址",
  "normalized_url": "规范化地址",
  "source": "来源名称",
  "source_type": "industry_media",
  "tier": "tier_3_industry_media",
  "author": null,
  "published_at": null,
  "fetched_at": "2026-07-11T12:00:00+08:00",
  "content_hash": "sha256:...",
  "fetch_status": "success",
  "content": {
    "mode": "summary_only",
    "text": null,
    "summary": "清洗后的原创摘要",
    "excerpt": null,
    "key_facts": [],
    "license": {
      "status": "restricted",
      "name": null,
      "url": null
    }
  },
  "media": {
    "images": [],
    "videos": []
  }
}
```

受限、付费或授权不明内容不得整篇镜像。只有官方 API 条款允许、公共领域、许可允许转载或用户自有内容，才能保存获准全文。

## 事件与事实引用

事件 Feed 的目标版本为 `1.2`。每个事件必须包含：

- `source_ids`：指向原始素材库
- `facts`：逐条事实表
- `heat_signals`：可解释的热度信号
- `conflicts`：不同来源之间的冲突
- `risk_flags`：传闻、版权、法律敏感等风险
- `content.overview`、`content.key_points`、`content.timeline`

每条事实必须具有：

```json
{
  "fact_id": "F001",
  "statement": "可核验的事实声明",
  "source_ids": ["S20260711_EXAMPLE"],
  "evidence_status": "confirmed",
  "fact_type": "release",
  "can_use_as_fact": true
}
```

事实状态包括：

- `confirmed`：官方来源确认
- `cross_confirmed`：两个以上独立可靠来源确认
- `single_source`：只有一个非官方来源
- `unconfirmed`：传闻或尚未确认
- `conflicting`：来源之间存在冲突
- `opinion`：主观评价
- `unsupported`：原文不支持
- `refuted`：已被正式否认

只有 `confirmed` 和 `cross_confirmed` 可以直接作为确定事实写入文章。

## 热度计算

热度由可解释指标计算，不由模型凭感觉判断：

- 独立来源数量
- 官方来源数量
- 跨平台数量
- 可核验的榜单排名
- 传播速度
- 可获得的点赞、评论、转发和播放量
- 与娱乐领域的相关度

无法获得的数据必须写为 `null`，不得估算。

## 归档与清理

每天 23:00 先归档，再清理：

- 当天事件：`archive/YYYY/MM/DD/events.json`
- 当天来源：`archive/YYYY/MM/DD/sources.json`
- 归档清单：`archive/YYYY/MM/DD/manifest.json`

保留策略：

- 当前事件窗口：24 小时
- 在线来源快照：7 天
- 历史归档：30 天
- 失败日志：14 天

不再每天无条件清空全部热点。只移除已过期、无热度且不再被引用的事件和来源。

## Schema

- 兼容事件 Schema：`schema/hotspot.schema.json`
- 新事件 Schema：`schema/hotspot-v1.2.schema.json`
- 原始素材 Schema：`schema/source-record.schema.json`

下一次成功抓取应将事件文件迁移为 `schema_version: 1.2`。
