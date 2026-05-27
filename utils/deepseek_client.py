"""
DeepSeek API 客户端
用于AI驱动的商品价格对比分析
"""
import os
import openai
from typing import Dict, List, Any, Optional
from config import SUPABASE_URL, SUPABASE_KEY


class DeepSeekClient:
    def __init__(self, api_key: str = None):
        self.api_key = api_key or os.getenv("DEEPSEEK_API_KEY")
        if not self.api_key:
            # 如果没有环境变量，则使用传入的密钥
            self.api_key = api_key
        
        if not self.api_key:
            raise ValueError("请设置 DEEPSEEK_API_KEY 环境变量或传入API密钥")
        
        # 配置OpenAI客户端以使用DeepSeek API
        self.client = openai.OpenAI(
            api_key=self.api_key,
            base_url="https://api.deepseek.com"
        )

    def compare_prices(self, products: List[Dict[str, Any]], keyword: str = "") -> Dict[str, Any]:
        """
        使用AI分析商品价格对比
        """
        # 构建商品信息文本
        product_texts = []
        for idx, product in enumerate(products, 1):
            product_info = f"商品{idx}: {product.get('title', '未知商品')}\n"
            product_info += f"  价格: ¥{product.get('price', '未知')}\n"
            product_info += f"  店铺: {product.get('shop', '未知')}\n"
            product_info += f"  链接: {product.get('url', '')}\n"
            product_texts.append(product_info)
        
        all_products_text = "\n".join(product_texts)
        
        prompt = f"""
请分析以下关于"{keyword}"的搜索结果中各商品的价格对比情况，并提供购买建议：

{all_products_text}

请按以下格式回复：
1. 价格分析：指出价格区间、最高价、最低价及差异原因
2. 推荐指数：对每个商品给出1-10分的推荐指数
3. 购买建议：推荐性价比最高的商品并说明理由
4. 注意事项：指出需要注意的地方（如价格波动、售后服务等）
"""
        
        try:
            response = self.client.chat.completions.create(
                model="deepseek-chat",
                messages=[
                    {
                        "role": "user",
                        "content": prompt
                    }
                ],
                temperature=0.7,
                max_tokens=1500
            )
            
            ai_analysis = response.choices[0].message.content
            
            return {
                "success": True,
                "analysis": ai_analysis,
                "usage": {
                    "prompt_tokens": response.usage.prompt_tokens,
                    "completion_tokens": response.usage.completion_tokens,
                    "total_tokens": response.usage.total_tokens
                } if response.usage else {}
            }
        except Exception as e:
            return {
                "success": False,
                "error": f"API请求失败: {str(e)}"
            }

    def get_price_trend_analysis(self, product_details: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        获取价格趋势分析
        """
        product_texts = []
        for idx, product in enumerate(product_details, 1):
            product_info = f"商品{idx}: {product.get('title', '未知商品')}\n"
            product_info += f"  当前价格: ¥{product.get('price', '未知')}\n"
            product_info += f"  店铺: {product.get('shop', '未知')}\n"
            if 'history' in product:
                product_info += f"  历史价格: {product['history']}\n"
            product_texts.append(product_info)
        
        all_products_text = "\n".join(product_texts)
        
        prompt = f"""
基于以下商品信息，分析价格趋势并预测未来价格走向：

{all_products_text}

请提供：
1. 当前市场状况分析
2. 价格趋势预测（上涨/下跌/稳定）
3. 最佳购买时机建议
4. 风险提示
"""
        
        try:
            response = self.client.chat.completions.create(
                model="deepseek-chat",
                messages=[
                    {
                        "role": "user",
                        "content": prompt
                    }
                ],
                temperature=0.6,
                max_tokens=1000
            )
            
            ai_analysis = response.choices[0].message.content
            
            return {
                "success": True,
                "analysis": ai_analysis,
                "usage": {
                    "prompt_tokens": response.usage.prompt_tokens,
                    "completion_tokens": response.usage.completion_tokens,
                    "total_tokens": response.usage.total_tokens
                } if response.usage else {}
            }
        except Exception as e:
            return {
                "success": False,
                "error": f"API请求失败: {str(e)}"
            }


# 全局实例
_deepseek_client = None


def get_deepseek_client() -> DeepSeekClient:
    global _deepseek_client
    if _deepseek_client is None:
        _deepseek_client = DeepSeekClient()
    return _deepseek_client