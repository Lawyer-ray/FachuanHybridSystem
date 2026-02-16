//
//  TokenManager.swift
//  MacOS_FC
//
//  JWT Token 管理
//

import Foundation
import os.log

struct TokenPair: Codable {
    let access: String
    let refresh: String
}

final class TokenManager {
    static let shared = TokenManager()

    private let keychain = KeychainService()
    private let logger = Logger(subsystem: "com.fachuan.macos", category: "auth")

    private init() {}

    // MARK: - Token 存取

    var accessToken: String? {
        get { keychain.get("access_token") }
        set { keychain.set("access_token", value: newValue) }
    }

    var refreshToken: String? {
        get { keychain.get("refresh_token") }
        set { keychain.set("refresh_token", value: newValue) }
    }

    var hasToken: Bool {
        accessToken != nil
    }

    // MARK: - Token 操作

    /// 从 WebView 登录成功后捕获 Token
    func captureTokenFromWebView(_ token: TokenPair) {
        accessToken = token.access
        refreshToken = token.refresh

        // 同步到 App Group（供 Finder 扩展使用）
        AppGroupStorage.shared.setToken(token)

        logger.info("Token 已捕获并存储")
    }

    /// 检查 Token 是否过期
    func isTokenExpired() -> Bool {
        guard let token = accessToken else { return true }
        return JWTDecoder.isExpired(token)
    }

    /// 刷新 Token
    func refreshAccessToken() async throws -> String {
        guard let refresh = refreshToken else {
            throw AuthError.noRefreshToken
        }

        do {
            let newToken = try await APIClient.shared.refreshToken(refresh)
            accessToken = newToken

            // 同步到 App Group
            if let refresh = refreshToken {
                AppGroupStorage.shared.setToken(TokenPair(access: newToken, refresh: refresh))
            }

            logger.info("Token 已刷新")
            return newToken
        } catch {
            if case APIError.unauthorized = error {
                clearTokens()
            }
            throw error
        }

    }

    /// 清除所有 Token
    func clearTokens() {
        accessToken = nil
        refreshToken = nil
        AppGroupStorage.shared.clearToken()
        logger.info("Token 已清除")
    }
}

// MARK: - JWT 解码

enum JWTDecoder {
    static func decode(_ token: String) -> [String: Any]? {
        let parts = token.split(separator: ".")
        guard parts.count == 3 else { return nil }

        let payload = String(parts[1])

        // Base64 URL 解码
        var base64 = payload
            .replacingOccurrences(of: "-", with: "+")
            .replacingOccurrences(of: "_", with: "/")

        // 补齐 padding
        let remainder = base64.count % 4
        if remainder > 0 {
            base64 += String(repeating: "=", count: 4 - remainder)
        }

        guard let data = Data(base64Encoded: base64),
              let json = try? JSONSerialization.jsonObject(with: data) as? [String: Any] else {
            return nil
        }

        return json
    }

    static func isExpired(_ token: String) -> Bool {
        guard let payload = decode(token),
              let exp = payload["exp"] as? TimeInterval else {
            return true
        }

        // 提前 30 秒认为过期
        return Date().timeIntervalSince1970 >= (exp - 30)
    }
}

// MARK: - 错误类型

enum AuthError: LocalizedError {
    case noRefreshToken
    case tokenExpired
    case invalidCredentials
    case networkError(String)

    var errorDescription: String? {
        switch self {
        case .noRefreshToken: return "无刷新令牌"
        case .tokenExpired: return "令牌已过期"
        case .invalidCredentials: return "凭证无效"
        case .networkError(let msg): return "网络错误: \(msg)"
        }
    }
}
