"""
Shared OpenCMP cookie consent logic for markt.de (same behavior as markt_user_init._click_accept_all_cookies).
- Selenium/Appium: use click_accept_all_cookies_selenium(driver, email, log_fn).
- Nodriver/Playwright: markt_user_init imports FIND_ACCEPT_BTN_JS for async evaluate().
"""

from __future__ import annotations

import time
from collections.abc import Callable
from typing import Any, Optional

# OpenCMP: .cmp-button-accept-all in nested shadow DOM (keep in sync with markt_user_init)
# Full tree walk (document + open/closed shadow roots) for OpenCMP / similar UIs.
DEEP_CLICK_ACCEPT_SHADOW_JS = """
        return (function () {
            function clickEl(el) {
                if (!el) return false;
                try {
                    el.click();
                } catch (e) {}
                try {
                    el.dispatchEvent(new MouseEvent("click", { bubbles: true, cancelable: true, view: window }));
                } catch (e) {}
                return true;
            }
            function walk(root) {
                if (!root) return false;
                try {
                    if (root.querySelectorAll) {
                        var hit = root.querySelector(".cmp-button-accept-all, [class*='cmp-button-accept-all']");
                        if (hit) return clickEl(hit);
                        var buttons = root.querySelectorAll("button, a[role='button'], [role='button'], a");
                        for (var i = 0; i < buttons.length; i++) {
                            var b = buttons[i];
                            var t = ((b.textContent || "") + "").replace(/\\s+/g, " ").trim().toLowerCase();
                            if ((t.indexOf("akzeptieren") >= 0 && t.indexOf("weiter") >= 0)
                                || t.indexOf("alle akzeptieren") >= 0
                                || t === "akzeptieren") {
                                return clickEl(b);
                            }
                        }
                    }
                } catch (e) {}
                var kids = root.children ? Array.prototype.slice.call(root.children) : [];
                for (var j = 0; j < kids.length; j++) {
                    var el = kids[j];
                    if (el.shadowRoot && walk(el.shadowRoot)) return true;
                    if (walk(el)) return true;
                }
                return false;
            }
            var cmp = document.querySelector(".cmp-root-container");
            if (cmp && walk(cmp)) return true;
            if (cmp && cmp.shadowRoot && walk(cmp.shadowRoot)) return true;
            return walk(document.body);
        })();
"""

FORCE_HIDE_CMP_OVERLAY_JS = """
        return (function () {
            var n = 0;
            var sels = [
                ".cmp-root-container",
                "#usercentrics-root",
                ".uc-embedding-container",
                "[id*='usercentrics']",
                ".fc-consent-root",
                ".fc-dialog-container"
            ];
            for (var i = 0; i < sels.length; i++) {
                try {
                    var list = document.querySelectorAll(sels[i]);
                    for (var j = 0; j < list.length; j++) {
                        var el = list[j];
                        el.style.setProperty("display", "none", "important");
                        el.style.setProperty("visibility", "hidden", "important");
                        el.style.setProperty("pointer-events", "none", "important");
                        n++;
                    }
                } catch (e) {}
            }
            try {
                document.body.style.overflow = "auto";
            } catch (e) {}
            return n;
        })();
"""

FIND_ACCEPT_BTN_JS = """
        function findAcceptInRoot(root) {
            if (!root) return null;
            try {
                var byClass = root.querySelector && (root.querySelector('.cmp-button-accept-all') || root.querySelector('[class*="cmp-button-accept-all"]'));
                if (byClass) return byClass;
            } catch (e) {}
            function walk(node) {
                if (!node) return null;
                if (node.nodeType === Node.ELEMENT_NODE) {
                    if (node.shadowRoot) {
                        var inShadow = findAcceptInRoot(node.shadowRoot);
                        if (inShadow) return inShadow;
                    }
                    for (var i = 0; i < node.children.length; i++) {
                        var r = walk(node.children[i]);
                        if (r) return r;
                    }
                }
                return null;
            }
            return walk(root);
        }
"""


def _default_log(email: str, message: str, level: str = "info") -> None:
    print(f"[{level.upper()}] {email}: {message}", flush=True)


def _try_selenium_shadow_accept(
    driver: Any,
    email: str,
    log_fn: Callable[[str, str, str], None],
) -> bool:
    """Selenium 4: pierce .cmp-root-container closed shadow root and click accept."""
    from selenium.webdriver.common.by import By

    try:
        host = driver.find_element(By.CSS_SELECTOR, ".cmp-root-container")
    except Exception:
        return False
    try:
        sr = host.shadow_root
    except Exception:
        return False
    selectors = (
        ".cmp-button-accept-all",
        '[class*="cmp-button-accept-all"]',
        'button[class*="accept"]',
        "button.cmp-button",
    )
    for sel in selectors:
        try:
            for el in sr.find_elements(By.CSS_SELECTOR, sel):
                try:
                    if el.is_displayed():
                        el.click()
                        log_fn(email, f"Clicked cookie accept (shadow_root selector {sel!r}).", "debug")
                        time.sleep(1)
                        return True
                except Exception:
                    continue
        except Exception:
            continue
    return False


def _cmp_overlay_visible(driver: Any) -> bool:
    from selenium.webdriver.common.by import By

    try:
        for el in driver.find_elements(By.CSS_SELECTOR, ".cmp-root-container"):
            try:
                if el.is_displayed():
                    return True
            except Exception:
                continue
    except Exception:
        pass
    return False


def force_hide_cmp_overlay(driver: Any, email: str, log_fn: Callable[[str, str, str], None]) -> bool:
    """Last resort: hide CMP host nodes so the login form is clickable (prefer real accept when possible)."""
    try:
        n = driver.execute_script(FORCE_HIDE_CMP_OVERLAY_JS.strip())
        if n and int(n) > 0:
            log_fn(
                email,
                f"CMP/cookie layer hidden via CSS fallback ({n} node(s)) so automation can continue.",
                "warning",
            )
            time.sleep(0.5)
            return True
    except Exception as e:
        log_fn(email, f"CMP hide fallback failed: {e}", "debug")
    return False


def click_accept_all_cookies_selenium(
    driver: Any,
    email: str,
    log_fn: Optional[Callable[[str, str, str], None]] = None,
) -> bool:
    """
    Selenium/Appium port of markt_user_init._click_accept_all_cookies.
    log_fn(email, message, level) — if None, prints to stdout.
    """
    from selenium.webdriver.common.by import By
    from selenium.webdriver.support import expected_conditions as EC
    from selenium.webdriver.support.ui import WebDriverWait

    log = log_fn or _default_log

    time.sleep(3)
    for _ in range(10):
        try:
            if _try_selenium_shadow_accept(driver, email, log):
                return True
        except Exception:
            pass
        try:
            if driver.execute_script(DEEP_CLICK_ACCEPT_SHADOW_JS.strip()) is True:
                log(email, "Clicked cookie accept (deep shadow walk).", "debug")
                time.sleep(1)
                return True
        except Exception:
            pass
        try:
            for el in driver.find_elements(By.CSS_SELECTOR, ".cmp-button-accept-all"):
                if el.is_displayed():
                    el.click()
                    log(email, "Clicked cookie accept (CSS .cmp-button-accept-all).", "debug")
                    time.sleep(1)
                    return True
        except Exception:
            pass
        try:
            xp = (
                "//*[contains(normalize-space(.), 'AKZEPTIEREN UND WEITER')]"
                " | //*[contains(normalize-space(.), 'Akzeptieren und weiter')]"
            )
            for el in driver.find_elements(By.XPATH, xp):
                if el.is_displayed():
                    el.click()
                    log(email, "Clicked cookie accept (XPath text).", "debug")
                    time.sleep(1)
                    return True
        except Exception:
            pass
        time.sleep(1)

    for _ in range(20):
        try:
            has_cmp = driver.execute_script(
                "return document.querySelector('.cmp-root-container') !== null",
            )
            if has_cmp is True:
                break
        except Exception:
            pass
        time.sleep(0.5)

    shadow_click_script = (
        FIND_ACCEPT_BTN_JS
        + """
        var cmp = document.querySelector('.cmp-root-container');
        var btn = cmp && cmp.shadowRoot ? findAcceptInRoot(cmp.shadowRoot) : null;
        if (!btn) btn = findAcceptInRoot(document.body);
        if (btn) {
            btn.focus();
            btn.click();
            try { btn.dispatchEvent(new MouseEvent('click', { bubbles: true, cancelable: true, view: window })); } catch (e) {}
            return true;
        }
        return false;
    """
    )
    for _ in range(20):
        try:
            clicked_now = driver.execute_script("return (function() {" + shadow_click_script + "})();")
            if clicked_now is True:
                log(email, "Clicked cookie accept (shadow DOM).", "debug")
                time.sleep(1)
                return True
        except Exception:
            pass
        time.sleep(0.5)

    try:
        tcf_ok = driver.execute_script(
            """
            return new Promise((resolve) => {
                if (typeof __tcfapi !== 'function') { resolve(false); return; }
                try {
                    __tcfapi('acceptAll', 2, (success) => { resolve(!!success); });
                    setTimeout(() => resolve(false), 1000);
                } catch (e) { resolve(false); }
            });
            """,
        )
        if tcf_ok is True:
            log(email, "Cookie accept via TCF API.", "debug")
            return True
    except Exception:
        pass

    text_click_script = (
        FIND_ACCEPT_BTN_JS
        + """
                    var cmp = document.querySelector('.cmp-root-container');
                    var btn = cmp && cmp.shadowRoot ? findAcceptInRoot(cmp.shadowRoot) : null;
                    if (!btn) btn = findAcceptInRoot(document.body);
                    if (btn) {
                        btn.focus();
                        btn.click();
                        try {
                            btn.dispatchEvent(new MouseEvent('click', { bubbles: true, cancelable: true, view: window }));
                        } catch (e) {}
                        return true;
                    }
                    var exact = ['AKZEPTIEREN UND WEITER', 'Akzeptieren und weiter', 'Accept and go on', 'Alle akzeptieren', 'Accept all'];
                    const norm = (s) => (s || '').replace(/\\s+/g, ' ').trim();
                    const matches = (el) => {
                        const t = norm(el.textContent || '');
                        if (exact.some(txt => t === txt || t.startsWith(txt) || t.includes(txt))) return true;
                        const lower = t.toLowerCase();
                        if (lower.includes('akzeptieren') && lower.includes('weiter')) return true;
                        return false;
                    };
                    const isClickable = (el) => {
                        if (!el || el.nodeType !== Node.ELEMENT_NODE) return false;
                        const tag = (el.tagName || '').toLowerCase();
                        const role = (el.getAttribute('role') || '').toLowerCase();
                        return tag === 'button' || tag === 'a' || role === 'button' || !!el.onclick;
                    };
                    const clickableParent = (el) => {
                        let p = el;
                        while (p && p !== document.body) {
                            if (isClickable(p)) return p;
                            p = p.parentElement;
                        }
                        return el;
                    };
                    const doClick = (el) => {
                        const toClick = isClickable(el) ? el : clickableParent(el);
                        toClick.click();
                        try {
                            toClick.dispatchEvent(new MouseEvent('click', { bubbles: true, cancelable: true, view: window }));
                        } catch (e) {}
                    };
                    function findInRoot(root) {
                        if (!root) return null;
                        const walk = (node) => {
                            if (!node) return null;
                            if (node.nodeType !== Node.ELEMENT_NODE) return null;
                            if (matches(node)) return node;
                            for (const c of node.children) {
                                const r = walk(c);
                                if (r) return r;
                            }
                            return null;
                        };
                        return walk(root);
                    }
                    function findInShadowRoots(root) {
                        let el = findInRoot(root);
                        if (el) return el;
                        const walk = (node) => {
                            if (!node) return null;
                            if (node.nodeType === Node.ELEMENT_NODE) {
                                if (node.shadowRoot) {
                                    const inner = findInShadowRoots(node.shadowRoot);
                                    if (inner) return inner;
                                }
                                for (const c of node.children) {
                                    const r = walk(c);
                                    if (r) return r;
                                }
                            }
                            return null;
                        };
                        return walk(root);
                    }
                    function tryDoc(doc) {
                        if (!doc || !doc.body) return false;
                        const cmp = doc.querySelector('.cmp-root-container');
                        let el = null;
                        if (cmp) {
                            el = findInRoot(cmp) || (cmp.shadowRoot ? findInShadowRoots(cmp.shadowRoot) : null);
                        }
                        if (!el) el = findInRoot(doc.body) || findInShadowRoots(doc.body);
                        if (el) { doClick(el); return true; }
                        return false;
                    }
                    if (tryDoc(document)) return true;
                    try {
                        for (let i = 0; i < document.querySelectorAll('iframe').length; i++) {
                            const doc = document.querySelectorAll('iframe')[i].contentDocument;
                            if (doc && tryDoc(doc)) return true;
                        }
                    } catch (e) {}
                    return false;
        """
    )

    for attempt in range(5):
        try:
            time.sleep(1)
            for selector in (
                ".cmp-button-accept-all",
                '[class*="cmp-button-accept-all"]',
                'div[role="button"].cmp-button-accept-all',
            ):
                try:
                    for el in driver.find_elements(By.CSS_SELECTOR, selector):
                        if el.is_displayed():
                            el.click()
                            log(email, "Clicked cookie accept (selector).", "debug")
                            time.sleep(1)
                            return True
                except Exception:
                    continue
            clicked = driver.execute_script("return (function() {" + text_click_script + "})();")
            if clicked is True:
                log(email, "Clicked cookie accept (by text).", "debug")
                time.sleep(1)
                return True
        except Exception as e:
            log(email, f"Cookie accept attempt {attempt + 1}: {e}", "debug")

    for by, selector in [
        (By.CSS_SELECTOR, "button[data-action='accept']"),
        (
            By.XPATH,
            "//button[contains(translate(., 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'alle akzeptieren')]",
        ),
        (
            By.XPATH,
            "//a[contains(translate(., 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'alle akzeptieren')]",
        ),
        (By.CSS_SELECTOR, "[data-testid='accept-cookies'], .cookie-accept, #accept-cookies, .accept-cookies"),
    ]:
        try:
            el = WebDriverWait(driver, 3).until(EC.presence_of_element_located((by, selector)))
            if el.is_displayed():
                el.click()
                log(email, "Clicked cookie consent (legacy selector).", "debug")
                return True
        except Exception:
            continue

    if _cmp_overlay_visible(driver) and force_hide_cmp_overlay(driver, email, log):
        return True

    try:
        diag = driver.execute_script(
            """return (function() {
                const cmp = document.querySelector('.cmp-root-container');
                const hasCmp = !!cmp;
                let hasShadow = false, shadowChildCount = 0;
                if (cmp && cmp.shadowRoot) {
                    hasShadow = true;
                    shadowChildCount = cmp.shadowRoot.childNodes.length;
                }
                return {
                    url: window.location.href,
                    hasCmp: hasCmp,
                    hasShadow: hasShadow,
                    shadowChildCount: shadowChildCount,
                    iframeCount: document.querySelectorAll('iframe').length,
                    bodyTextSnippet: (document.body && document.body.innerText || '').substring(0, 200)
                };
            })();""",
        )
        log(email, f"Cookie accept diagnostic: {diag}", "debug")
    except Exception as e:
        log(email, f"Cookie accept diagnostic failed: {e}", "debug")
    if _cmp_overlay_visible(driver) and force_hide_cmp_overlay(driver, email, log):
        return True
    log(email, "Cookie accept not found after retries (may already be accepted).", "debug")
    return False


def dismiss_cmp_if_blocking(driver: Any, email: str, log_fn: Optional[Callable[[str, str, str], None]] = None) -> None:
    """If the CMP host is still visible (e.g. accept click missed), hide it so form interactions work."""
    log = log_fn or _default_log
    if _cmp_overlay_visible(driver):
        force_hide_cmp_overlay(driver, email, log)
