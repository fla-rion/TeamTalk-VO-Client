import SwiftUI

@main
struct TeamTalkVOApp: App {
    @StateObject private var serverStore = SavedServerStore()
    @StateObject private var prefs = AppPreferencesStore()
    @StateObject private var connection = TTConnectionController()
    @StateObject private var chatHistory = ChatHistoryStore()
    @StateObject private var elevenlabs = ElevenLabsService()

    var body: some Scene {
        WindowGroup {
            MainTabView()
                .environmentObject(serverStore)
                .environmentObject(prefs)
                .environmentObject(connection)
                .environmentObject(chatHistory)
                .environmentObject(elevenlabs)
                .onReceive(connection.eventPublisher) { event in
                    handleEvent(event)
                }
        }
    }

    private func handleEvent(_ event: TTEvent) {
        switch event {
        case .channelMessage(let msg):
            chatHistory.appendChannel(msg)
            if prefs.preferences.announcementsEnabled && prefs.preferences.announcementMode == .full {
                TTAccessibility.announce("\(msg.author): \(msg.content)")
            }
        case .privateMessage(let msg):
            chatHistory.appendPrivate(msg)
            TTAccessibility.announce("Privatnachricht von \(msg.from): \(msg.content)")
        case .userJoined(let user):
            if prefs.preferences.announcementsEnabled {
                TTAccessibility.announce("\(user.nickname) betritt den Kanal")
            }
            SoundPlayer.shared.play("newuser")
        case .userLeft(let user):
            if prefs.preferences.announcementsEnabled {
                TTAccessibility.announce("\(user.nickname) verlässt den Kanal")
            }
            SoundPlayer.shared.play("removeuser")
        case .userTalkingChanged(let user):
            if prefs.preferences.announcementsEnabled && prefs.preferences.announcementMode == .full {
                if user.isTalking {
                    TTAccessibility.announce("\(user.nickname) spricht")
                }
            }
        case .channelListUpdated(let channels):
            connection.channels = channels
        case .userListUpdated(let users):
            connection.users = users
        case .connectionLost:
            TTAccessibility.announce("Verbindung zum Server verloren")
            SoundPlayer.shared.play("serverlost")
        default:
            break
        }
    }
}
