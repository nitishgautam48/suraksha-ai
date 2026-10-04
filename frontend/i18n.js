/* Suraksha AI - interface translation for 12 Indian languages.
 *
 * The app is written in English. This runtime translates what is on screen, in place, using one
 * small dictionary per language (i18n/<code>.json, loaded on demand and cached by the service
 * worker). A MutationObserver keeps the page translated as React re-renders it, before the
 * browser paints, so there is no flash of English.
 *
 * Never translated: inputs, <textarea>, <pre>, <script>/<style>, and anything inside an element
 * with translate="no" (user messages, AI answers, complaint summaries). AI and server text arrives
 * already in the user's language from the API.
 *
 * Dictionary keys are the exact English UI strings. Keys containing {0}, {1}... are patterns, e.g.
 * "Question {0} of {1}" -> "प्रश्न {1} में से {0}".
 */
(function () {
  'use strict';
  // Text inside these is never translated (<i> holds icon ligatures). Placeholders of inputs and
  // text areas still are, via doEl().
  var SKIP = {SCRIPT: 1, STYLE: 1, TEXTAREA: 1, PRE: 1, CODE: 1, NOSCRIPT: 1, I: 1};
  var ATTRS = ['placeholder', 'aria-label', 'title'];
  var LETTER = /[A-Za-z]/;
  var state = {lang: 'en', dict: null, patterns: [], cache: {}, listeners: []};
  var textOrig = new WeakMap(); // text node -> {en, tr}
  var attrOrig = new WeakMap(); // element -> {attr: {en, tr}}

  function escapeRe(s) { return s.replace(/[.*+?^${}()|[\]\\]/g, '\\$&'); }

  function compile(dict) {
    var pats = [];
    Object.keys(dict).forEach(function (k) {
      if (k.indexOf('{0}') < 0) return;
      var re = new RegExp('^' + escapeRe(k).replace(/\\\{(\d)\\\}/g, '(.+?)') + '$');
      pats.push([re, dict[k]]);
    });
    return pats;
  }

  function translate(s) {
    if (!state.dict || !s) return null;
    var key = s.trim();
    if (!key || !LETTER.test(key)) return null;
    var v = state.dict[key];
    if (v == null) {
      for (var i = 0; i < state.patterns.length; i++) {
        var m = key.match(state.patterns[i][0]);
        if (m) { v = state.patterns[i][1].replace(/\{(\d)\}/g, function (_, n) { var g = m[+n + 1]; return state.dict[g] != null ? state.dict[g] : g; }); break; }
      }
    }
    if (v == null) return null;
    var lead = s.match(/^\s*/)[0], trail = s.match(/\s*$/)[0];
    return lead + v + trail;
  }

  function skipped(node) {
    for (var e = node.parentElement; e; e = e.parentElement) {
      if (SKIP[e.tagName] || e.getAttribute('translate') === 'no') return true;
    }
    return false;
  }

  function doText(n) {
    var rec = textOrig.get(n);
    var en = rec && n.nodeValue === rec.tr ? rec.en : n.nodeValue;
    var t = translate(en);
    if (t != null) {
      textOrig.set(n, {en: en, tr: t});
      if (n.nodeValue !== t) n.nodeValue = t;
    } else if (rec && n.nodeValue === rec.tr) {
      n.nodeValue = en; // back to English
      textOrig.delete(n);
    }
  }

  function doEl(el) {
    for (var i = 0; i < ATTRS.length; i++) {
      var a = ATTRS[i];
      if (!el.hasAttribute(a)) continue;
      var cur = el.getAttribute(a), map = attrOrig.get(el) || {}, rec = map[a];
      var en = rec && cur === rec.tr ? rec.en : cur;
      var t = translate(en);
      if (t != null) { map[a] = {en: en, tr: t}; attrOrig.set(el, map); if (cur !== t) el.setAttribute(a, t); }
      else if (rec && cur === rec.tr) { el.setAttribute(a, en); delete map[a]; }
    }
  }

  var filter = {acceptNode: function (n) {
    if (n.nodeType === 1 && (SKIP[n.tagName] || n.getAttribute('translate') === 'no')) {
      if (n.tagName === 'TEXTAREA') doEl(n);
      return NodeFilter.FILTER_REJECT;
    }
    return NodeFilter.FILTER_ACCEPT;
  }};

  function walk(root) {
    if (!root) return;
    if (root.nodeType === 3) { if (!skipped(root)) doText(root); return; }
    if (root.nodeType !== 1 || root.getAttribute('translate') === 'no' || skipped(root)) return;
    if (SKIP[root.tagName]) { if (root.tagName === 'TEXTAREA') doEl(root); return; }
    doEl(root);
    var w = document.createTreeWalker(root, NodeFilter.SHOW_ELEMENT | NodeFilter.SHOW_TEXT, filter), n;
    while ((n = w.nextNode())) { if (n.nodeType === 3) doText(n); else doEl(n); }
  }

  var observer = new MutationObserver(function (records) {
    if (!state.dict) return;
    for (var i = 0; i < records.length; i++) {
      var r = records[i];
      if (r.type === 'characterData') { if (!skipped(r.target)) doText(r.target); }
      else if (r.type === 'attributes') { if (!skipped(r.target)) doEl(r.target); }
      else for (var j = 0; j < r.addedNodes.length; j++) walk(r.addedNodes[j]);
    }
  });

  function start() {
    observer.observe(document.body, {subtree: true, childList: true, characterData: true, attributes: true, attributeFilter: ATTRS});
  }
  if (document.body) start(); else document.addEventListener('DOMContentLoaded', start);

  function load(code) {
    if (state.cache[code]) return Promise.resolve(state.cache[code]);
    return fetch('./i18n/' + code + '.json', {credentials: 'same-origin'})
      .then(function (r) { if (!r.ok) throw new Error('HTTP ' + r.status); return r.json(); })
      .then(function (d) { delete d._meta; state.cache[code] = d; return d; });
  }

  window.SurakshaI18n = {
    get lang() { return state.lang; },
    /** Switch the interface language ("en", "hi", "ta", ...). Resolves once the page is translated. */
    setLang: function (code) {
      code = code || 'en';
      document.documentElement.lang = code;
      if (code === 'en') {
        state.lang = 'en'; state.dict = null; state.patterns = [];
        walk(document.body);
        state.listeners.forEach(function (f) { try { f(code); } catch (e) {} });
        return Promise.resolve();
      }
      return load(code).then(function (d) {
        state.lang = code; state.dict = d; state.patterns = compile(d);
        walk(document.body);
        state.listeners.forEach(function (f) { try { f(code); } catch (e) {} });
      }).catch(function () { /* keep the current language if the dictionary is unavailable */ });
    },
    /** Translate one English UI string (for speech, confirm() dialogs, ...). */
    t: function (s) { var v = translate(s); return v == null ? s : v; },
    onChange: function (f) { state.listeners.push(f); },
  };
})();
