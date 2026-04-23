import os
import random
import requests
from dotenv import load_dotenv
from supabase import create_client, Client

load_dotenv()


class JDCookiePool:
    def __init__(self, use_db=True, cookie_file='cookies.txt'):
        """
        :param use_db: 是否使用 Supabase 数据库，True 则从数据库加载，False 则从本地文件加载
        :param cookie_file: 本地文件路径（仅在 use_db=False 时使用）
        """
        self.use_db = use_db
        self.cookie_file = cookie_file
        self.ua = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/147.0.0.0 Safari/537.36'

        if self.use_db:
            self.supabase: Client = self._init_supabase()
            self.cookies = self._load_cookies_from_db()
        else:
            self.cookies = self._load_cookies_from_file()

    def _init_supabase(self):
        """初始化 Supabase 客户端"""
        url = os.getenv('SUPABASE_URL')
        key = os.getenv('SUPABASE_KEY')
        if not url or not key:
            raise Exception("Supabase 配置缺失，请检查 .env 文件")
        return create_client(url, key)

    def _load_cookies_from_db(self):
        """从 Supabase 加载状态为 'active' 的 Cookie"""
        try:
            response = self.supabase.table('jd_cookies').select('id, cookie').eq('status', 'active').execute()
            cookies = [item['cookie'] for item in response.data]
            print(f"✅ 从 Supabase 加载 {len(cookies)} 个有效 Cookie")
            return cookies
        except Exception as e:
            print(f"❌ 从 Supabase 加载失败: {e}")
            return []

    def _load_cookies_from_file(self):
        """从本地文件加载 Cookie（备用）"""
        if not os.path.exists(self.cookie_file):
            print(f"⚠️ Cookie 文件 {self.cookie_file} 不存在")
            return []
        with open(self.cookie_file, 'r', encoding='utf-8') as f:
            lines = [line.strip() for line in f if line.strip()]
        print(f"✅ 从文件加载 {len(lines)} 个 Cookie")
        return lines

    def reload(self):
        """重新加载 Cookie"""
        if self.use_db:
            self.cookies = self._load_cookies_from_db()
        else:
            self.cookies = self._load_cookies_from_file()

    def get_random_cookie(self):
        """随机返回一个 Cookie 字符串"""
        if not self.cookies:
            raise Exception("Cookie 池为空")
        return random.choice(self.cookies)

    def cookie_str_to_dict(self, cookie_str):
        """将 Cookie 字符串转为字典格式"""
        cookie_dict = {}
        for item in cookie_str.split(';'):
            item = item.strip()
            if not item or '=' not in item:
                continue
            key, value = item.split('=', 1)
            cookie_dict[key] = value
        return cookie_dict

    def check_cookie_valid(self, cookie_str):
        """检测单个 Cookie 是否有效"""
        headers = {'User-Agent': self.ua}
        cookies = self.cookie_str_to_dict(cookie_str)
        try:
            resp = requests.get('https://order.jd.com/center/list.action',
                                headers=headers, cookies=cookies, timeout=10, allow_redirects=False)
            if resp.status_code == 302 and 'passport' in resp.headers.get('Location', ''):
                return False
            return True
        except Exception as e:
            print(f"检测异常: {e}")
            return False

    def update_cookie_status_in_db(self, cookie_str, status):
        """更新数据库中指定 Cookie 的状态"""
        try:
            # 通过 cookie 内容定位记录（注意：cookie 可能很长，建议通过 id 更新）
            self.supabase.table('jd_cookies').update({
                'status': status,
                'last_checked': 'now()'
            }).eq('cookie', cookie_str).execute()
        except Exception as e:
            print(f"更新数据库状态失败: {e}")

    def check_all_cookies(self, remove_invalid=True):
        """
        遍历检测所有 Cookie，并更新数据库状态
        :param remove_invalid: 是否将失效 Cookie 的状态设为 'expired'
        :return: (valid_list, invalid_list)
        """
        valid, invalid = [], []
        for idx, c in enumerate(self.cookies):
            print(f"检测第 {idx + 1}/{len(self.cookies)} 个 Cookie...")
            is_valid = self.check_cookie_valid(c)
            if is_valid:
                print("  ✅ 有效")
                valid.append(c)
                if self.use_db:
                    self.update_cookie_status_in_db(c, 'active')
            else:
                print("  ❌ 失效")
                invalid.append(c)
                if self.use_db and remove_invalid:
                    self.update_cookie_status_in_db(c, 'expired')

        # 更新内存中的列表（只保留有效的）
        if remove_invalid:
            self.cookies = valid

        return valid, invalid

    def add_cookie_to_db(self, cookie_str, status='active'):
        """向数据库添加新 Cookie"""
        try:
            self.supabase.table('jd_cookies').insert({
                'cookie': cookie_str,
                'status': status
            }).execute()
            print("✅ 新 Cookie 已添加到 Supabase")
        except Exception as e:
            print(f"添加失败: {e}")

 