//
//  Client.swift
//  MacOS_FC
//
//  客户数据模型
//

import Foundation

struct Client: Codable, Identifiable {
    let id: Int
    let name: String
    let clientType: String?
    let idNumber: String?
    let phone: String?
    let address: String?
    let isOurClient: Bool?

    var displayName: String {
        name.isEmpty ? "未命名客户" : name
    }

    var isNaturalPerson: Bool {
        clientType == "natural_person"
    }
}

struct Lawyer: Codable, Identifiable {
    let id: Int
    let username: String
    let realName: String?
    let phone: String?

    var displayName: String {
        realName ?? username
    }
}
