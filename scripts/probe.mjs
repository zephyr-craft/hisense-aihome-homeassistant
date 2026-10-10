#!/usr/bin/env node
/**
 * 海信账号 · 设备自查工具（只读）
 * ===============================================================
 * 用途：不依赖 Home Assistant，直接问海信云「这个账号下到底绑定了哪些设备」，
 *       用来判断 HA 里看不到设备的原因到底在账号侧、云端侧，还是集成侧。
 *
 * 用法：
 *   HISENSE_PHONE='<你的手机号>' HISENSE_PASSWORD='<你的密码>' node scripts/probe.mjs
 *
 * 安全：
 *   - 凭据只从环境变量读取，绝不写文件、绝不出现在输出里；
 *   - 输出中的 token / customerId / deviceId 等一律脱敏；
 *   - 全程只读，不下发任何控制指令。
 *
 * ⚠️ 本脚本**强制使用加密登录**。明文登录会被服务端放进一个"不校验密码"的旧分支，
 *    返回固定假身份，导致误判为"账号里没有设备"。详见 references/protocol.md 第 2.3 节。
 */
import crypto from 'node:crypto';
import fs from 'node:fs';

const PHONE = process.env.HISENSE_PHONE;
const PASSWORD = process.env.HISENSE_PASSWORD;
if (!PHONE || !PASSWORD) {
  console.error("缺少环境变量：HISENSE_PHONE / HISENSE_PASSWORD");
  console.error("用法：HISENSE_PHONE='<手机号>' HISENSE_PASSWORD='<密码>' node scripts/probe.mjs");
  process.exit(1);
}

// ---------------------------------------------------------------------------
// 应用级常量（来自海信官方 App 协议，非个人凭据；海信更新 App 后可能需要重新抓包替换）
// ---------------------------------------------------------------------------
const PORTAL_SECRET = 'MORZRbkuiWxjp+SM4vR_GxY4pZxLZ6rn';   // 32 字节
const AIHOME_SIGN_KEY = 'AOSj8JBr0IpUzv5w+hURR6W4oINsI4o5';
const APP_VERSION = '6.4.0.3';
const PLACEHOLDER_DEVICE_ID = '862fff02fffefff00000fffe53b30aa3fdb331c013166f31a6089802';

const md5b64 = (s, key) => crypto.createHash('md5').update(s + key, 'utf8').digest('base64');
const mask = (v) => (v == null ? v : String(v).length <= 6 ? '***' : String(v).slice(0, 3) + '***' + String(v).slice(-3));

// ⚠️ Node 的 createCipheriv 默认已自动做 PKCS7 填充，**不要再手动 pad**，
//    否则双重填充 → 密文错误 → 服务端返回 202012（看起来像"密码错"）。
const AES_KEY = Buffer.from(PORTAL_SECRET, 'ascii');
const AES_IV = Buffer.from(PORTAL_SECRET.slice(0, 16), 'ascii');
function encrypt(value) {
  const c = crypto.createCipheriv('aes-256-cbc', AES_KEY, AES_IV);
  return Buffer.concat([c.update(Buffer.from(String(value), 'utf8')), c.final()]).toString('base64');
}

// ---------------------------------------------------------------------------
// 1) 登录
// ---------------------------------------------------------------------------
async function login() {
  const body = JSON.stringify({
    loginName: encrypt(PHONE),
    signature: encrypt(PASSWORD),
    serverCode: '9501',
    distributeId: '2001',
    termType: 2,
  });
  const params = new URLSearchParams({
    lastUpdateTime: '0', version: '1.0', deviceType: '2', appType: '100',
    versionCode: '101', adaptertRank: '720', _: String(Date.now()),
  });
  const r = await fetch(`https://portal-account.hismarttv.com/mobile/se/signon?${params}`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json; charset=UTF-8',
      appKey: 'commonweb',
      'X-Sign-For': md5b64(body, PORTAL_SECRET),
    },
    body,
  });
  const j = await r.json().catch(() => ({}));
  const d = j.data || {};
  if (d.resultCode !== 0) {
    const code = d.errorCode;
    if (String(code) === '202012') {
      throw new Error(
        '海信账号服务拒绝了这组凭据（errorCode=202012）。请依次确认：\n' +
        '   ① 你实现的密文算法是否正确（Node 不要重复做 PKCS7 填充）；\n' +
        '   ② 密码是否为 App 当前使用的密码；\n' +
        '   ③ 该账号是否用「手机号+密码」登录 —— 若平时用短信验证码或一键登录，\n' +
        '      可能从未设置过密码，需要先在 App 里设置一个。'
      );
    }
    throw new Error(`登录失败：${d.errorDesc || '未知'}（errorCode=${code}）`);
  }
  const ti = d.tokenInfo || {};
  return { token: ti.token, customerId: String(ti.customerId), subscriberId: String(ti.subscriberId || '') };
}

// ---------------------------------------------------------------------------
// 2) 爱家侧接口
// ---------------------------------------------------------------------------
async function aihome(path, token, payload) {
  const body = JSON.stringify({
    deviceId: PLACEHOLDER_DEVICE_ID,
    appType: '2',
    appVersion: APP_VERSION,
    header: { messageId: crypto.randomUUID() },
    accessToken: token,
    payload,
  });
  const r = await fetch('https://iot-aihome.hismarttv.com' + path, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json; charset=utf-8',
      'User-Agent': `JHKMain/${APP_VERSION} (iPhone; iOS 18.0; Scale/3.00)`,
      'X_REAL_HOST': '220.243.140.228',
      'X-Sign-For': md5b64(body, AIHOME_SIGN_KEY),
    },
    body,
  });
  return r.json().catch(() => ({}));
}

// ---------------------------------------------------------------------------
// 3) 智慧家侧家庭列表（用于对照判断设备在哪套云）
// ---------------------------------------------------------------------------
async function wgHomes(token) {
  const params = new URLSearchParams({
    sign: '', languageId: '0', version: '8.0', accessToken: token,
    timezone: '28800', format: '1', timeStamp: String(Date.now()),
  });
  const r = await fetch(`https://api-wg.hismarttv.com/wg/dm/getHomeList?${params}`, {
    headers: { Host: 'api.wg.hismarttv.com', 'User-Agent': 'okhttp/4.10.0', 'Accept-Encoding': 'gzip' },
  });
  const j = await r.json().catch(() => ({}));
  return ((j.response || {}).homeList) || [];
}

// ===========================================================================
// 主流程
// ===========================================================================
const report = { generatedAt: new Date().toISOString(), account: mask(PHONE) };

const auth = await login();
report.customer_id = mask(auth.customerId);
console.log(`✅ 登录成功  账号 ${report.account}  customerId ${report.customer_id}`);

// --- 爱家侧 ---
const homeRes = await aihome('/4.0/iot/home/list', auth.token, {});
const aiHomes = (homeRes.payload || {}).homes || [];
console.log(`   海信爱家 家庭数：${aiHomes.length}`);

const devRes = await aihome('/4.0/iot/devices/list', auth.token, {
  withMultiSplit: true, customerId: auth.customerId, withState: true, sourceType: 20, whitelist: 1,
});
const devices = (devRes.payload || {}).devices || [];
console.log(`   海信爱家 设备数：${devices.length}`);

const catCount = {};
for (const d of devices) {
  const p = d.product || {};
  const cat = d.categoryCode || '(无品类码)';
  catCount[cat] = (catCount[cat] || 0) + 1;
  console.log(`     · 昵称=${d.nickname || d.deviceName || '?'}  品类码=${cat}  型号=${p.code || p.name || '?'}  房间=${(d.room || {}).name || '?'}`);
}

// --- 智慧家侧（对照）---
try {
  const wg = await wgHomes(auth.token);
  console.log(`   海信智慧家 家庭数：${wg.length}`);
  report.legacy_homes = wg.map((h) => ({ home_name: h.homeName, address: h.address }));
} catch (e) {
  console.log(`   海信智慧家 查询失败：${e.message}`);
}

report.aihome_homes = aiHomes.map((h) => ({ id: mask(h.id || h.homeId), name: h.name || h.homeName }));
report.aihome_devices = devices.map((d) => ({
  nickname: d.nickname || d.deviceName,
  category_code: d.categoryCode,
  product_code: (d.product || {}).code,
  feature_code: (d.product || {}).featureCode,
  room: (d.room || {}).name || null,
  device_id: mask(d.deviceId),
  state_field_count: Object.keys(d.states || {}).length,
}));

// --- 判定 ---
console.log('\n──────── 判定 ────────');
if (devices.length === 0) {
  console.log('❗ 云端 0 台设备。请按顺序排查：');
  console.log('   1) 用明显错误的密码再跑一次：若仍返回成功且 customerId 不变，');
  console.log('      → 说明你走了「明文登录」的旧分支，拿到的是假身份（不是你的账号）。');
  console.log('   2) 核对 App 里登录的绑定手机号是否就是这个号。');
  console.log('   3) 关掉手机 Wi-Fi、只用 4G，确认 App 仍能控制设备 —— 能控制就说明设备确实在云上。');
} else {
  console.log(`✅ 云端共 ${devices.length} 台设备，可以接入 HA。`);
  console.log('   品类分布：' + Object.entries(catCount).map(([k, v]) => `${k}×${v}`).join('，'));
  console.log('');
  console.log('   下一步：');
  console.log('   · 若品类码是 .airconditioner / .refrigerator，可优先尝试现成集成；');
  console.log('   · 其他品类（.washer / .dryer / …）请使用本 SKILL 附带的集成（无品类白名单）。');
}

const outFile = 'probe_report.json';
fs.writeFileSync(outFile, JSON.stringify(report, null, 2));
console.log(`\n脱敏报告已写入 ${outFile}`);
