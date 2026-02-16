//
//  FinderSync.swift
//  FinderSyncExtension
//
//  Finder 右键菜单扩展
//

import Cocoa
import FinderSync
import Darwin

class FinderSync: FIFinderSync {
    
    // 今日文件夹名称格式
    private var todayFolderName: String {
        let formatter = DateFormatter()
        formatter.dateFormat = "yyyy.MM.dd"
        return "\(formatter.string(from: Date()))-"
    }

    private var monitoredRootURL: URL?
    private var isAccessingSecurityScopedResource = false
    private lazy var rootMenu: NSMenu = makeRootMenu()
    private let isoFormatter = ISO8601DateFormatter()
    
    override init() {
        super.init()
        
        NSLog("FinderSync() 法穿AI扩展已启动")
        recordEvent(name: "init", payload: ["pid": "\(getpid())"])
        refreshDirectoryURLs()
    }

    deinit {
        stopAccessingMonitoredRootIfNeeded()
    }
    
    // MARK: - Menu
    
    override func menu(for menuKind: FIMenuKind) -> NSMenu {
        refreshDirectoryURLs()
        updateMenuState()
        recordEvent(
            name: "menu",
            payload: [
                "kind": "\(menuKind.rawValue)",
                "targetedURL": FIFinderSyncController.default().targetedURL()?.path ?? "",
                "selectedCount": "\(FIFinderSyncController.default().selectedItemURLs()?.count ?? 0)"
            ]
        )
        return rootMenu
    }

    private func refreshDirectoryURLs() {
        var directoryURLs = Set<URL>()
        let homeURL = preferredUserHomeDirectory()
        directoryURLs.insert(homeURL)

        if let url = loadDefaultFolderURLFromBookmark() {
            if monitoredRootURL?.path != url.path {
                stopAccessingMonitoredRootIfNeeded()
                monitoredRootURL = url
                isAccessingSecurityScopedResource = url.startAccessingSecurityScopedResource()
            }
            directoryURLs.insert(url)
        } else {
            stopAccessingMonitoredRootIfNeeded()
            monitoredRootURL = nil
        }

        let candidateFolders: [String] = ["Downloads", "Desktop", "Documents"]
        for folder in candidateFolders {
            let url = homeURL.appendingPathComponent(folder, isDirectory: true)
            if FileManager.default.fileExists(atPath: url.path) {
                directoryURLs.insert(url)
            }
        }

        FIFinderSyncController.default().directoryURLs = directoryURLs
        recordEvent(
            name: "directoryURLs",
            payload: [
                "count": "\(directoryURLs.count)",
                "values": directoryURLs.map(\.path).sorted().joined(separator: "|")
            ]
        )
    }

    private func preferredUserHomeDirectory() -> URL {
        if let pwd = getpwuid(getuid()), let dir = pwd.pointee.pw_dir {
            return URL(fileURLWithPath: String(cString: dir), isDirectory: true)
        }
        return FileManager.default.homeDirectoryForCurrentUser
    }

    private func makeRootMenu() -> NSMenu {
        let menu = NSMenu(title: "法穿AI")

        let todayFolderItem = NSMenuItem(
            title: "新建今日文件夹",
            action: #selector(createTodayFolder(_:)),
            keyEquivalent: ""
        )
        todayFolderItem.target = self
        todayFolderItem.image = NSImage(systemSymbolName: "folder.badge.plus", accessibilityDescription: nil)
        menu.addItem(todayFolderItem)

        return menu
    }

    private func updateMenuState() {
        guard let todayFolderItem = rootMenu.items.first(where: { $0.action == #selector(createTodayFolder(_:)) }) else {
            return
        }

        todayFolderItem.isEnabled = true
        todayFolderItem.title = "新建今日文件夹"

        if let targetURL = targetDirectoryURL() {
            let todayFolderURL = targetURL.appendingPathComponent(todayFolderName)
            if FileManager.default.fileExists(atPath: todayFolderURL.path) {
                todayFolderItem.isEnabled = false
                todayFolderItem.title = "新建今日文件夹（已存在）"
            }
        }
    }

    private func stopAccessingMonitoredRootIfNeeded() {
        guard isAccessingSecurityScopedResource, let url = monitoredRootURL else { return }
        url.stopAccessingSecurityScopedResource()
        isAccessingSecurityScopedResource = false
    }

    private func loadDefaultFolderURLFromBookmark() -> URL? {
        guard let defaults = UserDefaults(suiteName: SharedConstants.appGroupID) else {
            return nil
        }

        guard let bookmarkData = defaults.data(forKey: SharedConstants.defaultFolderBookmarkKey) else {
            return nil
        }

        var isStale = false
        do {
            let url = try URL(
                resolvingBookmarkData: bookmarkData,
                options: [.withSecurityScope],
                relativeTo: nil,
                bookmarkDataIsStale: &isStale
            )

            if isStale {
                if let refreshed = try? url.bookmarkData(
                    options: [.withSecurityScope],
                    includingResourceValuesForKeys: nil,
                    relativeTo: nil
                ) {
                    defaults.set(refreshed, forKey: SharedConstants.defaultFolderBookmarkKey)
                }
            }

            return url
        } catch {
            return nil
        }
    }

    private func recordEvent(name: String, payload: [String: String]) {
        guard let containerURL = FileManager.default.containerURL(forSecurityApplicationGroupIdentifier: SharedConstants.appGroupID) else {
            return
        }

        let logURL = containerURL.appendingPathComponent("finder-sync-events.jsonl")
        var event: [String: String] = [
            "ts": isoFormatter.string(from: Date()),
            "name": name,
            "bundle": Bundle.main.bundleIdentifier ?? "",
            "version": Bundle.main.object(forInfoDictionaryKey: "CFBundleShortVersionString") as? String ?? "",
            "build": Bundle.main.object(forInfoDictionaryKey: "CFBundleVersion") as? String ?? ""
        ]
        for (k, v) in payload {
            event[k] = v
        }

        guard let data = try? JSONSerialization.data(withJSONObject: event, options: []) else {
            return
        }
        guard var line = String(data: data, encoding: .utf8) else { return }
        line.append("\n")

        do {
            if FileManager.default.fileExists(atPath: logURL.path) {
                let handle = try FileHandle(forWritingTo: logURL)
                try handle.seekToEnd()
                try handle.write(contentsOf: Data(line.utf8))
                try handle.close()
            } else {
                try Data(line.utf8).write(to: logURL, options: [.atomic])
            }
        } catch {
            return
        }
    }
    
    // MARK: - Actions
    
    @objc func createTodayFolder(_ sender: AnyObject?) {
        guard let targetURL = targetDirectoryURL() else {
            NSLog("无法获取目标文件夹路径")
            return
        }
        
        let newFolderURL = targetURL.appendingPathComponent(todayFolderName)

        if FileManager.default.fileExists(atPath: newFolderURL.path) {
            NSSound.beep()
            return
        }
        
        do {
            try FileManager.default.createDirectory(
                at: newFolderURL,
                withIntermediateDirectories: false,
                attributes: nil
            )
            NSLog("成功创建今日文件夹: %@", newFolderURL.path)
            
            revealAndBeginRename(newFolderURL)
            
        } catch {
            NSLog("创建文件夹失败: %@", error.localizedDescription)
        }
    }

    private func revealAndBeginRename(_ url: URL) {
        NSWorkspace.shared.activateFileViewerSelecting([url])
        
        DispatchQueue.main.asyncAfter(deadline: .now() + 0.35) { [path = url.path] in
            let escapedPath = path.replacingOccurrences(of: "\"", with: "\\\"")
            let scriptSource = """
            tell application "Finder"
                activate
                reveal POSIX file "\(escapedPath)"
            end tell
            delay 0.15
            tell application "System Events"
                tell process "Finder"
                    key code 36
                end tell
            end tell
            """
            
            if let script = NSAppleScript(source: scriptSource) {
                var error: NSDictionary?
                script.executeAndReturnError(&error)
            }
        }
    }

    private func targetDirectoryURL() -> URL? {
        let controller = FIFinderSyncController.default()
        if let url = controller.targetedURL() {
            return url
        }

        if let selected = controller.selectedItemURLs(), let first = selected.first {
            return first.deletingLastPathComponent()
        }

        return nil
    }
    
    // MARK: - Toolbar (可选，暂时隐藏)
    
    override var toolbarItemName: String {
        return "法穿AI"
    }
    
    override var toolbarItemToolTip: String {
        return "法穿AI 快捷操作"
    }
    
    override var toolbarItemImage: NSImage {
        return NSImage(systemSymbolName: "folder.badge.gearshape", accessibilityDescription: nil) 
            ?? NSImage(named: NSImage.folderName)!
    }
}
