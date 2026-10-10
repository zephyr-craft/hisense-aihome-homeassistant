# 海信云协议参考（接入与状态/控制）

> 本文是 `SKILL.md` 的技术底稿。所有内容来自实测，非推测；推测部分会显式标注「推测」。
> 文中不含任何真实账号、令牌、设备 ID。

---

## 1. 账号体系：两套互不相通的云

| | 海信爱家（AIHome） | 海信智慧家（WG / legacy） |
|---|---|---|
| 设备与状态 | `https://iot-aihome.hismarttv.com` | `https://api-wg.hismarttv.com` |
| 对应 App | 「海信爱家」（新，覆盖全品类） | 「海信智慧家」/ 旧版 |
| 典型现象 | 新品类（洗衣机/干衣机/烘干机…）**只在这里** | 常见"有家庭、但设备列表为空" |

**同一个手机号在两套体系里可能是两个不同账号。** 接入前必须先判断设备在哪一边，
判断方法：分别查两边的家庭与设备列表（见第 3、4 节）。

---

## 2. 登录

### 2.1 请求

```
POST https://portal-account.hismarttv.com/mobile/se/signon
```

**Query 参数**

| 参数 | 值 |
|---|---|
| `lastUpdateTime` | `0` |
| `version` | `1.0` |
| `deviceType` | `2` |
| `appType` | `100` |
| `versionCode` | `101` |
| `adaptertRank` | `720` |
| `_` | 毫秒时间戳 |

**Header**

| 头 | 值 |
|---|---|
| `Content-Type` | `application/json; charset=UTF-8` |
| `appKey` | `commonweb` ← **必需，其他值一律 401** |
| `X-Sign-For` | `base64( md5( body原始字符串 + PORTAL_SECRET ) )` |

**Body（JSON，字段顺序敏感：签名基于原始字符串）**

```json
{
  "loginName": "<AES(手机号)>",
  "signature": "<AES(密码)>",
  "serverCode": "9501",
  "distributeId": "2001",
  "termType": 2
}
```

### 2.2 加密算法

```
算法：AES-256-CBC
密钥：PORTAL_SECRET（32 字节 ASCII 字符串）
IV  ：PORTAL_SECRET 的前 16 字节
填充：PKCS7
编码：base64
```

`PORTAL_SECRET` 与应用级常量见第 9 节。

> ⚠️ **Node 注意**：`crypto.createCipheriv()` **默认已自动 PKCS7 填充**，不要再手动 pad，
> 否则双重填充 → 密文错误 → 服务端返回 `202012`。
> Python `cryptography` 不会自动填充，必须显式 pad。
> 交叉验证：`printf '<手机号>' | openssl enc -aes-256-cbc -K <key_hex> -iv <iv_hex> -base64 -A`

### 2.3 ⚠️ 明文登录会返回「假身份」（最重要的一条）

如果 `loginName` 传**明文**，服务端会走进一个旧分支，**完全不校验密码**：

| 输入 | 返回 |
|---|---|
| 正确密码 | `resultCode=0` + token + **固定的** `customerId` |
| 错误密码 | 同上，`customerId` 完全相同 |
| 空密码 | 同上 |
| 不存在的手机号 | 同上 |

该 token **能通过**后续接口的合法性校验（伪造 token 会报 `accessToken is illegal`），
因此极具迷惑性——但它是默认身份，拿它查设备永远是 0 台。

**判定方法**：多试几个明显错误的密码/不存在的手机号，若 `customerId` 完全不变 → 说明走了旧分支。
**结论：永远只用加密登录。**

### 2.4 成功响应

```json
{
  "data": {
    "resultCode": 0,
    "tokenInfo": {
      "token": "<ACCESS_TOKEN>",
      "customerId": "<CUSTOMER_ID>",
      "subscriberId": "<SUBSCRIBER_ID>",
      "...": "..."
    }
  }
}
```

### 2.5 错误码

| errorCode | 含义 | 处理 |
|---|---|---|
| `202012` | 密码不被账号服务接受 | ① 核对是否为 App 当前密码；② 账号可能没设过密码（一直用验证码/一键登录）；③ **检查密文算法是否重复填充** |
| `401`（HTTP） | `appKey` 不对 | 用 `commonweb` |

---

## 3. 家庭列表（智慧家侧）

```
GET https://api-wg.hismarttv.com/wg/dm/getHomeList?<query>
```

| Query | 值 |
|---|---|
| `accessToken` | 登录拿到的 token |
| `sign` | 空字符串 |
| `languageId` | `0` |
| `version` | `8.0` |
| `timezone` | `28800` |
| `format` | `1` |
| `timeStamp` | 毫秒时间戳 |

建议 Header：`Host: api.wg.hismarttv.com`、`User-Agent: okhttp/4.10.0`。

响应：

```json
{ "response": { "resultCode": 0, "homeList": [ { "homeId": "<HOME_ID>", "homeName": "<家庭名>", "...": "..." } ] } }
```

> 接入时**必须**用家庭列表里的真实 `homeId`，不要自己编。

---

## 4. 设备列表 + 实时状态（爱家侧）

```
POST https://iot-aihome.hismarttv.com/4.0/iot/devices/list
```

**Body**

```json
{
  "deviceId": "<占位设备ID>",
  "appType": "2",
  "appVersion": "<App 版本号>",
  "header": { "messageId": "<uuid>" },
  "accessToken": "<ACCESS_TOKEN>",
  "payload": {
    "withMultiSplit": true,
    "customerId": "<CUSTOMER_ID>",
    "withState": true,
    "sourceType": 20,
    "whitelist": 1
  }
}
```

**Header**

| 头 | 值 |
|---|---|
| `Content-Type` | `application/json; charset=utf-8` |
| `User-Agent` | 形如 `JHKMain/<App版本> (iPhone; iOS <版本>; Scale/3.00)` |
| `X_REAL_HOST` | 厂商网关 IP（部分环境下带上更稳；见第 9 节） |
| `X-Sign-For` | `base64( md5( body原始字符串 + AIHOME_SIGN_KEY ) )` |

> 顶层 `deviceId` 传**固定占位值**（见第 9 节）；真正的设备 ID 在 `payload` 之外不参与。

**响应要点**

```json
{
  "payload": {
    "status": "SUCCESS",
    "devices": [
      {
        "deviceId": "<DEVICE_ID>",
        "comModuleId": "<COM_MODULE_ID>",
        "nickname": "<人话名，如 洗衣机>",
        "categoryCode": "connector.device.type.washer",
        "product": { "code": "<型号>", "name": "<型号>", "featureCode": "<特征码>" },
        "room": { "id": "<ROOM_ID>", "name": "<房间名>" },
        "partner": { "id": "1001" },
        "homeId": "<HOME_ID>",
        "states": { "...": "实时状态，见第 6 节" },
        "deviceInfo": { "hwVersion": "...", "swVersion": "..." },
        "reportTime": "YYYY-MM-DD HH:mm:ss",
        "labels": [ { "key": "...", "type": "2", "value": "...", "valueDef": "" } ]
      }
    ]
  }
}
```

**关键实践**：
- `withState: true` 时**实时状态就在 `states` 里**，不必再逐台调详情接口（少一半请求，降低限流风险）；
- `nickname` 才是人话名，`room.name` 是房间名（可用来设置实体的 `suggested_area`）；
- `categoryCode` 是品类判定依据（`connector.device.type.<品类>`）；
- **写集成时不要做品类白名单**，否则新品类会被静默丢弃。

---

## 5. 设备详情（可选）

```
POST https://iot-aihome.hismarttv.com/4.0/iot/devices/detail
```

```json
{ "deviceId": "<真实设备ID>", "sourceType": 20, "partnerId": "1001", "customerId": "<CUSTOMER_ID>" }
```

`payload.device` 结构与列表里的元素基本一致（额外多 `labels`、`originalState`、`reportTime` 等）。
若列表已带 `withState: true`，**一般不需要调用它**。

---

## 6. 状态字段（states）说明

单台设备可能上报 **100~200 个字段**，其中绝大多数是**故障位**：

| 前缀 | 说明 |
|---|---|
| `fault.*`（如 `fault.F52`、`fault.0x1A`） | 故障位，正常时值均为 `"--"` |
| `cl_Error_*` | 故障/错误位，正常时 `"--"` |
| `fault`（无后缀） | 汇总故障码，正常时 `"0"` |

**写集成时不要把每个故障位都建成实体**，会把界面淹没。做法：
用一个「故障」实体汇总（只报第一个非 `"--"` 的值），其余原始字段塞进属性或忽略。

其余有意义的字段示例（洗衣机）：

| 字段 | 含义 |
|---|---|
| `powerStatus` / `runStatus` / `startStop` / `startPauseStatus` | 电源 / 运行 / 启停 |
| `workMode` | 当前程序编号（程序选择就是改它） |
| `washTemperature` / `dehydrationSpeed` / `rinsingFrequency` / `waterLevel` / `washTime` | 温度 / 转速 / 漂洗 / 水位 / 洗涤时间 |
| `remainRunTime` / `totalRunTime` | 剩余 / 总时长（分钟）——**App 卡片上显示的分钟数对应的是这两个**，不是 `washTime` |
| `powerConsumption` / `waterConsumption` | 耗电量(kWh) / 耗水量(L)（**每次运行的值**，非累计） |
| `childLock` / `uvDegermingSwitch` / `airingSwitch` 等 | 各类开关 |
| `onlineStatus` | `"1"` 在线 / `"0"` 离线 |

> 字段名与品类相关。取字段时要**容错**：认不出来的直接原样透出，不要假设一定存在。

---

## 7. 控制（下发指令）

```
POST https://iot-aihome.hismarttv.com/4.0/iot/devices/execute
```

**Body**

```json
{
  "header": { "messageId": "<uuid>" },
  "deviceId": "<占位设备ID>",
  "appVersion": "<App 版本号>",
  "payload": {
    "deviceId": "<真实设备ID>",
    "sourceType": "20",
    "exclusionFlag": 1,
    "customerId": "<CUSTOMER_ID>",
    "partnerId": "<设备自带 partner.id>",
    "actions": [ { "command": "connector.device.command.<X>", "params": { "<字段名>": { "value": 数字 } } } ]
  },
  "accessToken": "<ACCESS_TOKEN>",
  "appType": "2",
  "sourceName": "smartlifeAppH5"
}
```

签名与第 4 节相同（`X-Sign-For = base64(md5(body + AIHOME_SIGN_KEY))`）。

### 7.1 命名规律

- 命令名：`connector.device.command.Set<字段名首字母大写>`，参数为 `{ <字段名>: { "value": 数字 } }`
- 例：`SetWashTemperature` + `{"washTemperature": {"value": 40}}`
- **电源是特例**：`Power` + `{"onAndOff": {"code": "On"|"Off"}}`，
  且 **`sourceName` 必须为 `smartlifeApp`**（不是 `smartlifeAppH5`）

### 7.2 ⚠️ 生效前提：设备必须先开机

海信云端对**关机态**设备会把**绝大多数命令误报为 `notSupported`**（看起来像"该机型不支持"），
**开机后同样的命令就变成 `SUCCESS`**。

> 因此：**枚举/排查命令集前，务必先把设备开机**。只看关机态结果会得出完全错误的命令表。

### 7.3 靠错误语义探测命令名（不用抓包）

| 返回 | 含义 |
|---|---|
| `notSupported` / `Unsupported command 'x'` | 命令名错（**或设备处于关机态**，见 7.2） |
| `notSupported` / `Missing required action param 'x'` | 命令名对、**参数名错**（正确参数名就在提示里） |
| `conflictCommand` / `ctl control failed, errorcode = 7` | 名字与参数都对，但设备当前状态拒绝 |
| `deviceNotFound` | `partnerId` 传错 |
| `SUCCESS` | 成功，响应里还会带回最新的 `device.states` |

配合"用设备自身 `states` 的字段名自动生成 `Set<PascalCase(字段)>` 候选"批量试，效率很高。
> ⚠️ 但探测"启动类"命令要克制：`Start` 在**关机态也可能返回 SUCCESS**（真机会被拉起）。

### 7.4 已实测可用的命令（同型号/同品类参考）

| 功能 | 命令 | 参数 |
|---|---|---|
| 开关机 | `Power` | `{"onAndOff": {"code": "On"/"Off"}}`，sourceName=`smartlifeApp` |
| 启动 / 暂停 | `Start` / `Pause` | `{"startStop": {"value": 1/0}}` |
| 程序选择 | `SetModes` | `{"modes": {"value": N}}`（状态里的 `workMode` 会同步跟随） |
| 预约时间 | `SetOrderTime` | `{"orderTime": {"value": 分钟}}` |
| 开启远程控制 | `SetRemoteControlFlag` | `{"remoteControlFlag": {"value": 1}}` |
| 洗涤温度 | `SetWashTemperature` | `{"washTemperature": {"value": 40}}` |
| 漂洗次数 | `SetRinsingFrequency` | `{"rinsingFrequency": {"value": 2}}` |
| 脱水转速 | `SetDehydrationSpeed` | `{"dehydrationSpeed": {"value": 800}}` |
| 水位档位 | `SetWaterLevel` | `{"waterLevel": {"value": 2}}` |
| 洗涤时间 | `SetWashTime` | `{"washTime": {"value": 10}}` |
| 投放模式 | `SetDetergentMode` | `{"detergentMode": {"value": 2}}` |
| 夜间洗 | `SetSmartNightWashSwitch` | `{"smartNightWashSwitch": {"value": 1}}` |
| 衣物材质 | `SetClotheMaterial` | `{"clotheMaterial": {"value": 0}}`※ |
| 童锁 | `SetChildLock` | `{"childLock": {"value": 1}}` |

※ `SetClotheMaterial` 返回 `SUCCESS` 但实测**不改变设备状态**——命令存在但无效，
别把它做成可调实体（会误导）。凡是"返回成功但不生效"的，都应视为不可用。

### 7.5 程序编号与程序名

- 程序选择就是 `SetModes` 的取值，`workMode` 会同步跟随；**其余取值一律返回 `notSupported`**，
  所以可以用它把本机支持的编号枚举出来。
- **程序名服务端不返回**（在 App 客户端本地字典里）。可靠的对法：
  1. 逐个程序号选到设备上，读回该程序的**总时长**（洗衣机 `totalRunTime`、干衣机 `drySetTime`）；
  2. 与 App「全部程序」列表里每个程序卡片显示的分钟数比对，**只认唯一匹配**；
  3. 多个候选时宁可留空显示编号，也不猜。
- 设备 `labels` 里的 `common_prg` 是"首页常用"程序，**顺序与 App 展示顺序一致**，
  值就是程序代码，可以直接对上第一批名字。
- App 上带「云程序」角标的程序提示"设备上没有"，但**实测它们在设备上同样占用了程序号槽位**，
  一样可以用 `SetModes` 选中。

---

## 8. label 通道（`/4.0/iot/devices/label/batchSave`）

```
POST https://iot-aihome.hismarttv.com/4.0/iot/devices/label/batchSave
```

```json
{
  "accessToken": "<ACCESS_TOKEN>",
  "deviceId": "<真实设备ID>",
  "header": { "languageId": 0, "messageId": "<uuid>", "timestamp": 毫秒 },
  "appVersion": "<App 版本号>",
  "payload": { "labels": [ { "partnerId": "<partner.id>", "devId": "<真实设备ID>",
                             "labelKey": "<key>", "labelValue": "<value>" } ] }
}
```

**实测情况（避免走弯路）**：

- 通道是通的，但**对设备控制基本没用**；
- 部分键（如 `program_last_use`）写入返回 `SUCCESS`，但**不影响 `workMode`**；
- 另一些键（如 `airing_set_running`、`auto_put_in`）写不进去，报
  `totallyFailed` + "设备在品类(<品类码>)标签信息中没有查到 labelName 数据"
  ——即该键对该品类不是可写标签；
- 探测 20+ 个候选 label 键**全部不存在**。

结论：**设置设备参数优先用 `command`，不要指望 label 通道。**

---

## 9. 应用级常量（非个人凭据）

以下常量来自海信官方 App 的通信协议，也广泛存在于多个开源集成中。
海信更新 App 后可能失效——届时重新抓包替换即可。集中放在
`scripts/probe.mjs` 顶部与 `assets/hisense_aihome/const.py`。

| 常量 | 值 | 用途 |
|---|---|---|
| `PORTAL_SECRET` | `MORZRbkuiWxjp+SM4vR_GxY4pZxLZ6rn` | 登录：AES 密钥 + `X-Sign-For` 的签名密钥（32 字节） |
| `AIHOME_SIGN_KEY` | `AOSj8JBr0IpUzv5w+hURR6W4oINsI4o5` | 爱家接口 `X-Sign-For` 的签名密钥 |
| 占位 `deviceId` | `862fff02fffefff00000fffe53b30aa3fdb331c013166f31a6089802` | 爱家接口顶层的固定占位值 |
| `appKey` | `commonweb` | 登录 Header，必需 |
| `appVersion` | 形如 `6.4.0.3` | 建议与 App 实际版本接近 |
| `X_REAL_HOST` | 厂商网关 IP | 部分环境下需要；实测带上更稳定 |

---

## 10. 用于排查的最小验证顺序

1. 加密登录 → 拿到 token 与 `customerId`（且换错误密码时 `customerId` 应**变化**或直接报错）
2. 查爱家家庭列表 + 设备列表 → 确认设备数 > 0，记下 `categoryCode`
3. 查智慧家家庭列表做对照 → 判断设备到底在哪套云
4. 用设备列表里 `states` 的字段值，驱动集成建实体
5. 下发一条无害指令（如设置温度为其当前值），确认返回 `SUCCESS`
6. 读回 `states` 确认值确实变化

以上任何一步失败，查 `troubleshooting.md` 的对应条目。
