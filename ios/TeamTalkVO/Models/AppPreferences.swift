import Foundation

struct AppPreferences: Codable {
    var nickname: String = ""
    var statusMessage: String = ""
    var voiceActivationEnabled: Bool = false
    var voiceActivationLevel: Int = 2000
    var pushToTalkEnabled: Bool = true
    var masterVolume: Int = 100
    var microphoneGain: Int = 100
    var elevenLabsApiKey: String = ""
    var elevenLabsVoiceId: String = ""
    var announcementsEnabled: Bool = true
    var announcementMode: AnnouncementMode = .full
    var soundTheme: SoundTheme = .default_
    var autoReconnect: Bool = true
    var rejoinLastChannel: Bool = true
    var mediaStreamingURL: String = ""
}

enum AnnouncementMode: String, Codable, CaseIterable {
    case quiet = "quiet"
    case full = "full"
}

enum SoundTheme: String, Codable, CaseIterable {
    case default_ = "default"
    case majorlyG = "majorlyG"
    case none = "none"
}
