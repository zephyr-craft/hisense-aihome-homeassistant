---
name: hisense-aihome-onboarding
summary: 把海信（Hisense）洗衣机 / 干衣机等家电接入 Home Assistant 的完整可复现流程
description: 面向想把海信家电接入 Home Assistant 的用户。覆盖环境前提、账号体系判断（海信爱家 vs 海信智慧家）、加密登录、设备与品类枚举、集成安装、配置流程创建、实体验证，以及两个极易踩且难自查的坑（明文登录返回假身份、AES 双重填充）。附带可直接运行的脱敏自查脚本与配置流程脚本，以及一套自建集成。仅覆盖「设备接入」，不含 Lovelace 卡片 / 仪表盘等展示层配置。
agent_created: true
---

# 海信家电接入 Home Assistant

> **本 SKILL 的边界**：只解决「把设备接进 HA、能看到状态、能控制」。
> 不含 Lovelace 卡片、仪表盘、美化等展示层配置。
>
> 文中所有账号、密码、令牌、设备 ID、内网地址一律写成 `<占位符>`，请替换成你自己的。

---

## 1. 先确认你属于哪种情况

| 你的情况 | 建议方案 |
|---|---|
| 只有**空调 / 冰箱**，想接 HA | 先用现成集成 `manymuch/HisenseHA`（v1.6.2 支持空调+冰箱）。若失败再走本文自建方案 |
| 有**洗衣机 / 干衣机 / 洗碗机**等新品类 | 现成集成**都不支持**，走本文自建方案（`assets/hisense_aihome/`） |
| 现成集成分分钟报「账号下没有设备」 | ⚠️ 先看第 3.3 节——很可能你被"假身份"骗了，**不是**账号的问题 |
| 设备在 App 里能远程控制，但云端查不到 | 同上，先看第 3.3 节 |

**关键结论（踩过坑才知道）**：
- `manymuch/HisenseHA` v1.6.2 的设备类型白名单**只有空调和冰箱**，其他品类在扫描阶段就被代码静默丢弃；
- 而且它查的是「海信**智慧家**」云，新品类（洗衣机/干衣机等）在「海信**爱家**」云上——**两套云数据不互通**。

---

## 2. 环境前提

### 2.1 必须满足

| 项 | 要求 | 为什么 |
|---|---|---|
| Home Assistant | 2025.6 或更新（实测 2026.7.4） | 自建集成用到较新的 `Platform` 枚举与配置流程 API |
| 部署方式 | 任意（HA OS / Supervised / **Docker 容器版**均可） | 容器版没有 Supervisor，本方案不依赖 Supervisor |
| 设备状态 | **已在手机 App 里完成配网绑定** | 云端没有的设备，任何集成都不可能显示出来 |
| 远程可控 | 关掉手机 Wi-Fi、只用 4G 时 App 仍能控制设备 | 这是"设备确实在云上"的唯一可靠证据 |
| 登录方式 | 该账号能用**手机号 + 密码**登录 App | 若你平时只用短信验证码 / 华为一键登录，账号可能根本没设过密码，先去 App 里设置一个 |
| 一台电脑 | 能访问 HA，且装有 Node.js 18+ | 跑自查脚本与配置流程脚本 |

### 2.2 网络要求

HA 所在的网络需要能访问以下域名（HTTPS 443）：

| 域名 | 用途 |
|---|---|
| `portal-account.hismarttv.com` | 账号登录 |
| `api-wg.hismarttv.com` | 「海信智慧家」侧的家庭列表 |
| `iot-aihome.hismarttv.com` | 「海信爱家」侧的设备列表与状态（**新品类在这里**） |

> 若 HA 与电脑不在同一网络，请在**能访问这些域名**的机器上跑脚本排查。

### 2.3 需要准备的凭据

| 占位符 | 说明 |
|---|---|
| `<HISENSE_PHONE>` | 「海信爱家」App 的登录手机号 |
| `<HISENSE_PASSWORD>` | 该 App 当前使用的密码（不是短信验证码） |
| `<HA_HOST>` | 你的 HA 地址，形如 `http://homeassistant.local:8123` 或 `http://<你的IP>:8123` |
| `<HA_TOKEN>` | HA 的**长期访问令牌**：HA → 左下角用户名 → 安全 → 长期访问令牌 → 创建 |

---

## 3. 核心原理（不理解这节，后面一定会踩坑）

### 3.1 海信有两套互不相通的云

| | 海信爱家 | 海信智慧家 |
|---|---|---|
| 设备 / 状态接口 | `iot-aihome.hismarttv.com` | `api-wg.hismarttv.com` |
| 对应 App | 「海信爱家」（新，全品类） | 「海信智慧家」/旧版 |
| 特征 | **新品类只在这里** | 常见"有家庭、但 0 设备" |

同一个手机号在两套体系里可能是**两个不同账号**。判断办法见 Step 1。

### 3.2 三个接口就够了

| 用途 | 接口 |
|---|---|
| 登录换 token | `POST https://portal-account.hismarttv.com/mobile/se/signon` |
| 家庭列表（智慧家侧） | `GET https://api-wg.hismarttv.com/wg/dm/getHomeList?accessToken=…` |
| **设备列表 + 实时状态**（爱家侧） | `POST https://iot-aihome.hismarttv.com/4.0/iot/devices/list` |

设备的**实时状态就在设备列表返回的 `device.states` 字段**里（带 `withState: true`），
不需要再逐台调详情接口。完整参数与签名算法见 `references/protocol.md`。

### 3.3 ⚠️ 陷阱一：明文登录会返回一个「假身份」

**这是本文档存在的最重要原因。**

登录请求里如果 `loginName` 传的是**明文**，服务端会走进一个旧分支，**完全不校验密码**：

| 输入 | 返回 |
|---|---|
| 正确密码 | `resultCode=0` + token + 一个**固定**的 `customerId` |
| 错误密码 | 同上，一模一样的 `customerId` |
| **空密码** | 同上 |
| **根本不存在的手机号** | 同上 |

这个 token **能通过**后续接口的合法性校验（伪造 token 会直接报 `accessToken is illegal`），
所以看起来一切正常——但它是**别人的/默认的身份**，拿它查云端永远是 0 台设备。

**后果**：你会得出"我的账号里没有设备"的错误结论，然后去反复重绑设备、换集成，
浪费掉一整轮排查。**真实的设备一直都在你账号里。**

**规避方法**：只走**加密登录**（见 3.4）。本项目附带的自查脚本已强制加密。

### 3.4 ⚠️ 陷阱二：加密时不要重复填充

加密算法是 **AES-256-CBC + PKCS7**，密钥 = 32 字节的应用密钥，IV = 该密钥前 16 字节。

**Node 的 `crypto.createCipheriv()` 默认已经自动做 PKCS7 填充**。
如果按其他语言的写法再手动补一次 pad，就会**双重填充** → 密文错误 → 服务端返回
`errorCode 202012`（"用户名或密码错误"），极易被误判成"密码不对"。

```js
// ✅ 正确：交给 Node 自己填充
const c = crypto.createCipheriv('aes-256-cbc', KEY, IV);
return Buffer.concat([c.update(Buffer.from(v, 'utf8')), c.final()]).toString('base64');

// ❌ 错误：手动 pad 之后 Node 又 pad 一次
const pad = 16 - (raw.length % 16);
c.update(Buffer.concat([raw, Buffer.alloc(pad, pad)]));   // 双重填充
```

**自查手段**：拿 `openssl` 交叉验证密文（最快能定位"是不是填充写错了"）。

```bash
# PORTAL_SECRET 见第 8 节，是 32 字节字符串；下面是它对应的 key / iv 的十六进制形式
SECRET='MORZRbkuiWxjp+SM4vR_GxY4pZxLZ6rn'
KEY_HEX=$(printf '%s' "$SECRET" | xxd -p -c 64)   # 32 字节 -> 64 位 hex（AES-256 的 key）
IV_HEX=${KEY_HEX:0:32}                            # 前 16 字节 -> 32 位 hex（IV）
# 没有 xxd 的话可用： KEY_HEX=$(printf '%s' "$SECRET" | od -An -tx1 | tr -d ' \n')

printf '<HISENSE_PHONE>' | openssl enc -aes-256-cbc -K "$KEY_HEX" -iv "$IV_HEX" -base64 -A
```

Python 的 `cryptography` 库**不会**自动填充（必须显式 pad），所以同样的代码在 Python 侧是正确的——
这也是为什么"HA 里能登录、脚本却报 202012"。

---

## 4. 接入步骤

### Step 1 · 账号自查（约 3 分钟）

先不碰 HA，直接问云端「这个账号到底有哪些设备」。用附带脚本（全程只读，凭据只走环境变量）：

```bash
HISENSE_PHONE='<HISENSE_PHONE>' HISENSE_PASSWORD='<HISENSE_PASSWORD>' \
  node scripts/probe.mjs
```

> 本 SKILL 附带的脚本都用 **Node.js 18+ 的原生能力**（内置 `crypto` 与全局 `fetch`）编写，
> **不需要 `npm install`、也没有 `package.json`**——`.mjs` 后缀表示它就是 ES 模块，直接跑。

期望看到类似输出：

```
✅ 登录成功  账号 138***000  customerId 100***001        ← 此处为示例数据
   海信爱家 家庭数：N
   海信爱家 设备数：M
     - [<型号>] <昵称>   品类码=connector.device.type.washer
   海信智慧家 家庭数：K  <家庭名>
✅ 云端共 M 台设备，可正常接入 HA。
```

**判断标准**：

| 结果 | 含义与下一步 |
|---|---|
| 登录成功 + 设备数 > 0 | ✅ 继续 Step 2 |
| 报 `202012` | 密码问题：确认是 App 当前密码；或该账号没设过密码（只在用验证码/一键登录） |
| 设备数 = 0 | ❌ **先别改 HA**。核对 App 里登录的是不是同一个手机号；确认关 Wi-Fi 用 4G 时 App 能控制设备 |
| 报 `accessToken is illegal` | token 无效，重新登录 |

> ⚠️ 如果这里的 `customerId` 每次跑都不一样或明显是个短数字，说明你可能没走加密登录——
> 回到 3.3 / 3.4 检查。

### Step 2 · 判断品类与方案

记下输出里的**品类码**：

- `connector.device.type.airconditioner` / `.refrigerator` → 可先用现成集成试试
- `connector.device.type.washer` / `.dryer` / `.dishwasher` / 其他 → **用本文附带的自建集成**

本文附带的集成（`assets/hisense_aihome/`）**刻意不做品类白名单**：
识别不了的品类归为「其他」也照常建实体，避免以后又被"静默丢弃"。

> ⚠️ **一件必须做的事**：集成里的「程序名对照表」（`assets/hisense_aihome/programs.py`）
> 是**基于某个具体机型实测**生成的。你的机型不同，支持的程序编号和时长都会不同，
> 直接用会导致程序下拉里的名字对不上。请用自己的设备重新枚举：

```bash
# 只会下发"程序选择"命令，不会启动机器；结束时会把设备恢复原状
ALLOW_POWER_CYCLE=yes HISENSE_PHONE='<HISENSE_PHONE>' HISENSE_PASSWORD='<HISENSE_PASSWORD>' \
  node scripts/enumerate_modes.mjs
```

它会打印出可直接粘贴的 `PROGRAM_OPTIONS` 片段。程序**名字**要到 App 的「全部程序」列表里
用"时长"去匹配（**只填唯一匹配的，多个候选就留空**）。原理见 `references/protocol.md` 第 7.5 节。

> 这一步**只对洗衣机 / 干衣机这类有"程序选择"的家电有意义**。
> 洗碗机、净水器、除湿机等设备可能根本没有 `SetModes` 命令，直接跳过即可——
> 基础的状态传感器与开关不受影响，照常可用。

### Step 3 · 安装集成

1. 找到 HA 的**配置目录**（就是含 `configuration.yaml` 的那个目录）：

   | 部署方式 | 配置目录 |
   |---|---|
   | HA OS / Supervised | `/config` |
   | Docker | 启动容器时 `-v <宿主目录>:/config` 里那个**宿主目录** |
   | NAS（群晖 / 威联通 / 飞牛等） | 对应 Docker 共享文件夹 |

2. 把 `assets/hisense_aihome/` 整个目录复制到 `<配置目录>/custom_components/hisense_aihome/`  
   最终应形如：`<配置目录>/custom_components/hisense_aihome/manifest.json`

3. **重启 Home Assistant**（改动 `custom_components/` 下的代码必须重启，`reload_config_entry` 无效）

4. 重启后看日志，应出现：

   ```
   WARNING ... We found a custom integration hisense_aihome which has not been tested by Home Assistant.
   ```

   这个 WARNING 是正常的（自建集成都会有），**只要不是 ERROR 就说明加载成功**。

### Step 4 · 创建配置项

**方式 A：图形界面（推荐）**

设置 → 设备与服务 → 右下角「添加集成」→ 搜索「海信爱家」→ 依次填写：

1. 手机号 / 密码
2. 选择家庭（下拉里是 Step 1 查到的家庭）
3. 勾选要接入的设备

**方式 B：命令行（适合无界面 / 批量 / 复现）**

```bash
HA_URL='<HA_HOST>' HA_TOKEN='<HA_TOKEN>' \
HISENSE_PHONE='<HISENSE_PHONE>' HISENSE_PASSWORD='<HISENSE_PASSWORD>' \
  node scripts/ha_create_entry.mjs
```

它会自动走完「账号 → 家庭 → 设备」三步并创建配置项，最后打印 `entry_id`。

> ⚠️ `<HA_HOST>` 请填 **HA 真实可达的局域网地址**（`http://<IP>:8123`）。
> 如果 HA 跑在 Docker / NAS 容器里，在宿主机上写 `localhost` 会因为网络命名空间不同而连不上。

> 为什么不用图形界面也能创建：HA 2026.7 起 **WebSocket 已没有 `config_entries/flow` 命令**，
> 必须走 REST（脚本里已经这么实现）。

### Step 5 · 验证

见下一节的清单。**重点：不要只看 HA 界面，要绕过 HA 直读云端做交叉验证。**

---

## 5. 验证清单（逐条打勾）

### 5.1 服务端侧

- [ ] `POST /api/config/core/check_config` 返回 `{"result":"valid"}`
- [ ] 重启后日志里该集成**没有 ERROR**（有 "not been tested" WARNING 是正常的）
- [ ] `GET /api/config/config_entries/entry` 里能看到该配置项，且 `state` 为 `loaded`

### 5.2 实体侧

- [ ] 每台设备生成了**几十个实体**（本项目实测：洗衣机 47 个、干衣机 24 个；远不止"状态"一个）
- [ ] 关键实体状态**不是** `unknown` / `unavailable`
- [ ] 「状态」实体显示为「待机 / 运行中 / 已开机 / 离线」之一
- [ ] 「在线」二进制传感器为 `on`

### 5.3 闭环控制验证（**必做**）

HA 自身轮询有延迟（默认 120 秒），**只看 HA 界面会误判成"命令没生效"**。
正确做法是：用 HA 下发一条无害指令，然后**绕过 HA 直读云端**确认设备真的动了。

```bash
# 1) 让 HA 下发（示例：把某台洗衣机的洗涤温度设为 30）
curl -X POST '<HA_HOST>/api/services/number/set_value' \
  -H 'Authorization: Bearer <HA_TOKEN>' -H 'Content-Type: application/json' \
  -d '{"entity_id":"number.<...>","value":30}'

# 2) 等 5~10 秒，再用 scripts/probe.mjs 或手写请求读 device.states 里的对应字段
#    看到目标值确实变了，才算真正打通。
```

- [ ] 云端状态确实随指令变化
- [ ] 验证完把参数**改回原值**，避免给用户留下无意的设置

---

## 6. 故障速查表

| 症状 | 最可能的原因 | 处理 |
|---|---|---|
| 云端正查得到设备，但 HA 里 0 台 | 集成有品类白名单，把该品类静默丢弃了 | 换本文自建集成（无白名单） |
| 云端"有家庭、但 0 设备" | 你装的是走「智慧家」云的集成，而新品类在「爱家」云 | 换走爱家云的方案 |
| 自查脚本报 `errorCode 202012` | ① 密码不对 ② 账号没设过密码 ③ **密文算法写错（重复填充）** | 先按 3.4 用 openssl 交叉验证密文，再怀疑密码 |
| 登录"成功"但设备数恒为 0 | **踩了 3.3 的明文登录陷阱**，拿到的是假身份 | 改用加密登录 |
| 添加集成时提示认证失败 | 同上，或令牌过期 | 重新走 Step 4 |
| 集成在列表里但设备页空白 | 只勾选了部分设备，或家庭选错 | 删掉配置项重新添加，注意勾选设备 |
| 装了集成但「添加集成」搜不到 | 目录层级不对 / 没重启 HA | 确认路径是 `custom_components/<domain>/manifest.json`，然后重启 |
| `accessToken is illegal` | token 失效 | 重新登录 |
| `deviceNotFound` | 下发指令时 `partnerId` 传错 | 用设备列表里 `partner.id` 的真实值（本项目是它自带的值，**不是**示例里的固定值） |
| 改完代码不生效 | HA 只认进程重启 | 重启 HA（`reload` 不够） |
| 重启后集成报 ERROR | 自定义集成 import 报错 | 看 `GET /api/error_log` 里的 Traceback，多半是缺少依赖或语法问题 |

更详细的排查（含每个错误的完整报文样例）见 `references/troubleshooting.md`。

---

## 7. 凭据与隐私

**必须遵守**：

1. 账号密码**只从环境变量注入内存**，不写入任何文件、不出现在命令行文本、不写进日志或截图；
2. 分享排查结果前**一律脱敏**：手机号保留前 3 后 3（形如 `138***000`）、
   customerId 同样处理、deviceId 只留首尾；
3. HA 长期令牌等同密码，不要贴进聊天记录或 issue；
4. 本 SKILL 附带的脚本**全程只读**，不会下发任何控制指令（除 `ha_create_entry.mjs` 会创建配置项）。

---

## 8. 本 SKILL 文件清单

```
hisense-aihome-onboarding/
├── SKILL.md                      ← 你正在读的文件
├── references/
│   ├── protocol.md               ← 完整协议：登录 / 家庭 / 设备 / 状态 / 控制命令 与签名算法
│   └── troubleshooting.md        ← 逐条错误报文与排查（含两个陷阱的完整证据）
├── scripts/
│   ├── probe.mjs                 ← ① 账号设备自查（加密登录、输出脱敏、全程只读）
│   ├── enumerate_modes.mjs       ← ② 按自己的机型重新枚举程序编号（只发程序选择命令）
│   └── ha_create_entry.mjs       ← ③ 走完 HA 配置流程并创建配置项（REST，非 WebSocket）
└── assets/
    └── hisense_aihome/           ← 可直接安装的自建集成（无品类白名单，含读与控制）
```

### 使用建议顺序

1. 读第 2 章确认前提 → 2. 读第 3 章理解两个陷阱 → 3. 跑 `scripts/probe.mjs` → 4. 按 Step 2 重新生成程序表 →
5. 按 Step 3/4 安装并创建配置项 → 6. 按第 5 章清单验收。
遇到问题查第 6 章 → 再查 `references/troubleshooting.md`。

---

## 附录 · 打包分享前的检查清单

如果你要把这份 SKILL（或包含它的整个项目目录）转发给他人，建议先过一遍：

- [ ] **只分享 `hisense-aihome-onboarding/` 这一层目录**。它内部不含任何个人数据；
      项目里的其它目录（调试脚本、抓包结果、截图、配置备份）可能含真实信息，**不要一起打包**。
- [ ] 自查一遍：`grep -rniE '1[3-9][0-9]{9}|Bearer |accessToken' <待分享目录>`
- [ ] 确认没有 `.env` / `*.local` / 抓包导出的 JSON —— 这类文件常含真实设备 SN、MAC、
      经纬度、家庭名，是最容易漏掉的盲区。
- [ ] 若用 Git 分享，检查**历史提交**里有没有早期的未脱敏版本
      （`git log -p | grep -iE '1[3-9][0-9]{9}|Bearer '`）。
- [ ] 本文档里的示例输出**已全部替换为 mock 数据**；但你自己跑出来的报告
      （如 `probe_report.json`）要脱敏后再对外粘贴。

> 说明：本 SKILL 附带的脚本一律从**环境变量**读取凭据，源码中不含任何硬编码的账号、密码或地址，
> 可以直接分享；需要你留意的只是"运行产物"和"项目里的其它目录"。

### 关于协议常量的说明

集成与脚本里用到几个**应用级常量**（AES 密钥、签名密钥、占位 deviceId、`appKey` 等），
它们来自海信官方 App 的通信协议，也广泛存在于多个开源集成中，**不是个人凭据**。
海信若更新 App，这些常量可能失效——届时重新抓包即可，替换位置都在
`scripts/probe.mjs` 顶部和 `assets/hisense_aihome/const.py` 里，已集中放置便于维护。
