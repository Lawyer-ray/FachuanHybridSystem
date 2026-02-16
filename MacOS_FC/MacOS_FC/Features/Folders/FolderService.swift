//
//  FolderService.swift
//  MacOS_FC
//
//  文件夹创建服务
//

import Foundation
import AppKit
import os.log

final class FolderService {
    static let shared = FolderService()
    
    private let fileManager = FileManager.default
    private let logger = Logger(subsystem: "com.fachuan.macos", category: "folders")
    
    private init() {}
    
    // MARK: - 合同文件夹
    
    /// 为合同创建文件夹结构
    @discardableResult
    func createContractFolders(contract: Contract, at baseURL: URL) throws -> URL {
        let folderName = contract.folderName
        let contractURL = baseURL.appendingPathComponent(folderName)
        
        try fileManager.createDirectory(
            at: contractURL,
            withIntermediateDirectories: true,
            attributes: nil
        )
        
        // 创建标准子文件夹
        let subfolders = [
            "01_委托材料",
            "02_证据材料",
            "03_法律文书",
            "04_案件进展",
            "05_财务记录"
        ]
        
        for subfolder in subfolders {
            let subURL = contractURL.appendingPathComponent(subfolder)
            try fileManager.createDirectory(
                at: subURL,
                withIntermediateDirectories: true,
                attributes: nil
            )
        }
        
        logger.info("已创建合同文件夹: \(contractURL.path)")
        return contractURL
    }
    
    // MARK: - 案件文件夹
    
    /// 为案件创建文件夹结构
    @discardableResult
    func createCaseFolders(case caseItem: Case, at baseURL: URL) throws -> URL {
        let folderName = caseItem.folderName
        let caseURL = baseURL.appendingPathComponent(folderName)
        
        try fileManager.createDirectory(
            at: caseURL,
            withIntermediateDirectories: true,
            attributes: nil
        )
        
        // 根据案件阶段创建子文件夹
        let subfolders = caseItem.stageFolderStructure
        
        for subfolder in subfolders {
            let subURL = caseURL.appendingPathComponent(subfolder)
            try fileManager.createDirectory(
                at: subURL,
                withIntermediateDirectories: true,
                attributes: nil
            )
        }
        
        logger.info("已创建案件文件夹: \(caseURL.path)")
        return caseURL
    }
    
    // MARK: - 文件夹选择
    
    /// 打开文件夹选择面板
    func selectFolder(title: String = "选择文件夹") async -> URL? {
        await MainActor.run {
            let panel = NSOpenPanel()
            panel.title = title
            panel.canChooseFiles = false
            panel.canChooseDirectories = true
            panel.allowsMultipleSelection = false
            panel.canCreateDirectories = true
            
            let response = panel.runModal()
            return response == .OK ? panel.url : nil
        }
    }

    func saveDefaultFolderBookmark(for url: URL) -> Bool {
        do {
            let bookmarkData = try url.bookmarkData(
                options: [.withSecurityScope],
                includingResourceValuesForKeys: nil,
                relativeTo: nil
            )

            guard let defaults = UserDefaults(suiteName: SharedConstants.appGroupID) else {
                logger.error("无法创建 App Group UserDefaults")
                return false
            }

            defaults.set(bookmarkData, forKey: SharedConstants.defaultFolderBookmarkKey)
            defaults.synchronize()
            NotificationCenter.default.post(name: .folderBindingDidChange, object: nil)
            logger.info("已保存默认目录书签: \(url.path)")
            return true
        } catch {
            logger.error("保存默认目录书签失败: \(error.localizedDescription)")
            return false
        }
    }

    func loadDefaultFolderURLFromBookmark() -> URL? {
        guard let defaults = UserDefaults(suiteName: SharedConstants.appGroupID) else {
            logger.error("无法创建 App Group UserDefaults")
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
                _ = saveDefaultFolderBookmark(for: url)
            }

            return url
        } catch {
            logger.error("解析默认目录书签失败: \(error.localizedDescription)")
            return nil
        }
    }
    
    // MARK: - 文件夹操作
    
    /// 在 Finder 中显示文件夹
    func revealInFinder(_ url: URL) {
        NSWorkspace.shared.selectFile(nil, inFileViewerRootedAtPath: url.path)
    }
    
    /// 检查文件夹是否存在
    func folderExists(at url: URL) -> Bool {
        var isDirectory: ObjCBool = false
        return fileManager.fileExists(atPath: url.path, isDirectory: &isDirectory) && isDirectory.boolValue
    }
    
    /// 获取文件夹内容
    func contentsOfFolder(at url: URL) throws -> [URL] {
        try fileManager.contentsOfDirectory(
            at: url,
            includingPropertiesForKeys: [.isDirectoryKey],
            options: [.skipsHiddenFiles]
        )
    }
}

// MARK: - 文件夹模板

enum FolderTemplate {
    case contract
    case civilCase
    case criminalCase
    case administrativeCase
    case custom([String])
    
    var subfolders: [String] {
        switch self {
        case .contract:
            return [
                "01_委托材料",
                "02_证据材料",
                "03_法律文书",
                "04_案件进展",
                "05_财务记录"
            ]
        case .civilCase:
            return [
                "01_起诉材料",
                "02_证据材料",
                "03_法律文书",
                "04_庭审记录",
                "05_判决文书",
                "06_执行材料"
            ]
        case .criminalCase:
            return [
                "01_侦查阶段",
                "02_审查起诉",
                "03_一审材料",
                "04_二审材料",
                "05_申诉材料"
            ]
        case .administrativeCase:
            return [
                "01_行政复议",
                "02_行政诉讼",
                "03_证据材料",
                "04_法律文书"
            ]
        case .custom(let folders):
            return folders
        }
    }
}
