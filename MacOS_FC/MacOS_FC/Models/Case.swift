//
//  Case.swift
//  MacOS_FC
//
//  案件数据模型（对应后端 CaseOut Schema）
//

import Foundation

struct Case: Codable, Identifiable {
    let id: Int
    let name: String
    let status: String?
    let isArchived: Bool
    let caseType: String?
    let startDate: String?
    let effectiveDate: String?
    let targetAmount: Double?
    let preservationAmount: Double?
    let causeOfAction: String?
    let currentStage: String?
    let parties: [CaseParty]?
    let assignments: [CaseAssignment]?
    let caseNumbers: [CaseNumber]?
    let contractId: Int?

    // MARK: - 计算属性

    var displayName: String {
        name.isEmpty ? "未命名案件" : name
    }

    var folderName: String {
        "\(displayName)_\(id)"
    }

    var isActive: Bool {
        status != "closed" && !isArchived
    }

    /// 根据案件阶段返回文件夹结构
    var stageFolderStructure: [String] {
        switch currentStage {
        case "first_instance":
            return [
                "01_起诉材料",
                "02_证据材料",
                "03_法律文书",
                "04_庭审记录",
                "05_判决文书"
            ]
        case "second_instance":
            return [
                "01_上诉材料",
                "02_证据材料",
                "03_法律文书",
                "04_庭审记录",
                "05_判决文书"
            ]
        case "execution":
            return [
                "01_执行申请",
                "02_财产线索",
                "03_执行文书",
                "04_执行记录"
            ]
        default:
            return [
                "01_委托材料",
                "02_证据材料",
                "03_法律文书",
                "04_案件进展"
            ]
        }
    }
}

struct CaseParty: Codable, Identifiable {
    let id: Int
    let `case`: Int
    let client: Int
    let legalStatus: String?
    let clientDetail: Client?
}

struct CaseAssignment: Codable, Identifiable {
    let id: Int
    let `case`: Int
    let lawyer: Int
    let lawyerDetail: Lawyer?
}

struct CaseNumber: Codable, Identifiable {
    let id: Int
    let number: String
    let remarks: String?
    let createdAt: String?
}
