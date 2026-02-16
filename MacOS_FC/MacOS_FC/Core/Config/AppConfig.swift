//
//  AppConfig.swift
//  MacOS_FC
//
//  应用全局配置
//

import Foundation

enum AppConfig {
    // MARK: - API 配置
    static let apiBaseURL = "http://localhost:8002/api/v1"
    static let wsBaseURL = "ws://localhost:8002/ws"
    static let webAppURL = "http://localhost:5173/login"  // 直接打开登录页
    
    // MARK: - App Group（主应用与 Finder 扩展共享）
    static let appGroupID = "group.com.fachuan.macos"
    
    // MARK: - Keychain
    static let keychainService = "com.fachuan.macos.auth"
    
    // MARK: - URL Scheme
    static let urlScheme = "fachuan"
    
    // MARK: - 版本信息
    static var appVersion: String {
        Bundle.main.infoDictionary?["CFBundleShortVersionString"] as? String ?? "1.0.0"
    }
    
    static var buildNumber: String {
        Bundle.main.infoDictionary?["CFBundleVersion"] as? String ?? "1"
    }
}
