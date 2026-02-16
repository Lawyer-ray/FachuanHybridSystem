//
//  MacOS_FCApp.swift
//  MacOS_FC
//
//  应用入口
//

import SwiftUI

@main
struct MacOS_FCApp: App {
    @NSApplicationDelegateAdaptor(AppDelegate.self) var appDelegate

    var body: some Scene {
        WindowGroup {
            MainWindowView()
        }
        .windowStyle(.automatic)
        .windowToolbarStyle(.unified(showsTitle: false))
        .commands {
            // 文件菜单
            CommandGroup(replacing: .newItem) {
                Button("新建合同文件夹") {
                    NotificationCenter.default.post(name: .createContractFolder, object: nil)
                }
                .keyboardShortcut("n", modifiers: [.command, .shift])

                Button("新建案件文件夹") {
                    NotificationCenter.default.post(name: .createCaseFolder, object: nil)
                }
                .keyboardShortcut("n", modifiers: [.command, .option])
            }

            // 视图菜单
            CommandGroup(after: .sidebar) {
                Button("刷新") {
                    NotificationCenter.default.post(name: .refreshData, object: nil)
                }
                .keyboardShortcut("r", modifiers: .command)
            }
        }

        // 设置窗口
        Settings {
            SettingsView()
        }
    }
}

// MARK: - Notification Names

extension Notification.Name {
    static let createContractFolder = Notification.Name("createContractFolder")
    static let createCaseFolder = Notification.Name("createCaseFolder")
    static let refreshData = Notification.Name("refreshData")
}
