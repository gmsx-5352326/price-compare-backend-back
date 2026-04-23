import os
import random
import requests
from fake_useragent import UserAgent
from dotenv import load_dotenv

load_dotenv()  # 仍保留，用于其他敏感配置（如 SUPABASE）

class JDCookiePool:
    def __init__(self, cookie_file='cookies.txt'):
        """
        :param cookie_file: Cookie 文件路径，默认为当前目录下的 cookies.txt
        """
        self.cookie_file = cookie_file
        self.cookies = self._load_cookies_from_file()
        self.ua = UserAgent()

    def _load_cookies_from_file(self):
        """从文件加载 Cookie，每行一个完整 Cookie 字符串"""
        if not os.path.exists(self.cookie_file):
            print(f"⚠️ Cookie 文件 {self.cookie_file} 不存在，请创建并填入 Cookie（每行一个）")
            return []
        with open(self.cookie_file, 'r', encoding='utf-8') as f:
            lines = [line.strip() for line in f if line.strip()]
        print(f"✅ 从文件加载 {len(lines)} 个 Cookie")
        return lines

    def reload(self):
        """重新加载 Cookie 文件"""
        self.cookies = self._load_cookies_from_file()

    def get_random_cookie(self):
        """随机返回一个 Cookie 字符串"""
        if not self.cookies:
            raise Exception("Cookie 池为空，请在 cookies.txt 中添加有效 Cookie")
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
        """简单检测 Cookie 是否有效"""
        headers = {'User-Agent': self.ua.random}
        cookies = self.cookie_str_to_dict(cookie_str)
        try:
            resp = requests.get('https://order.jd.com/center/list.action',
                                headers=headers, cookies=cookies, timeout=10)
            if 'passport.jd.com' in resp.url:
                return False
            return True
        except Exception as e:
            print(f"检测异常: {e}")
            return False

    def check_all_cookies(self, remove_invalid=False):
        """
        遍历所有 Cookie，检测有效性
        :param remove_invalid: 是否自动从内存和文件中移除失效的 Cookie
        :return: (valid_list, invalid_list)
        """
        valid = []
        invalid = []
        for idx, c in enumerate(self.cookies):
            print(f"检测第 {idx + 1}/{len(self.cookies)} 个 Cookie...")
            if self.check_cookie_valid(c):
                print("  ✅ 有效")
                valid.append(c)
            else:
                print("  ❌ 失效")
                invalid.append(c)

        if remove_invalid and invalid:
            self.cookies = valid
            with open(self.cookie_file, 'w', encoding='utf-8') as f:
                for c in valid:
                    f.write(c + '\n')
            print(f"已从文件移除 {len(invalid)} 个失效 Cookie")
        return valid, invalid



if __name__ == '__main__':
    import os

    base_dir = os.path.dirname(os.path.abspath(__file__))
    cookie_path = os.path.join(os.path.dirname(base_dir), 'cookies.txt')

    pool = JDCookiePool(cookie_file=cookie_path)

    if not pool.cookies:
        print("Cookie 池为空，退出")
        exit()

    print(f"\n当前池中共有 {len(pool.cookies)} 个 Cookie，开始逐一检测...\n")
    valid_list, invalid_list = pool.check_all_cookies(remove_invalid=True)

    print("\n=== 检测结果 ===")
    print(f"有效 Cookie: {len(valid_list)} 个")
    print(f"失效 Cookie: {len(invalid_list)} 个")