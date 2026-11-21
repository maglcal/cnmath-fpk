/* 版本更新提醒（壳工程新增，Copyright © 2026 许诺，MIT License）。
 *
 * 联网边界（verify_grant 白名单锚点，勿改）：仅请求 api.github.com / github.com
 * 上 maglcal/cnmath-fpk 的公开发布页，且只在「用户点击检查更新」或「用户显式
 * 开启自动提醒」后才发起；不发送任何数据、不读取页面内容，失败静默降级。
 * 不点击、不开启即零联网，产品「断网也能用」承诺不变。 */
'use strict';
(function () {
  var API_LATEST = 'https://api.github.com/repos/maglcal/cnmath-fpk/releases/latest';
  var RELEASES_URL = 'https://github.com/maglcal/cnmath-fpk/releases';
  var CURRENT = '__CNM_VERSION__'; // 构建时替换为 manifest version
  var K_AUTO = 'cnmUpdateCheck.v1.auto';
  var K_CACHE = 'cnmUpdateCheck.v1.cache';
  var K_DISMISSED = 'cnmUpdateCheck.v1.dismissed';
  var DAY = 24 * 60 * 60 * 1000;

  function get(k) { try { return window.localStorage.getItem(k); } catch (e) { return null; } }
  function set(k, v) { try { window.localStorage.setItem(k, v); } catch (e) {} }

  /* 版本比较：剥 main-v / v 前缀、逐段取数字、补零对齐（与版本命名规则一致） */
  function parseVer(s) {
    s = String(s || '').trim().replace(/^main-v/i, '').replace(/^v/i, '');
    return s.split('.').map(function (x) {
      var m = /^\d+/.exec(x);
      return m ? parseInt(m[0], 10) : 0;
    });
  }
  function cmpVer(a, b) {
    var A = parseVer(a), B = parseVer(b), L = Math.max(A.length, B.length);
    for (var i = 0; i < L; i++) {
      var d = (A[i] || 0) - (B[i] || 0);
      if (d) return d > 0 ? 1 : -1;
    }
    return 0;
  }

  function fetchLatest() {
    return fetch(API_LATEST, { headers: { Accept: 'application/vnd.github+json' } })
      .then(function (r) {
        if (r.status === 403 || r.status === 429) throw new Error('rate');
        if (!r.ok) throw new Error('http' + r.status);
        return r.json();
      })
      .then(function (j) {
        if (!j || !j.tag_name) throw new Error('empty');
        return { tag: j.tag_name, url: j.html_url || RELEASES_URL };
      });
  }

  function cacheRead() {
    try { return JSON.parse(get(K_CACHE) || 'null'); } catch (e) { return null; }
  }
  function cacheWrite(info) {
    set(K_CACHE, JSON.stringify({ tag: info.tag, url: info.url, ts: Date.now() }));
  }

  /* ---- 首页提醒横幅 ---- */
  function renderBanner(info) {
    if (!document.body || get(K_DISMISSED) === info.tag) return;
    if (document.getElementById('cnm-update-banner')) return;
    var bar = document.createElement('div');
    bar.id = 'cnm-update-banner';
    bar.style.cssText = 'position:sticky;top:0;z-index:9999;background:#2563eb;color:#fff;' +
      'padding:10px 16px;font:14px/1.7 -apple-system,"PingFang SC","Microsoft YaHei",sans-serif;' +
      'display:flex;flex-wrap:wrap;gap:10px;align-items:center;justify-content:center;';
    var t1 = document.createElement('span');
    t1.textContent = '发现新版本 ' + info.tag + '（当前 ' + CURRENT + '）';
    var a = document.createElement('a');
    a.href = info.url; a.target = '_blank'; a.rel = 'noopener';
    a.style.cssText = 'color:#fff;text-decoration:underline;font-weight:600;';
    a.textContent = '查看更新';
    var btn = document.createElement('button');
    btn.textContent = '不再提醒';
    btn.style.cssText = 'border:1px solid rgba(255,255,255,.7);background:transparent;color:#fff;' +
      'border-radius:6px;padding:2px 10px;cursor:pointer;font-size:13px;';
    btn.addEventListener('click', function () {
      set(K_DISMISSED, info.tag);
      if (bar.parentNode) bar.parentNode.removeChild(bar);
    });
    bar.appendChild(t1); bar.appendChild(a); bar.appendChild(btn);
    document.body.insertBefore(bar, document.body.firstChild);
  }

  /* ---- 关于页：按钮与开关 ---- */
  function renderResult(out, info) {
    out.textContent = '';
    if (cmpVer(info.tag, CURRENT) > 0) {
      out.appendChild(document.createTextNode('发现新版本 ' + info.tag + '（当前 ' + CURRENT + '）。'));
      var a = document.createElement('a');
      a.href = info.url; a.target = '_blank'; a.rel = 'noopener';
      a.textContent = '前往下载与查看更新说明';
      out.appendChild(a);
    } else {
      out.textContent = '已是最新版本（当前 ' + CURRENT + '，发布页最新 ' + info.tag + '）。';
    }
  }

  function runCheck(out) {
    out.textContent = '正在查询公开发布页……';
    fetchLatest().then(function (info) {
      cacheWrite(info);
      renderResult(out, info);
      if (cmpVer(info.tag, CURRENT) > 0) renderBanner(info);
    }).catch(function (e) {
      out.textContent = (e && e.message === 'rate')
        ? '查询过于频繁，请稍后再试；也可直接访问 '
        : '暂时无法连接更新服务（网络原因），可稍后再试，或直接访问 ';
      var a = document.createElement('a');
      a.href = RELEASES_URL; a.target = '_blank'; a.rel = 'noopener';
      a.textContent = '公开发布页';
      out.appendChild(a);
    });
  }

  function wireAbout() {
    var btn = document.getElementById('update-check-btn');
    var out = document.getElementById('update-result');
    var auto = document.getElementById('update-auto');
    if (auto) {
      auto.checked = get(K_AUTO) === '1';
      auto.addEventListener('change', function () {
        set(K_AUTO, auto.checked ? '1' : '0');
        if (out) out.textContent = auto.checked
          ? '已开启自动提醒：每天最多一次联网查询公开发布页，发现新版本会在首页提示。'
          : '已关闭自动提醒：不再自动联网；仍可手动点击「检查更新」。';
        if (auto.checked && out) runCheck(out);
      });
    }
    if (btn && out) btn.addEventListener('click', function () { runCheck(out); });
  }

  /* ---- 启动：仅当用户开启自动提醒且当日未查过才联网 ---- */
  function boot() {
    wireAbout();
    if (get(K_AUTO) !== '1') return;
    var c = cacheRead();
    if (c && Date.now() - (c.ts || 0) < DAY) {
      if (cmpVer(c.tag, CURRENT) > 0) renderBanner(c);
      return;
    }
    fetchLatest().then(function (info) {
      cacheWrite(info);
      if (cmpVer(info.tag, CURRENT) > 0) renderBanner(info);
    }).catch(function () { /* 自动检查失败静默，手动检查才提示 */ });
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', boot);
  } else {
    boot();
  }
})();
