# 公交刷卡换乘优惠与日封顶回算

供公交清分中心复核员核对原始记录、处理差异并封存证据。

## 启动

```sh
docker compose up --build -d
docker compose exec -T app pytest -q
```

打开 http://localhost:18245 。首次进入自动运行仓内脏样例。工具条可重跑、切换样例或上传CSV。SQLite保存在命名卷records中，重建服务保留批次。

## 模块

- 1. 刷卡采信：`/taps`，`/api/taps`。
- 2. 线路换乘：`/routes`，`/api/routes`。
- 3. 票价版本：`/fares`，`/api/fares`。
- 4. 行程配对：`/journeys`，`/api/journeys`。
- 5. 优惠回算：`/discounts`，`/api/discounts`。
- 6. 清分对账：`/clearing`，`/api/clearing`。
- 7. 日结归档：`/settlement`，`/api/settlement`。

## 核心规则

换乘按上次有效付费行程的时间窗计算，优惠与日封顶按确定顺序裁决并保留分币守恒。

## 日结裁决

按期先出带缺口的暂定日结，不压整日等补件。完整可核靠逐行去向保证，不靠数据齐全：

- 上传文件按业务日并入日结单 `POST /api/days/<day>/files`，坏行、冲突、空行、分段表头逐行登记去向，页面显示暂定状态与缺口来源，不再伪装完整归档。
- 补件并入同一日结单：文件内先见为准，跨文件同键以后到补件为准，被取代行留痕；暂定转完整不丢任何来源行。
- 同一文件重试按内容摘要去重，不生成第二份日结结果。
- 行数守恒且无未决缺口（对平）后才允许 `POST /api/days/<day>/seal` 封存为完整日结，否则返回409；封存后拒绝再并入文件。

## 演示

1. 打开首页，核对当次计算、差异和隔离原因。
2. 切换模块查看源行及裁决依据。
3. 重跑相同样例，批次号与行数保持一致。
4. 复核后导出一份证据CSV。版本已变化的复核提交返回409。
5. 在日结归档页选择业务日上传dirty.csv，日结单显示暂定与3个待补缺口及其来源行。
6. 再上传补件fix.csv，缺口逐行转为已补，被取代行留痕；对平后封存为完整日结，导出日结证据CSV含每个文件每一行的去向。

## 输入与输出

输入列见 `docs/DATA-DICTIONARY.md`。项目包含dirty.csv、clean.csv、legacy.csv，统一走实际导入路径。上传限制4MB，拒绝不带时区的时间。业务键按字符串保留，Decimal参与计算，空值不会当零。

`POST /api/runs` 接收sample或csv；`GET /api/runs`返回历史批次；`POST /api/runs/<id>/review`需要version与decision；`GET /api/runs/<id>/archive`返回唯一证据导出。

`POST /api/days/<day>/files` 并入来源文件（JSON csv或multipart），同内容重试返回当前日结；`GET /api/days` 与 `GET /api/days/<day>` 查看日结单；`POST /api/days/<day>/seal` 需要version且仅在对平后成功；`GET /api/days/<day>/archive` 导出逐行去向证据。

## 范围

样例均为虚构。单机复核工具不连接生产系统；不提供登录、远端数据库或自动支付。内存计算按4MB输入上限控制，SQLite事务保证结果完整写入。

## 目录

app为服务与规则，sample_data为输入，tests为测试，docs为定义与深度登记。
