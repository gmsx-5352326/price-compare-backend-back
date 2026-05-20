"""
DrissionPage 京东搜索 —— 一键式方案。

首次：浏览器打开 → 用户在浏览器中登录京东 → 关闭浏览器 → 点击搜索
之后：点击搜索 → 自动关闭弹窗 → 搜索 → 提取 → 返回

核心：持久化浏览器配置（.drission-profile），登录态保留，之后一键完成。
"""
from __future__ import annotations

import os
import random
import re
import time
from pathlib import Path
from typing import Any, Dict, List, Set

from DrissionPage import ChromiumOptions, ChromiumPage
from DrissionPage.common import Keys

_MAX_PAGES = int(os.getenv("JD_DRISSION_MAX_PAGES", "3"))
_PROFILE_DIR = Path(__file__).resolve().parent.parent / ".drission-profile"


def _sleep(tag: str = "") -> None:
    s = random.uniform(1.0, 7.0)
    print(f"[jd-drission] {s:.1f}s {tag}" if tag else "")
    time.sleep(s)


def _ensure_profile() -> ChromiumOptions:
    _PROFILE_DIR.mkdir(parents=True, exist_ok=True)
    co = ChromiumOptions()
    co.set_user_data_path(str(_PROFILE_DIR))
    co.auto_port()
    co.set_argument("--no-sandbox")
    return co


def search_with_drission(keyword: str, *, max_pages: int = _MAX_PAGES) -> Dict[str, Any]:
    """一键搜索京东。"""
    all_products: List[Dict[str, Any]] = []
    seen: Set[str] = set()
    page_num = 1

    try:
        co = _ensure_profile()
        dp = ChromiumPage(addr_or_opts=co)
    except Exception as e:
        return {"ok": False, "error": f"浏览器启动失败: {e}", "products": []}

    try:
        # ---- Step 1: 打开京东 ----
        dp.get("https://www.jd.com/")
        _sleep("首页加载")

        # ---- Step 2: 等待登录（如有弹窗则等用户登录后自动继续） ----
        waited = 0
        while True:
            try:
                close_btn = dp.ele("css:#login2025-dialog-close", timeout=3)
            except Exception:
                # 浏览器可能被用户关闭
                return {"ok": False, "error": "browser_closed", "hint": "浏览器已关闭，请重试", "products": []}

            if close_btn:
                if waited == 0:
                    print("[jd-drission] 检测到登录弹窗，请在浏览器中登录京东")
                if waited >= 180:
                    try:
                        dp.quit()
                    except Exception:
                        pass
                    return {"ok": False, "error": "login_timeout", "hint": "登录超时（3分钟），请重试", "products": []}
                print(f"[jd-drission] 等待登录… {waited}s")
                time.sleep(3)
                waited += 3
                continue

            # 可能跳转到登录页
            if "passport" in dp.url:
                if waited == 0:
                    print("[jd-drission] 跳转到登录页，请在浏览器中登录京东")
                if waited >= 180:
                    try:
                        dp.quit()
                    except Exception:
                        pass
                    return {"ok": False, "error": "login_timeout", "hint": "登录超时（3分钟），请重试", "products": []}
                print(f"[jd-drission] 等待登录… {waited}s")
                time.sleep(3)
                waited += 3
                continue

            # 既无弹窗也未跳登录 = 已登录
            if waited > 0:
                print(f"[jd-drission] 登录成功! (耗时 {waited}s)")
            break

        # ---- Step 3: 已登录，执行搜索 ----
        print(f"[jd-drission] 搜索: {keyword}")

        search_box = None
        for sel in ["css:input[type=text]", "css:#key", "css:.jd_pc_search_bar_react_search_input"]:
            search_box = dp.ele(sel, timeout=5)
            if search_box:
                break
        if not search_box:
            return {"ok": False, "error": "search_box_not_found", "products": []}

        search_box.input(keyword)
        _sleep("键入后")
        search_box.input(Keys.ENTER)
        _sleep("搜索加载")

        # ---- Step 4: 翻页提取 ----
        while page_num <= max_pages:
            print(f"[jd-drission] === 第 {page_num} 页 ===")
            _sleep("页面渲染")

            # 滚动加载
            dp.scroll.to_bottom()
            time.sleep(1.5)
            dp.scroll.to_top()
            time.sleep(1)

            # 提取商品：优先 data-sku 卡片，回退到 item.jd.com 链接
            batch = _extract_products(dp, seen)
            all_products.extend(batch)
            print(f"[jd-drission] 第{page_num}页: {len(batch)} 件, 累计 {len(all_products)} 件")

            # --- 翻页 ---
            page_num += 1
            if page_num > max_pages:
                break

            nxt = None
            for sel in [
                "css:[class*=_pagination_next_]:not([class*=disabled])",
                "css:[class*=_pagination_next_]",
                "css:.pn-next:not(.disabled)",
                "css:.pn-next",
                "css:a[class*=next]",
            ]:
                try:
                    nxt = dp.ele(sel, timeout=3)
                    if nxt:
                        break
                except Exception:
                    pass

            if not nxt:
                print("[jd-drission] 未找到下一页按钮，结束")
                break

            cls = nxt.attr("class") or ""
            if "disabled" in cls:
                print("[jd-drission] 下一页已禁用，已到末页")
                break

            try:
                nxt.click(by_js=True)
            except Exception:
                try:
                    nxt.click()
                except Exception:
                    break
            _sleep("翻页后")

        return {
            "ok": len(all_products) > 0,
            "products": all_products,
            "total": len(all_products),
            "pages": page_num - 1,
            "render_source": "drission",
        }

    except Exception as exc:
        import traceback
        traceback.print_exc()
        return {
            "ok": len(all_products) > 0,
            "error": str(exc),
            "products": all_products,
            "render_source": "drission",
        }
    finally:
        try:
            dp.quit()
        except Exception:
            pass


def _extract_products(dp: ChromiumPage, seen: Set[str]) -> List[Dict[str, Any]]:
    """从当前页提取商品，多重策略兜底。"""
    items: List[Dict[str, Any]] = []

    # 策略1: data-sku 商品卡片
    cards = dp.eles("css:[data-sku]", timeout=8)
    if not cards:
        cards = dp.eles("css:[class*=gl-item]", timeout=5)
    if not cards:
        cards = dp.eles("css:li[data-sku]", timeout=5)

    for card in (cards or []):
        sku = (card.attr("data-sku") or "").strip()
        if not sku:
            a = card.ele("css:a[href*='item.jd.com']")
            if a:
                m = re.search(r"item\.jd\.com/(\d+)\.html", a.attr("href") or "")
                if m:
                    sku = m.group(1)
        if not sku or sku in seen:
            continue
        seen.add(sku)

        title = ""
        for ts in ["css:.p-name a", "css:.p-name em", "css:a[title]", "css:[class*=title] a", "css:[class*=name]"]:
            t = card.ele(ts, timeout=1)
            if t:
                title = (t.attr("title") or t.text or "").strip()
                break

        price = _extract_price(card)
        items.append({"sku": sku, "title": title, "url": f"https://item.jd.com/{sku}.html", "price": price})

    # 策略2: 回退到页面中所有 item.jd.com 链接
    if not items:
        print("[jd-drission] data-sku 未命中，使用链接回退")
        links = dp.eles("css:a[href*='item.jd.com']", timeout=8)
        for a in (links or []):
            href = a.attr("href") or ""
            m = re.search(r"item\.jd\.com/(\d+)\.html", href)
            if not m:
                continue
            sku = m.group(1)
            if sku in seen:
                continue
            seen.add(sku)
            items.append({
                "sku": sku,
                "title": (a.attr("title") or a.text or "").strip(),
                "url": f"https://item.jd.com/{sku}.html",
                "price": "",
            })

    return items


def _extract_price(card) -> str:
    """从商品卡片提取价格。"""
    # .price-int + .price-decimal (新版)
    i = card.ele("css:.price-int", timeout=1)
    if i:
        p = (i.text or "").strip().replace(",", "")
        d = card.ele("css:.price-decimal", timeout=1)
        if d:
            p += "." + (d.text or "").strip()
        if p and p != "0":
            return p
    # .p-price (旧版)
    for s in ["css:.p-price i", "css:.p-price em", "css:.p-price"]:
        el = card.ele(s, timeout=1)
        if el:
            m = re.search(r"(\d{2,6}(?:\.\d{1,2})?)", el.text or "")
            if m:
                return m.group(1)
    # 任何含 price 类名的元素
    ap = card.ele("css:[class*=price]", timeout=1)
    if ap:
        m = re.search(r"(\d{2,6}(?:\.\d{1,2})?)", ap.text or "")
        if m:
            return m.group(1)
    return ""
