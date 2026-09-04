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

            FilesView()
                .tabItem {
                    Label("Dateien", systemImage: "folder")
                }
                .accessibilityLabel("Dateien-Tab")

            SpeakView()
                .tabItem {
                    Label("Sprechen", systemImage: "waveform")
                }
                .accessibilityLabel("Sprechen-Tab")

            AdminView()
                .tabItem {
                    Label("Admin", systemImage: "shield")
                }
                .accessibilityLabel("Administration-Tab")

            VideoView()
                .tabItem {
                    Label("Video", systemImage: "video")
                }
                .accessibilityLabel("Video-Tab")

            SystemView()
                .tabItem {
                    Label("System", systemImage: "terminal")
                }
                .accessibilityLabel("System-Tab")

            SettingsView()
                .tabItem {
                    Label("Einstellungen", systemImage: "gear")
                }
                .accessibilityLabel("Einstellungen-Tab")
        }
    }
}
