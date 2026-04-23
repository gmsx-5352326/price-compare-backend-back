from jd_cookie_pool.cookie_pool import JDCookiePool

# 先从文件加载
file_pool = JDCookiePool(use_db=False, cookie_file='cookies.txt')
db_pool = JDCookiePool(use_db=True)

for cookie in file_pool.cookies:
    print(f"导入: {cookie[:50]}...")
    db_pool.add_cookie_to_db(cookie)