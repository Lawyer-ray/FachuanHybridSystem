//
//  SidebarView.swift
//  MacOS_FC
//
//  侧边栏视图
//

import SwiftUI

struct SidebarView: View {
    @StateObject private var authService = AuthService.shared
    @State private var contracts: [Contract] = []
    @State private var cases: [Case] = []
    @State private var isLoadingContracts = false
    @State private var isLoadingCases = false
    @State private var selectedSection: SidebarSection = .contracts

    enum SidebarSection: String, CaseIterable {
        case contracts = "合同"
        case cases = "案件"
        case folders = "文件夹"
    }

    var body: some View {
        List(selection: $selectedSection) {
            Section("快捷操作") {
                Button(action: createContractFolder) {
                    Label("新建合同文件夹", systemImage: "folder.badge.plus")
                }
                .buttonStyle(.plain)

                Button(action: createCaseFolder) {
                    Label("新建案件文件夹", systemImage: "folder.badge.plus")
                }
                .buttonStyle(.plain)
            }

            Section("合同") {
                if isLoadingContracts {
                    ProgressView()
                        .frame(maxWidth: .infinity)
                } else if contracts.isEmpty {
                    Text("暂无合同")
                        .foregroundStyle(.secondary)
                } else {
                    ForEach(contracts.prefix(10)) { contract in
                        ContractRow(contract: contract)
                    }
                }
            }

            Section("案件") {
                if isLoadingCases {
                    ProgressView()
                        .frame(maxWidth: .infinity)
                } else if cases.isEmpty {
                    Text("暂无案件")
                        .foregroundStyle(.secondary)
                } else {
                    ForEach(cases.prefix(10)) { caseItem in
                        CaseRow(caseItem: caseItem)
                    }
                }
            }
        }
        .listStyle(.sidebar)
        .task {
            await loadData()
        }
        .refreshable {
            await loadData()
        }
    }

    // MARK: - Data Loading

    private func loadData() async {
        guard authService.isAuthenticated else { return }

        await withTaskGroup(of: Void.self) { group in
            group.addTask { await loadContracts() }
            group.addTask { await loadCases() }
        }
    }

    private func loadContracts() async {
        isLoadingContracts = true
        defer { isLoadingContracts = false }

        do {
            contracts = try await APIClient.shared.getContracts()
        } catch {
            // 静默处理错误
        }
    }

    private func loadCases() async {
        isLoadingCases = true
        defer { isLoadingCases = false }

        do {
            cases = try await APIClient.shared.getCases()
        } catch {
            // 静默处理错误
        }
    }

    // MARK: - Actions

    private func createContractFolder() {
        Task {
            guard let baseURL = await FolderService.shared.selectFolder(title: "选择合同文件夹位置") else {
                return
            }

            // TODO: 显示合同选择器
        }
    }

    private func createCaseFolder() {
        Task {
            guard let baseURL = await FolderService.shared.selectFolder(title: "选择案件文件夹位置") else {
                return
            }

            // TODO: 显示案件选择器
        }
    }
}

// MARK: - Row Views

struct ContractRow: View {
    let contract: Contract

    var body: some View {
        HStack {
            Image(systemName: "doc.text")
                .foregroundStyle(.blue)

            VStack(alignment: .leading, spacing: 2) {
                Text(contract.displayName)
                    .lineLimit(1)

                if let status = contract.statusLabel {
                    Text(status)
                        .font(.caption)
                        .foregroundStyle(.secondary)
                }
            }
        }
        .contextMenu {
            Button("创建文件夹") {
                Task {
                    guard let baseURL = await FolderService.shared.selectFolder() else { return }
                    try? FolderService.shared.createContractFolders(contract: contract, at: baseURL)
                }
            }

            Button("在浏览器中打开") {
                if let url = URL(string: "\(AppConfig.webAppURL)/admin/contracts/\(contract.id)") {
                    NSWorkspace.shared.open(url)
                }
            }
        }
    }
}

struct CaseRow: View {
    let caseItem: Case

    var body: some View {
        HStack {
            Image(systemName: "folder")
                .foregroundStyle(.orange)

            VStack(alignment: .leading, spacing: 2) {
                Text(caseItem.displayName)
                    .lineLimit(1)

                if let stage = caseItem.currentStage {
                    Text(stage)
                        .font(.caption)
                        .foregroundStyle(.secondary)
                }
            }
        }
        .contextMenu {
            Button("创建文件夹") {
                Task {
                    guard let baseURL = await FolderService.shared.selectFolder() else { return }
                    try? FolderService.shared.createCaseFolders(case: caseItem, at: baseURL)
                }
            }

            Button("在浏览器中打开") {
                if let url = URL(string: "\(AppConfig.webAppURL)/admin/cases/\(caseItem.id)") {
                    NSWorkspace.shared.open(url)
                }
            }
        }
    }
}

#Preview {
    SidebarView()
        .frame(width: 250)
}
