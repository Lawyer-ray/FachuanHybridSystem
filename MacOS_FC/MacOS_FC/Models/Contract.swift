//
//  Contract.swift
//  MacOS_FC
//
//  合同数据模型（对应后端 ContractOut Schema）
//

import Foundation

struct Contract: Codable, Identifiable {
    let id: Int
    let name: String
    let caseType: String?
    let status: String?
    let specifiedDate: String?
    let startDate: String?
    let endDate: String?
    let isArchived: Bool
    let feeMode: String
    let fixedAmount: Double?
    let riskRate: Double?
    let customTerms: String?
    let representationStages: [String]?
    let cases: [Case]?
    let contractParties: [ContractParty]?
    let assignments: [ContractAssignment]?
    let primaryLawyer: Lawyer?
    let caseTypeLabel: String?
    let statusLabel: String?
    let totalReceived: Double?
    let totalInvoiced: Double?
    let unpaidAmount: Double?
    
    // MARK: - 计算属性
    
    var displayName: String {
        name.isEmpty ? "未命名合同" : name
    }
    
    var folderName: String {
        "\(displayName)_\(id)"
    }
    
    var isActive: Bool {
        status == "active" && !isArchived
    }
}

struct ContractParty: Codable, Identifiable {
    let id: Int
    let contract: Int
    let client: Int
    let role: String?
    let clientDetail: Client?
    let roleLabel: String?
}

struct ContractAssignment: Codable, Identifiable {
    let id: Int
    let lawyerId: Int
    let lawyerName: String
    let isPrimary: Bool
    let order: Int
}
