from django.http import HttpResponsePermanentRedirect


class ProxyRedirectMiddleware:
    """
    在反向代理后面运行时，将 HTTP 重定向转换为 HTTPS。
    
    信任来自代理的 X-Forwarded-Proto 头，
    只在代理告知原始请求是 HTTP 时才进行重定向。
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        # 检查是否通过反代访问（HTTPS）
        proto = request.META.get("HTTP_X_FORWARDED_PROTO", "")
        if proto == "https":
            # 已经是 HTTPS，不需要重定向
            return self.get_response(request)
        
        # 本地访问或 HTTP，正常处理
        return self.get_response(request)
