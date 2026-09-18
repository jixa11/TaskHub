/* TaskHub - bilingual display layer (Persian / English)
 *
 * The interface is written in Persian and stays that way in the source. English
 * is produced at display time: every text node and readable attribute is looked
 * up in a Persian to English table (i18n.json) before the user sees it, and
 * anything without a translation is left untouched. That keeps one language in
 * the code while the screen can show either.
 *
 * In English mode the layer also switches the page to left-to-right, turns
 * Persian digits into Latin ones, and prints Jalali dates as Gregorian.
 *
 * Switching language reloads the page: the app renders continuously from its
 * own Persian sources, so a reload is both simpler and safer than trying to put
 * every screen back the way it was.
 */
'use strict';

var I18N = (function () {
  var STORAGE_KEY = 'taskhub_lang';
  var TEXT_ATTRIBUTES = ['title', 'placeholder', 'aria-label', 'alt'];
  var DIGITS = /[۰-۹٠-٩]/g;
  var JALALI_DATE = /\b(1[34]\d{2})\/(\d{1,2})\/(\d{1,2})\b/g;

  var table = {};       // Persian text -> English text
  var patterns = [];    // for sentences built around a value at runtime
  var language = 'fa';
  var observer = null;
  var busy = false;

  function stored() {
    try {
      return localStorage.getItem(STORAGE_KEY);
    } catch (e) {
      return null;
    }
  }

  function current() {
    return language;
  }

  function set(next) {
    try {
      localStorage.setItem(STORAGE_KEY, next);
    } catch (e) { /* private window: the choice simply does not persist */ }
    location.reload();
  }

  function toggle() {
    set(language === 'en' ? 'fa' : 'en');
  }

  // ── Jalali to Gregorian, used only for display ──────────────────────────
  function gregorianOf(jy, jm, jd) {
    var gy = jy <= 979 ? 621 : 1600;
    jy -= jy <= 979 ? 0 : 979;
    var days = 365 * jy + Math.floor(jy / 33) * 8 + Math.floor(((jy % 33) + 3) / 4) + 78 + jd +
      (jm < 7 ? (jm - 1) * 31 : (jm - 7) * 30 + 186);
    gy += 400 * Math.floor(days / 146097);
    days %= 146097;
    if (days > 36524) {
      gy += 100 * Math.floor(--days / 36524);
      days %= 36524;
      if (days >= 365) days++;
    }
    gy += 4 * Math.floor(days / 1461);
    days %= 1461;
    if (days > 365) {
      gy += Math.floor((days - 1) / 365);
      days = (days - 1) % 365;
    }
    var gd = days + 1;
    var leap = (gy % 4 === 0 && gy % 100 !== 0) || gy % 400 === 0;
    var lengths = [0, 31, leap ? 29 : 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31];
    var gm = 0;
    while (gm < 13 && gd > lengths[gm]) gd -= lengths[gm++];
    return [gy, gm, gd];
  }

  function pad(value) {
    return value < 10 ? '0' + value : String(value);
  }

  function datesToGregorian(text) {
    return text.replace(JALALI_DATE, function (whole, year, month, day) {
      var parts = gregorianOf(Number(year), Number(month), Number(day));
      if (!parts[1]) return whole;
      return parts[0] + '-' + pad(parts[1]) + '-' + pad(parts[2]);
    });
  }

  function latinDigits(text) {
    return text.replace(DIGITS, function (digit) {
      var code = digit.charCodeAt(0);
      return String(code >= 0x06F0 ? code - 0x06F0 : code - 0x0660);
    });
  }

  // ── translation ────────────────────────────────────────────────────────
  function translate(text) {
    if (language !== 'en' || !text) return text;
    var trimmed = text.trim();
    if (!trimmed) return text;
    // Numbers reach the screen in Persian digits, so look the text up both
    // as written and with Latin digits.
    var plain = latinDigits(trimmed);
    var hit = table[trimmed];
    if (hit === undefined) hit = table[plain];
    if (hit === undefined) {
      for (var i = 0; i < patterns.length; i++) {
        var match = plain.match(patterns[i].from);
        if (match) {
          hit = patterns[i].to.replace(/\$(\d)/g, function (_, index) {
            return match[Number(index)] || '';
          });
          break;
        }
      }
    }
    var result = hit === undefined ? trimmed : hit;
    result = latinDigits(datesToGregorian(result));
    if (result === trimmed) return text;          // nothing changed: keep spacing
    var before = text.match(/^\s*/)[0];
    var after = text.match(/\s*$/)[0];
    return before + result + after;
  }

  function translateNode(root) {
    if (language !== 'en' || !root) return;
    var walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT, {
      acceptNode: function (node) {
        var parent = node.parentNode;
        if (!parent) return NodeFilter.FILTER_REJECT;
        var tag = parent.nodeName;
        if (tag === 'SCRIPT' || tag === 'STYLE' || tag === 'TEXTAREA') return NodeFilter.FILTER_REJECT;
        if (parent.closest && parent.closest('[data-no-i18n]')) return NodeFilter.FILTER_REJECT;
        return NodeFilter.FILTER_ACCEPT;
      }
    });
    var node;
    while ((node = walker.nextNode())) {
      var translated = translate(node.nodeValue);
      if (translated !== node.nodeValue) node.nodeValue = translated;
    }
    var elements = root.nodeType === 1 ? [root] : [];
    if (root.querySelectorAll) {
      elements = elements.concat(Array.prototype.slice.call(root.querySelectorAll('*')));
    }
    elements.forEach(function (element) {
      TEXT_ATTRIBUTES.forEach(function (name) {
        var value = element.getAttribute && element.getAttribute(name);
        if (!value) return;
        var translated = translate(value);
        if (translated !== value) element.setAttribute(name, translated);
      });
      if (element.nodeName === 'INPUT' && /^(button|submit|reset)$/i.test(element.type || '')) {
        var label = translate(element.value);
        if (label !== element.value) element.value = label;
      }
    });
  }

  function translateDocument() {
    if (language !== 'en' || busy) return;
    busy = true;
    translateNode(document.body);
    if (observer) observer.takeRecords();   // ignore what we just changed
    busy = false;
  }

  function watch() {
    if (!window.MutationObserver) return;
    observer = new MutationObserver(function (records) {
      if (busy) return;
      busy = true;
      records.forEach(function (record) {
        if (record.type === 'characterData') {
          var translated = translate(record.target.nodeValue);
          if (translated !== record.target.nodeValue) record.target.nodeValue = translated;
          return;
        }
        Array.prototype.forEach.call(record.addedNodes, function (node) {
          if (node.nodeType === 3) {
            var text = translate(node.nodeValue);
            if (text !== node.nodeValue) node.nodeValue = text;
          } else if (node.nodeType === 1) {
            translateNode(node);
          }
        });
      });
      observer.takeRecords();
      busy = false;
    });
    observer.observe(document.body, {
      childList: true, subtree: true, characterData: true,
      attributes: true, attributeFilter: TEXT_ATTRIBUTES
    });
  }

  function load() {
    return fetch('/assets/i18n.json', { cache: 'no-store' })
      .then(function (response) { return response.json(); })
      .then(function (data) {
        table = data.strings || {};
        patterns = (data.patterns || []).map(function (entry) {
          return { from: new RegExp(entry.from), to: entry.to };
        });
      })
      .catch(function () { /* no dictionary: the app stays Persian */ });
  }

  function markSwitch() {
    // The button offers the other language, so it reads FA while in English.
    var button = document.getElementById('lang-toggle');
    if (button) button.textContent = language === 'en' ? 'FA' : 'EN';
  }

  function start() {
    language = stored() === 'en' ? 'en' : 'fa';
    var root = document.documentElement;
    root.setAttribute('lang', language === 'en' ? 'en' : 'fa');
    root.setAttribute('dir', language === 'en' ? 'ltr' : 'rtl');
    root.setAttribute('data-lang', language);
    if (document.readyState === 'loading') {
      document.addEventListener('DOMContentLoaded', markSwitch);
    } else {
      markSwitch();
    }
    if (language !== 'en') return Promise.resolve();
    return load().then(function () {
      translateDocument();
      watch();
    });
  }

  return {
    start: start,
    toggle: toggle,
    set: set,
    current: current,
    translate: translate,
    refresh: translateDocument
  };
})();

// The toolbar button calls this.
function toggleLanguage() {
  I18N.toggle();
}

I18N.start();
