# 接口

模块GET使用仓内样例，模块POST可传csv或rows与context，直接计算当前规则。/api/runs使用完整流水线并原子保存。每个阶段返回rows、quarantine、metrics；后续阶段还返回累计隔离。/api/upload接收multipart文件file。/api/runs/<id>/archive只导出一份带清单与证据的CSV。

## 日结单

- `POST /api/days/<day>/files`：把来源文件并入该业务日的日结单，day为YYYY-MM-DD。接收JSON `{"csv":文本,"name":文件名}` 或multipart文件file。同内容文件重试返回 `added:false` 与当前日结，不产生第二份结果；文件无法解析时整体拒绝，日结不变；已封存返回409。
- `GET /api/days`：全部日结单摘要。`GET /api/days/<day>`：日结单详情，含files、gaps与逐行ledger（采信/隔离/重复/空行/分段表头/被取代，隔离行带缺口状态open/covered/terminal）。
- `POST /api/days/<day>/seal`：需 `{"version":当前版本}`。行数守恒且无未决缺口才封存为完整日结，否则409（OPEN_GAPS）；版本陈旧409（STALE_VERSION）；重复封存409（DAY_SEALED）。
- `GET /api/days/<day>/archive`：导出日结证据CSV，每个来源文件的每一行各一条去向记录。
