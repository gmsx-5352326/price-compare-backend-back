# 配置文件：放 Supabase 密钥、数据库配置
# Supabase 配置
import os
from dotenv import load_dotenv

load_dotenv()  # 加载 .env 文件中的环境变量

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")
DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY")

# 添加检查，确保变量已设置
if not SUPABASE_URL or not SUPABASE_KEY:
    raise ValueError("请在 .env 文件中设置 SUPABASE_URL 和 SUPABASE_KEY")