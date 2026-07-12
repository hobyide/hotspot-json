# Automation Contract

本文件定义 ChatGPT 定时任务对仓库 `hobyide/hotspot-json` 的写入规则。

## 时区与频率

- 时区：Asia/Shanghai
- 热点抓取：每天 00:00、06:00、12:00、18:00
- 归档清理：每天 23:00

## 核心目标

仓库必须持续保有可用热点数据。固定榜单或结构化接口失败时，自动化必须继续使用可靠媒体、官方公开页面和浏览器搜索补源。只要能够访问到明确支持事件内容的来源，就不得仅更新 `data/status.json` 而不更新事件 Feed。

每轮目标为尽量写入不少于 5 个近 24 小时事件。目标数量不是编造数据的理由；确实不足时按实际数量写入，并记录原因。只有固定信源、补源搜索和公开页面全部不可访问时，才允许保留上一版有效 Feed。

## 总体流程

1. 读取固定信源池。
2. 获取固定来源素材；失败时执行搜索补源。
3. 将独立素材写入 `data/sources.json`。
4. 用规范化 URL 与 `content_hash` 去重。
5. 聚合同一事件。
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

## 信源与补源

抓取优先级：

`官方 API / RSS / Atom > 固定网页解析 > 搜索 API > 浏览器式搜索补源`

热榜可以证明“某主题出现在榜单及其可核验排名”，但不能单独证明主题中的争议、指控或私人信息。无法取得结构化热榜时，不得终止整轮任务，应继续从可靠媒体和官方公开页面寻找近 24 小时娱乐内容。

不得虚构榜单、排名、互动量、发布时间、作者、链接、图片或视频地址。缺失值写 `null`。

## 单一来源入库规则

允许单一可靠来源事件进入正式 Feed：

- `verification.status` 使用 `reported`；
- 事实使用 `evidence_status=single_source`；
- `risk_flags` 加入 `single_source`；
- 摘要和事实必须使用“据某来源报道”“页面显示”“活动方称”等归因措辞。

对于节目播出、定档、公开阵容、公开活动、作品发行、公开采访和普通工作动态，只要来源页面明确支持，可以令 `can_use_as_fact=true`，但不得去掉来源归因。

以下内容仅有单一来源时不得写成确定事实：恋情、隐私、违法或法律指控、伤亡、未成年人、重大负面争议。此类内容必须降级、保留明确风险标记，必要时不收录。

## 原始素材与版权

每个来源先写入 `data/sources.json`，至少包含标题、URL、来源、作者、发布时间、抓取时间、哈希、抓取状态、合规摘要、关键事实、授权状态和媒体页面 URL。

只有明确许可、公共领域、Creative Commons、API 条款允许或用户自有内容可以保存全文。其他内容使用原创摘要和结构化事实，不复制付费墙或授权不明全文。

## 事实与引用

每个事件必须包含 `facts`，每条事实必须引用存在于 `data/sources.json` 的 `source_ids`。数字、日期、引语、阵容、播出和争议信息必须能定位到来源。

单一来源非敏感事实可以按带归因的陈述进入正文；不带归因的确定性重要结论仍需官方一手来源或两个独立可靠来源。冲突来源必须写入 `conflicts`，无证据内容不得进入摘要。

## Feed 与校验

更新：

- `data/sources.json`
- `data/latest.json`
- `data/drama.json`
- `data/variety.json`
- `data/celebrity.json`
- `data/entertainment-events.json`
- `data/manifest.json`
- `data/status.json`

写入前检查 JSON、Schema、引用完整性、事实支持、哈希去重、文件大小和条目上限。任一关键文件失败时不得提交部分结果。

## 每日归档与清理

每天 23:00 先归档当天事件和来源，再清理过期数据。当前事件窗口 24 小时，在线来源快照 7 天，历史归档 30 天，失败日志 14 天。不得无条件清空当前 Feed。

## 运行报告

报告新增来源、单一来源事件、交叉确认事件、未收录高风险事件、来源访问状态和 GitHub 提交结果。写入失败时必须报告真实错误。
