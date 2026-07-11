# Automation Contract

本文件定义 ChatGPT 定时任务对仓库 `hobyide/hotspot-json` 的写入规则。

## 时区与频率

- 时区：Asia/Shanghai
- 热点抓取：每天 00:00、06:00、12:00、18:00
- 归档清理：每天 23:00

## 总体流程

自动化必须按以下顺序执行，不得跳过原始素材层直接生成热点文章：

1. 读取固定信源池。
2. 获取独立来源素材。
3. 将素材写入 `data/sources.json`。
4. 用规范化 URL 与 `content_hash` 去重。
5. 将同一事件的多个来源聚合。
6. 建立逐条事实表。
7. 校验每条事实是否被引用来源支持。
8. 计算可解释热度。
9. 写入 `data/latest.json` 与分类 Feed。
10. 执行风险检查。

## 启动时必须读取

- `README.md`
- `AUTOMATION.md`
- `config/sources.json`
- `config/rules.json`
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

## 信源抓取规则

抓取优先级必须是：

`官方 API / RSS / Atom > 固定网页解析 > 搜索 API > 浏览器式搜索补源`

1. 优先访问 `config/sources.json` 中启用的固定信源。
2. 官方账号、节目组、平台、电视台、制作公司、经纪公司、当事方和正式通报优先。
3. 热榜用于发现事件和计算热度，不得单独作为重要事实证据。
4. 行业媒体必须位于白名单逻辑内，重要结论需要交叉验证。
5. 搜索补源只能在固定信源不足时启用。
6. 无法访问的来源必须在 `source_status` 中如实标记。
7. 不得虚构榜单、排名、互动量、时间、作者、链接、图片或视频地址。
8. 单轮所有来源均失败时，不得用空数据覆盖上一版有效 Feed。

## 原始素材落库

每个独立来源必须先写入 `data/sources.json`，并具有：

- `source_id`
- 原始标题和 URL
- 规范化 URL
- 来源名称与类型
- 信源层级
- 作者或机构
- 原始发布时间；无法确认时为 `null`
- 抓取时间
- `content_hash`
- 抓取状态
- 合规正文、摘要或短摘录
- 关键事实
- 授权状态
- 图片和视频页面 URL

### 正文授权

只有以下情况可使用 `full_text`：

- 来源明确允许转载；
- 内容属于公共领域；
- Creative Commons 许可允许；
- 官方 API 条款允许保留；
- 内容归用户所有。

其他来源使用 `excerpt_and_summary`、`summary_only` 或 `metadata_only`。不得复制付费墙内容，不得绕过访问限制，不得整篇镜像授权不明或受限文章。

单一来源获准全文不超过 20000 字符；单个事件最多保留 3 份获准全文。

## 去重与事件聚合

来源去重至少检查：

- 规范化 URL；
- `content_hash`；
- 标题和正文高度重复；
- 同一媒体转载链。

同一事件聚合至少使用：

- 标题相似度；
- 人物、节目和机构实体；
- 关键词重合；
- 语义相似度；
- 发布时间接近程度。

同名不同人、不同季或不同事件不得错误合并。无法解决的来源分歧写入 `conflicts`。

## 事实表与引用核验

每个事件必须包含 `facts`。每条事实必须有：

- `fact_id`
- `statement`
- `source_ids`
- `evidence_status`
- `fact_type`
- `can_use_as_fact`

数字、日期、人物引语、阵容、官宣、播出、法律和争议信息必须能定位到来源。

重要结论必须满足以下任一条件：

- 一个官方一手来源；
- 至少两个独立可靠来源。

来源冲突时必须完整保留冲突，不得自行挑选一个版本。无证据内容标为 `unsupported` 并从确定性摘要中删除。传闻只能标为 `single_source` 或 `unconfirmed`，并使用明确的非确定性措辞。

写入前必须再次检查：

1. 每个 `source_id` 均存在于 `data/sources.json`；
2. 每条事实引用的来源确实支持该陈述；
3. 不支持的事实被删除、退回重写或降级；
4. 只有 `confirmed` 与 `cross_confirmed` 可作为确定事实。

## 事件 Feed

事件写入：

- `data/latest.json`
- `data/drama.json`
- `data/variety.json`
- `data/celebrity.json`
- `data/entertainment-events.json`

目标 Schema 为 `schema/hotspot-v1.2.schema.json`。

每个事件必须包含：

- `content.overview`
- `content.key_points`
- `content.timeline`
- `source_ids`
- 兼容性的 `sources`
- `facts`
- `heat_signals`
- `conflicts`
- `risk_flags`
- `verification`
- `media`

## 热度计算

热度只能来自可解释信号：

- 独立来源数量；
- 官方来源数量；
- 跨平台数量；
- 最佳可核验榜单排名；
- 传播速度；
- 可获得的点赞、评论、转发和播放量；
- 与娱乐领域的相关度。

缺失值必须为 `null`，不得估算。重复搬运、低可信来源、传闻风险和陈旧信息应降低热度分。

## 媒体规则

1. 仓库只保存原始页面、官方页面、图片、封面、视频播放页或官方嵌入页 URL。
2. 不下载或重新托管第三方图片和视频文件。
3. 不保存临时 CDN 视频流地址。
4. 单个事件最多 5 个图片 URL、3 个视频页面 URL。

## 每日归档与清理

每天 23:00 执行：

1. 将当天事件写入 `archive/YYYY/MM/DD/events.json`。
2. 将当天来源写入 `archive/YYYY/MM/DD/sources.json`。
3. 写入 `archive/YYYY/MM/DD/manifest.json`，记录归档时间、数量、Schema 版本和哈希摘要。
4. 验证所有事件 `source_ids` 可在同日来源文件中找到。
5. 归档验证成功后，才允许执行过期清理。

不得每天无条件清空当前 Feed。

保留策略：

- 当前热点窗口：24 小时；
- 在线来源快照：7 天；
- 历史归档：30 天；
- 失败日志：14 天。

只移除已过期、无热度且不再被引用的事件和来源。不得改写已经归档的历史事实。

## 校验与写入限制

写入前必须检查：

- JSON 可解析；
- 符合对应 Schema；
- `source_id` 引用完整；
- 事实引用有效；
- `content_hash` 去重；
- 单文件不超过 5 MB；
- 综合 Feed 不超过 100 条；
- 分类 Feed 不超过 50 条。

任一关键文件校验失败时，不得提交部分结果。

## 运行报告

热点任务结束时报告：

- 新增来源数；
- 去重来源数；
- 新增、更新、移除事件数；
- 已确认与未确认事实数；
- 引用核验失败数；
- 来源访问状态；
- GitHub 提交结果。

归档任务结束时报告：

- 归档路径；
- 归档事件数；
- 归档来源数；
- 移除的过期事件、来源和归档数量；
- GitHub 提交结果。

写入失败时必须报告准确错误，不得声称成功。
