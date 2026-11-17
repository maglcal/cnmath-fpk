/* 纯本地事件钩子（自研替换层，MIT，属于壳工程）
 * ---------------------------------------------------------------
 * 保留上游页面依赖的接口：window.cnmTrack / cnmIsStandalone、
 * data-display-mode 属性、cnm:track 自定义事件与本地回访计数。
 *
 * 与上游版本的差别（也是授权条件 1/4 的要求）：
 *  - 不加载任何第三方信标脚本、不发任何网络请求；
 *  - 不读取 endpoint，事件只交给 stats-config.js 的 onEvent 治理；
 *  - 本地回访状态只写浏览器 localStorage，不出本机。
 *
 * 本文件不改动上游业务逻辑；children/page.js 等处的 cnmTrack 调用照常工作。
 */
(function () {
  'use strict';
  var cfg = window.CNM_STATS || {};
  var LS = 'cnmStats.v1';

  function isStandalone() {
    try {
      if (window.matchMedia && window.matchMedia('(display-mode: standalone)').matches) return true;
      if (window.matchMedia && window.matchMedia('(display-mode: fullscreen)').matches) return true;
    } catch (e) { /* ignore */ }
    return window.navigator.standalone === true;
  }
  var standalone = isStandalone();
  var source = standalone ? 'pwa' : 'web';
  window.cnmIsStandalone = standalone;
  document.documentElement.setAttribute('data-display-mode', standalone ? 'standalone' : 'browser');

  function track(name, props) {
    var ev = { event: name, source: source, path: location.pathname, ts: new Date().toISOString() };
    if (props) Object.keys(props).forEach(function (k) { ev[k] = props[k]; });
    try { window.dispatchEvent(new CustomEvent('cnm:track', { detail: ev })); } catch (e) { /* ignore */ }
    /* 只交治理层：治理层会丢弃业务 props，仅映射 install/open/update，
       且默认关闭时 enabled() 为 false，直接丢弃，绝不落任何网络请求。 */
    try { if (typeof cfg.onEvent === 'function') cfg.onEvent(ev); } catch (e) { /* ignore */ }
  }
  window.cnmTrack = track;

  function today() {
    var d = new Date();
    return d.getFullYear() + '-' + ('0' + (d.getMonth() + 1)).slice(-2) + '-' + ('0' + d.getDate()).slice(-2);
  }

  function visit() {
    var st = null;
    try { st = JSON.parse(localStorage.getItem(LS)); } catch (e) { st = null; }
    var day = today();
    var returning = false;
    if (!st || !st.first) st = { first: day, last: day, days: 1 };
    else if (st.last !== day) { st.last = day; st.days = (st.days || 1) + 1; returning = true; }
    try { localStorage.setItem(LS, JSON.stringify(st)); } catch (e) { /* 隐私模式 */ }

    track('pageview');
    var launched = false;
    try {
      launched = sessionStorage.getItem('cnmStats.launch') === '1';
      sessionStorage.setItem('cnmStats.launch', '1');
    } catch (e) { /* ignore */ }
    if (standalone && !launched) track('pwa_launch');
    if (returning && !launched) {
      track('return_visit', {
        days_since_first: Math.round((Date.parse(day) - Date.parse(st.first)) / 86400000),
        visit_days: st.days
      });
    }
  }

  window.addEventListener('appinstalled', function () {
    try { localStorage.setItem('cnmPwa.installed.v1', '1'); } catch (e) { /* ignore */ }
    track('appinstalled');
  });

  visit();
})();
