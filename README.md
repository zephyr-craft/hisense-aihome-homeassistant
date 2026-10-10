# 海信家电接入 Home Assistant

把海信（Hisense）**洗衣机 / 干衣机 / 洗碗机等新品类家电**接入 Home Assistant 的完整可复现流程。

> 起因：网上现成的海信集成只支持「空调 + 冰箱」，洗衣机、干衣机这类新品类会被代码静默丢弃；
> 而且它们查的是「海信智慧家」云，新品类却在「海信爱家」云上——两套云数据不互通。
> 这个仓库把踩过的坑和走通的路径整理成一套可直接照做的步骤。

## 这个项目包含什么

| 内容 | 说明 |
|---|---|
| **[SKILL.md](SKILL.md)** | 主文档：环境前提 → 判断品类 → 装集成 → 建配置项 → 验证，共 5 步 |
| [references/protocol.md](references/protocol.md) | 完整协议：登录 / 家庭 / 设备 / 状态 / 控制命令 / 签名算法 |
| [references/troubleshooting.md](references/troubleshooting.md) | 分阶段故障手册，附实测错误报文，看到能对号入座 |
| [scripts/probe.mjs](scripts/probe.mjs) | 账号设备自查（只读、凭据走环境变量、输出脱敏） |
| [scripts/enumerate_modes.mjs](scripts/enumerate_modes.mjs) | 按你自己的机型重新枚举程序编号 |
| [scripts/ha_create_entry.mjs](scripts/ha_create_entry.mjs) | 走 HA 的 REST 配置流程，自动创建配置项 |
| [assets/hisense_aihome/](assets/hisense_aihome/) | 可直接安装的自建集成（**无品类白名单**，含状态与控制） |

## 两个最值得一看的坑

这两条都是"看起来成功、结果却是错的"类型，最容易让人白折腾一整晚：

### 1. 明文登录会返回一个「假身份」

海信登录接口如果 `loginName` 传**明文**，服务端会走进一个旧分支，**完全不校验密码**：

| 输入 | 返回 |
|---|---|
| 正确密码 / 错误密码 / **空密码** / **不存在的手机号** | 全都是 `resultCode=0` + **同一个固定 customerId** |

这个 token 能通过后续接口的校验，看起来一切正常——但它是默认身份，拿它查云端永远是 0 台设备。
很多人因此得出「我的账号里没有设备」的错误结论，然后反复重绑设备。

**规避：只走加密登录。**

### 2. Node.js 的 AES 会自动填充，别再手动 pad

加密是 AES-256-CBC + PKCS7。Node 的 `crypto.createCipheriv()` **默认已经自动做了 PKCS7 填充**，
如果按其他语言的写法再手动补一次，就会双重填充 → 密文错误 → 服务端返回 `errorCode 202012`
（提示"用户名或密码错误"），极易被误判成密码不对。

Python 的 `cryptography` 则**不会**自动填充，必须显式 pad——所以同样的逻辑在 Python 侧是对的，
这也是"HA 里登录得进去、脚本却报 202012"的原因。

文档里附了 `openssl` 交叉验证命令，可以直接比对密文。

## 快速开始

```bash
# 1) 先确认云端到底有哪些设备（只读，不发任何控制指令）
HISENSE_PHONE='<你的手机号>' HISENSE_PASSWORD='<你的密码>' \
  node scripts/probe.mjs

# 2) 把 assets/hisense_aihome/ 复制到 <HA配置目录>/custom_components/hisense_aihome/，重启 HA

# 3) 在 HA 界面「添加集成」里搜索「海信爱家」，或在命令行走 REST 流程
HA_URL='http://<HA的局域网IP>:8123' HA_TOKEN='<长期访问令牌>' \
HISENSE_PHONE='<你的手机号>' HISENSE_PASSWORD='<你的密码>' \
  node scripts/ha_create_entry.mjs
```

脚本只用 **Node.js 18+ 的原生能力**（内置 `crypto` 与全局 `fetch`），无需 `npm install`。

详细步骤、验证清单与排错请看 **[SKILL.md](SKILL.md)**。

## 验证做了什么

- 实机跑通：洗衣机与干衣机接入后生成 70+ 个实体（状态、参数、能耗、程序选择、控制按钮）
- 控制闭环：HA 下发指令 → **绕过 HA 直读云端**确认设备状态确实变化（只看 HA 界面会因轮询延迟误判）
- 命令集是用"错误语义"探测出来的：`Unsupported command` = 名字错、`Missing required action param` = 参数名错、
  `conflictCommand` = 名字对但设备状态拒绝——不用抓包也能摸清命令表

## 免责声明

- 本项目通过**非官方、逆向得到**的接口与海信云端通信，海信随时可能修改协议导致失效；
- 文中所述的应用级常量（AES 密钥、签名密钥、占位 deviceId 等）来自官方 App 的通信协议，
  也公开存在于其他开源项目中，**不属于个人凭据**，但请知悉其可能随 App 更新而变化；
- 项目中的控制能力会**真实操作你的家电**（例如"启动"会真的启动设备）。
  请在确认滚筒内情况后使用，风险自负；
- 本项目与海信（Hisense）官方无任何关联。

## 作为 WorkBuddy / Claude Skill 使用

本仓库根目录的 `SKILL.md` 带 YAML frontmatter，可直接作为 Skill 使用：

```bash
git clone https://github.com/910957869/hisense-aihome-homeassistant \
    ~/.workbuddy/skills/hisense-aihome-onboarding
```

## License

见 [LICENSE](LICENSE)。
