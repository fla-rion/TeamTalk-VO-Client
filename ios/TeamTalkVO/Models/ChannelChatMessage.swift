import Foundation

struct ChannelChatMessage: Identifiable, Codable {
    var id: UUID = UUID()
    var author: String
    var content: String
    var timestamp: Date
    var isOwn: Bool
}
