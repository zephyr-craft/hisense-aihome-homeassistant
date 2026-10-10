#!/usr/bin/env node
/**
 * 通过 Home Assistant REST API 走完「海信爱家」配置流程并创建配置项
 * ===============================================================
 * 用途：在没有图形界面 / 需要可复现 / 需要批量创建时，用脚本完成集成的添加。
 *
 * 用法：
 *   HA_URL='http://<HA_HOST>:8123' HA_TOKEN='<长期访问令牌>' \
 *   HISENSE_PHONE='<手机号>' HISENSE_PASSWORD='<密码>' \
 *     node scripts/ha_create_entry.mjs
 *
 * 安全：凭据只走环境变量；输出中设备 ID 一律脱敏。
 *
 * 为什么要用 REST 而不是 WebSocket：
 *   HA 2026.7 起 WebSocket 已移除 `config_entries/flow` 命令（会返回 unknown_command），
 *   驱动配置流程必须走 REST。
 */
const HA = (process.env.HA_URL || '').replace(/\/+$/, '');
const TOKEN = process.env.HA_TOKEN;
const PHONE = process.env.HISENSE_PHONE;
const PASSWORD = process.env.HISENSE_PASSWORD;
const HANDLER = process.env.HANDLER || 'hisense_aihome';

for (const [k, v] of [['HA_URL', HA], ['HA_TOKEN', TOKEN], ['HISENSE_PHONE', PHONE], ['HISENSE_PASSWORD', PASSWORD]]) {
  if (!v) {
    console.error(`缺少环境变量：${k}`);
    console.error("用法：HA_URL='http://<HA_HOST>:8123' HA_TOKEN='<令牌>' HISENSE_PHONE='<手机号>' HISENSE_PASSWORD='<密码>' node scripts/ha_create_entry.mjs");
    process.exit(1);
  }
}

const H = { Authorization: `Bearer ${TOKEN}`, 'Content-Type': 'application/json' };
const mask = (v) => (v == null ? v : String(v).length <= 6 ? '***' : String(v).slice(0, 6) + '***' + String(v).slice(-3));

async function api(path, method = 'GET', body) {
  const r = await fetch(HA + path, { method, headers: H, body: body ? JSON.stringify(body) : undefined });
  const t = await r.text();
  let j;
  try { j = JSON.parse(t); } catch { j = { raw: t }; }
  if (!r.ok) throw new Error(`${method} ${path} -> HTTP ${r.status} ${t.slice(0, 300)}`);
  return j;
}

/** multi_select 的 options 是 **对象** {id: label}，不是数组——别直接 for...of */
function optionsOf(schema, fieldName) {
  const field = (schema || []).find((f) => f.name === fieldName) || (schema || [])[0] || {};
  const raw = field.options || field.schema || {};
  return Array.isArray(raw) ? raw : Object.entries(raw);
}

console.log('1) 启动配置流程…');
const start = await api('/api/config/config_entries/flow', 'POST', { handler: HANDLER });
if (!start.flow_id) throw new Error('未拿到 flow_id：' + JSON.stringify(start).slice(0, 300));
const flow = start.flow_id;
console.log(`   step=${start.step_id}  flow=${mask(flow)}`);

console.log('2) 提交账号密码…');
const s2 = await api(`/api/config/config_entries/flow/${flow}`, 'POST', { username: PHONE, password: PASSWORD });
console.log(`   step=${s2.step_id}  errors=${JSON.stringify(s2.errors || {})}`);
if (s2.errors && Object.keys(s2.errors).length) {
  console.error('\n❌ 凭据被拒。排查顺序：');
  console.error('   ① 密码是否为 App 当前密码；② 该账号是否设置过密码；');
  console.error('   ③ 看 HA 日志 GET /api/error_log 里的 errorCode（202012 = 密码不被接受）。');
  process.exit(1);
}

let step = s2;
if (step.step_id === 'home') {
  const homes = optionsOf(step.data_schema, 'home_id');
  if (!homes.length) {
    console.error('❌ 家庭列表为空。若你的账号是新品类用户，可能智慧家侧没有家庭——');
    console.error('   请确认所用集成版本是否支持"无家庭也能列出设备"。');
    process.exit(1);
  }
  console.log('   可选家庭：' + homes.map(([id, label]) => `${label}`).join('、'));
  step = await api(`/api/config/config_entries/flow/${flow}`, 'POST', { home_id: homes[0][0] });
  console.log(`3) 已提交家庭 -> step=${step.step_id}  errors=${JSON.stringify(step.errors || {})}`);
}

if (step.step_id === 'device') {
  const devices = optionsOf(step.data_schema, 'device_ids');
  console.log('   发现设备：');
  for (const [id, label] of devices) console.log(`     - ${label}   <${mask(id)}>`);
  if (!devices.length) {
    console.error('❌ 设备列表为空。请先运行 scripts/probe.mjs 确认云端确实有设备。');
    process.exit(1);
  }
  const ids = devices.map((o) => o[0]);
  const done = await api(`/api/config/config_entries/flow/${flow}`, 'POST', { device_ids: ids });
  console.log(`4) 已提交设备 -> type=${done.type}  entry_id=${done.result && done.result.entry_id}`);
  console.log('\n✅ 配置项已创建。请到 HA「设置 → 设备与服务」查看，或在界面上核对实体。');
} else {
  console.log(`\n提示：流程停在 step=${step.step_id}，请按该步的 data_schema 手工补齐字段后重试。`);
  console.log(JSON.stringify(step.data_schema, null, 2).slice(0, 800));
}
