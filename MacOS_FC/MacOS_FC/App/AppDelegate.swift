//
//  AppDelegate.swift
//  MacOS_FC
//
//  AppKit 代理
//

import AppKit
import os.log

class AppDelegate: NSObject, NSApplicationDelegate {
    private let logger = Logger(subsystem: "com.fachuan.macos", category: "app")

    func applicationDidFinishLaunching(_ notification: Notification) {
        logger.info("应用启动完成")

        // 注册 URL Scheme
        NSAppleEventManager.shared().setEventHandler(
            self,
            andSelector: #selector(handleURLEvent(_:withReplyEvent:)),
            forEventClass: AEEventClass(kInternetEventClass),
            andEventID: AEEventID(kAEGetURL)
        )
    }

    func applicationWillTerminate(_ notification: Notification) {
        logger.info("应用即将退出")
    }

    func applicationShouldTerminateAfterLastWindowClosed(_ sender: NSApplication) -> Bool {
        true  // 关闭窗口后退出应用
    }

    // MARK: - URL Scheme 处理

    @objc func handleURLEvent(_ event: NSAppleEventDescriptor, withReplyEvent replyEvent: NSAppleEventDescriptor) {
        guard let urlString = event.paramDescriptor(forKeyword: AEKeyword(keyDirectObject))?.stringValue,
              let url = URL(string: urlString) else {
            return
        }

        logger.info("收到 URL: \(urlString)")
        handleURL(url)
    }

    private func handleURL(_ url: URL) {
        guard url.scheme == AppConfig.urlScheme else { return }

        switch url.host {
        case "create-contract-folder":
            if let path = url.queryParameters["path"] {
                logger.info("创建合同文件夹: \(path)")
            }

        case "create-case-folder":
            if let path = url.queryParameters["path"] {
                logger.info("创建案件文件夹: \(path)")
            }

        case "sync":
            if let path = url.queryParameters["path"] {
                logger.info("同步文件夹: \(path)")
            }

        default:
            logger.warning("未知的 URL 操作: \(url.host ?? "")")
        }
    }
}

// MARK: - URL 扩展

extension URL {
    var queryParameters: [String: String] {
        guard let components = URLComponents(url: self, resolvingAgainstBaseURL: false),
              let queryItems = components.queryItems else {
            return [:]
        }

        var params: [String: String] = [:]
        for item in queryItems {
            params[item.name] = item.value
        }
        return params
    }
}
