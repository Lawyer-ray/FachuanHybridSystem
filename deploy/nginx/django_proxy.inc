# 转发到公网后端 gunicorn(127.0.0.1:8003) 的公共代理参数。
# 被 /api/、/social/、/media/ 三个 location include。
proxy_pass http://127.0.0.1:8003;
proxy_http_version 1.1;
proxy_set_header Host $host;
proxy_set_header X-Real-IP $remote_addr;
# cloudflared 已带真实客户端 IP，追加本跳；uvicorn 信任 127.0.0.1 的
# X-Forwarded-For，限流按真实 IP 计数
proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
# cloudflared(https) → nginx(http)：透传上游的 X-Forwarded-Proto（本机直连
# 时该头为空，Django 的 SECURE_PROXY_SSL_HEADER 匹配不上 https，语义正确）
proxy_set_header X-Forwarded-Proto $http_x_forwarded_proto;
proxy_set_header Connection "";
# 长请求对齐 gunicorn timeout（LLM/下载类接口）
proxy_read_timeout 300s;
proxy_send_timeout 300s;
# 兼容未来 SSE/流式响应，避免 nginx 缓冲住分块输出
proxy_buffering off;
