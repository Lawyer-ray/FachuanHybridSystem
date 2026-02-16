//
//  MainWindowView.swift
//  MacOS_FC
//
//  主窗口视图 - 纯 WebView 容器
//

import SwiftUI

struct MainWindowView: View {
    @StateObject private var authService = AuthService.shared
    @State private var isLoading = false
    @State private var canGoBack = false
    @State private var canGoForward = false
    
    var body: some View {
        MainTabViewHost(
            isLoading: $isLoading,
            canGoBack: $canGoBack,
            canGoForward: $canGoForward,
            onTokenCaptured: { token in
                authService.handleWebViewLogin(token)
            }
        )
        .toolbar {
            ToolbarItem(placement: .primaryAction) {
                HStack(spacing: 6) {
                    Circle()
                        .fill(authService.isAuthenticated ? .green : .gray)
                        .frame(width: 8, height: 8)
                    Text(authService.isAuthenticated ? "已登录" : "未登录")
                        .font(.caption)
                        .foregroundStyle(.secondary)
                }
            }
        }
        .frame(minWidth: 1000, minHeight: 700)
    }
}

#Preview {
    MainWindowView()
}
