"""
京东联盟 API 客户端

接口文档:
  - 商品查询: jd.union.open.goods.query
  - 推广详情: jd.union.open.goods.promotiongoodsinfo.query

注册与获取 AppKey/AppSecret: https://union.jd.com/
"""
from __future__ import annotations

import hashlib
import json
import os
import time
from typing import Any, Dict, List, Optional

from curl_cffi import requests

JD_API_URL = "https://api.jd.com/routerjson"


def _env(key: str, default: str = "") -> str:
    return os.getenv(key, default).strip()


class JDUnionAPI:
    def __init__(
        self,
        app_key: Optional[str] = None,
        app_secret: Optional[str] = None,
    ):
        self.app_key = app_key or _env("JD_UNION_APP_KEY")
        self.app_secret = app_secret or _env("JD_UNION_APP_SECRET")
        if not self.app_key or not self.app_secret:
            raise RuntimeError(
                "缺少 JD_UNION_APP_KEY / JD_UNION_APP_SECRET，请在 .env 配置"
            )

    # ---- sign ----

    def _sign(self, params: Dict[str, str]) -> str:
        """京东联盟 MD5 签名：sort keys -> concat -> app_secret + str + app_secret -> MD5 uppercase"""
        sorted_kv = sorted(params.items(), key=lambda x: x[0])
        raw = "".join(f"{k}{v}" for k, v in sorted_kv)
        raw = self.app_secret + raw + self.app_secret
        return hashlib.md5(raw.encode("utf-8")).hexdigest().upper()

    # ---- low-level call ----

    def _call(self, method: str, biz_params: Dict[str, Any]) -> Dict[str, Any]:
        """发送请求到京东联盟 API。"""
        ts = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())
        param_json = json.dumps(biz_params, ensure_ascii=False)

        sys_params: Dict[str, str] = {
            "method": method,
            "app_key": self.app_key,
            "timestamp": ts,
            "v": "1.0",
            "format": "json",
            "sign_method": "md5",
            "360buy_param_json": param_json,
        }
        sys_params["sign"] = self._sign(sys_params)

        resp = requests.post(
            JD_API_URL,
            data=sys_params,
            timeout=30,
            headers={"Content-Type": "application/x-www-form-urlencoded;charset=utf-8"},
        )
        resp.raise_for_status()

        outer = resp.json()

        # 顶层错误
        error_resp = outer.get("error_response", {})
        if error_resp:
            code = error_resp.get("code", "")
            msg = error_resp.get("zh_desc", "") or error_resp.get("msg", "")
            raise RuntimeError(f"京东联盟 API 错误 [{code}] {msg}")

        return outer

    @staticmethod
    def _unwrap(raw: str) -> Dict[str, Any]:
        """queryResult 是 JSON 字符串，解一层。"""
        if not raw:
            return {}
        return json.loads(raw)

    # ---- 业务接口 ----

    def search_goods(
        self,
        keyword: str,
        *,
        page: int = 1,
        page_size: int = 20,
    ) -> Dict[str, Any]:
        """
        搜索商品（含京东价、到手价、优惠券信息）。

        返回: {"ok": True/False, "products": [...], "total": int, "page": int, "page_size": int}
        """
        biz = {
            "goodsReqDTO": {
                "keyword": keyword,
                "pageIndex": str(page),
                "pageSize": str(min(page_size, 50)),
            }
        }

        try:
            outer = self._call("jd.union.open.goods.query", biz)
        except Exception as exc:
            return {"ok": False, "error": str(exc), "products": [], "total": 0}

        data_key = "jd_union_open_goods_query_response"
        resp = outer.get(data_key, {})
        if not resp:
            return {"ok": False, "error": "empty_response", "products": [], "total": 0}

        code_str = str(resp.get("code", ""))
        if code_str != "0":
            msg = resp.get("zh_desc", "") or resp.get("message", "") or code_str
            return {"ok": False, "error": f"API code {code_str}: {msg}", "products": [], "total": 0}

        inner = self._unwrap(resp.get("queryResult", ""))
        raw_products = inner.get("data") or []
        total = int(inner.get("totalCount", len(raw_products)))

        products: List[Dict[str, Any]] = []
        for item in raw_products:
            sku_id = str(item.get("skuId", ""))
            if not sku_id:
                continue

            # 价格：unitPrice=京东价, wlPrice=到手价（扣除返利后）
            unit_price = item.get("unitPrice") or 0.0
            wl_price = item.get("wlPrice") or item.get("unitPrice") or 0.0

            # 优惠券
            coupon_info = item.get("commissionInfo") or {}
            coupons = coupon_info.get("couponList") or coupon_info.get("coupon") or []
            if isinstance(coupons, dict):
                coupons = [coupons]
            best_coupon: Dict[str, Any] = {}
            for cp in coupons:
                disc = float(cp.get("discount", 0))
                if disc <= 0:
                    continue
                if not best_coupon or disc > float(best_coupon.get("discount", 0)):
                    best_coupon = cp

            products.append(
                {
                    "sku": sku_id,
                    "title": str(item.get("goodsName", "")),
                    "url": str(item.get("materialUrl") or f"https://item.jd.com/{sku_id}.html"),
                    "price": str(unit_price) if unit_price else "",
                    "wlPrice": str(wl_price) if wl_price else "",
                    "coupon": {
                        "discount": best_coupon.get("discount", ""),
                        "quota": best_coupon.get("quota", ""),
                        "link": best_coupon.get("link", ""),
                    } if best_coupon else {},
                    "commissionShare": int(item.get("commissionShare", 0)),
                    "inOrderCount": int(item.get("inOrderCount30DaysSku", 0)),
                }
            )

        return {
            "ok": True,
            "products": products,
            "total": total,
            "page": page,
            "page_size": page_size,
        }

    def get_promotion_info(self, sku_ids: List[str]) -> List[Dict[str, Any]]:
        """
        批量查询商品推广信息（更详细的价格/优惠券/佣金）。

        sku_ids: 最多 20 个 SKU
        """
        if not sku_ids:
            return []
        sku_str = ",".join(str(s) for s in sku_ids[:20])
        biz = {"skuIds": sku_str}

        try:
            outer = self._call("jd.union.open.goods.promotiongoodsinfo.query", biz)
        except Exception as exc:
            print(f"[jd-union] promotion query error: {exc}")
            return []

        data_key = "jd_union_open_goods_promotiongoodsinfo_query_response"
        resp = outer.get(data_key, {})
        if str(resp.get("code", "")) != "0":
            return []

        inner = self._unwrap(resp.get("queryResult", ""))
        raw = inner.get("data") or []
        out: List[Dict[str, Any]] = []
        for item in raw:
            out.append(
                {
                    "sku": str(item.get("skuId", "")),
                    "title": str(item.get("goodsName", "")),
                    "url": str(item.get("materialUrl") or ""),
                    "price": str(item.get("unitPrice", "")),
                    "wlPrice": str(item.get("wlPrice", "")),
                }
            )
        return out


# ---- 便捷工厂 ----

_api_instance: Optional[JDUnionAPI] = None


def get_union_api() -> JDUnionAPI:
    global _api_instance
    if _api_instance is None:
        _api_instance = JDUnionAPI()
    return _api_instance
