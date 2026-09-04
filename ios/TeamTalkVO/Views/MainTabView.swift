import SwiftUI

struct MainTabView: View {
    @EnvironmentObject var connection: TTConnectionController

    var body: some View {
        TabView {
            ServerListView()
                .tabItem {
                    Label("Server", systemImage: "server.rack")
                }
                .accessibilityLabel("Server-Tab")

            ChannelsView()
                .tabItem {
                    Label("Kanäle", systemImage: "list.bullet.indent")
                }
                .accessibilityLabel("Kanäle-Tab")

            ChatView()
                .tabItem {
                    Label("Chat", systemImage: "bubble.left.and.bubble.right")
                }
                .accessibilityLabel("Chat-Tab")

            AudioView()
                .tabItem {
                    Label("Audio", systemImage: "mic")
                }
                .accessibilityLabel("Audio-Tab")

            MediaView()
                .tabItem {
                    Label("Medien", systemImage: "radio")
                }
                .accessibilityLabel("Medien-Tab")

            SpeakView()
                .tabItem {
                    Label("Sprechen", systemImage: "waveform")
                }
                .accessibilityLabel("Sprechen-Tab")

            SettingsView()
                .tabItem {
                    Label("Einstellungen", systemImage: "gear")
                }
                .accessibilityLabel("Einstellungen-Tab")
        }
    }
}
