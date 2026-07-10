# Automation Contract

本文件定义 ChatGPT 定时任务对本仓库的写入规则。

## 时区与频率

- 时区：Asia/Shanghai
- 热点检查：每天 00:00、04:00、08:00、12:00、16:00、20:00
- 每日清理：每天 23:00

## 热点检查任务

1. 搜索当前可访问的国内外公开榜单和可靠媒体。
2. 主题仅限电视剧、网剧、短剧、综艺、真人秀、晚会、明星公开动态及娱乐圈事件。
3. 优先检查微博、百度、抖音、腾讯视频、爱奇艺、B站、芒果TV、优酷、Google Trends、YouTube、TMDB。
4. 不得虚构榜单、排名、热度、链接、图片或视频地址。
5. 同一事件跨平台合并；保留所有有效来源。
6. 无法确认的爆料标记为 unverified，不能写成确定事实。
7. 图片仅保存官方图片或原页面缩略图 URL。
8. 视频仅保存作品页面或官方嵌入页 URL，不保存临时 CDN 流地址。
9. 只保留最近 24 小时内发现且仍具有热度的内容。
10. 更新 data/latest.json 以及对应分类文件。
11. 如果所有来源均失败，不得用空数组覆盖上一版有效数据；只更新 data/status.json。
12. 只有数据发生实质变化时才提交。

## 每日清理任务

1. 在每天 23:00 清除当日所有热点条目。
2. 将以下文件的 items 重置为空数组：
   - data/latest.json
   - data/drama.json
   - data/variety.json
   - data/celebrity.json
   - data/entertainment-events.json
3. 保留 schema_version、feed、timezone、window_hours、source_status 和 cleanup 结构。
4. cleanup.last_run_at 使用北京时间 ISO 8601 时间。
5. cleanup.status 写为 completed。
6. data/status.json 记录清理结果。
7. 清理前后必须保持合法 JSON；任何校验失败都不得提交部分结果。

## 可信状态

- official：官方账号、节目组、平台或当事人发布
- confirmed：至少两个可靠来源确认
- reported：可靠媒体报道但尚无官方确认
- unverified：单一来源或网络传闻
- refuted：已被正式否认

## 写入限制

- 综合热点最多 200 条
- 单个分类最多 100 条
- 每条最多 5 个图片 URL
- 每条最多 3 个视频页面 URL
- 每个 JSON 文件目标大小不超过 1 MB
- 不上传第三方图片、视频或其他二进制媒体
