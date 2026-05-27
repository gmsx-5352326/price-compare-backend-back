from jd_cookie_pool.JDCookiePool import JDCookiePool

# 使用数据库模式
pool = JDCookiePool(use_db=True)

if not pool.cookies:
    print("[jd-cookie] 数据库无 active 记录，可先 add_cookie_to_db 或从文件导入")
    # pool.add_cookie_to_db("你的完整Cookie字符串")
else:
    pool.check_all_cookies(remove_invalid=True)