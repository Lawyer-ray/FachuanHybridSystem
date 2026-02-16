//
//  Constants.swift
//  MacOS_FC
//
//  共享常量（主应用与 Finder 扩展共用）
//

import Foundation

// MARK: - App Group 配置

enum SharedConstants {
    static let appGroupID = "group.com.fachuan.macos"
    static let keychainService = "com.fachuan.macos.auth"
    static let urlScheme = "fachuan"
    static let defaultFolderBookmarkKey = "com.fachuan.macos.defaultFolderBookmark"
}

// MARK: - 文件夹模板

enum FolderTemplateType: String, Codable, CaseIterable {
    case contract = "contract"
    case civilCase = "civil_case"
    case criminalCase = "criminal_case"
    case administrativeCase = "administrative_case"
    
    var displayName: String {
        switch self {
        case .contract: return "合同"
        case .civilCase: return "民事案件"
        case .criminalCase: return "刑事案件"
        case .administrativeCase: return "行政案件"
        }
    }
    
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
        }
    }
}

// MARK: - 案件阶段

enum CaseStageType: String, Codable {
    case investigation = "investigation"
    case prosecution = "prosecution"
    case firstInstance = "first_instance"
    case secondInstance = "second_instance"
    case retrial = "retrial"
    case execution = "execution"
    
    var displayName: String {
        switch self {
        case .investigation: return "侦查阶段"
        case .prosecution: return "审查起诉"
        case .firstInstance: return "一审"
        case .secondInstance: return "二审"
        case .retrial: return "再审"
        case .execution: return "执行"
        }
    }
}

// MARK: - 通知名称

extension Notification.Name {
    static let tokenDidUpdate = Notification.Name("com.fachuan.tokenDidUpdate")
    static let folderBindingDidChange = Notification.Name("com.fachuan.folderBindingDidChange")
    static let syncStatusDidChange = Notification.Name("com.fachuan.syncStatusDidChange")
}
