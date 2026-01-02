import json
import asyncio
import websockets
from typing import Callable, Optional, Dict, Any
from urllib.parse import parse_qs
import base64

class ClientConnection:
    def __init__(self, websocket):
        self.websocket = websocket
        self.pending_requests = {}  # echo: future

class OneBotWSServer:
    def __init__(self, host: str = "0.0.0.0", port: int = 8080, access_token: Optional[str] = None):
        self.host = host
        self.port = port
        self.access_token = access_token  # 服务端验证Token
        self._server = None
        self._connections: Dict[str, ClientConnection] = {}
        self._event_handler: Optional[Callable] = None

    def on_event(self, handler: Callable):
        self._event_handler = handler

    async def _token_auth(self, websocket):
        try:
            client_token = None
            
            # 方法1: 检查 Authorization 请求头 (OneBot 11协议推荐方式)
            headers = websocket.request.headers
            if 'Authorization' in headers:
                auth_header = headers['Authorization']
                # 支持 "Bearer <token>" 格式
                if auth_header.startswith('Bearer '):
                    client_token = auth_header[7:]
                # 支持 Basic 认证 (有些实现可能用这种方式)
                elif auth_header.startswith('Basic '):
                    # 解码 Base64
                    encoded_str = auth_header[6:]
                    try:
                        decoded_str = base64.b64decode(encoded_str).decode('utf-8')
                        # 格式通常是 "username:password" 或 "token:"
                        if ':' in decoded_str:
                            client_token = decoded_str.split(':', 1)[1]
                    except:
                        pass
            
            # 方法2: 检查查询参数 (兼容旧方式)
            if client_token is None:
                # 尝试从查询参数获取
                if hasattr(websocket.request, 'request_uri'):
                    from urllib.parse import urlparse
                    parsed_url = urlparse(websocket.request.request_uri)
                    query_params = parse_qs(parsed_url.query)
                elif hasattr(websocket.request, 'path'):
                    path = websocket.request.path
                    if '?' in path:
                        query_string = path.split('?', 1)[1]
                        query_params = parse_qs(query_string)
                    else:
                        query_params = {}
                elif hasattr(websocket.request, 'query'):
                    query_params = parse_qs(websocket.request.query)
                else:
                    query_params = {}
                
                client_token = query_params.get("access_token", [None])[0]
            
            # 调试信息：显示所有请求头
            print(f"[调试] 请求头: {dict(headers)}")
            print(f"[调试] 提取到的Token: {client_token}")
            
            # Token 校验逻辑
            if self.access_token is not None:
                if client_token is None or client_token != self.access_token:
                    print(f"[Token验证失败] 客户端传入: {client_token} | 服务端期望: {self.access_token}")
                    await websocket.close(code=4001, reason="Token authentication failed")
                    return False
            
            print(f"[Token验证成功] 客户端鉴权通过")
            return True
        except Exception as e:
            print(f"[Token验证异常] {str(e)}")
            await websocket.close(code=4000, reason="Auth process error")
            return False

    async def _handle_client(self, websocket):
        # 先验Token，失败直接断开
        if not await self._token_auth(websocket):
            return
        
        客户端ID = f"{websocket.remote_address[0]}:{websocket.remote_address[1]}"
        self._connections[客户端ID] = ClientConnection(websocket)
        print(f"客户端 {客户端ID} 连接成功")

        try:
            async for message in websocket:
                try:
                    data = json.loads(message)
                    # 处理API响应
                    if "echo" in data and "status" in data:
                        client = self._connections.get(客户端ID)
                        if client and data["echo"] in client.pending_requests:
                            client.pending_requests.pop(data["echo"]).set_result(data)
                        continue
                    # 处理事件推送
                    if "post_type" in data and self._event_handler:
                        asyncio.create_task(self._event_handler(data))
                    # 处理心跳
                    elif data.get("meta_event_type") == "heartbeat":
                        await websocket.send(json.dumps({
                            "status": "ok", "retcode": 0, "echo": data.get("echo")
                        }))
                except json.JSONDecodeError:
                    print(f"无效JSON消息: {message}")
        except websockets.exceptions.ConnectionClosedError:
            print(f"客户端 {客户端ID} 连接断开")
        finally:
            client = self._connections.pop(客户端ID, None)
            if client:
                for future in client.pending_requests.values():
                    future.set_exception(ConnectionError("客户端已断开连接"))

    async def call_api(self, client_id: str, action: str, params: Dict = None, timeout: int = 10) -> Dict:
        if client_id not in self._connections:
            raise ValueError("客户端未连接")
        client = self._connections[client_id]
        echo = str(asyncio.get_event_loop().time())
        future = asyncio.get_event_loop().create_future()
        client.pending_requests[echo] = future

        try:
            await client.websocket.send(json.dumps({
                "action": action, "params": params or {}, "echo": echo
            }))
            return await asyncio.wait_for(future, timeout)
        except asyncio.TimeoutError:
            client.pending_requests.pop(echo, None)
            raise TimeoutError(f"API {action} 调用超时")
        except Exception as e:
            client.pending_requests.pop(echo, None)
            raise e

    async def start(self):
        self._server = await websockets.serve(self._handle_client, self.host, self.port)
        print(f"服务端启动: ws://{self.host}:{self.port}")
        if self.access_token:
            print(f"[安全配置] Token验证已开启")
        await self._server.wait_closed()