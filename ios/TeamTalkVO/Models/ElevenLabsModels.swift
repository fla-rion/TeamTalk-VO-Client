import Foundation

struct ElevenLabsVoice: Identifiable, Codable {
    var id: String { voiceId }
    var voiceId: String
    var name: String

    enum CodingKeys: String, CodingKey {
        case voiceId = "voice_id"
        case name
    }
}

struct ElevenLabsVoicesResponse: Codable {
    var voices: [ElevenLabsVoice]
}
