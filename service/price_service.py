# 历史价格、涨幅计算
from typing import List, Dict, Any
from utils.deepseek_client import get_deepseek_client


def analyze_price_comparison(products: List[Dict[str, Any]], keyword: str = "") -> Dict[str, Any]:
    """
    使用AI分析商品价格对比
    """
    if not products:
        return {"success": False, "error": "没有商品数据可供分析"}
    
    deepseek_client = get_deepseek_client()
    result = deepseek_client.compare_prices(products, keyword)
    
    return result


def analyze_price_trends(product_details: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    使用AI分析价格趋势
    """
    if not product_details:
        return {"success": False, "error": "没有商品详情数据可供分析"}
    
    deepseek_client = get_deepseek_client()
    result = deepseek_client.get_price_trend_analysis(product_details)
    
    return result