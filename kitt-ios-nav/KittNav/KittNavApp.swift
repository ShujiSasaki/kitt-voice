import SwiftUI
import MapKit

/// KITT Nav - ナビ専用iOSアプリ
///
/// Firebase RTDBの /nav パスを監視。
/// ナビ先が更新されたらMapKitでターンバイターンナビを自動開始。
/// Shujiは何も操作しない。画面はずっとナビ表示。
@main
struct KittNavApp: App {
    @StateObject private var navManager = NavManager()

    var body: some Scene {
        WindowGroup {
            ContentView()
                .environmentObject(navManager)
                .onAppear {
                    // 画面を常にON (ナビ専用端末)
                    UIApplication.shared.isIdleTimerDisabled = true
                    navManager.startListening()
                }
        }
    }
}
