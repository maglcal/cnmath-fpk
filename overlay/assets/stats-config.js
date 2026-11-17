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
        if (window.crypto && window.crypto.getRandomValues) {
          window.crypto.getRandomValues(b);
        } else {
          for (var i = 0; i < 16; i++) b[i] = Math.floor(Math.random() * 256);
        }
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

  /* 纯 JS SHA-256（FIPS 180-4）。仅在 crypto.subtle 不可用（http 等非安全上下文）
   * 时兜底；输出与 WebCrypto 逐位一致（标准测试向量验证），哈希规则不变。 */
  function sha256Hex(str) {
    var utf8 = [];
    for (var i = 0; i < str.length; i++) {
      var c = str.charCodeAt(i);
      if (c < 0x80) utf8.push(c);
      else if (c < 0x800) utf8.push(0xc0 | (c >> 6), 0x80 | (c & 63));
      else if (c < 0xd800 || c >= 0xe000) utf8.push(0xe0 | (c >> 12), 0x80 | ((c >> 6) & 63), 0x80 | (c & 63));
      else { i++; var c2 = 0x10000 + (((c & 0x3ff) << 10) | (str.charCodeAt(i) & 0x3ff));
             utf8.push(0xf0 | (c2 >> 18), 0x80 | ((c2 >> 12) & 63), 0x80 | ((c2 >> 6) & 63), 0x80 | (c2 & 63)); }
    }
    var H = [0x6a09e667, 0xbb67ae85, 0x3c6ef372, 0xa54ff53a, 0x510e527f, 0x9b05688c, 0x1f83d9ab, 0x5be0cd19];
    var K = [
      0x428a2f98, 0x71374491, 0xb5c0fbcf, 0xe9b5dba5, 0x3956c25b, 0x59f111f1, 0x923f82a4, 0xab1c5ed5,
      0xd807aa98, 0x12835b01, 0x243185be, 0x550c7dc3, 0x72be5d74, 0x80deb1fe, 0x9bdc06a7, 0xc19bf174,
      0xe49b69c1, 0xefbe4786, 0x0fc19dc6, 0x240ca1cc, 0x2de92c6f, 0x4a7484aa, 0x5cb0a9dc, 0x76f988da,
      0x983e5152, 0xa831c66d, 0xb00327c8, 0xbf597fc7, 0xc6e00bf3, 0xd5a79147, 0x06ca6351, 0x14292967,
      0x27b70a85, 0x2e1b2138, 0x4d2c6dfc, 0x53380d13, 0x650a7354, 0x766a0abb, 0x81c2c92e, 0x92722c85,
      0xa2bfe8a1, 0xa81a664b, 0xc24b8b70, 0xc76c51a3, 0xd192e819, 0xd6990624, 0xf40e3585, 0x106aa070,
      0x19a4c116, 0x1e376c08, 0x2748774c, 0x34b0bcb5, 0x391c0cb3, 0x4ed8aa4a, 0x5b9cca4f, 0x682e6ff3,
      0x748f82ee, 0x78a5636f, 0x84c87814, 0x8cc70208, 0x90befffa, 0xa4506ceb, 0xbef9a3f7, 0xc67178f2
    ];
    var l = utf8.length;
    var bitLen = l * 8;
    utf8.push(0x80);
    while (utf8.length % 64 !== 56) utf8.push(0);
    utf8.push(0, 0, 0, 0, (bitLen >>> 24) & 255, (bitLen >>> 16) & 255, (bitLen >>> 8) & 255, bitLen & 255);
    var w = new Array(64);
    for (var off = 0; off < utf8.length; off += 64) {
      var j;
      for (j = 0; j < 16; j++) {
        w[j] = (utf8[off + j * 4] << 24) | (utf8[off + j * 4 + 1] << 16) |
               (utf8[off + j * 4 + 2] << 8) | utf8[off + j * 4 + 3];
      }
      for (j = 16; j < 64; j++) {
        var s0 = ((w[j - 15] >>> 7) | (w[j - 15] << 25)) ^ ((w[j - 15] >>> 18) | (w[j - 15] << 14)) ^ (w[j - 15] >>> 3);
        var s1 = ((w[j - 2] >>> 17) | (w[j - 2] << 15)) ^ ((w[j - 2] >>> 19) | (w[j - 2] << 13)) ^ (w[j - 2] >>> 10);
        w[j] = (w[j - 16] + s0 + w[j - 7] + s1) | 0;
      }
      var a = H[0], b = H[1], c = H[2], d = H[3], e = H[4], f = H[5], g = H[6], h = H[7];
      for (j = 0; j < 64; j++) {
        var S1 = ((e >>> 6) | (e << 26)) ^ ((e >>> 11) | (e << 21)) ^ ((e >>> 25) | (e << 7));
        var ch = (e & f) ^ (~e & g);
        var t1 = (h + S1 + ch + K[j] + w[j]) | 0;
        var S0 = ((a >>> 2) | (a << 30)) ^ ((a >>> 13) | (a << 19)) ^ ((a >>> 22) | (a << 10));
        var maj = (a & b) ^ (a & c) ^ (b & c);
        var t2 = (S0 + maj) | 0;
        h = g; g = f; f = e; e = (d + t1) | 0; d = c; c = b; b = a; a = (t1 + t2) | 0;
      }
      H[0] = (H[0] + a) | 0; H[1] = (H[1] + b) | 0; H[2] = (H[2] + c) | 0; H[3] = (H[3] + d) | 0;
      H[4] = (H[4] + e) | 0; H[5] = (H[5] + f) | 0; H[6] = (H[6] + g) | 0; H[7] = (H[7] + h) | 0;
    }
    var out = '';
    for (var k = 0; k < 8; k++) out += ('00000000' + (H[k] >>> 0).toString(16)).slice(-8);
    return out;
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
    if (!code) { machineHashPromise = Promise.resolve(null); return machineHashPromise; }
    var input = CFG.appSalt + SALT_JOIN + code;
    if (window.crypto && window.crypto.subtle && window.TextEncoder) {
      machineHashPromise = window.crypto.subtle
        .digest('SHA-256', new TextEncoder().encode(input))
        .then(hex32)
        .catch(function () { try { return sha256Hex(input).slice(0, 32); } catch (e) { return null; } });
    } else {
      /* crypto.subtle 仅存在于安全上下文；http 访问 NAS 时缺席 →
       * 纯 JS 同规则兜底（2026-11-17 修复：此前直接放弃导致 http 下零上报）。 */
      try { machineHashPromise = Promise.resolve(sha256Hex(input).slice(0, 32)); }
      catch (e) { machineHashPromise = Promise.resolve(null); }
    }
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
        /* fetch 优先（2026-11-17 实测修复）：sendBeacon 的 JSON 跨域信标在需要
         * CORS 预检时被浏览器静默丢弃（返回 true 但 POST 不发，实测证实）；
         * 服务端严格要求 application/json（其他类型 415），text/plain 信标也不可用。
         * fetch 走预检正常到达（服务端 /collect 有 OPTIONS/CORS）；keepalive 覆盖
         * pagehide 卸载场景。机制零变化：同端点、同载荷、同三类事件。 */
        if (typeof fetch === 'function') {
          fetch(CFG.endpoint, { method: 'POST', headers: { 'Content-Type': 'application/json' },
                                body: JSON.stringify(payload), keepalive: true, mode: 'cors' })
            .catch(function () { /* 忽略：统计不可影响主功能 */ });
        } else if (navigator.sendBeacon) {
          navigator.sendBeacon(CFG.endpoint, new Blob([JSON.stringify(payload)], { type: 'application/json' }));
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
