import requests
import json

def fetch_jd_price_via_api(sku_id):
    url = "https://p.3.cn/prices/mgets"
    # 注意：需要从浏览器复制完整的 Cookie 字符串
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Referer": "https://item.jd.com/",
        "Cookie": "你复制的完整Cookie字符串" # 从浏览器复制
    }
    params = {
        "skuIds": f"J_{sku_id}",
        "pduid": "你的pduid", # 可从cookie中或通过JS生成
    }
    resp = requests.get(url, headers=headers, params=params)
    # 处理JSONP响应
    json_str = resp.text.strip()[resp.text.find('(')+1 : resp.text.rfind(')')]
    data = json.loads(json_str)
    if data:
        print(f"价格: {data[0]['p']}")
    return data