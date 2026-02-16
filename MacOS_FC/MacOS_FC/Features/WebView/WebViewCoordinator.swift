//
//  WebViewCoordinator.swift
//  MacOS_FC
//
//  WebView 协调器 - 处理导航和 JS Bridge
//

import WebKit
import os.log

class WebViewCoordinator: NSObject {
    var parent: WebViewContainer
    private let logger = Logger(subsystem: "com.fachuan.macos", category: "webview")
    
    init(_ parent: WebViewContainer) {
        self.parent = parent
    }
}

// MARK: - WKNavigationDelegate

extension WebViewCoordinator: WKNavigationDelegate {
    func webView(_ webView: WKWebView, didStartProvisionalNavigation navigation: WKNavigation!) {
        parent.isLoading = true
        logger.info("开始加载: \(webView.url?.absoluteString ?? "")")
    }
    
    func webView(_ webView: WKWebView, didFinish navigation: WKNavigation!) {
        parent.isLoading = false
        parent.canGoBack = webView.canGoBack
        parent.canGoForward = webView.canGoForward
        logger.info("加载完成: \(webView.url?.absoluteString ?? "")")
        
        // 页面加载完成后，检查 localStorage 中是否已有 Token
        checkExistingToken(in: webView)
    }
    
    /// 检查 WebView localStorage 中是否已有 Token
    private func checkExistingToken(in webView: WKWebView) {
        let script = """
        (function() {
            var access = localStorage.getItem('access_token');
            var refresh = localStorage.getItem('refresh_token');
            if (access && refresh && window.webkit && window.webkit.messageHandlers && window.webkit.messageHandlers.nativeAuth) {
                window.webkit.messageHandlers.nativeAuth.postMessage({
                    type: 'tokenUpdate',
                    access: access,
                    refresh: refresh
                });
            }
        })();
        """
        
        webView.evaluateJavaScript(script) { _, error in
            if let error = error {
                self.logger.warning("检查现有 Token 失败: \(error.localizedDescription)")
            }
        }
    }
    
    func webView(_ webView: WKWebView, didFail navigation: WKNavigation!, withError error: Error) {
        parent.isLoading = false
        logger.error("加载失败: \(error.localizedDescription)")
    }
    
    func webView(_ webView: WKWebView, didFailProvisionalNavigation navigation: WKNavigation!, withError error: Error) {
        parent.isLoading = false
        logger.error("加载失败: \(error.localizedDescription)")
    }
    
    // 处理新窗口打开请求
    func webView(_ webView: WKWebView, decidePolicyFor navigationAction: WKNavigationAction, decisionHandler: @escaping (WKNavigationActionPolicy) -> Void) {
        
        // 外部链接在默认浏览器打开
        if let url = navigationAction.request.url,
           navigationAction.targetFrame == nil {
            NSWorkspace.shared.open(url)
            decisionHandler(.cancel)
            return
        }
        
        decisionHandler(.allow)
    }
}

// MARK: - WKScriptMessageHandler

extension WebViewCoordinator: WKScriptMessageHandler {
    func userContentController(_ userContentController: WKUserContentController, didReceive message: WKScriptMessage) {
        
        switch message.name {
        case "nativeAuth":
            handleAuthMessage(message.body)
            
        case "nativeFolders":
            handleFoldersMessage(message.body)
            
        case "nativeLog":
            handleLogMessage(message.body)
            
        default:
            logger.warning("未知消息类型: \(message.name)")
        }
    }
    
    // MARK: - 消息处理
    
    private func handleAuthMessage(_ body: Any) {
        guard let dict = body as? [String: Any] else {
            logger.warning("无效的认证消息格式")
            return
        }
        
        let messageType = dict["type"] as? String ?? "unknown"
        
        switch messageType {
        case "tokenUpdate":
            guard let access = dict["access"] as? String,
                  let refresh = dict["refresh"] as? String else {
                logger.warning("tokenUpdate 消息缺少必要字段")
                return
            }
            
            let token = TokenPair(access: access, refresh: refresh)
            
            // 存储 Token
            TokenManager.shared.captureTokenFromWebView(token)
            
            // 更新认证状态
            Task { @MainActor in
                AuthService.shared.handleWebViewLogin(token)
            }
            
            // 回调通知
            parent.onTokenCaptured?(token)
            
            logger.info("收到 Token 更新")
            
        case "logout":
            // 清除 Token 并更新状态
            Task { @MainActor in
                AuthService.shared.logout()
            }
            logger.info("收到登出消息")
            
        default:
            logger.warning("未知的认证消息类型: \(messageType)")
        }
    }
    
    private func handleFoldersMessage(_ body: Any) {
        guard let dict = body as? [String: Any],
              let action = dict["action"] as? String else {
            logger.warning("无效的文件夹消息格式")
            return
        }
        
        switch action {
        case "createContractFolder":
            if let contractId = dict["contractId"] as? Int {
                logger.info("请求创建合同文件夹: \(contractId)")
                // TODO: 调用 FolderService
            }
            
        case "createCaseFolder":
            if let caseId = dict["caseId"] as? Int {
                logger.info("请求创建案件文件夹: \(caseId)")
                // TODO: 调用 FolderService
            }
            
        case "openFolder":
            if let path = dict["path"] as? String {
                let url = URL(fileURLWithPath: path)
                NSWorkspace.shared.selectFile(nil, inFileViewerRootedAtPath: url.path)
            }
            
        default:
            logger.warning("未知的文件夹操作: \(action)")
        }
    }
    
    private func handleLogMessage(_ body: Any) {
        guard let dict = body as? [String: Any],
              let level = dict["level"] as? String,
              let message = dict["message"] as? String else {
            return
        }
        
        switch level {
        case "error":
            logger.error("[Web] \(message)")
        case "warn":
            logger.warning("[Web] \(message)")
        case "info":
            logger.info("[Web] \(message)")
        default:
            logger.debug("[Web] \(message)")
        }
    }
}
