"""京东 PC 搜索列表解析（需有效 Cookie）。失败时交由调用方换 Cookie 重试。"""
from __future__ import annotations

import json
import os
import re
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import quote

from curl_cffi import requests
from bs4 import BeautifulSoup

from .proxy_pool import ProxyPool

DEFAULT_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)
SEARCH_URL = "https://search.jd.com/Search"
PRICE_URL = "https://p.3.cn/prices/mgets"

_TRUST_ENV = os.getenv("JD_REQUEST_TRUST_ENV", "").strip().lower() in ("1", "true", "yes", "on")
# 新版搜索页为 SPA，无 Playwright 时往往解析不到商品；设为 0 可关闭（仅调试用）
_USE_PLAYWRIGHT = os.getenv("JD_SEARCH_USE_PLAYWRIGHT", "1").strip().lower() not in ("0", "false", "no", "off")
# TLS 指纹伪装目标浏览器版本
_IMPERSONATE = os.getenv("JD_TLS_IMPERSONATE", "chrome120").strip()
# 爬虫请求是否走代理（默认关闭，代理可能导致 p.3.cn 等 CDN 不可达）
_USE_PROXY = os.getenv("JD_SEARCH_USE_PROXY", "0").strip().lower() in ("1", "true", "yes", "on")
# 随机延迟（秒）
_DELAY_MIN = float(os.getenv("JD_DELAY_MIN", "1.0"))
_DELAY_MAX = float(os.getenv("JD_DELAY_MAX", "3.0"))
# 预热链（默认关闭）
_PREHEAT = os.getenv("JD_PREHEAT", "0").strip().lower() in ("1", "true", "yes", "on")
_PREHEAT_SKUS = [
    "100012043978", "100008348542", "100025828884",
    "100005847385", "100014891026", "100009737068",
]


def _random_delay(tag: str = "") -> None:
    import random, time
    s = random.uniform(_DELAY_MIN, _DELAY_MAX)
    print(f"[jd-search] delay {s:.1f}s ({tag})" if tag else f"[jd-search] delay {s:.1f}s")
    time.sleep(s)


def _preheat_cookie(
    cookie_str: str,
    *,
    ua: str = DEFAULT_UA,
    proxy_pool: Optional[ProxyPool] = None,
    random_proxy: bool = False,
) -> None:
    """预热 Cookie: 先逛首页再逛商品页，模拟真人浏览路径。"""
    import random
    session = requests.Session()
    session.trust_env = _TRUST_ENV
    session.headers.update({
        "User-Agent": ua,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "zh-CN,zh;q=0.9",
    })
    session.cookies.update(cookie_str_to_dict(cookie_str))
    if _USE_PROXY and proxy_pool and proxy_pool.count > 0:
        proxies = proxy_pool.get_random_proxies_dict() if random_proxy else proxy_pool.get_proxies_dict()
    else:
        proxies = None

    _random_delay("preheat-home")
    try:
        session.get("https://m.jd.com/", timeout=15, proxies=proxies, impersonate=_IMPERSONATE)
        print("[jd-search] preheat ok: m.jd.com")
    except Exception as exc:
        print(f"[jd-search] preheat skip m.jd.com: {exc}")

    sku = random.choice(_PREHEAT_SKUS)
    _random_delay("preheat-item")
    try:
        session.get(
            f"https://item.m.jd.com/product/{sku}.html",
            timeout=15, proxies=proxies, impersonate=_IMPERSONATE,
        )
        print(f"[jd-search] preheat ok: item {sku}")
    except Exception as exc:
        print(f"[jd-search] preheat skip item: {exc}")

    _random_delay("preheat-search")


def cookie_str_to_dict(cookie_str: str) -> Dict[str, str]:
    out: Dict[str, str] = {}
    for part in cookie_str.split(";"):
        part = part.strip()
        if not part or "=" not in part:
            continue
        k, v = part.split("=", 1)
        out[k.strip()] = v.strip()
    return out


def _parse_jsonp_prices(text: str) -> List[dict]:
    text = text.strip()
    if "(" not in text or ")" not in text:
        return []
    inner = text[text.find("(") + 1 : text.rfind(")")]
    return json.loads(inner)


def fetch_prices_for_skus(
    sku_list: List[str],
    cookie_str: str = "",
    *,
    ua: str = DEFAULT_UA,
    proxy_pool: Optional[ProxyPool] = None,
) -> Dict[str, str]:
    """拉取京东价格（p.3.cn 是 CDN 公开接口，不需要 Cookie / TLS 伪装）。"""
    if not sku_list:
        return {}
    session = requests.Session()
    session.trust_env = _TRUST_ENV
    session.headers.update(
        {
            "User-Agent": ua,
            "Referer": "https://item.jd.com/",
            "Accept": "*/*",
        }
    )
    # p.3.cn 无需 Cookie（跨域发送反而可能被拦截），也不走代理/指纹
    sku_param = ",".join(f"J_{s}" for s in sku_list)
    try:
        r = session.get(
            PRICE_URL,
            params={"skuIds": sku_param, "type": "1"},
            timeout=15,
        )
        r.raise_for_status()
        data = _parse_jsonp_prices(r.text)
    except Exception as exc:
        print(f"[jd-search] 价格接口异常: {exc}")
        return {}
    out: Dict[str, str] = {}
    for item in data:
        iid = str(item.get("id", ""))
        sku = iid.replace("J_", "") if iid else ""
        if sku:
            out[sku] = str(item.get("p", ""))
    return out


def _parse_search_html(html: str) -> List[Dict[str, str]]:
    soup = BeautifulSoup(html, "html.parser")
    items: List[Dict[str, str]] = []
    for li in soup.select("li.gl-item"):
        sku = (li.get("data-sku") or "").strip()
        if not sku:
            continue
        title = ""
        name_a = li.select_one(".p-name a")
        if name_a:
            title = name_a.get_text(strip=True) or (name_a.get("title") or "").strip()
        items.append(
            {
                "sku": sku,
                "title": title,
                "url": f"https://item.jd.com/{sku}.html",
            }
        )
    if items:
        return items

    seen: set[str] = set()
    fallback: List[Dict[str, str]] = []
    for sku in re.findall(r'data-sku="(\d+)"', html):
        if sku in seen:
            continue
        seen.add(sku)
        fallback.append(
            {"sku": sku, "title": "", "url": f"https://item.jd.com/{sku}.html"}
        )
    return fallback


def _is_spa_search_shell(html: str) -> bool:
    """京东 PC 搜索 React 壳页面：HTTP 200 但无服务端商品 DOM。"""
    if len(html) < 8000:
        return False
    return "search-pc-java" in html or "retail-mall/main_search" in html


def _looks_like_risk_page(html: str) -> bool:
    return (
        "京东验证" in html
        or "JDR_shields" in html
        or "risk_handler" in html
        or "privatedomain/risk_handler" in html
    )


def _cookies_for_playwright(cookie_dict: Dict[str, str]) -> List[Dict[str, str]]:
    out: List[Dict[str, str]] = []
    for name, value in cookie_dict.items():
        if not name or value is None:
            continue
        out.append({"name": name, "value": str(value), "domain": ".jd.com", "path": "/"})
    return out


def _try_playwright_search(
    keyword: str,
    page: int,
    cookie_str: str,
    *,
    ua: str,
    timeout_ms: int = 45000,
) -> Tuple[List[Dict[str, str]], Dict[str, str]]:
    """用 Chromium 打开搜索页，返回 (items, price_map)。"""
    if not _USE_PLAYWRIGHT:
        return [], {}
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        return [], {}

    kw_q = quote(keyword)
    url = f"https://search.jd.com/Search?keyword={kw_q}&wq={kw_q}&enc=utf-8&page={max(1, page)}"
    cookies = _cookies_for_playwright(cookie_str_to_dict(cookie_str))
    wait_ms = int(os.getenv("JD_PLAYWRIGHT_WAIT_MS", "5000"))
    item_pat = re.compile(r"item\.jd\.com/(\d+)\.html", re.I)
    pid_pat = re.compile(r"[?&]pid=(\d+)", re.I)

    items: List[Dict[str, str]] = []
    price_map: Dict[str, str] = {}
    seen: set[str] = set()

    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=True,
            args=["--disable-blink-features=AutomationControlled"],
        )
        try:
            context = browser.new_context(
                user_agent=ua,
                locale="zh-CN",
                viewport={"width": 1365, "height": 900},
            )
            if cookies:
                context.add_cookies(cookies)
            pg = context.new_page()
            pg.goto(url, wait_until="domcontentloaded", timeout=timeout_ms)

            # 被重定向到登录页则直接返回
            if "passport.jd.com" in pg.url or "login.jd.com" in pg.url:
                print(f"[jd-search] Playwright 被重定向到登录页，Cookie 可能已失效")
                return [], {}

            pg.wait_for_timeout(wait_ms)
            try:
                pg.wait_for_selector("a[href*='item.jd.com']", timeout=12000)
            except Exception:
                pass

            # 从渲染后的 DOM 提取商品 SKU / 标题 / 价格
            result = pg.evaluate(
                """() => {
                  var items = [];
                  var prices = {};
                  var seen = new Set();

                  // Collect product links
                  var links = document.querySelectorAll('a[href]');
                  for (var i = 0; i < links.length; i++) {
                    var h = links[i].getAttribute('href') || '';
                    if (!(h.indexOf('item.jd.com') > -1 || h.indexOf('chat.jd.com') > -1 || h.indexOf('pid=') > -1)) continue;
                    if (seen.has(h)) continue;
                    seen.add(h);

                    var sku = '';
                    var m1 = h.match(/item\\.jd\\.com\\/(\\d+)\\.html/i);
                    if (m1) { sku = m1[1]; }
                    else {
                      var m2 = h.match(/[?&]pid=(\\d+)/i);
                      if (m2) sku = m2[1];
                    }
                    if (!sku) continue;

                    var title = '';
                    if (h.indexOf('chat.jd.com') > -1) {
                      try {
                        var u = h.indexOf('//') === 0 ? 'https:' + h : h;
                        var q = new URL(u).searchParams;
                        title = decodeURIComponent(q.get('wname') || '');
                      } catch(e) {}
                    }
                    items.push({ sku: sku, title: title, url: 'https://item.jd.com/' + sku + '.html' });
                  }

                  // ---- 价格提取（多策略兜底） ----
                  function isPriceNum(n) { return n > 0.5 && n < 500000; }

                  // 策略1: data-sku 元素内提取任何像价格的数字
                  var skuCards = document.querySelectorAll('[data-sku]');
                  for (var i = 0; i < skuCards.length; i++) {
                    var card = skuCards[i];
                    var sku = card.getAttribute('data-sku');
                    if (!sku || prices[sku]) continue;
                    var txt = card.textContent || '';
                    // 匹配 ¥12.34 或 12.34 元 或纯数字（两三位到六位数，可选小数）
                    var nums = txt.match(/\d{2,6}(?:\.\d{1,2})?/g);
                    if (nums) {
                      for (var ni = 0; ni < nums.length; ni++) {
                        var nv = parseFloat(nums[ni]);
                        if (isPriceNum(nv)) { prices[sku] = '' + nv; break; }
                      }
                    }
                  }

                  // 策略2: 叶子节点找价格，向上8层找 data-sku 关联
                  var allEls = document.querySelectorAll('*');
                  for (var j = 0; j < allEls.length; j++) {
                    var el = allEls[j];
                    if (el.children.length > 0) continue;
                    var tn = (el.textContent || '').trim();
                    // 严格匹配: 整段文字就是价格
                    var pm = tn.match(/^(\d{2,6})(?:\.(\d{1,2}))?$/);
                    if (!pm) pm = tn.match(/^[¥￥]\s*(\d{2,6}(?:\.\d{1,2})?)\s*$/);
                    if (!pm) continue;
                    var priceVal = parseFloat(pm[1] + (pm[2] ? '.' + pm[2] : ''));
                    if (!isPriceNum(priceVal)) continue;
                    var p = el.parentElement;
                    var found = '';
                    for (var k = 0; k < 8 && p; k++) {
                      var ds = p.getAttribute && p.getAttribute('data-sku');
                      if (ds) { found = ds; break; }
                      p = p.parentElement;
                    }
                    if (found && !prices[found]) prices[found] = '' + priceVal;
                  }

                  // 策略3: 正文中在 SKU 附近搜价格数字
                  if (Object.keys(prices).length < items.length) {
                    var bodyText = document.body.innerText || '';
                    for (var si2 = 0; si2 < items.length; si2++) {
                      var sk2 = items[si2].sku;
                      if (prices[sk2]) continue;
                      var idx2 = bodyText.indexOf(sk2);
                      if (idx2 === -1) continue;
                      var chunk2 = bodyText.substring(Math.max(0, idx2 - 80), idx2 + sk2.length + 80);
                      var cm2 = chunk2.match(/\d{2,6}(?:\.\d{1,2})?/g);
                      if (cm2) {
                        for (var ni2 = 0; ni2 < cm2.length; ni2++) {
                          var nv2 = parseFloat(cm2[ni2]);
                          if (isPriceNum(nv2)) { prices[sk2] = '' + nv2; break; }
                        }
                      }
                    }
                  }

                  // 策略4: TreeWalker + 位置关联 — 扫描所有叶子文本，与 SKU 链接按垂直距离匹配
                  var remaining4 = [];
                  for (var ri3 = 0; ri3 < items.length; ri3++) {
                    if (!prices[items[ri3].sku]) remaining4.push(items[ri3].sku);
                  }
                  if (remaining4.length > 0) {
                    var tw = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
                    var priceNodes4 = [];
                    var tx;
                    while ((tx = tw.nextNode()) !== null) {
                      var txt4 = (tx.textContent || '').trim();
                      var pm4 = txt4.match(/^(\d{2,6}(?:\.\d{1,2})?)$/);
                      if (!pm4) pm4 = txt4.match(/^[¥￥]\s*(\d{2,6}(?:\.\d{1,2})?)\s*$/);
                      if (!pm4) continue;
                      var pv4 = parseFloat(pm4[1]);
                      if (!isPriceNum(pv4)) continue;
                      var pe4 = tx.parentElement;
                      var r4 = pe4 && pe4.getBoundingClientRect ? pe4.getBoundingClientRect() : null;
                      if (r4 && r4.top > 0) priceNodes4.push({ price: '' + pv4, top: r4.top });
                    }
                    var skuPos4 = [];
                    for (var ri4 = 0; ri4 < remaining4.length; ri4++) {
                      var s4 = remaining4[ri4];
                      var el4 = document.querySelector('a[href*="item.jd.com/' + s4 + '.html"]');
                      if (el4 && el4.getBoundingClientRect) {
                        var br = el4.getBoundingClientRect();
                        skuPos4.push({ sku: s4, top: br.top });
                      }
                    }
                    for (var si4 = 0; si4 < skuPos4.length; si4++) {
                      var sp = skuPos4[si4];
                      var bestP = '', bestD = 500;
                      for (var pi4 = 0; pi4 < priceNodes4.length; pi4++) {
                        var pp = priceNodes4[pi4];
                        var d4 = Math.abs(sp.top - pp.top);
                        if (d4 < bestD) { bestD = d4; bestP = pp.price; }
                      }
                      if (bestP) prices[sp.sku] = bestP;
                    }
                  }

                  return { items: items, prices: prices };
                }"""
            )
            raw_items = (result or {}).get("items", []) if isinstance(result, dict) else []
            pw_prices = (result or {}).get("prices", {}) if isinstance(result, dict) else {}

            for ri in raw_items:
                sku = str(ri.get("sku", ""))
                if not sku or sku in seen:
                    continue
                seen.add(sku)
                items.append(
                    {
                        "sku": sku,
                        "title": str(ri.get("title", "")),
                        "url": f"https://item.jd.com/{sku}.html",
                    }
                )
            for sku, price in pw_prices.items():
                price_map[str(sku)] = str(price)

            # 极少情况：DOM 选择器未命中，回退到从 HTML 源码用正则提取
            if len(items) < 3:
                body = pg.content()
                for m in item_pat.finditer(body):
                    sku = m.group(1)
                    if sku not in seen:
                        seen.add(sku)
                        items.append({"sku": sku, "title": "", "url": f"https://item.jd.com/{sku}.html"})
                for m in pid_pat.finditer(body):
                    sku = m.group(1)
                    if len(sku) < 5 or sku in seen:
                        continue
                    seen.add(sku)
                    items.append({"sku": sku, "title": "", "url": f"https://item.jd.com/{sku}.html"})
        finally:
            browser.close()
    return items, price_map


def _looks_blocked(status_code: int, html: str, final_url: str) -> bool:
    if status_code in (401, 403):
        return True
    low = html[:8000].lower()
    if "passport.jd.com" in final_url or "login.jd.com" in final_url:
        return True
    if "安全验证" in html or "请登录" in html[:3000]:
        return True
    if _looks_like_risk_page(html):
        return True
    return False


def search_keyword(
    keyword: str,
    cookie_str: str,
    *,
    page: int = 1,
    fetch_prices: bool = True,
    ua: str = DEFAULT_UA,
    timeout: float = 20.0,
    proxy_pool: Optional[ProxyPool] = None,
    random_proxy: bool = False,
) -> Dict[str, Any]:
    session = requests.Session()
    session.trust_env = _TRUST_ENV
    session.headers.update(
        {
            "User-Agent": ua,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "zh-CN,zh;q=0.9",
            "Referer": "https://www.jd.com/",
        }
    )
    session.cookies.update(cookie_str_to_dict(cookie_str))
    if _USE_PROXY and proxy_pool and proxy_pool.count > 0:
        proxies = proxy_pool.get_random_proxies_dict() if random_proxy else proxy_pool.get_proxies_dict()
    else:
        proxies = None
    kw = keyword
    params = {"keyword": kw, "wq": kw, "enc": "utf-8", "page": max(1, page)}
    try:
        resp = session.get(SEARCH_URL, params=params, timeout=timeout, proxies=proxies, impersonate=_IMPERSONATE)
    except requests.RequestsError as exc:
        return {
            "ok": False,
            "blocked": False,
            "status_code": 0,
            "keyword": keyword,
            "page": page,
            "products": [],
            "final_url": "",
            "error": "request_failed",
            "message": str(exc),
        }
    try:
        resp.encoding = resp.apparent_encoding or "utf-8"
    except AttributeError:
        resp.encoding = resp.encoding or "utf-8"
    html = resp.text
    final_url = str(resp.url)
    blocked = _looks_blocked(resp.status_code, html, final_url)
    products = [] if blocked else _parse_search_html(html)
    render_source = "requests"

    seen: set[str] = set()
    unique: List[Dict[str, Any]] = []
    for p in products:
        if p["sku"] in seen:
            continue
        seen.add(p["sku"])
        unique.append(dict(p))

    pw_price_map: Dict[str, str] = {}
    spa_shell = not blocked and resp.status_code == 200 and not unique and _is_spa_search_shell(html)
    if spa_shell:
        pw_list, pw_price_map = _try_playwright_search(keyword, page, cookie_str, ua=ua)
        if pw_list:
            for p in pw_list:
                if p["sku"] in seen:
                    continue
                seen.add(p["sku"])
                unique.append(dict(p))
            render_source = "playwright"
        elif _USE_PLAYWRIGHT:
            try:
                import playwright  # noqa: F401
            except ImportError:
                pass  # hint below

    price_map: Dict[str, str] = {}
    if fetch_prices and unique and not blocked:
        try:
            batch = [p["sku"] for p in unique[:60]]
            price_map = fetch_prices_for_skus(batch, cookie_str, ua=ua, proxy_pool=proxy_pool)
        except Exception:
            price_map = {}

        # p.3.cn 不可达时，回落到 Playwright 从搜索页提取的价格
        if not price_map and pw_price_map:
            price_map = pw_price_map
        elif not price_map and not pw_price_map and not spa_shell:
            # 当前请求拿到了 HTML 商品列表但价格 API 不可达，且也没走 Playwright 搜索路径；
            # 再开一次 Playwright 专门拿价格（仅取前 30 个 SKU 避免太慢）
            try:
                from playwright.sync_api import sync_playwright as _pw  # noqa: F401
            except ImportError:
                pass
            else:
                _, pw_prices = _try_playwright_search(keyword, page, cookie_str, ua=ua)
                if pw_prices:
                    price_map = pw_prices
                    print(f"[jd-search] 价格 API 不可达，已通过 Playwright 提取 {len(pw_prices)} 条价格")

    for p in unique:
        p["price"] = price_map.get(p["sku"], "")

    out: Dict[str, Any] = {
        "ok": not blocked and resp.status_code == 200 and (bool(unique) or not spa_shell),
        "blocked": blocked,
        "status_code": resp.status_code,
        "keyword": keyword,
        "page": page,
        "products": unique,
        "final_url": final_url,
        "render_source": render_source,
    }
    if spa_shell and not unique:
        out["ok"] = False
        out["error"] = "spa_empty"
        try:
            import playwright  # noqa: F401
        except ImportError:
            out["hint"] = (
                "当前京东搜索为前端渲染，requests 拿不到商品列表。请安装: pip install playwright && playwright install chromium"
            )
        else:
            out["hint"] = (
                "已安装 Playwright 但仍无数据：可能需更长等待或页面结构变化。"
                "可尝试增大环境变量 JD_PLAYWRIGHT_WAIT_MS（默认 5000）。"
            )
    return out


def search_with_pool(
    pool: Any,
    keyword: str,
    *,
    page: int = 1,
    fetch_prices: bool = True,
    proxy_pool: Optional[ProxyPool] = None,
    random_pick: bool = False,
) -> Dict[str, Any]:
    """
    使用池内 Cookie 轮询/随机：依次尝试，直至成功解析到商品或判定未拦截。
    pool: JDCookiePool 实例，需实现 .cookies / .get_cookie() / .get_random_cookie()
    """
    cookies: List[str] = getattr(pool, "cookies", []) or []
    n = len(cookies)
    if n == 0:
        return {"ok": False, "error": "cookie_pool_empty", "products": [], "attempts": 0}

    if random_pick:
        import random as _random
        indices = list(range(n))
        _random.shuffle(indices)
        ordered_cookies = [cookies[i] for i in indices]
    else:
        ordered_cookies = list(cookies)

    last: Optional[Dict[str, Any]] = None
    for attempt in range(n):
        if attempt > 0:
            _random_delay("retry")
        if random_pick:
            cookie_str = pool.get_random_cookie()
        else:
            cookie_str = pool.get_cookie()

        if _PREHEAT:
            _preheat_cookie(
                cookie_str,
                ua=getattr(pool, "ua", DEFAULT_UA),
                proxy_pool=proxy_pool,
                random_proxy=random_pick,
            )

        last = search_keyword(
            keyword,
            cookie_str,
            page=page,
            fetch_prices=fetch_prices,
            ua=getattr(pool, "ua", DEFAULT_UA),
            proxy_pool=proxy_pool,
            random_proxy=random_pick,
        )
        last["attempts"] = attempt + 1
        if last.get("error") == "request_failed":
            continue
        if last.get("blocked"):
            continue
        if last.get("status_code") != 200:
            continue
        if last.get("error") == "spa_empty":
            continue
        if last.get("products"):
            return last
        # 200 但无商品（旧逻辑会误报成功）；换下一个 Cookie 再试
        continue

    if last is not None:
        last.setdefault("ok", False)
        if last.get("error") == "request_failed":
            last.setdefault(
                "hint",
                "访问京东失败（常见为系统 HTTP_PROXY/HTTPS_PROXY 指向无效代理）。"
                "爬虫请求已默认不走环境代理；若必须走代理请在 .env 设置 JD_REQUEST_TRUST_ENV=1 并配置正确代理。"
            )
        return last
    return {"ok": False, "error": "no_attempt", "products": [], "attempts": 0}


def search_playwright_direct(
    pool: Any,
    keyword: str,
    *,
    page: int = 1,
    timeout_ms: int = 60000,
    proxy_pool: Optional[ProxyPool] = None,
    random_proxy: bool = False,
) -> Dict[str, Any]:
    """
    Playwright 直搜模式：最多尝试 3 条 Cookie，直接从浏览器渲染的 DOM 提取商品和价格。
    """
    if not _USE_PLAYWRIGHT:
        return {"ok": False, "error": "playwright_disabled", "products": [], "attempts": 0}

    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        return {"ok": False, "error": "playwright_not_installed", "products": [], "attempts": 0}

    ua = getattr(pool, "ua", DEFAULT_UA)
    cookie_list = getattr(pool, "cookies", []) or []
    if not cookie_list:
        return {"ok": False, "error": "cookie_pool_empty", "products": [], "attempts": 0}

    kw_q = quote(keyword)
    url = f"https://search.jd.com/Search?keyword={kw_q}&wq={kw_q}&enc=utf-8&page={max(1, page)}"
    wait_ms = int(os.getenv("JD_PLAYWRIGHT_WAIT_MS", "5000"))

    tried = 0
    skipped = 0
    total_cookies = len(cookie_list)

    while tried < 3 and skipped < total_cookies:
        cookie_str = pool.get_cookie()
        skipped += 1
        # 快速检测：访问京东订单页判断是否跳登录
        if pool.cookie_str_to_dict(cookie_str).get("pin", ""):
            try:
                test_sess = requests.Session()
                test_sess.cookies.update(pool.cookie_str_to_dict(cookie_str))
                test_r = test_sess.get(
                    "https://order.jd.com/center/list.action",
                    headers={"User-Agent": ua},
                    timeout=8,
                    allow_redirects=False,
                    impersonate=_IMPERSONATE,
                )
                if test_r.status_code == 302 and "passport" in test_r.headers.get("Location", ""):
                    print(f"[jd-search] direct skip cookie: expired")
                    continue
            except Exception:
                pass
        tried += 1

        try:
            with sync_playwright() as p:
                browser = p.chromium.launch(
                    headless=True,
                    args=[
                        "--disable-blink-features=AutomationControlled",
                        "--disable-features=IsolateOrigins,site-per-process",
                        "--no-sandbox",
                        "--disable-setuid-sandbox",
                        "--disable-infobars",
                        "--disable-dev-shm-usage",
                        "--disable-web-security",
                        "--disable-features=VizDisplayCompositor",
                        "--disable-gpu",
                    ],
                )
                try:
                    vw = 1365 + (hash(cookie_str) % 41)  # 1365-1405 随机
                    vh = 900 + (hash(cookie_str + "h") % 51)  # 900-950 随机
                    ctx_kwargs: Dict[str, Any] = {
                        "user_agent": ua,
                        "locale": "zh-CN",
                        "viewport": {"width": vw, "height": vh},
                    }
                    # 走代理切换出口 IP
                    if _USE_PROXY and proxy_pool and proxy_pool.count > 0:
                        proxy_url = proxy_pool.get_random_proxy() if random_proxy else proxy_pool.get_proxy()
                        if proxy_url:
                            ctx_kwargs["proxy"] = {"server": proxy_url}
                            print(f"[jd-search] direct via proxy: {proxy_url[:50]}")
                    context = browser.new_context(**ctx_kwargs)
                    pw_cookies = _cookies_for_playwright(cookie_str_to_dict(cookie_str))
                    if pw_cookies:
                        context.add_cookies(pw_cookies)
                    pg = context.new_page()

                    # 去除 navigator.webdriver 特征
                    pg.add_init_script("""
                        Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
                        Object.defineProperty(navigator, 'plugins', { get: () => [1, 2, 3, 4, 5] });
                        Object.defineProperty(navigator, 'languages', { get: () => ['zh-CN', 'zh', 'en'] });
                        window.chrome = { runtime: {} };
                    """)

                    # 暖机：访问京东首页，模拟真人浏览
                    try:
                        pg.goto("https://www.jd.com/", wait_until="domcontentloaded", timeout=20000)
                        pg.wait_for_timeout(2000 + (hash(cookie_str) % 2000))
                        # 随机滚动
                        pg.evaluate("() => window.scrollBy(0, 200 + Math.random() * 400)")
                        pg.wait_for_timeout(500 + (hash(cookie_str + "s") % 1000))
                        print("[jd-search] direct warmup ok")
                    except Exception:
                        pass

                    pg.goto(url, wait_until="domcontentloaded", timeout=timeout_ms)
                    # 模拟真人等页面渲染
                    pg.wait_for_timeout(wait_ms)
                    pg.evaluate("() => window.scrollBy(0, 100 + Math.random() * 200)")
                    pg.wait_for_timeout(1000)

                    final_url = pg.url
                    if "passport.jd.com" in final_url or "login.jd.com" in final_url:
                        browser.close()
                        print(f"[jd-search] direct: cookie expired, retry")
                        continue

                    if "risk_handler" in final_url:
                        browser.close()
                        print(f"[jd-search] direct: risk blocked, retry")
                        continue

                    try:
                        pg.wait_for_selector(
                            "a[href*='item.jd.com'], .price-int, .gl-item", timeout=15000
                        )
                    except Exception:
                        pass

                    # ---- 浏览器 DOM 提取商品 + 价格 ----
                    result = pg.evaluate("""() => {
                      var products = [], seenSkus = new Set();
                      var cards = document.querySelectorAll('li.gl-item, [data-sku]');
                      if (cards.length === 0) {
                        cards = document.querySelectorAll('[data-sku]');
                      }
                      if (cards.length === 0) {
                        var links = document.querySelectorAll('a[href*="item.jd.com"]');
                        for (var li = 0; li < links.length; li++) {
                          var el = links[li];
                          var h = el.getAttribute('href') || '';
                          var m = h.match(/item\\.jd\\.com\\/(\\d+)\\.html/i);
                          if (!m) continue;
                          var sku = m[1];
                          if (seenSkus.has(sku)) continue;
                          seenSkus.add(sku);
                          products.push({
                            sku: sku,
                            title: (el.getAttribute('title') || el.textContent || '').trim().substring(0, 200),
                            url: 'https://item.jd.com/' + sku + '.html',
                            price: ''
                          });
                        }
                      }
                      for (var ci = 0; ci < cards.length; ci++) {
                        var card = cards[ci];
                        var sku = (card.getAttribute && card.getAttribute('data-sku')) || '';
                        if (!sku) {
                          var a = card.querySelector('a[href*="item.jd.com"]');
                          if (a) { var m2 = (a.getAttribute('href')||'').match(/item\\.jd\\.com\\/(\\d+)\\.html/i); if (m2) sku = m2[1]; }
                        }
                        if (!sku || seenSkus.has(sku)) continue;
                        seenSkus.add(sku);
                        var title = '';
                        var tEl = card.querySelector('.p-name a, .p-name em, [class*="title"], a[title]');
                        if (tEl) title = (tEl.getAttribute('title') || tEl.textContent || '').trim().substring(0, 200);
                        var price = '';
                        var intEl = card.querySelector('.price-int');
                        if (intEl) {
                          price = (intEl.textContent||'').trim().replace(/[^.\\d]/g,'');
                          var decEl = card.querySelector('.price-decimal');
                          if (decEl) price += '.' + (decEl.textContent||'').trim().replace(/[^\\d]/g,'');
                        }
                        if (!price) {
                          var prEl = card.querySelector('[class*="price"]');
                          if (prEl) { var pm=(prEl.textContent||'').match(/(\\d{2,6}(?:\\.\\d{1,2})?)/); if(pm) price=pm[1]; }
                        }
                        products.push({sku:sku,title:title,url:'https://item.jd.com/'+sku+'.html',price:price});
                      }
                      return products;
                    }""")

                    parsed: List[Dict[str, Any]] = []
                    seen: set = set()
                    for ri in (result or []):
                        s = str(ri.get("sku", ""))
                        if not s or s in seen:
                            continue
                        seen.add(s)
                        parsed.append({
                            "sku": s,
                            "title": str(ri.get("title", "")),
                            "url": str(ri.get("url", "")),
                            "price": str(ri.get("price", "")),
                        })
                    browser.close()

                    if parsed:
                        return {
                            "ok": True,
                            "blocked": False,
                            "status_code": 200,
                            "keyword": keyword,
                            "page": page,
                            "products": parsed,
                            "final_url": final_url,
                            "render_source": "playwright-direct",
                            "attempts": tried,
                        }
                    else:
                        print(f"[jd-search] direct: 0 products from page, retry")
                        continue

                except Exception as exc:
                    try: browser.close()
                    except Exception: pass
                    print(f"[jd-search] direct browser error: {exc}")
                    continue

        except Exception as exc:
            print(f"[jd-search] direct playwright error: {exc}")
            continue

    return {
        "ok": False,
        "error": "all_attempts_failed",
        "blocked": False,
        "products": [],
        "attempts": tried,
    }
