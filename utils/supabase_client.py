# Supabase 连接工具

from supabase import create_client
from config import SUPABASE_URL, SUPABASE_KEY


def get_supabase():
    """
    获取 Supabase 客户端（给后端/爬虫用）
    必须使用 service_role key，权限最高
    """
    return create_client(SUPABASE_URL, SUPABASE_KEY)
