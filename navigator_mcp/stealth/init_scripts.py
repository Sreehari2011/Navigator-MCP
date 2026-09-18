"""Stealth runtime patches injected into every frame of a session.

This is the JS layer that makes a stock Playwright Chromium look like a normal
user browser. It is generated per-session from the chosen fingerprint so all
spoofed values agree with the context-level headers (UA / sec-ch-ua / locale /
timezone). A per-session random seed drives canvas/audio noise, making each
session fingerprint-distinct yet internally consistent.

Patches applied (all with native-looking ``toString``):
  * ``navigator.webdriver`` removed, plugins/mimeTypes mocked
  * ``navigator.platform / languages / hardwareConcurrency / deviceMemory``
  * ``chrome.runtime / chrome.app / chrome.loadTimes / chrome.csi`` present
  * Permissions / Notification consistency
  * WebGL vendor + renderer spoof, session-stable canvas noise
  * AnalyserNode audio noise, NetworkInformation mock, Battery mock
  * ``window.outerWidth/outerHeight`` plausibility
"""

from __future__ import annotations

import json
import random

from .fingerprints import Fingerprint

_TEMPLATE = r"""
(() => {
  if (window.__navigatorStealthApplied) { return; }
  Object.defineProperty(window, '__navigatorStealthApplied', {value: 1, enumerable: false});

  const cfg = __NAVIGATOR_CFG__;

  // ---- helpers -------------------------------------------------------------
  const makeNative = (fn, name) => {
    try {
      const nativeStr = `function ${name}() { [native code] }`;
      Object.defineProperty(fn, 'toString', {
        value: function () { return nativeStr; },
        writable: true, configurable: true
      });
    } catch (e) { /* best effort */ }
  };
  const defineProp = (obj, prop, value) => {
    try {
      Object.defineProperty(obj, prop, {
        get: (() => typeof value === 'function' ? value : () => value)(),
        configurable: true, enumerable: true
      });
    } catch (e) { /* best effort */ }
  };

  // Deterministic PRNG so canvas noise is stable within this session.
  const seeded = (seed) => {
    let s = (seed >>> 0) || 1;
    return () => {
      s = Math.imul(s ^ (s >>> 15), s | 1);
      s ^= s + Math.imul(s ^ (s >>> 7), s | 61);
      return ((s ^ (s >>> 14)) >>> 0) / 4294967296;
    };
  };
  const stableHash = (str) => {
    let h = 2166136261 >>> 0;
    for (let i = 0; i < str.length; i++) {
      h = Math.imul(h ^ str.charCodeAt(i), 16777619);
    }
    return h >>> 0;
  };

  // ---- 1. webdriver & core navigator --------------------------------------
  try {
    if (navigator.webdriver !== undefined) {
      Object.defineProperty(Object.getPrototypeOf(navigator), 'webdriver', {
        get: () => undefined, configurable: true, enumerable: true
      });
    }
  } catch (e) {}

  defineProp(navigator, 'platform', cfg.platform);
  defineProp(navigator, 'languages', Object.freeze([cfg.locale, 'en']));
  defineProp(navigator, 'hardwareConcurrency', cfg.hardwareConcurrency);
  try {
    defineProp(navigator, 'deviceMemory', cfg.deviceMemory);
  } catch (e) {}
  defineProp(navigator, 'maxTouchPoints', 0);

  // ---- 2. plugins / mimeTypes ----------------------------------------------
  try {
    const mkPlugin = (name, filename, desc, mimes) => {
      const p = { name, filename, description: desc, length: mimes.length };
      mimes.forEach((m, i) => {
        p[i] = { type: m.type, suffixes: m.suffixes, description: m.desc,
                 enabledPlugin: p };
      });
      return p;
    };
    const pdfMimes = [
      { type: 'application/pdf', suffixes: 'pdf', desc: 'Portable Document Format' },
      { type: 'text/pdf', suffixes: 'pdf', desc: 'Portable Document Format' }
    ];
    const pluginList = [
      mkPlugin('PDF Viewer', 'internal-pdf-viewer', 'Portable Document Format', pdfMimes),
      mkPlugin('Chrome PDF Viewer', 'internal-pdf-viewer', 'Portable Document Format', pdfMimes),
      mkPlugin('Chromium PDF Viewer', 'internal-pdf-viewer', 'Portable Document Format', pdfMimes),
      mkPlugin('Microsoft Edge PDF Viewer', 'internal-pdf-viewer', 'Portable Document Format', pdfMimes),
      mkPlugin('WebKit built-in PDF', 'internal-pdf-viewer', 'Portable Document Format', pdfMimes)
    ];
    const plugins = Object.create(PluginArray.prototype);
    pluginList.forEach((p, i) => { Object.defineProperty(plugins, i, {value: p, enumerable: true}); });
    defineProp(plugins, 'length', pluginList.length);
    defineProp(plugins, 'item', (i) => pluginList[i] || null);
    defineProp(plugins, 'namedItem', (n) => pluginList.find(p => p.name === n) || null);
    defineProp(plugins, 'refresh', () => {});
    defineProp(navigator, 'plugins', plugins);

    const mimeArr = Object.create(MimeTypeArray.prototype);
    const flatMimes = [];
    pluginList.forEach(p => { for (let i = 0; i < p.length; i++) flatMimes.push(p[i]); });
    flatMimes.forEach((m, i) => { Object.defineProperty(mimeArr, i, {value: m, enumerable: true}); });
    defineProp(mimeArr, 'length', flatMimes.length);
    defineProp(navigator, 'mimeTypes', mimeArr);
  } catch (e) {}

  // ---- 3. window.chrome -----------------------------------------------------
  try {
    if (!window.chrome) { window.chrome = {}; }
    if (!window.chrome.runtime) {
      const port = {
        onMessage: { addListener() {}, removeListener() {} },
        onDisconnect: { addListener() {}, removeListener() {} },
        postMessage() {}, disconnect() {}
      };
      window.chrome.runtime = {
        connect: () => port,
        sendMessage: () => {},
        onMessage: { addListener() {}, removeListener() {} },
        id: undefined
      };
    }
    if (!window.chrome.loadTimes) {
      window.chrome.loadTimes = function () {
        return {
          requestTime: Date.now() / 1000 - 1.2,
          startLoadTime: Date.now() / 1000 - 1.1,
          commitLoadTime: Date.now() / 1000 - 1.0,
          finishDocumentLoadTime: Date.now() / 1000 - 0.7,
          finishLoadTime: Date.now() / 1000 - 0.5,
          firstPaintAfterLoadTime: 0,
          firstPaintTime: Date.now() / 1000 - 0.9,
          navigationType: 'Other',
          wasFetchedViaSpdy: false,
          wasNpnNegotiated: true,
          wasAlternateProtocolAvailable: false,
          connectionInfo: 'h2'
        };
      };
    }
    if (!window.chrome.csi) {
      window.chrome.csi = function () { return { startE: Date.now() - 800, onloadT: Date.now() - 400, pageT: 400, tran: 15 }; };
    }
    if (!window.chrome.app) {
      window.chrome.app = {
        isInstalled: false,
        InstallState: { DISABLED: 'disabled', INSTALLED: 'installed', NOT_INSTALLED: 'not_installed' },
        RunningState: { CANNOT_RUN: 'cannot_run', READY_TO_RUN: 'ready_to_run', RUNNING: 'running' },
        getDetails: () => null,
        getIsInstalled: () => false
      };
    }
  } catch (e) {}

  // ---- 4. permissions / notifications ---------------------------------------
  try {
    const origQuery = navigator.permissions && navigator.permissions.query;
    if (origQuery) {
      navigator.permissions.query = (params) => {
        if (params && params.name === 'notifications') {
          return Promise.resolve({ state: 'prompt', onchange: null });
        }
        return origQuery.call(navigator.permissions, params);
      };
      makeNative(navigator.permissions.query, 'query');
    }
  } catch (e) {}
  try {
    if (window.Notification) {
      Object.defineProperty(Notification, 'permission', {
        get: () => 'default', configurable: true
      });
    }
  } catch (e) {}

  // ---- 5. WebGL --------------------------------------------------------------
  try {
    const GL = WebGLRenderingContext;
    const WRAP = [WebGL2RenderingContext, GL].filter(Boolean);
    const VENDOR_ID = 0x9245, RENDERER_ID = 0x9246;
    WRAP.forEach((Ctx) => {
      const orig = Ctx.prototype.getParameter;
      Ctx.prototype.getParameter = function (param) {
        if (param === VENDOR_ID) { return cfg.webglVendor; }
        if (param === RENDERER_ID) { return cfg.webglRenderer; }
        return orig.call(this, param);
      };
      makeNative(Ctx.prototype.getParameter, 'getParameter');
    });
  } catch (e) {}

  // ---- 6. canvas noise (stable per canvas + session) --------------------------
  try {
    const nudge = (canvas, ctx, w, h) => {
      const key = `${w}x${h}:${cfg.seed}`;
      const rnd = seeded(stableHash(key));
      const count = 2 + Math.floor(rnd() * 3);
      for (let i = 0; i < count; i++) {
        const x = Math.floor(rnd() * w), y = Math.floor(rnd() * h);
        try {
          const px = ctx.getImageData(x, y, 1, 1);
        px.data[0] = (px.data[0] + (rnd() > 0.5 ? 1 : 255)) & 255;
          ctx.putImageData(px, x, y);
        } catch (e2) { /* tainted canvas */ }
      }
    };
    const origToDataURL = HTMLCanvasElement.prototype.toDataURL;
    HTMLCanvasElement.prototype.toDataURL = function (...args) {
      try {
        const ctx = this.getContext('2d');
        if (ctx && this.width > 0 && this.height > 0) {
          nudge(this, ctx, this.width, this.height);
        }
      } catch (e) { }
      return origToDataURL.apply(this, args);
    };
    makeNative(HTMLCanvasElement.prototype.toDataURL, 'toDataURL');

    const origToBlob = HTMLCanvasElement.prototype.toBlob;
    if (origToBlob) {
      HTMLCanvasElement.prototype.toBlob = function (cb, ...args) {
        try {
          const ctx = this.getContext('2d');
          if (ctx && this.width > 0 && this.height > 0) {
            nudge(this, ctx, this.width, this.height);
          }
        } catch (e) { }
        return origToBlob.call(this, cb, ...args);
      };
      makeNative(HTMLCanvasElement.prototype.toBlob, 'toBlob');
    }
  } catch (e) {}

  // ---- 7. audio noise ----------------------------------------------------------
  try {
    const origGetFloat = AnalyserNode.prototype.getFloatFrequencyData;
    AnalyserNode.prototype.getFloatFrequencyData = function (array) {
      const rnd = seeded(stableHash(String(this.fftSize) + cfg.seed));
      origGetFloat.call(this, array);
      for (let i = 0; i < array.length; i++) {
        array[i] += (rnd() - 0.5) * 0.1;
      }
    };
    makeNative(AnalyserNode.prototype.getFloatFrequencyData, 'getFloatFrequencyData');
  } catch (e) {}

  // ---- 8. network information / battery ---------------------------------------
  try {
    if (!navigator.connection && navigator.mozConnection === undefined) {
      const conn = {
        effectiveType: '4g', rtt: 50, downlink: 10, saveData: false,
        type: 'wifi',
        addEventListener() {}, removeEventListener() {},
        dispatchEvent() { return false; }
      };
      defineProp(navigator, 'connection', conn);
      defineProp(navigator, 'onLine', true);
    }
  } catch (e) {}
  try {
    if (navigator.getBattery) {
      navigator.getBattery = () => Promise.resolve({
        charging: true, chargingTime: 0, dischargingTime: Infinity, level: 1,
        addEventListener() {}, removeEventListener() {}
      });
      makeNative(navigator.getBattery, 'getBattery');
    }
  } catch (e) {}

  // ---- 9. outer dimensions plausibility ----------------------------------------
  try {
    Object.defineProperty(window, 'outerWidth', {
      get: () => window.innerWidth + 16, configurable: true
    });
    Object.defineProperty(window, 'outerHeight', {
      get: () => window.innerHeight + 88, configurable: true
    });
  } catch (e) {}

  // ---- 10. focus & misc ---------------------------------------------------------
  try { document.hasFocus = () => true; makeNative(document.hasFocus, 'hasFocus'); } catch (e) {}
})();
"""


def build_stealth_script(fp: Fingerprint) -> str:
    """Render the per-session stealth init script for a fingerprint."""
    cfg = {
        "platform": fp.platform,
        "locale": fp.locale,
        "hardwareConcurrency": fp.hardware_concurrency,
        "deviceMemory": fp.device_memory_gb,
        "webglVendor": fp.webgl_vendor,
        "webglRenderer": fp.webgl_renderer,
        "seed": random.getrandbits(31),
    }
    return _TEMPLATE.replace("__NAVIGATOR_CFG__", json.dumps(cfg))
