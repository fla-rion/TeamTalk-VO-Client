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
    var elevenLabsModel: String = "eleven_multilingual_v2"
    var elevenLabsStability: Double = 0.5
    var elevenLabsSimilarity: Double = 0.75
    var elevenLabsStreamingMode: Bool = false
    var announcementsEnabled: Bool = true
    var announcementMode: AnnouncementMode = .full
    var soundTheme: SoundTheme = .default_
    var autoReconnect: Bool = true
    var rejoinLastChannel: Bool = true
    var mediaStreamingURL: String = ""
    var favoriteChannelIds: [Int] = []
    var serverGroups: [String: [String]] = [:]  // group name → [server UUID strings]
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
