import sys
import os

# 将项目根目录加入模块搜索路径
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, project_root)

from jd_cookie_pool.JDCookiePool import JDCookiePool

# 构造 cookies.txt 的完整路径
cookie_file_path = os.path.join(project_root, 'cookies.txt')

# 先从文件加载
file_pool = JDCookiePool(use_db=False, cookie_file=cookie_file_path)
db_pool = JDCookiePool(use_db=True)

for cookie in file_pool.cookies:
    print(f"导入: {cookie[:50]}...")
    db_pool.add_cookie_to_db(cookie)