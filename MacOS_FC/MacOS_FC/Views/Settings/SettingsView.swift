//
//  SettingsView.swift
//  MacOS_FC
//
//  设置视图
//

import SwiftUI
import AppKit
import os.log
import FinderSync

struct SettingsView: View {
    @StateObject private var authService = AuthService.shared
    @AppStorage("defaultFolderPath") private var defaultFolderPath = ""
    @AppStorage("autoSyncEnabled") private var autoSyncEnabled = false
    @AppStorage("showNotifications") private var showNotifications = true
    
    var body: some View {
        TabView {
            GeneralSettingsView(
                defaultFolderPath: $defaultFolderPath,
                autoSyncEnabled: $autoSyncEnabled,
                showNotifications: $showNotifications
            )
            .tabItem {
                Label("通用", systemImage: "gear")
            }
            
            AccountSettingsView()
            .tabItem {
                Label("账户", systemImage: "person.circle")
            }
            
            AboutView()
            .tabItem {
                Label("关于", systemImage: "info.circle")
            }
        }
        .frame(width: 450, height: 300)
    }
}

// MARK: - 通用设置

struct GeneralSettingsView: View {
    @Binding var defaultFolderPath: String
    @Binding var autoSyncEnabled: Bool
    @Binding var showNotifications: Bool

    @State private var installErrorMessage: String?
    @State private var extensionStatusText: String = "未检测"
    private let logger = Logger(subsystem: "com.fachuan.macos", category: "settings")
    
    var body: some View {
        Form {
            Section("Finder 扩展") {
                VStack(alignment: .leading, spacing: 10) {
                    VStack(alignment: .leading, spacing: 4) {
                        Text("启用 Finder 右键菜单")
                            .font(.body)
                        Text("如果 Finder 里一直看不到菜单，通常需要把应用安装到 /Applications 后再启用扩展。")
                            .font(.caption)
                            .foregroundStyle(.secondary)
                    }

                    VStack(alignment: .leading, spacing: 6) {
                        LabeledContent("应用位置", value: isInstalledInApplications ? "已安装（Applications）" : "未安装（Applications）")
                        LabeledContent("扩展已嵌入", value: embeddedFinderSyncExtensionExists ? "是" : "否")
                        LabeledContent("默认目录书签", value: hasDefaultFolderBookmark ? "已保存" : "未保存")
                        LabeledContent("扩展运行状态", value: extensionStatusText)
                    }
                    .font(.caption)

                    HStack {
                        Button("打开扩展设置") {
                            openExtensionSettings()
                        }

                        Button("打开 Finder 扩展管理") {
                            openFinderSyncExtensionManagement()
                        }

                        Button("刷新状态") {
                            refreshExtensionStatus()
                        }

                        if !isInstalledInApplications {
                            Button("安装到 Applications 并重启") {
                                Task { await installToApplicationsAndRelaunch() }
                            }
                        }
                    }

                    if let message = installErrorMessage {
                        Text(message)
                            .font(.caption)
                            .foregroundStyle(.red)
                    }
                }
                .onAppear {
                    refreshExtensionStatus()
                }
            }
            
            Section("文件夹") {
                HStack {
                    TextField("默认文件夹路径", text: $defaultFolderPath)
                        .textFieldStyle(.roundedBorder)
                    
                    Button("选择...") {
                        selectDefaultFolder()
                    }
                }
                
                Toggle("自动同步文件夹", isOn: $autoSyncEnabled)
                Toggle("显示通知", isOn: $showNotifications)
            }
        }
        .padding()
    }
    
    private func openExtensionSettings() {
        // 打开系统设置的扩展页面
        if let url = URL(string: "x-apple.systempreferences:com.apple.ExtensionsPreferences") {
            NSWorkspace.shared.open(url)
        }
    }

    private func openFinderSyncExtensionManagement() {
        FIFinderSyncController.showExtensionManagementInterface()
    }

    private func refreshExtensionStatus() {
        let status = readLastFinderSyncEvent()
        extensionStatusText = status ?? "未检测到扩展事件（可能未被 Finder 加载）"
    }

    private func readLastFinderSyncEvent() -> String? {
        guard let containerURL = FileManager.default.containerURL(forSecurityApplicationGroupIdentifier: SharedConstants.appGroupID) else {
            return "App Group 容器不可用"
        }

        let logURL = containerURL.appendingPathComponent("finder-sync-events.jsonl")
        guard let data = try? Data(contentsOf: logURL), let text = String(data: data, encoding: .utf8) else {
            return nil
        }

        let lines = text.split(separator: "\n", omittingEmptySubsequences: true)
        guard let last = lines.last, let jsonData = last.data(using: .utf8) else {
            return nil
        }

        guard
            let obj = try? JSONSerialization.jsonObject(with: jsonData) as? [String: Any]
        else {
            return "扩展事件解析失败"
        }

        let ts = (obj["ts"] as? String) ?? ""
        let name = (obj["name"] as? String) ?? ""
        let pid = (obj["pid"] as? String) ?? ""
        if !pid.isEmpty {
            return "\(ts) \(name) pid=\(pid)"
        }
        return "\(ts) \(name)"
    }


    private var isInstalledInApplications: Bool {
        let path = Bundle.main.bundleURL.path
        let userApplicationsPrefix = FileManager.default.homeDirectoryForCurrentUser
            .appendingPathComponent("Applications")
            .path
            .appending("/")
        return path.hasPrefix("/Applications/") || path.hasPrefix(userApplicationsPrefix)
    }

    private var embeddedFinderSyncExtensionExists: Bool {
        guard let pluginsURL = Bundle.main.builtInPlugInsURL else { return false }
        let url = pluginsURL.appendingPathComponent("FinderSyncExtension.appex")
        return FileManager.default.fileExists(atPath: url.path)
    }

    private var hasDefaultFolderBookmark: Bool {
        guard let defaults = UserDefaults(suiteName: SharedConstants.appGroupID) else { return false }
        return defaults.data(forKey: SharedConstants.defaultFolderBookmarkKey) != nil
    }

    @MainActor
    private func installToApplicationsAndRelaunch() async {
        installErrorMessage = nil
#if DEBUG
        installErrorMessage = "提示：当前是 Debug 构建。若系统仍提示无法打开，请改用 Scheme：法穿AI-Release 安装。"
#endif

        let sourceURL = Bundle.main.bundleURL
        let systemApplicationsURL = URL(fileURLWithPath: "/Applications").appendingPathComponent(sourceURL.lastPathComponent)
        let userApplicationsRootURL = FileManager.default.homeDirectoryForCurrentUser.appendingPathComponent("Applications")


        do {
            let installedURL: URL
            do {
                if FileManager.default.fileExists(atPath: systemApplicationsURL.path) {
                    try FileManager.default.removeItem(at: systemApplicationsURL)
                }
                try FileManager.default.copyItem(at: sourceURL, to: systemApplicationsURL)
                installedURL = systemApplicationsURL
            } catch {
                let panel = NSOpenPanel()
                panel.message = "请选择安装目录（建议选择“/Applications”或“~/Applications”）。"
                panel.prompt = "选择"
                panel.canChooseDirectories = true
                panel.canChooseFiles = false
                panel.allowsMultipleSelection = false
                panel.directoryURL = FileManager.default.fileExists(atPath: userApplicationsRootURL.path) ? userApplicationsRootURL : FileManager.default.homeDirectoryForCurrentUser

                let response = panel.runModal()
                guard response == .OK, let destinationDirURL = panel.url else {
                    installErrorMessage = "已取消安装。"
                    return
                }

                let didAccess = destinationDirURL.startAccessingSecurityScopedResource()
                defer {
                    if didAccess { destinationDirURL.stopAccessingSecurityScopedResource() }
                }

                let destinationURL = destinationDirURL.appendingPathComponent(sourceURL.lastPathComponent)
                if FileManager.default.fileExists(atPath: destinationURL.path) {
                    try FileManager.default.removeItem(at: destinationURL)
                }
                try FileManager.default.copyItem(at: sourceURL, to: destinationURL)
                installedURL = destinationURL
            }

            logger.info("已复制应用到: \(installedURL.path)")

            let configuration = NSWorkspace.OpenConfiguration()
            NSWorkspace.shared.openApplication(at: installedURL, configuration: configuration) { _, error in
                if let error {
                    self.logger.error("重新启动应用失败: \(error.localizedDescription)")
                }
                NSRunningApplication.current.terminate()
            }
        } catch {
            installErrorMessage = "安装失败：\(error.localizedDescription)"
            logger.error("安装到 /Applications 失败: \(error.localizedDescription)")
        }
    }
    
    private func selectDefaultFolder() {
        Task {
            if let url = await FolderService.shared.selectFolder(title: "选择默认文件夹") {
                defaultFolderPath = url.path
                _ = FolderService.shared.saveDefaultFolderBookmark(for: url)
            }
        }
    }
}

// MARK: - 账户设置

struct AccountSettingsView: View {
    @StateObject private var authService = AuthService.shared
    
    var body: some View {
        Form {
            if authService.isAuthenticated {
                Section {
                    if let user = authService.currentUser {
                        LabeledContent("用户名", value: user.username)
                        if let realName = user.realName {
                            LabeledContent("姓名", value: realName)
                        }
                        if let lawfirmName = user.lawfirmName {
                            LabeledContent("律所", value: lawfirmName)
                        }
                    }
                    
                    Button("退出登录", role: .destructive) {
                        authService.logout()
                    }
                }
            } else {
                Section {
                    Text("未登录")
                        .foregroundStyle(.secondary)
                    
                    Text("请在主窗口中登录")
                        .font(.caption)
                        .foregroundStyle(.secondary)
                }
            }
        }
        .padding()
    }
}

// MARK: - 关于

struct AboutView: View {
    var body: some View {
        VStack(spacing: 16) {
            Image(systemName: "doc.text.magnifyingglass")
                .font(.system(size: 64))
                .foregroundStyle(.blue)
            
            Text("法传")
                .font(.title)
                .fontWeight(.bold)
            
            Text("版本 \(AppConfig.appVersion) (\(AppConfig.buildNumber))")
                .foregroundStyle(.secondary)
            
            Text("律师案件管理系统")
                .font(.caption)
                .foregroundStyle(.secondary)
            
            Spacer()
            
            Link("访问官网", destination: URL(string: "https://fachuan.com")!)
                .buttonStyle(.link)
        }
        .padding()
        .frame(maxWidth: .infinity, maxHeight: .infinity)
    }
}

#Preview {
    SettingsView()
}
