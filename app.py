from __future__ import annotations

import os
import sys

from dotenv import load_dotenv
from flask import Flask, jsonify, request

load_dotenv()

_ROOT = os.path.dirname(os.path.abspath(__file__))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from crawler.jd_drission import search_with_drission
from crawler.jd_union_api import get_union_api
from jd.jd_pc import search as jd_pc_search

app = Flask(__name__)
app.config["JSON_AS_ASCII"] = False


@app.after_request
def _cors(response):
    origin = os.getenv("CORS_ORIGIN", "*")
    response.headers["Access-Control-Allow-Origin"] = origin
    response.headers["Access-Control-Allow-Headers"] = "Content-Type, Authorization"
    response.headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS"
    return response


@app.get("/")
def root():
    return jsonify(
        {
            "service": "price-compare-backend",
            "search_drission": "/api/jd/search-drission?keyword=关键词（自动登录，自动关闭浏览器）",
            "search_pc": "/api/jd/pc/search?keyword=关键词&pages=10（复用已打开 Chrome，不关浏览器）",
            "search_union": "/api/jd/union/search?keyword=关键词（京东联盟 API，需注册）",
            "hint": "search-pc 首次：启动 Chrome → 手动登录京东 → 后端调用接口自动搜索翻页。之后 Chrome 保持打开可直接复用。",
        }
    )


@app.route("/api/jd/search-drission", methods=["GET", "POST", "OPTIONS"])
def api_jd_search():
    """DrissionPage 浏览器直搜：打开 Chrome → 京东搜索 → 提取商品 → 翻页。"""
    if request.method == "OPTIONS":
        return "", 204

    keyword = (request.args.get("keyword") or request.args.get("q") or "").strip()
    if not keyword and request.is_json:
        body = request.get_json(silent=True) or {}
        keyword = str(body.get("keyword") or body.get("q") or "").strip()
    if not keyword:
        return jsonify({"error": "缺少参数 keyword 或 q"}), 400

    try:
        max_pages = int(request.args.get("pages", "3"))
    except ValueError:
        max_pages = 3
    max_pages = max(1, min(max_pages, 10))

    try:
        result = search_with_drission(keyword, max_pages=max_pages)
    except Exception as e:
        return jsonify({"ok": False, "error": str(e), "products": []}), 502

    status = 200 if result.get("ok") else 502
    return jsonify(result), status


@app.route("/api/jd/pc/search", methods=["GET", "POST", "OPTIONS"])
def api_jd_pc_search():
    """京东 PC 端爬虫 —— 复用已打开 Chrome，等待手动登录，翻页爬取 10 页。完成后不关闭浏览器。"""
    if request.method == "OPTIONS":
        return "", 204

    keyword = (request.args.get("keyword") or request.args.get("q") or "").strip()
    if not keyword and request.is_json:
        body = request.get_json(silent=True) or {}
        keyword = str(body.get("keyword") or body.get("q") or "").strip()
    if not keyword:
        return jsonify({"error": "缺少参数 keyword 或 q"}), 400

    try:
        max_pages = int(request.args.get("pages", "10"))
    except ValueError:
        max_pages = 10
    max_pages = max(1, min(max_pages, 10))

    try:
        result = jd_pc_search(keyword, max_pages=max_pages)
    except Exception as e:
        return jsonify({"ok": False, "error": str(e), "products": []}), 502

    status = 200 if result.get("ok") else 502
    return jsonify(result), status


@app.route("/api/jd/union/search", methods=["GET", "POST", "OPTIONS"])
def api_jd_union_search():
    """京东联盟 API 搜索 —— 无需 Cookie/浏览器，直接获取京东价+到手价+优惠券。"""
    if request.method == "OPTIONS":
        return "", 204

    keyword = (request.args.get("keyword") or request.args.get("q") or "").strip()
    if not keyword and request.is_json:
        body = request.get_json(silent=True) or {}
        keyword = str(body.get("keyword") or body.get("q") or "").strip()
    if not keyword:
        return jsonify({"error": "缺少参数 keyword 或 q"}), 400

    try:
        page = int(request.args.get("page", 1))
    except ValueError:
        page = 1
    try:
        page_size = int(request.args.get("page_size", 20))
    except ValueError:
        page_size = 20
    page_size = max(1, min(page_size, 50))

    try:
        api = get_union_api()
        result = api.search_goods(keyword, page=page, page_size=page_size)
    except RuntimeError as e:
        return jsonify({"ok": False, "error": str(e), "products": []}), 503
    except Exception as e:
        return jsonify({"ok": False, "error": str(e), "products": []}), 502

    if not result.get("ok"):
        return jsonify(result), 502
    return jsonify(result), 200


def main():
    port = int(os.getenv("PORT", "5000"))
    app.run(host="0.0.0.0", port=port, debug=os.getenv("FLASK_DEBUG") == "1")


if __name__ == "__main__":
    main()
