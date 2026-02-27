import SwiftUI

struct MainTabView: View {
    var body: some View {
        TabView {
            TopicSelectionView()
                .tabItem {
                    Label("練習", systemImage: "text.bubble")
                }

            ProfileView()
                .tabItem {
                    Label("我的", systemImage: "person.crop.circle")
                }
        }
    }
}
