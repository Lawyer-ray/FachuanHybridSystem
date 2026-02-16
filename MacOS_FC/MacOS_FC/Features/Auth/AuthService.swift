//
//  AuthService.swift
//  MacOS_FC
//
//  认证服务
//

import Foundation
import Combine
import os.log

@MainActor
final class AuthService: ObservableObject {
    static let shared = AuthService()

    @Published private(set) var isAuthenticated = false
    @Published private(set) var currentUser: CurrentUser? = nil
    @Published private(set) var isLoading = false

    private let logger = Logger(subsystem: "com.fachuan.macos", category: "auth")

    private init() {
        // 检查已存储的 Token
        checkStoredToken()
    }

    // MARK: - Public Methods

    /// 检查已存储的 Token
    func checkStoredToken() {
        if TokenManager.shared.hasToken && !TokenManager.shared.isTokenExpired() {
            isAuthenticated = true
            currentUser = AppGroupStorage.shared.getCurrentUser()
            logger.info("已恢复登录状态")
        } else if TokenManager.shared.hasToken {
            // Token 过期，尝试刷新
            Task {
                await refreshTokenIfNeeded()
            }
        }
    }

    /// 处理 WebView 登录成功
    func handleWebViewLogin(_ token: TokenPair) {
        TokenManager.shared.captureTokenFromWebView(token)
        isAuthenticated = true
        logger.info("WebView 登录成功")

        // 获取用户信息
        Task {
            await fetchCurrentUser()
        }
    }

    /// 登出
    func logout() {
        TokenManager.shared.clearTokens()
        isAuthenticated = false
        currentUser = nil
        logger.info("已登出")
    }

    /// 刷新 Token
    func refreshTokenIfNeeded() async {
        guard TokenManager.shared.hasToken else { return }

        do {
            _ = try await TokenManager.shared.refreshAccessToken()
            isAuthenticated = true
            logger.info("Token 刷新成功")
        } catch {
            logger.error("Token 刷新失败: \(error.localizedDescription)")
            logout()
        }
    }

    // MARK: - Private Methods

    private func fetchCurrentUser() async {
        // TODO: 调用 API 获取当前用户信息
        // let user = try await APIClient.shared.getCurrentUser()
        // currentUser = user
        // AppGroupStorage.shared.setCurrentUser(user)
    }
}
