"""
京东 PC 端爬虫 —— DrissionPage 方案

- 连接已打开的 Chrome（localhost:9222），绝不启动新浏览器
- 等待用户手动登录京东
- 搜索关键词 → 提取全部商品数据（含图片、店铺）
- 自动翻页，默认 10 页
- 完成后不关闭浏览器，下次可直接复用
"""
from __future__ import annotations

import os
import re
import socket
import time
import random
from typing import Any, Dict, List, Set
from urllib.parse import quote

from DrissionPage import ChromiumPage

DEBUG_PORT = 9222
_MAX_PAGES = int(os.getenv("JD_PC_MAX_PAGES", "10"))


def _sleep(tag: str = "", lo: float = 1.0, hi: float = 3.0) -> None:
    s = random.uniform(lo, hi)
    if tag:
        print(f"[jd-pc] 等待 {s:.1f}s — {tag}")
    time.sleep(s)


def _port_is_open(host: str = "127.0.0.1", port: int = DEBUG_PORT) -> bool:
    try:
        with socket.create_connection((host, port), timeout=1.0):
            return True
    except (OSError, ConnectionRefusedError, TimeoutError):
        return False


def _connect_existing() -> ChromiumPage:
    """仅连接已打开的 Chrome，绝不启动新浏览器。"""
    if not _port_is_open(port=DEBUG_PORT):
        raise RuntimeError(
            f"未检测到 Chrome 调试端口 (localhost:{DEBUG_PORT})。\n"
            "请先关闭所有 Chrome 窗口，然后用以下命令启动 Chrome：\n"
            'chrome.exe --remote-debugging-port=9222'
        )

    page = ChromiumPage(DEBUG_PORT)
    page.get("about:blank")
    print(f"[jd-pc] 已连接到现有 Chrome (localhost:{DEBUG_PORT})")
    return page


def _wait_for_login(page: ChromiumPage, timeout: int = 300) -> None:
    """等待用户手动登录京东（检测弹窗/登录页）。"""
    waited = 0
    while True:
        try:
            close_btn = page.ele("css:#login2025-dialog-close", timeout=2)
        except Exception:
            return

        on_passport = "passport" in page.url

        if not close_btn and not on_passport:
            if waited > 0:
                print(f"[jd-pc] 登录成功 (耗时 {waited}s)")
            return

        if waited == 0:
            print("[jd-pc] 请在浏览器中手动登录京东…")

        if waited >= timeout:
            raise TimeoutError(f"登录超时 ({timeout}s)，请重试")

        print(f"[jd-pc] 等待登录… {waited}s")
        time.sleep(3)
        waited += 3


def _do_search(page: ChromiumPage, keyword: str) -> None:
    """直接导航到京东搜索结果页。"""
    url = f"https://search.jd.com/Search?keyword={quote(keyword)}&enc=utf-8"
    print(f"[jd-pc] 搜索: {keyword}")
    page.get(url)
    _sleep("搜索结果加载", lo=2.0, hi=4.0)

    # 等待商品卡片出现
    try:
        page.wait.ele_displayed("[data-sku]", timeout=15)
        print("[jd-pc] 搜索结果已加载")
    except Exception:
        print("[jd-pc] 等待 [data-sku] 超时，尝试继续…")


def _scroll_to_load(page: ChromiumPage) -> None:
    """模拟人类滚动，触发懒加载。"""
    for _ in range(3):
        page.scroll.down(random.randint(400, 800))
        time.sleep(random.uniform(0.5, 1.2))
    page.scroll.to_bottom()
    time.sleep(1.5)
    page.scroll.to_top()
    time.sleep(0.8)


def _extract_price(card) -> str:
    for sel in [
        "css:[class*=price]",
        "css:.p-price i",
        "css:.p-price em",
        "css:.p-price",
    ]:
        try:
            el = card.ele(sel, timeout=1)
            if el and el.text:
                m = re.search(r"(\d{1,8}(?:\.\d{1,2})?)", el.text)
                if m:
                    return m.group(1)
        except Exception:
            pass
    return ""


def _extract_products(page: ChromiumPage, seen: Set[str]) -> List[Dict[str, Any]]:
    items: List[Dict[str, Any]] = []

    # 查找所有 data-sku 商品卡片
    cards = None
    for sel in ["css:[data-sku]", "css:div[data-sku]", "css:li[data-sku]"]:
        try:
            cards = page.eles(sel, timeout=5)
            if cards:
                break
        except Exception:
            continue

    if cards:
        print(f"[jd-pc] 找到 {len(cards)} 个 data-sku 卡片")
    else:
        print("[jd-pc] 未找到 data-sku 卡片")

    for card in (cards or []):
        try:
            sku = (card.attr("data-sku") or "").strip()
            if not sku or sku in seen:
                continue
            seen.add(sku)

            # 标题：取元素自身的 title 属性（京东新版用这个）
            title = (card.attr("title") or "").strip()
            if not title:
                # 回退：找卡片内带 title 的 span/a
                for ts in ["css:[title]", "css:a[title]", "css:span[title]"]:
                    t = card.ele(ts, timeout=1)
                    if t:
                        title = (t.attr("title") or t.text or "").strip()
                        if title:
                            break

            price = _extract_price(card)

            # 图片
            image = ""
            for isel in ["css:img[src]", "css:img[data-src]", "css:img"]:
                img = card.ele(isel, timeout=1)
                if img:
                    src = (
                        img.attr("src")
                        or img.attr("data-src")
                        or img.attr("data-loading")
                        or ""
                    ).strip()
                    if src and not src.startswith("data:"):
                        image = ("https:" + src) if src.startswith("//") else src
                        break

            # 店铺
            shop = ""
            for ssel in ["css:[class*=shop]", "css:[class*=_name_]", "css:[class*=store]"]:
                shop_el = card.ele(ssel, timeout=1)
                if shop_el:
                    shop = (shop_el.text or "").strip()
                    if shop:
                        break

            items.append({
                "sku": sku,
                "title": title,
                "url": f"https://item.jd.com/{sku}.html",
                "price": price,
                "image": image,
                "shop": shop,
            })
        except Exception as e:
            print(f"[jd-pc] 提取单条异常: {e}")
            continue

    # 回退：从页面中所有 item.jd.com 链接提取
    if not items:
        print("[jd-pc] data-sku 未命中，使用链接回退")
        try:
            links = page.eles("css:a[href*='item.jd.com']", timeout=8)
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
                    "image": "",
                    "shop": "",
                })
        except Exception as e:
            print(f"[jd-pc] 链接回退也失败: {e}")

    return items


def _click_next(page: ChromiumPage) -> bool:
    """点击下一页，京东新版搜索结果页的分页选择器。"""
    selectors = [
        "css:.pn-next:not(.disabled)",
        "css:.pn-next",
        "css:a.pn-next",
        "css:[class*=page] a:last-child",
        "css:[class*=pagination] a:last-child",
        "css:a[rel=next]",
        "css:a:text(下一页)",
        "css:a:text(>)",
    ]
    for sel in selectors:
        try:
            btn = page.ele(sel, timeout=3)
            if btn:
                cls = btn.attr("class") or ""
                if "disabled" in cls or "disable" in cls:
                    continue
                btn.click(by_js=True)
                _sleep("翻页后加载", lo=2.0, hi=4.0)
                return True
        except Exception:
            pass
    return False


def search(keyword: str, max_pages: int = _MAX_PAGES) -> Dict[str, Any]:
    """搜索京东商品，翻页爬取。完成后不关闭浏览器。"""
    all_products: List[Dict[str, Any]] = []
    seen: Set[str] = set()
    page_num = 1

    page = _connect_existing()

    try:
        page.get("https://www.jd.com/")
        _sleep("京东首页加载", lo=2.0, hi=3.0)

        _wait_for_login(page)

        _do_search(page, keyword)

        while page_num <= max_pages:
            print(f"[jd-pc] ===== 第 {page_num}/{max_pages} 页 =====")
            _sleep("页面渲染", lo=0.8, hi=1.5)

            _scroll_to_load(page)

            batch = _extract_products(page, seen)
            all_products.extend(batch)
            print(f"[jd-pc] 第{page_num}页: {len(batch)} 件, 累计 {len(all_products)} 件")

            page_num += 1
            if page_num > max_pages:
                break

            if not _click_next(page):
                print("[jd-pc] 无下一页，翻页结束")
                break

        return {
            "ok": len(all_products) > 0,
            "products": all_products,
            "total": len(all_products),
            "pages": page_num - 1,
            "source": "jd_pc_drission",
        }

    except Exception as exc:
        import traceback
        traceback.print_exc()
        return {
            "ok": len(all_products) > 0,
            "error": str(exc),
            "products": all_products,
            "source": "jd_pc_drission",
        }
    # 不关闭浏览器，保持供下次复用
