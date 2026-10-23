# 故障排查手册

> 按「现象 → 先查什么 → 原因 → 处理」组织。所有报文样例均为实测，已脱敏。
> 遇到问题请**从 A 到 G 按阶段顺序**定位，不要跳。

---

## A. 账号与登录阶段

### A1. 登录返回 `errorCode 202012`

**现象**

```json
{"data":{"resultCode":1,"errorCode":"202012","errorDesc":"..."}}
```

**先查什么**：密文算得对不对（这一条最容易被忽略）。

**原因优先级**

1. **密文算法写错**。最常见的是 **Node `createCipheriv` 默认已自动 PKCS7 填充，
   代码又手动 pad 了一次** → 双重填充 → 密文错误 → 服务端认为密码不对。
2. 密码不是 App 当前使用的密码。
3. 该账号从未设置过密码（平时只用短信验证码 / 华为一键登录），需要先在 App 里设一个。

**处理**

```bash
# 用 openssl 交叉验证你自己的加密实现：两边输出应完全一致
printf '<你的手机号>' | openssl enc -aes-256-cbc -K <key_hex> -iv <iv_hex> -base64 -A
```

- Node：**删掉手动 pad**，直接 `c.update(buf)` + `c.final()`；
- Python `cryptography`：**必须显式 pad**（它不会自动填充）。

---

### A2. 登录「成功」但云端设备数恒为 0

**现象**：`resultCode=0`，拿到 token，但设备列表返回 `devices: []`。

**先查什么**：这个 token 是不是**假身份**。

**原因**：登录时 `loginName` 传了**明文**，服务端走进一个**完全不校验密码**的旧分支。

**验证方法（决定性）**：用**明显错误的密码**、**空密码**、甚至**不存在的手机号**各跑一次。
若每次都返回 `resultCode=0` 且 `customerId` **完全相同** → 说明走了旧分支，拿的是默认身份。

**处理**：改成加密登录（`loginName` 与 `signature` 都要 AES 加密）。
本项目附带的 `scripts/probe.mjs` 已强制加密。

> ⚠️ 这个坑的代价极大：会让人误判"账号里没有设备"，进而去反复重绑设备、换集成。
> **设备一直都在，是你的登录方式不对。**

---

### A3. 登录返回 HTTP 401

**原因**：`appKey` Header 缺失或值不对。

**处理**：`appKey: commonweb`。注意其他值（如 `aihome`、`hisense`）都会 401。

---

### A4. `POST /mobile/signon`（不带 `/se`）返回 403

**现象**

```json
{"code":403,"message":"Forbidden: Access to the requested resource is denied"}
```

**原因**：那是**旧版登录端点**，已被网关拒绝。网上不少老教程还指向它。

**处理**：改用 `POST /mobile/se/signon`（本文档的方案）。

---

### A5. `accessToken is illegal`

**原因**：token 无效或已过期。

**处理**：重新登录。集成里应实现"401/失效即重新登录"的自动重试。

---

### A6. HA 里整套设备 `unavailable`，但手机 App 一切正常 ⭐ 最常见

**现象**：集成跑了几天都好好的，某天开始 HA 里所有实体变成 `unavailable`，
而手机 App 里设备照旧在线、照样能控制。

**先查什么**：`GET /api/error_log`，搜集成 domain。

典型日志：

```
ERROR (MainThread) [custom_components.hisense_aihome.coordinator]
  Error fetching hisense_aihome data: 获取设备列表失败: accessToken is illegal
```

**原因**：海信的 `accessToken` **有有效期（实测数天）**。
过期后所有接口都返回 `accessToken is illegal`。
早期版本的集成只持有 token、没有保存账号密码，因此**无法自己重新登录**，
每轮轮询都失败 → 实体全部不可用。
手机 App 不受影响，是因为它**每次打开都会重新登录**。

**处理**

1. **立刻恢复**：HA → 设置 → 设备与服务 → 该集成 → ⋮ → **重新加载**
   （重载会重新走登录流程拿到新 token），或走 API：

   ```bash
   curl -X POST '<HA_HOST>/api/config/config_entries/entry/<ENTRY_ID>/reload' \
     -H 'Authorization: Bearer <HA_TOKEN>'
   ```

2. **根治**：v1.1.0 起协调器会保存账号密码，检测到 token 失效后
   **自动重新登录并重试一次**（轮询与指令下发都覆盖），不再需要手动重载。
   如果你用的是更早的版本，请更新。

**排查技巧**：这个症状很容易被误判成"设备离线"或"网络问题"。
区分方法很简单——**看 App**：App 正常就说明设备与账号都没问题，问题一定在 token。

---

## B. 云端设备枚举阶段

### B1. 爱家设备数为 0，但智慧家有家庭

**现象**

```
海信爱家 家庭数：0
海信爱家 设备数：0
海信智慧家 家庭数：1  <家庭名>
```

**先查什么**：这个手机号在爱家侧是否真的绑定了设备——**在 App 里确认**：关掉手机 Wi-Fi、
只用 4G，能否控制设备。

**可能原因**

1. 手机号对，但设备绑在**另一个**海信账号下（例如用微信/第三方登录的账号）；
2. 踩了 A2 的假身份陷阱（用假身份查爱家必然是空的）。

**处理**：先排除 A2；再核对 App 里的绑定手机号。

---

### B2. 同一台设备在两套云里"各有一半"

**原因**：两套云数据不互通，新品类只在爱家侧。

**处理**：集成应同时支持两边——家庭列表走智慧家（`getHomeList`），
设备列表与状态走爱家（`iot-aihome`）。不要假设一边能拿全。

---

### B3. 设备列表能拿到，但 `states` 是空的

**原因**：请求 `payload` 里漏了 `withState: true`。

**处理**：加上 `"withState": true`。状态就在 `device.states` 里，无需再逐台调详情。

---

## C. 集成安装阶段

### C1. 装了集成，但「添加集成」里搜不到

**检查顺序**

1. 路径对不对：必须是 `<HA配置目录>/custom_components/<domain>/manifest.json`
   （**不是** `custom_components/<domain>/<domain>/manifest.json`，多一层就会失败）；
2. `manifest.json` 里 `"config_flow": true` 是否存在（没有它就不会出现在添加列表里）；
3. **是否重启了 HA**——只 reload 无效。

**处理**：修正路径 / 补 `config_flow` / 重启 HA。

---

### C2. 重启后日志里有该集成的 ERROR

**先查什么**：`GET <HA_HOST>/api/error_log`，搜集成 domain，看 Traceback 最后一行。

**常见原因**

| Traceback 关键词 | 原因 |
|---|---|
| `ModuleNotFoundError` | `manifest.json` 的 `requirements` 未申报，或 HA 拉不到该包 |
| `ImportError: cannot import name 'Platform'` | HA 版本过旧 |
| `SyntaxError` | 文件在传输中损坏（编码/换行）——用校验和比对源文件 |

---

### C3. 修改了 `custom_components/` 下的代码但不生效

**原因**：HA 把集成模块缓存在进程内存里，`reload_config_entry` **不会**重新导入代码。

**处理**：重启 HA 进程。（改 YAML 才可以用 reload。）

---

### C4. 平台加载失败的隐蔽原因：属性名与基类冲突

**现象**：日志类似

```
Error while setting up <domain> platform for select: property '_category' of 'XxxSelect' object has no setter
```

**原因**：基类里把 `_category` 定义成了**只读 `@property`**，子类又写 `self._category = ...`。

**处理**：换名（如 `self._cat = ...`）。
**写实体类时先检查基类有没有同名 property。**

---

### C5. `services.yaml` 解析失败

**现象**

```
Unable to parse services.yaml for the <domain> integration: mapping values are not allowed here
in ".../services.yaml", line N, column M
```

**原因**：`description` 里出现了**未加引号的** JSON 示例，其中 `": "`（冒号+空格）被 YAML 当成映射分隔符。

**处理**：把该描述整行加引号，或去掉裸冒号：

```yaml
    params:
      description: "指令参数，形如 {\"a\": {\"b\": 1}}"
```

---

### C6. 配置流程驱动的接口报 `unknown_command`

**原因**：HA 2026.7 起 **WebSocket 已移除 `config_entries/flow`**。

**处理**：改用 REST：

```
POST   <HA_HOST>/api/config/config_entries/flow           # 启动，body {"handler":"<domain>"}
POST   <HA_HOST>/api/config/config_entries/flow/<flow_id> # 推进，body 为该步的 user_input
DELETE <HA_HOST>/api/config/config_entries/flow/<flow_id> # 清理
```

**排错技巧**：多选字段在响应里是 `{"type":"multi_select","options":{"<id>":"<标签>"}}`
——`options` 是**对象**不是数组，直接 `for...of` 会报 `not iterable`。

---

## D. 配置流程阶段

### D1. 提交账号后报认证失败

**先查**：`GET <HA_HOST>/api/error_log` 里的详细原因。集成应把服务的 `errorCode` 一并打出来。

**常见**：`202012`（见 A1）、令牌/密码错、网络不通（见 2.2 节的域名清单）。

---

### D2. 到了「选择家庭」却只有一个空选项

**原因**：家庭列表接口走的是**智慧家**云，而你的账号在那边没有家庭（新品类用户的常见情况）。

**处理**：集成不应因"家庭为空"就中断流程——可以退化为"不选家庭、直接列出爱家侧全部设备"。

---

### D3. 选完家庭，设备页空白

**原因**：设备列表按选中的 `homeId` 过滤，但爱家侧设备的 `homeId` 与智慧家的 `homeId`
**不是同一套编号**，过滤后自然为空。

**处理**：设备列表**不要**再按智慧家的 `homeId` 过滤（附带的集成已如此实现）。

---

## E. 实体与状态阶段

### E1. 实体数量远少于预期 / 很多实体缺失

**原因**：集成做了**品类白名单**，或字段映射表不完整。

**处理**
- 白名单：去掉它，识别不了的品类归为「其他」也照常建实体；
- 字段映射：以云端 `states` 的真实键名为准补表，`states` 里有值的字段一个都别丢。

---

### E2. 「剩余时间」等数值实体显示 `unknown`

**原因**：云端返回的是 `"--"` 这类占位值，集成把它当成有效值了。

**处理**：把 `"--"`、空串、`"None"` 统一视为**无值**（返回 `None`），
实体显示 `unknown` 是 HA 的正常表现；界面上再统一渲染成 `—`。

---

### E3. 故障类实体刷屏（几百个）

**原因**：把 `fault.*` / `cl_Error_*` 的每一个故障位都建了实体。

**处理**：用一个「故障」汇总实体，只报第一个非 `"--"` 的故障位；
其余原始键值放进该实体的属性里备查。

---

### E4. 轮询太频繁导致云端限流 / 接口被拒

**处理**
- 优先用一次列表请求拿全状态（`withState: true`），不要逐台调详情；
- 轮询间隔取 120 秒级即可（洗衣机/干衣机不需要秒级实时）；
- 控制指令下发后做「立即刷新 + 数秒后补刷一次」，而不是靠缩短全局轮询间隔。

---

## F. 控制阶段

### F1. 所有设置类命令都返回 `notSupported`

**先查什么**：**设备是否处于开机态**。

**原因**：海信云端对**关机态**设备会把绝大多数命令误报为 `notSupported`，看起来像"该机型不支持"。

**处理**：先在 App / HA 里把设备开机，再重试。
**枚举命令集时务必在开机态进行**，否则会得到一张完全错误的"不可用清单"。

---

### F2. `conflictCommand` / `errorcode = 7`

**现象**

```json
{"payload":{"status":"ERROR","errorCode":"conflictCommand","subErrorCode":"7","errorDesc":"ctl control failed, errorcode = 7"}}
```

**含义**：命令名与参数名**都对**，但设备当前状态拒绝了它。

**常见场景**：关机态下发设置类命令；童锁开启时下发其他命令；运行中改不可改的参数。

**处理**：先满足前置条件（开机 / 解锁 / 暂停），再重试。
集成应把这个错误**原样透出给用户**，并附上"设置类参数需要设备先开机"的提示，不要静默失败。

---

### F3. `Missing required action param 'x'`

**含义**：命令名对了、参数名错了。**正确参数名就写在提示里**。

**处理**：按提示改参数名。这也说明「靠错误语义探测」是可行且安全的。

---

### F4. `deviceNotFound`

**原因**：`payload.partnerId` 传错。

**处理**：用**设备列表里 `partner.id` 的真实值**。
网上不少示例代码里硬编码了某个固定值（如 `10005`），换个设备就会 `deviceNotFound`。

---

### F5. 命令返回 `SUCCESS` 但设备毫无变化

**含义**：命令存在但**无效**。

**处理**：把它从可调实体里**移除**，否则用户会以为"能调"。
判断"有效"的唯一标准是**读回云端状态确实变了**。

---

### F6. `Start` 在设备关机时也返回 SUCCESS

**现象**：设备明明关着，`connector.device.command.Start` 返回 `SUCCESS`，设备真的被拉起来了。

**处理**
- 把"启动"做成**按钮**（一次性动作）而不是开关，降低误触；
- 文档里明确写出这是真实动作；
- 探测命令名时避免盲测 `Start*` 系列。

---

### F7. 只看 HA 界面以为"命令没生效"

**原因**：HA 自身轮询有延迟（默认上百秒），UI 状态是滞后的。

**处理**：**绕过 HA 直读云端** `device.states` 来判定，再回头检查集成是否需要在指令后主动刷新。

---

## G. 写集成时的其他注意点

| 事项 | 说明 |
|---|---|
| 部署 | Docker 容器版 HA 无 Supervisor，一切都要走 HA 的 REST/WebSocket API |
| 凭据 | 账号密码只从环境变量注入脚本；集成侧让 HA 存进 `core.config_entries` |
| `check_config` | 改 YAML 后、重启前**先跑** `POST /api/config/core/check_config`，拿到 `valid` 再重启 |
| 静态资源 | `<配置目录>/www` 对外映射为 `/local/`；该路径**免登录**，但页面里调 API 仍需令牌 |
| 日志 | `GET /api/error_log` 是最快的排查入口；集成里用 `_LOGGER.info/debug` 打关键节点 |
