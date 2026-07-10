# Entertainment Hotspot JSON

自动聚合国内外电视剧、网剧、短剧、综艺、明星和娱乐圈热点，并以稳定 JSON 格式供其他脚本读取。

## 数据地址

- 综合热点：`https://raw.githubusercontent.com/hobyide/hotspot-json/main/data/latest.json`
- 剧集热点：`https://raw.githubusercontent.com/hobyide/hotspot-json/main/data/drama.json`
- 综艺热点：`https://raw.githubusercontent.com/hobyide/hotspot-json/main/data/variety.json`
- 明星热点：`https://raw.githubusercontent.com/hobyide/hotspot-json/main/data/celebrity.json`
- 娱乐事件：`https://raw.githubusercontent.com/hobyide/hotspot-json/main/data/entertainment-events.json`
- 运行状态：`https://raw.githubusercontent.com/hobyide/hotspot-json/main/data/status.json`

## 自动化规则

- 时区：`Asia/Shanghai`
- 每 4 小时检查一次：00:00、04:00、08:00、12:00、16:00、20:00
- 每天 23:00 清理当天热点数据
- 只在数据发生实质变化时写入
- 清理后保留有效 JSON 结构和运行状态，热点数组重置为空
- 每次写入前必须符合 `schema/hotspot.schema.json`

## 收录范围

- 电视剧、网剧、短剧
- 综艺、真人秀、晚会
- 明星公开动态
- 官宣、定档、开机、杀青、选角
- 红毯、奖项、娱乐活动
- 公开争议、回应、道歉和法律事件
- 收视率、播放热度和口碑表现

排除普通社会新闻、政治、体育、游戏、数码、科研、开源内容、纯粉丝签到和无法确认来源的隐私爆料。

## 媒体规则

仓库只保存原始页面、图片、封面及视频播放页面 URL，不下载或重新托管第三方图片和视频文件。视频 CDN 临时直链默认不保存。

## 可信状态

- `official`：官方账号或当事方正式发布
- `confirmed`：多家可靠媒体确认
- `reported`：媒体报道但尚无官方确认
- `unverified`：网络传闻或单一来源
- `refuted`：已被官方或当事人否认

详见 [AUTOMATION.md](AUTOMATION.md)。
