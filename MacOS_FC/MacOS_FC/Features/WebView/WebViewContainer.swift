//
//  WebViewContainer.swift
//  MacOS_FC
//
//  SwiftUI WebView 容器
//

import SwiftUI
import WebKit
import os.log

struct WebViewContainer: NSViewRepresentable {
    let url: URL
    @Binding var isLoading: Bool
    @Binding var canGoBack: Bool
    @Binding var canGoForward: Bool
    
    var onTokenCaptured: ((TokenPair) -> Void)?
    
    func makeCoordinator() -> WebViewCoordinator {
        WebViewCoordinator(self)
    }
    
    func makeNSView(context: Context) -> WKWebView {
        let config = WKWebViewConfiguration()
        
        // 配置 JS Bridge
        let contentController = config.userContentController
        contentController.add(context.coordinator, name: "nativeAuth")
        contentController.add(context.coordinator, name: "nativeFolders")
        contentController.add(context.coordinator, name: "nativeLog")
        
        // 注入检测脚本
        let script = WKUserScript(
            source: Self.bridgeScript,
            injectionTime: .atDocumentEnd,
            forMainFrameOnly: true
        )
        contentController.addUserScript(script)
        
        // 允许开发者工具
        config.preferences.setValue(true, forKey: "developerExtrasEnabled")
        
        let webView = WKWebView(frame: .zero, configuration: config)
        webView.navigationDelegate = context.coordinator
        webView.allowsBackForwardNavigationGestures = true
        
        // 加载页面
        webView.load(URLRequest(url: url))
        
        return webView
    }
    
    func updateNSView(_ webView: WKWebView, context: Context) {
        // 更新导航状态
        DispatchQueue.main.async {
            canGoBack = webView.canGoBack
            canGoForward = webView.canGoForward
        }
    }
    
    // MARK: - JS Bridge 脚本
    
    static let bridgeScript = """
    (function() {
        // 标记为 Native App
        window.isNativeApp = true;
        window.nativeVersion = '\(AppConfig.appVersion)';
        
        // 监听 localStorage 变化，捕获 Token
        const originalSetItem = localStorage.setItem;
        localStorage.setItem = function(key, value) {
            originalSetItem.apply(this, arguments);
            
            if (key === 'access_token' || key === 'refresh_token') {
                const access = localStorage.getItem('access_token');
                const refresh = localStorage.getItem('refresh_token');
                
                if (access && refresh && window.webkit?.messageHandlers?.nativeAuth) {
                    window.webkit.messageHandlers.nativeAuth.postMessage({
                        type: 'tokenUpdate',
                        access: access,
                        refresh: refresh
                    });
                }
            }
        };
        
        // 提供主动通知方法
        window.notifyNativeAuth = function(tokens) {
            if (window.webkit?.messageHandlers?.nativeAuth) {
                window.webkit.messageHandlers.nativeAuth.postMessage({
                    type: 'login',
                    access: tokens.access,
                    refresh: tokens.refresh
                });
            }
        };
        
        // 日志桥接
        window.nativeLog = function(level, message) {
            if (window.webkit?.messageHandlers?.nativeLog) {
                window.webkit.messageHandlers.nativeLog.postMessage({
                    level: level,
                    message: message
                });
            }
        };
        
        console.log('[Native Bridge] 已注入');
    })();
    """
}

// MARK: - WebView 导航控制

extension WebViewContainer {
    func goBack(_ webView: WKWebView) {
        webView.goBack()
    }
    
    func goForward(_ webView: WKWebView) {
        webView.goForward()
    }
    
    func reload(_ webView: WKWebView) {
        webView.reload()
    }
}
