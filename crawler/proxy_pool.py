"""代理池：从环境变量或文件加载代理列表，轮询/随机取用。"""
from __future__ import annotations

import os
import random
from typing import Dict, List, Optional


class ProxyPool:
    """HTTP(S) 代理池，支持轮询和随机取用。"""

    def __init__(
        self,
        proxies: Optional[List[str]] = None,
        proxy_file: Optional[str] = None,
    ):
        self._proxies: List[str] = []
        self._index = 0

        if proxies:
            self._proxies = [p.strip() for p in proxies if p.strip()]
        elif proxy_file and os.path.exists(proxy_file):
            with open(proxy_file, "r", encoding="utf-8") as f:
                self._proxies = [
                    line.strip()
                    for line in f
                    if line.strip() and not line.strip().startswith("#")
                ]
        else:
            raw = os.getenv("PROXY_LIST", "")
            if raw:
                self._proxies = [p.strip() for p in raw.split(",") if p.strip()]

        if self._proxies:
            print(f"[proxy-pool] 已加载 {len(self._proxies)} 条代理")

    @property
    def proxies(self) -> List[str]:
        return list(self._proxies)

    @property
    def count(self) -> int:
        return len(self._proxies)

    def get_proxy(self) -> Optional[str]:
        """轮询取一条代理 URL。"""
        if not self._proxies:
            return None
        proxy = self._proxies[self._index % len(self._proxies)]
        self._index += 1
        return proxy

    def get_random_proxy(self) -> Optional[str]:
        """随机取一条代理 URL。"""
        if not self._proxies:
            return None
        return random.choice(self._proxies)

    def get_proxies_dict(self) -> Optional[Dict[str, str]]:
        """返回 requests/curl_cffi 格式: {'http': '...', 'https': '...'}"""
        p = self.get_proxy()
        if not p:
            return None
        return {"http": p, "https": p}

    def get_random_proxies_dict(self) -> Optional[Dict[str, str]]:
        p = self.get_random_proxy()
        if not p:
            return None
        return {"http": p, "https": p}
