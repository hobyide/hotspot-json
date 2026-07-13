# Automation Contract

本文件定义 ChatGPT 定时任务与仓库内采集程序对 `hobyide/hotspot-json` 的共同写入规则。

## 时区与频率

- 时区：Asia/Shanghai
- 热点抓取：每天 00:00、06:00、12:00、18:00
- 归档清理：每天 23:00

## 核心目标

仓库必须持续保有可用于下游选题和写稿的热点数据。总体健康状态由“当前 Feed 是否可发布”决定，而不是由某一个榜单、网页或结构化接口是否成功决定。

固定榜单或结构化接口失败时，自动化必须继续使用 `config/runtime-sources.json` 中的 RSS、新闻聚合、可靠媒体和浏览器搜索补源。结构化榜单不可用只能记为来源级 warning，不能单独把总体状态写成失败或 degraded。

每轮目标为写入不少于 5 个近 24 小时事件、至少 3 个独立发布者。目标数量不是编造数据的理由；确实不足时按 `config/health-gate.json` 进入 partial 模式。只有当前 Feed 和可用缓存 Feed 都不存在，或关键校验失败时，才允许总体状态为 failed。

## 启动时必须读取

- `README.md`
- `AUTOMATION.md`
- `config/sources.json`
- `config/runtime-sources.json`
- `config/rules.json`
- `config/health-gate.json`
- `schema/hotspot-v1.2.schema.json`
- `schema/source-record.schema.json`
- `data/manifest.json`
- `data/sources.json`
- `data/latest.json`
- `data/drama.json`
- `data/variety.json`
- `data/celebrity.json`
- `data/entertainment-events.json`
- `data/status.json`

## 固定执行顺序

1. 读取抽象信源政策 `config/sources.json`。
2. 读取可执行入口 `config/runtime-sources.json`。
3. 并行获取固定 RSS、Atom、公开页面和聚合入口。
4. 对失败入口按配置重试，并切换到下一组来源。
5. 固定入口不足时执行浏览器搜索补源，不得因缺少结构化榜单而停止。
6. 将每一篇独立素材先写入 `data/sources.json`。
7. 使用规范化 URL、发布者、标题和 `content_hash` 去重。
8. 识别转载链和同稿分发；同稿转载只算一个独立来源。
9. 聚合同一事件，建立逐条事实表。
10. 校验每条事实是否被来源支持。
11. 计算热度与来源多样性。
12. 执行版权、隐私、法律和谣言风险检查。
13. 按 `config/health-gate.json` 计算 publishability。
14. 原子更新 Feed、来源库、manifest 和 status。

## 禁止伪造健康数据

以下做法一律禁止：

- 把一篇电视指南、盘点或合集文章拆成多条事件，再把这些事件当作多个独立来源或多个热点；
- 同一篇稿件被多个站点转载后，按多个独立来源计数；
- 为了让总体状态变成 ready 而补写不存在的排名、互动量、发布时间、作者、图片或视频；
- 仅修改 `data/status.json`，不更新实际 Feed；
- 当前采集失败时用空数组覆盖上一版有效 Feed；
- 把“某个榜单无法解析”直接升级为总体 failed。

一个来源文章最多贡献一个独立热点候选；文章内包含多个完全独立、且各自有独立官方或媒体来源支持的事件时，才允许拆分。

## 来源多样性

ready 模式必须同时满足：

- 近 24 小时事件不少于 5 条；
- 独立发布者不少于 3 个；
- 可用于下游写作的事实不少于 3 条；
- 任一发布者占比不高于 45%；
- Feed 年龄不超过 30 小时；
- JSON、Schema、引用完整性、事实支持和去重校验全部通过。

partial 模式可以继续下游写作，但必须同时满足：

- 事件不少于 3 条；
- 独立发布者不少于 2 个；
- 可用事实不少于 2 条；
- 任一发布者占比不高于 67%；
- Feed 年龄不超过 36 小时；
- 只允许带明确来源归因的非敏感内容。

达不到 partial 标准时才设置 `publishability.can_publish=false`。

## 状态语义

总体 `data/status.json.status` 只允许：

- `ready`：满足完整发布门禁；
- `partial`：数据有限但仍满足带归因写作门禁；
- `failed`：无可用当前或缓存 Feed，或关键校验失败。

`degraded` 只允许出现在单个来源的 `source_status` 中，不得再作为总体状态。

下游不得只读取总体 status 做一刀切。下游主门禁字段为：

- `publishability.can_publish`
- `publishability.mode`
- `publishability.publishable_event_count`
- `publishability.distinct_publisher_count`
- `validation.overall`

当总体状态为 partial 且 `publishability.can_publish=true` 时，下游必须继续选题和写稿，但只使用已明确归因的非敏感事实。

## 单一来源入库规则

允许单一可靠来源事件进入正式 Feed：

- `verification.status=reported`；
- `evidence_status=single_source`；
- `risk_flags` 加入 `single_source`；
- 摘要和事实必须使用“据某来源报道”“页面显示”“活动方称”等归因措辞。

节目播出、定档、公开阵容、公开活动、作品发行、公开采访和普通工作动态，只要来源明确支持，可以令 `can_use_as_fact=true`，但不得去掉来源归因。

恋情、隐私、违法或法律指控、伤亡、未成年人、重大负面争议仅有单一来源时，不得写成确定事实，也不得在 partial 模式进入下游文章。

## 原始素材与版权

每个来源先写入 `data/sources.json`，至少包含标题、URL、来源、作者、发布时间、抓取时间、哈希、抓取状态、合规摘要、关键事实、授权状态和媒体页面 URL。

只有明确许可、公共领域、Creative Commons、API 条款允许或用户自有内容可以保存全文。其他内容使用原创摘要和结构化事实，不复制付费墙或授权不明全文。

## Feed 与校验

每轮更新：

- `data/sources.json`
- `data/latest.json`
- `data/drama.json`
- `data/variety.json`
- `data/celebrity.json`
- `data/entertainment-events.json`
- `data/manifest.json`
- `data/status.json`

写入前检查 JSON、Schema、引用完整性、事实支持、哈希去重、同稿转载识别、发布者集中度、文件大小和条目上限。任一关键校验失败时不得提交部分结果。

## 缓存与失败保护

当本轮新数据不足 partial 标准时：

1. 检查上一版 Feed 是否通过校验；
2. 若上一版年龄不超过 36 小时，保留上一版并标记 `partial`、`publishability.mode=cached_attributed`；
3. 不得用空数据覆盖；
4. 若上一版也不可用，才设置 failed。

## 每日归档与清理

每天 23:00 先归档当天事件和来源，再清理过期数据。当前事件窗口 24 小时，在线来源快照 7 天，历史归档 30 天，失败日志 14 天。不得无条件清空当前 Feed。

## 运行报告

报告必须包含：

- 成功和失败的来源入口；
- 新增来源数与独立发布者数；
- 单一来源事件与交叉确认事件数；
- 最大单一发布者占比；
- 未收录高风险事件数；
- `publishability` 判定依据；
- 全部校验结果；
- GitHub 提交结果。

写入失败时必须报告真实错误，不得把“未抓到结构化榜单”写成整条流水线失败，除非所有固定入口、RSS、公开页面、搜索补源和有效缓存均不可用。
