#!/usr/bin/env node
/**
 * 枚举本机支持的程序编号，并输出可直接粘贴的 Python 数据表
 * ===============================================================
 * 用途：`assets/hisense_aihome/programs.py` 里的程序表是**基于某个机型实测**生成的。
 *       如果你的机型不同，需要用自己的设备重新枚举一遍，否则程序下拉里的名字/编号会对不上。
 *
 * 安全须知（务必先读）：
 *   - 本脚本会**把设备开机**（海信云端对关机态设备会把大部分命令误报为 notSupported，
 *     所以枚举必须在开机态做），结束时会把设备恢复关机；
 *   - 全程**只下发程序选择命令 `SetModes`**，不发任何「启动/Start」类命令，
 *     因此不会真的开始洗衣/烘干；
 *   - 即便如此，也请确认滚筒内没有不宜被选程序的衣物。同意后再带上
 *     `ALLOW_POWER_CYCLE=yes` 运行，否则脚本会拒绝执行。
 *
 * 用法：
 *   ALLOW_POWER_CYCLE=yes \
 *   HISENSE_PHONE='<手机号>' HISENSE_PASSWORD='<密码>' \
 *     node scripts/enumerate_modes.mjs [型号关键词，如 washer / dryer]
 *
 * 拿到输出后：
 *   1) 把 PROGRAM_OPTIONS 对应的字典粘进 assets/hisense_aihome/programs.py；
 *   2) 打开 App 的「全部程序」列表，用每个程序卡片上显示的分钟数去匹配本表的时长字段，
 *      **只填唯一匹配的名字**，多个候选就留空（宁可不填也不要猜）；
 *   3) 提示：设备详情里的 labels.common_prg 是"首页常用"程序，**顺序与 App 展示顺序一致**，
 *      可以先拿它对上第一批名字。
 */
import crypto from 'node:crypto';

const PHONE = process.env.HISENSE_PHONE;
const PASSWORD = process.env.HISENSE_PASSWORD;
const ALLOW = process.env.ALLOW_POWER_CYCLE === 'yes';
const FILTER = (process.argv[2] || '').toLowerCase();
const MAX_MODE = Number(process.env.MAX_MODE || 60);

if (!PHONE || !PASSWORD) { console.error('缺少环境变量：HISENSE_PHONE / HISENSE_PASSWORD'); process.exit(1); }
if (!ALLOW) {
  console.error('本脚本会把设备开机以完成枚举。确认无误后，加上 ALLOW_POWER_CYCLE=yes 重新运行。');
  process.exit(1);
}

const PORTAL_SECRET = 'MORZRbkuiWxjp+SM4vR_GxY4pZxLZ6rn';
const AIHOME_SIGN_KEY = 'AOSj8JBr0IpUzv5w+hURR6W4oINsI4o5';
const APP_VERSION = '6.4.0.3';
const PLACEHOLDER_DEVICE_ID = '862fff02fffefff00000fffe53b30aa3fdb331c013166f31a6089802';
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const md5b64 = (s, k) => crypto.createHash('md5').update(s + k, 'utf8').digest('base64');
const mask = (v) => (v == null ? v : String(v).length <= 6 ? '***' : String(v).slice(0, 6) + '***' + String(v).slice(-3));

const AES_KEY = Buffer.from(PORTAL_SECRET, 'ascii');
const AES_IV = Buffer.from(PORTAL_SECRET.slice(0, 16), 'ascii');
const encrypt = (v) => {
  // ⚠️ Node 的 createCipheriv 默认已自动 PKCS7 填充，不要再手动 pad
  const c = crypto.createCipheriv('aes-256-cbc', AES_KEY, AES_IV);
  return Buffer.concat([c.update(Buffer.from(String(v), 'utf8')), c.final()]).toString('base64');
};

async function login() {
  const body = JSON.stringify({ loginName: encrypt(PHONE), signature: encrypt(PASSWORD), serverCode: '9501', distributeId: '2001', termType: 2 });
  const params = new URLSearchParams({ lastUpdateTime: '0', version: '1.0', deviceType: '2', appType: '100', versionCode: '101', adaptertRank: '720', _: String(Date.now()) });
  const r = await fetch(`https://portal-account.hismarttv.com/mobile/se/signon?${params}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json; charset=UTF-8', appKey: 'commonweb', 'X-Sign-For': md5b64(body, PORTAL_SECRET) },
    body,
  });
  const j = await r.json().catch(() => ({}));
  const d = j.data || {};
  if (d.resultCode !== 0) throw new Error(`登录失败：${d.errorDesc || '未知'}（errorCode=${d.errorCode}）`);
  return { token: d.tokenInfo.token, customerId: String(d.tokenInfo.customerId) };
}

async function post(path, token, payload, signKey = AIHOME_SIGN_KEY) {
  const body = JSON.stringify({ deviceId: PLACEHOLDER_DEVICE_ID, appType: '2', appVersion: APP_VERSION, header: { messageId: crypto.randomUUID() }, accessToken: token, payload });
  const r = await fetch('https://iot-aihome.hismarttv.com' + path, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json; charset=utf-8', 'User-Agent': `JHKMain/${APP_VERSION} (iPhone; iOS 18.0; Scale/3.00)`, 'X_REAL_HOST': '220.243.140.228', 'X-Sign-For': md5b64(body, signKey) },
    body,
  });
  return r.json().catch(() => ({}));
}

const auth = await login();
console.log(`✅ 登录成功  账号 ${mask(PHONE)}  customerId ${mask(auth.customerId)}`);

const listDevices = async () => {
  const j = await post('/4.0/iot/devices/list', auth.token, { withMultiSplit: true, customerId: auth.customerId, withState: true, sourceType: 20, whitelist: 1 });
  return (j.payload || {}).devices || [];
};

const all = await listDevices();
const targets = FILTER ? all.filter((d) => `${d.categoryCode} ${(d.product || {}).code} ${d.nickname}`.toLowerCase().includes(FILTER)) : all;
if (!targets.length) { console.error('没有匹配到设备。现有设备：'); all.forEach((d) => console.error(`  - ${d.nickname}  ${d.categoryCode}`)); process.exit(1); }

async function setMode(dev, partnerId, mode) {
  const body = JSON.stringify({
    header: { messageId: crypto.randomUUID() }, deviceId: PLACEHOLDER_DEVICE_ID, appVersion: APP_VERSION,
    payload: { deviceId: dev.deviceId, sourceType: '20', exclusionFlag: 1, customerId: auth.customerId, partnerId,
               actions: [{ command: 'connector.device.command.SetModes', params: { modes: { value: mode } } }] },
    accessToken: auth.token, appType: '2', sourceName: 'smartlifeAppH5',
  });
  const r = await fetch('https://iot-aihome.hismarttv.com/4.0/iot/devices/execute', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json; charset=utf-8', 'User-Agent': `JHKMain/${APP_VERSION} (iPhone; iOS 18.0; Scale/3.00)`, 'X_REAL_HOST': '220.243.140.228', 'X-Sign-For': md5b64(body, AIHOME_SIGN_KEY) },
    body,
  });
  const j = await r.json().catch(() => ({}));
  return (j.payload || {}).status;
}
async function setPower(dev, partnerId, on) {
  const body = JSON.stringify({
    header: { messageId: crypto.randomUUID() }, deviceId: PLACEHOLDER_DEVICE_ID, appVersion: APP_VERSION,
    payload: { deviceId: dev.deviceId, sourceType: '20', exclusionFlag: 1, customerId: auth.customerId, partnerId,
               actions: [{ command: 'connector.device.command.Power', params: { onAndOff: { code: on ? 'On' : 'Off' } } }] },
    accessToken: auth.token, appType: '2', sourceName: 'smartlifeApp',   // ⚠️ 电源必须用 smartlifeApp
  });
  await fetch('https://iot-aihome.hismarttv.com/4.0/iot/devices/execute', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json; charset=utf-8', 'User-Agent': `JHKMain/${APP_VERSION} (iPhone; iOS 18.0; Scale/3.00)`, 'X_REAL_HOST': '220.243.140.228', 'X-Sign-For': md5b64(body, AIHOME_SIGN_KEY) },
    body,
  });
}

for (const dev of targets) {
  const partnerId = (dev.partner || {}).id || '1001';
  const isDryer = /dryer|干衣|烘干/.test(`${dev.categoryCode} ${dev.nickname}`);
  const st0 = (await listDevices()).find((d) => d.deviceId === dev.deviceId).states || {};
  const wasOn = st0.powerStatus === '1';
  const origMode = st0.workMode;

  console.log(`\n════ ${dev.nickname || (dev.product || {}).code}  ${dev.categoryCode} ════`);
  console.log(`   起始 powerStatus=${st0.powerStatus} workMode=${origMode}`);

  if (!wasOn) {
    console.log('   开机中…（枚举必须在开机态进行，否则命令会被误报为 notSupported）');
    await setPower(dev, partnerId, true);
    for (let i = 0; i < 12; i++) { await sleep(3000); const s = (await listDevices()).find((d) => d.deviceId === dev.deviceId).states || {}; if (s.powerStatus === '1') break; }
    await sleep(4000);
  }

  const rows = [];
  for (let m = 1; m <= MAX_MODE; m++) {
    const r = await setMode(dev, partnerId, m);
    if (r !== 'SUCCESS') continue;
    await sleep(3000);
    const s = (await listDevices()).find((d) => d.deviceId === dev.deviceId).states || {};
    const row = isDryer
      ? { m, workMode: s.workMode, min: s.drySetTime, t: s.dryTemperature, lv: s.dryLevel }
      : { m, workMode: s.workMode, min: s.totalRunTime, t: s.washTemperature, rinse: s.rinsingFrequency, spin: s.dehydrationSpeed };
    rows.push(row);
    console.log(`   modes=${String(m).padStart(2)}  workMode=${String(row.workMode).padStart(2)}  ` +
      (isDryer ? `设定=${String(row.min).padEnd(5)} 温档=${row.t} 干度=${row.lv}` : `总时长=${String(row.min).padEnd(5)} 温度=${row.t} 漂洗=${row.rinse} 脱水=${row.spin}`));
  }

  console.log(`\n   ── 可直接粘贴进 programs.py 的 PROGRAM_OPTIONS["${isDryer ? '干衣机' : '洗衣机'}"] ──`);
  for (const r of rows) {
    const label = isDryer
      ? `${r.min}分·温档${r.t}·干度${r.lv}`
      : `${r.min}分·${r.t}℃·漂${r.rinse}·${r.spin}转`;
    console.log(`        ${r.m}: "${label}",`);
  }

  // 还原
  if (origMode !== undefined) await setMode(dev, partnerId, Number(origMode));
  await sleep(2500);
  if (!wasOn) { await setPower(dev, partnerId, false); await sleep(6000); }
  const fin = (await listDevices()).find((d) => d.deviceId === dev.deviceId).states || {};
  console.log(`   已还原：powerStatus=${fin.powerStatus} workMode=${fin.workMode}`);
}

console.log('\n完成。记得对照 App「全部程序」列表把名字填进 PROGRAM_NAMES（只填唯一匹配的）。');
