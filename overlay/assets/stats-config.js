/* 匿名使用统计 · 独立可插拔适配层（自用/上架通用）
 * ---------------------------------------------------------------
 * 设计约束：
 *  1. 不改动上游任何页面与脚本。上游 assets/stats.js 只认 window.CNM_STATS，
 *     本文件通过 onEvent 接管事件，endpoint 保持为空，避免上游发出未经治理的请求。
 *  2. 无 window.CNM_STATS_CONFIG（构建时可选注入的 stats-endpoint.js）时 = 零请求。
 *  3. 【授权条件 4】默认关闭，且锁死在代码层。开启只有两条用户显式动作的入口：
 *     ① 安装向导中选择「开启」（cmd/install_callback / cmd/upgrade_callback 据此
 *     把本文件的 INSTALL_DEFAULT 锚点由 false 烧写为 true）；
 *     ② 「关于 / 数据来源」页勾选（显式写 localStorage '1'）。
 *     localStorage 显式值（'1' 开 / '0' 关）永远优先于安装向导选择；两者皆无 = 关闭。
 *     配置文件里没有任何「默认开启」开关，构建参数、环境变量、URL 参数都无法绕过。
 *     关闭后 = 零请求、零定时器、零存储写入。
 *  4. 【授权条件 4】只上报 install / open / update 三类匿名事件；页面内交互细节
 *     （看过哪一页、诊断是否完成、停留时长等）一律不上报；不采集答题内容、
 *     孩子档案、错题数据或任何可识别个人信息。
 *  5. 服务端不收 IP/UA/机器码原文；本机标识经 SHA-256(app_salt‖UUID) 取前 32 位。
 *
 *  变更统计默认态、事件类型或上报方式，按授权条件 5 须事先重新取得原作者书面确认。
 *
 * 本文件属于壳工程自研代码（MIT，见工程 LICENSE），不属于上游 CC BY-NC 内容。
 */
(function () {
  'use strict';

  var CFG = window.CNM_STATS_CONFIG || null;
  var LS_ENABLED = 'cnmath.stats.enabled';   // 用户开关
  var LS_UUID = 'cnmath.stats.uuid';         // 随机设备标识（本站专用）
  var LS_VER = 'cnmath.stats.version';       // 上次上报的版本
  var SALT_JOIN = '\u2016';                  // ‖ 与 appstats 接入规范 §2 一致

  /* 安装向导选择锚点：出厂恒 false = 授权条件 4 的「默认关闭」。
   * 仅 cmd/install_callback、cmd/upgrade_callback 在用户于安装向导显式选择
   * 「开启」后，把本行的 false 烧写为 true（sed 锚点，勿改本行格式）。
   * 配置文件（stats-endpoint.js）无权读写此值。 */
  var INSTALL_DEFAULT = false;  // 安装向导选择（烧写锚点：false→true）

  /* 开启条件（授权条件 4，2026-11-16 书面确认）：默认关闭，仅用户主动开启后上报。
   * 优先级：localStorage 显式 '1'（开启）> 显式 '0'（关闭）> 安装向导选择 > 关。
   * 不读配置默认值、不读 URL、不读环境变量。 */
  function enabled() {
    if (!CFG || !CFG.endpoint || !CFG.appId || !CFG.appSalt) return false;
    try {
      var v = localStorage.getItem(LS_ENABLED);
      if (v === '1') return true;
      if (v === '0') return false;
    } catch (e) { /* 隐私模式：回落安装向导选择 */ }
    return INSTALL_DEFAULT === true;
  }

  function setEnabled(on) {
    try { localStorage.setItem(LS_ENABLED, on ? '1' : '0'); } catch (e) { /* 隐私模式 */ }
  }
  window.cnmathStatsSetEnabled = setEnabled;
  window.cnmathStatsIsEnabled = enabled;

  function uuid() {
    try {
      var u = localStorage.getItem(LS_UUID);
      if (!u) {
        var b = new Uint8Array(16);
        (window.crypto || window.msCrypto).getRandomValues(b);
        u = Array.prototype.map.call(b, function (x) { return ('0' + x.toString(16)).slice(-2); }).join('');
        localStorage.setItem(LS_UUID, u);
      }
      return u;
    } catch (e) { return null; }
  }

  function hex32(buf) {
    return Array.prototype.map.call(new Uint8Array(buf), function (x) {
      return ('0' + x.toString(16)).slice(-2);
    }).join('').slice(0, 32);
  }

  function today() {
    var d = new Date();
    return d.getFullYear() + '-' + ('0' + (d.getMonth() + 1)).slice(-2) + '-' + ('0' + d.getDate()).slice(-2);
  }

  var queue = [];
  var machineHashPromise = null;

  function getMachineHash() {
    if (machineHashPromise) return machineHashPromise;
    var code = uuid();
    if (!code || !window.crypto || !window.crypto.subtle || !window.TextEncoder) {
      machineHashPromise = Promise.resolve(null);
      return machineHashPromise;
    }
    machineHashPromise = window.crypto.subtle
      .digest('SHA-256', new TextEncoder().encode(CFG.appSalt + SALT_JOIN + code))
      .then(hex32)
      .catch(function () { return null; });
    return machineHashPromise;
  }

  function flush() {
    if (!queue.length || !enabled()) { queue = []; return; }
    var events = queue.slice(0, 50);
    queue = [];
    getMachineHash().then(function (mh) {
      if (!mh || !enabled()) return;
      var day = today();
      var payload = {
        app_id: CFG.appId,
        events: events.map(function (e) {
          var o = { type: e.type, machine_hash: mh, version: CFG.version || '0.0.0', client_date: day };
          if (e.type === 'update' && e.fromVersion) o.from_version = e.fromVersion;
          return o;
        })
      };
      try {
        if (navigator.sendBeacon) {
          navigator.sendBeacon(CFG.endpoint, new Blob([JSON.stringify(payload)], { type: 'application/json' }));
        } else {
          fetch(CFG.endpoint, { method: 'POST', headers: { 'Content-Type': 'application/json' },
                                body: JSON.stringify(payload), keepalive: true, mode: 'cors' })
            .catch(function () { /* 忽略：统计不可影响主功能 */ });
        }
      } catch (e) { /* ignore */ }
    });
  }

  function push(type, fromVersion) {
    if (!enabled()) return;
    queue.push({ type: type, fromVersion: fromVersion });
    if (queue.length >= 50) flush();
    else if (!flush._t) {
      flush._t = setTimeout(function () { flush._t = null; flush(); }, 800);
    }
  }

  var sentOpen = false;

  function boot() {
    if (!enabled()) return;
    var ver = CFG.version || '0.0.0';
    var last = null;
    try { last = localStorage.getItem(LS_VER); } catch (e) { /* ignore */ }
    if (!last) push('install');
    else if (last !== ver) push('update', last);
    try { localStorage.setItem(LS_VER, ver); } catch (e) { /* ignore */ }
    /* open 交给上游 pageview 事件触发；1.5s 内没收到则自行兜底，
     * 保证「只引用了本适配层、没加载上游 stats.js」的页面也能记到活跃。 */
    setTimeout(function () {
      if (!sentOpen && enabled()) { sentOpen = true; push('open'); }
    }, 1500);
  }

  /* 上游事件 → appstats 三种类型。其余事件（含任何带 props 的业务事件）一律丢弃，
   * 避免把页面路径、诊断结果、答题内容带出本机。 */
  function onUpstreamEvent(ev) {
    if (!enabled() || !ev || !ev.event) return;
    if (ev.event === 'appinstalled') push('install');
    else if (ev.event === 'pageview' || ev.event === 'return_visit' || ev.event === 'pwa_launch') {
      if (!sentOpen) { sentOpen = true; push('open'); }   // 服务端按 (app, machine, day) 去重
    }
  }

  window.CNM_STATS = {
    cloudflareToken: '',     // 禁用第三方信标
    endpoint: '',            // 禁用上游原始上报
    onEvent: onUpstreamEvent
  };

  /* 「关于 / 数据来源」页只读写开关，不产生任何事件。 */
  if (window.CNM_STATS_NO_BOOT) return;
  window.addEventListener('pagehide', flush);
  boot();
})();
