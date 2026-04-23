from jd_cookie_pool.JDCookiePool import JDCookiePool

# 使用数据库模式
pool = JDCookiePool(use_db=True)

if not pool.cookies:
    # 如果数据库为空，可以从本地文件导入一次
    print("数据库无有效 Cookie，请先添加")
    # 示例：添加一个 Cookie
    # pool.add_cookie_to_db("你的完整Cookie字符串")
else:
    print(f"当前池中共有 {len(pool.cookies)} 个 Cookie，开始检测...")
    valid, invalid = pool.check_all_cookies(remove_invalid=True)
    print(f"\n有效: {len(valid)} 个，失效: {len(invalid)} 个")