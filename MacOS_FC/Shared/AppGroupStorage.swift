//
//  AppGroupStorage.swift
//  MacOS_FC
//
//  本地共享存储（使用文件系统共享数据）
//

import Foundation

final class AppGroupStorage {
    static let shared = AppGroupStorage()

    private let sharedDirectory: URL

    private init() {
        // 使用 Application Support 目录作为共享存储
        let appSupport = FileManager.default
            .urls(for: .applicationSupportDirectory, in: .userDomainMask)
            .first!
            .appendingPathComponent("com.fachuan.macos")

        self.sharedDirectory = appSupport

        // 创建目录
        try? FileManager.default.createDirectory(
            at: appSupport,
            withIntermediateDirectories: true
        )
    }

    // MARK: - Token 存储

    func setToken(_ token: TokenPair) {
        let data = try? JSONEncoder().encode(token)
        let fileURL = sharedDirectory.appendingPathComponent("token.json")
        try? data?.write(to: fileURL)
    }

    func getToken() -> TokenPair? {
        let fileURL = sharedDirectory.appendingPathComponent("token.json")
        guard let data = try? Data(contentsOf: fileURL) else { return nil }
        return try? JSONDecoder().decode(TokenPair.self, from: data)
    }

    func clearToken() {
        let fileURL = sharedDirectory.appendingPathComponent("token.json")
        try? FileManager.default.removeItem(at: fileURL)
    }

    // MARK: - 用户信息

    func setCurrentUser(_ user: CurrentUser) {
        let data = try? JSONEncoder().encode(user)
        let fileURL = sharedDirectory.appendingPathComponent("user.json")
        try? data?.write(to: fileURL)
    }

    func getCurrentUser() -> CurrentUser? {
        let fileURL = sharedDirectory.appendingPathComponent("user.json")
        guard let data = try? Data(contentsOf: fileURL) else { return nil }
        return try? JSONDecoder().decode(CurrentUser.self, from: data)
    }

    // MARK: - 文件夹绑定

    func setFolderBindings(_ bindings: [FolderBinding]) {
        let data = try? JSONEncoder().encode(bindings)
        let fileURL = sharedDirectory.appendingPathComponent("bindings.json")
        try? data?.write(to: fileURL)
    }

    func getFolderBindings() -> [FolderBinding] {
        let fileURL = sharedDirectory.appendingPathComponent("bindings.json")
        guard let data = try? Data(contentsOf: fileURL) else { return [] }
        return (try? JSONDecoder().decode([FolderBinding].self, from: data)) ?? []
    }
}

// MARK: - 共享数据模型

struct CurrentUser: Codable {
    let id: Int
    let username: String
    let realName: String?
    let lawfirmId: Int?
    let lawfirmName: String?
}

struct FolderBinding: Codable, Identifiable {
    let id: Int
    let entityType: String
    let entityId: Int
    let entityName: String
    let folderPath: String
    let createdAt: String
}
