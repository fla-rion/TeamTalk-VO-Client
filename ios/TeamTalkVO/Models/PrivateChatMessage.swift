import Foundation

struct PrivateChatMessage: Identifiable, Codable {
    var id: UUID = UUID()
    var from: String
    var to: String
    var content: String
    var timestamp: Date
    var isOwn: Bool
}
