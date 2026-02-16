import SwiftUI

struct MainTabViewHost: NSViewControllerRepresentable {
    @Binding var isLoading: Bool
    @Binding var canGoBack: Bool
    @Binding var canGoForward: Bool
    let onTokenCaptured: (TokenPair) -> Void
    
    func makeNSViewController(context: Context) -> MainTabsViewController {
        let viewController = MainTabsViewController(
            isLoading: $isLoading,
            canGoBack: $canGoBack,
            canGoForward: $canGoForward,
            onTokenCaptured: onTokenCaptured
        )
        return viewController
    }
    
    func updateNSViewController(_ nsViewController: MainTabsViewController, context: Context) {
        nsViewController.updateBindings(
            isLoading: $isLoading,
            canGoBack: $canGoBack,
            canGoForward: $canGoForward,
            onTokenCaptured: onTokenCaptured
        )
    }
}

final class MainTabsViewController: NSTabViewController {
    private var isLoading: Binding<Bool>
    private var canGoBack: Binding<Bool>
    private var canGoForward: Binding<Bool>
    private var onTokenCaptured: (TokenPair) -> Void
    
    init(
        isLoading: Binding<Bool>,
        canGoBack: Binding<Bool>,
        canGoForward: Binding<Bool>,
        onTokenCaptured: @escaping (TokenPair) -> Void
    ) {
        self.isLoading = isLoading
        self.canGoBack = canGoBack
        self.canGoForward = canGoForward
        self.onTokenCaptured = onTokenCaptured
        super.init(nibName: nil, bundle: nil)
    }
    
    required init?(coder: NSCoder) {
        return nil
    }
    
    override func viewDidLoad() {
        super.viewDidLoad()
        
        tabStyle = .toolbar
        transitionOptions = [.crossfade]
        
        let web = NSHostingController(
            rootView: WebTabRootView(
                isLoading: isLoading,
                canGoBack: canGoBack,
                canGoForward: canGoForward,
                onTokenCaptured: { [weak self] token in
                    self?.onTokenCaptured(token)
                }
            )
        )
        let webItem = NSTabViewItem(viewController: web)
        webItem.label = "Web"
        webItem.image = NSImage(systemSymbolName: "globe", accessibilityDescription: nil)
        
        let mac = NSHostingController(rootView: MacPlaceholderView())
        let macItem = NSTabViewItem(viewController: mac)
        macItem.label = "Mac"
        macItem.image = NSImage(systemSymbolName: "macwindow", accessibilityDescription: nil)

        addTabViewItem(webItem)
        addTabViewItem(macItem)

        if tabViewItems.indices.contains(0) {
            selectedTabViewItemIndex = 0
        }
    }
    
    func updateBindings(
        isLoading: Binding<Bool>,
        canGoBack: Binding<Bool>,
        canGoForward: Binding<Bool>,
        onTokenCaptured: @escaping (TokenPair) -> Void
    ) {
        self.isLoading = isLoading
        self.canGoBack = canGoBack
        self.canGoForward = canGoForward
        self.onTokenCaptured = onTokenCaptured
    }
}

struct WebTabRootView: View {
    @Binding var isLoading: Bool
    @Binding var canGoBack: Bool
    @Binding var canGoForward: Bool
    let onTokenCaptured: (TokenPair) -> Void
    
    var body: some View {
        WebViewContainer(
            url: URL(string: AppConfig.webAppURL)!,
            isLoading: $isLoading,
            canGoBack: $canGoBack,
            canGoForward: $canGoForward,
            onTokenCaptured: onTokenCaptured
        )
        .overlay(alignment: .center) {
            if isLoading {
                ProgressView()
                    .scaleEffect(0.8)
                    .frame(width: 40, height: 40)
                    .background(.ultraThinMaterial, in: RoundedRectangle(cornerRadius: 8))
            }
        }
    }
}
