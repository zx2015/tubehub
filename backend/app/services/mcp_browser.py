"""
MCP Browser 客户端

通过 MCP Streamable HTTP (2026 spec) 协议连接 mcp-browser 服务，
从已登录 Chrome 浏览器中提取 YouTube cookies，转换为 Netscape 格式。

协议流程：
  1. POST /mcp  method=initialize   → 获取 Mcp-Session-Id
  2. POST /mcp  method=notifications/initialized  （无响应体）
  3. POST /mcp  method=tools/call   name=cookie_list  domain=youtube.com
  4. POST /mcp  method=tools/call   name=cookie_list  domain=google.com
  5. 合并 cookies → 转 Netscape 格式 → 返回字符串

API 文档：https://github.com/zx2015/mcp-browser/blob/main/docs/API.md
"""
from __future__ import annotations

import json
import logging
import time
import urllib.error
import urllib.request
from typing import Any

logger = logging.getLogger(__name__)


class McpBrowserError(Exception):
    """MCP Browser 服务调用失败"""


class McpBrowserClient:
    """轻量级 MCP Browser HTTP 客户端（无第三方依赖，仅用标准库）。"""

    def __init__(self, base_url: str, auth_token: str, timeout: int = 30):
        self.base_url = base_url.rstrip("/")
        self.auth_token = auth_token
        self.timeout = timeout
        self._mcp_url = f"{self.base_url}/mcp"
        self._headers = {
            "Authorization": f"Bearer {auth_token}",
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream",
        }

    # ------------------------------------------------------------------
    # 内部 HTTP 工具
    # ------------------------------------------------------------------

    def _post(self, body: dict, session_id: str | None = None) -> tuple[str | None, str]:
        """发送 POST 请求，返回 (Mcp-Session-Id | None, response_body)。"""
        headers = dict(self._headers)
        if session_id:
            headers["Mcp-Session-Id"] = session_id
        data = json.dumps(body).encode("utf-8")
        req = urllib.request.Request(self._mcp_url, data=data, headers=headers, method="POST")
        # MCP Browser 是局域网服务，强制绕过系统代理（urllib 默认会读取 HTTP_PROXY 环境变量）
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        try:
            with opener.open(req, timeout=self.timeout) as r:
                sid = r.headers.get("Mcp-Session-Id")
                return sid, r.read().decode("utf-8")
        except urllib.error.HTTPError as e:
            body_text = e.read().decode("utf-8")
            raise McpBrowserError(f"HTTP {e.code}: {body_text[:200]}") from e
        except Exception as e:
            raise McpBrowserError(f"连接 MCP Browser 失败: {e}") from e

    @staticmethod
    def _parse_sse(raw: str) -> Any:
        """从 SSE 流（event: message\\ndata: {...}）中解析最后一个 JSON。"""
        result = None
        for line in raw.splitlines():
            line = line.strip()
            if line.startswith("data:"):
                payload = line[5:].strip()
                if payload and payload != "[DONE]":
                    try:
                        result = json.loads(payload)
                    except json.JSONDecodeError:
                        pass
        return result

    # ------------------------------------------------------------------
    # MCP 会话
    # ------------------------------------------------------------------

    def _new_session(self) -> str:
        """发送 initialize + initialized，返回 session_id。"""
        sid, raw = self._post({
            "jsonrpc": "2.0", "id": 0, "method": "initialize",
            "params": {
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {"name": "tubehub-cookie-sync", "version": "1.0"},
            },
        })
        if not sid:
            # 有些版本 initialize 不返回 Session-Id，尝试从响应体中获取
            parsed = self._parse_sse(raw)
            if parsed and isinstance(parsed, dict):
                sid = parsed.get("result", {}).get("sessionId")
        if not sid:
            raise McpBrowserError("MCP initialize 未返回 Mcp-Session-Id")

        # 发送 initialized 通知（无需检查响应）
        self._post(
            {"jsonrpc": "2.0", "method": "notifications/initialized", "params": {}},
            session_id=sid,
        )
        return sid

    def _tool_call(self, session_id: str, tool_name: str, arguments: dict, req_id: int = 1) -> Any:
        """调用 MCP tool，返回 result.content[0].text（已 JSON 解析）。"""
        _, raw = self._post({
            "jsonrpc": "2.0", "id": req_id, "method": "tools/call",
            "params": {"name": tool_name, "arguments": arguments},
        }, session_id=session_id)
        parsed = self._parse_sse(raw)
        if not parsed:
            raise McpBrowserError(f"tool_call {tool_name}: 空响应")
        result = parsed.get("result", {})
        if result.get("isError"):
            content_text = (result.get("content") or [{}])[0].get("text", "unknown error")
            raise McpBrowserError(f"tool_call {tool_name} 返回错误: {content_text}")
        content = result.get("content") or []
        if not content:
            raise McpBrowserError(f"tool_call {tool_name}: content 为空")
        return json.loads(content[0]["text"])

    # ------------------------------------------------------------------
    # 公共接口
    # ------------------------------------------------------------------

    def health_check(self) -> bool:
        """检查 MCP Browser 服务是否可用。"""
        req = urllib.request.Request(f"{self.base_url}/health")
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        try:
            with opener.open(req, timeout=5) as r:
                data = json.loads(r.read())
                return data.get("status") == "ok"
        except Exception:
            return False

    def fetch_youtube_cookies_netscape(self) -> str:
        """
        从 MCP Browser 已登录的 Chrome 拉取 YouTube + Google cookies，
        转换为 Netscape HTTP Cookie 格式字符串（yt-dlp 兼容）。

        Returns:
            Netscape 格式 cookies 字符串

        Raises:
            McpBrowserError: 连接失败、认证失败或 cookies 为空
        """
        logger.info("McpBrowserClient: connecting to %s", self.base_url)
        session_id = self._new_session()
        logger.info("McpBrowserClient: session_id=%s", session_id)

        all_cookies: list[dict] = []
        for domain, req_id in [("youtube.com", 1), ("google.com", 2)]:
            cookies = self._tool_call(session_id, "cookie_list", {"domain": domain}, req_id=req_id)
            logger.info("McpBrowserClient: domain=%s cookies=%d", domain, len(cookies))
            all_cookies.extend(cookies)

        if not all_cookies:
            raise McpBrowserError("MCP Browser 返回的 cookies 为空，请确认 Chrome 已登录 YouTube")

        netscape = _cookies_to_netscape(all_cookies)
        logger.info(
            "McpBrowserClient: fetched %d cookies, netscape_size=%d bytes",
            len(all_cookies), len(netscape),
        )
        return netscape


# ------------------------------------------------------------------
# Netscape 格式转换（模块级函数）
# ------------------------------------------------------------------

def _cookies_to_netscape(cookies: list[dict]) -> str:
    """
    将 Playwright Cookie 对象列表转换为 Netscape HTTP Cookie 文件格式。

    Netscape 字段顺序（TAB 分隔）：
      domain  include_subdomains  path  https_only  expiry  name  value
    """
    lines = [
        "# Netscape HTTP Cookie File",
        "# This file is generated by TubeHub (via mcp-browser). Do not edit.",
        "",
    ]
    one_year = int(time.time()) + 86400 * 365
    for c in cookies:
        domain: str = c.get("domain", "")
        include_subdomains = "TRUE" if domain.startswith(".") else "FALSE"
        path: str = c.get("path", "/")
        secure = "TRUE" if c.get("secure", False) else "FALSE"
        expires = c.get("expires")
        if expires is None or expires <= 0:
            expires = one_year
        else:
            expires = int(expires)
        name: str = c.get("name", "")
        value: str = c.get("value", "")
        lines.append(f"{domain}\t{include_subdomains}\t{path}\t{secure}\t{expires}\t{name}\t{value}")
    return "\n".join(lines)
