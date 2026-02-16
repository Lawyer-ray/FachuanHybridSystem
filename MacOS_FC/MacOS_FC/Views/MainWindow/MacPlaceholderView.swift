import SwiftUI

struct MacPlaceholderView: View {
    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 18) {
                VStack(alignment: .leading, spacing: 6) {
                    Label("Mac", systemImage: "macwindow")
                        .font(.largeTitle)
                        .fontWeight(.semibold)
                    
                    Text("原生功能区域（占位）")
                        .foregroundStyle(.secondary)
                }
                
                GroupBox("计划中的能力") {
                    VStack(alignment: .leading, spacing: 10) {
                        Label("文件夹创建与模板", systemImage: "folder.badge.plus")
                        Label("本地索引与离线缓存", systemImage: "externaldrive")
                        Label("后台同步与状态栏入口", systemImage: "arrow.triangle.2.circlepath")
                        Label("通知/快捷指令/全局快捷键", systemImage: "bolt")
                    }
                    .frame(maxWidth: .infinity, alignment: .leading)
                    .padding(.vertical, 4)
                }
                
                GroupBox("占位动作") {
                    VStack(alignment: .leading, spacing: 12) {
                        Button("选择工作目录") {}
                            .disabled(true)
                        Button("新建合同文件夹") {}
                            .disabled(true)
                        Button("新建案件文件夹") {}
                            .disabled(true)
                    }
                    .frame(maxWidth: .infinity, alignment: .leading)
                    .padding(.vertical, 4)
                }
            }
            .padding(24)
            .frame(maxWidth: .infinity, alignment: .topLeading)
        }
        .background(Color(nsColor: .windowBackgroundColor))
    }
}

#Preview {
    MacPlaceholderView()
        .frame(width: 900, height: 600)
}
