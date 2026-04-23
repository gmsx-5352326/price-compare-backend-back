# debug_supabase.py
import os
import sys
from dotenv import load_dotenv
from supabase import create_client, Client
import logging

# 启用详细的日志记录
logging.basicConfig(level=logging.DEBUG)

# 加载环境变量
load_dotenv(override=True)

url = os.getenv("SUPABASE_URL")
key = os.getenv("SUPABASE_KEY")

print(f"Supabase URL: {url}")
print(f"Supabase Key (前15位): {key[:15] if key else '未找到'}...")
print(f"当前使用的 supabase 库版本: {sys.modules['supabase'].__version__}")

if not url or not key:
    print("❌ 环境变量 SUPABASE_URL 或 SUPABASE_KEY 未设置")
    sys.exit(1)

try:
    print("正在创建 Supabase 客户端...")
    client: Client = create_client(url, key)

    print("正在尝试一个简单的查询...")
    # 注意：如果 'jd_cookies' 表不存在，这个查询会失败，
    # 但至少我们能知道是不是密钥本身的问题。
    response = client.table('jd_cookies').select('*', count='exact').execute()
    print(f"✅ 连接成功！表中记录数: {response.count}")

except Exception as e:
    print(f"❌ 连接失败: {e}")
    import traceback

    traceback.print_exc()