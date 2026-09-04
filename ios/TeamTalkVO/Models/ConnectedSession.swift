import Foundation

struct ChannelEntry: Identifiable {
    var id: Int
    var name: String
    var parentId: Int
    var topic: String
    var userCount: Int
    var hasPassword: Bool
    var isJoined: Bool
}

struct UserEntry: Identifiable {
    var id: Int
    var nickname: String
    var username: String
    var channelId: Int
    var isTalking: Bool
    var isMuted: Bool
    var gender: String
    var statusMessage: String
}

struct ServerProperties {
    var name: String
    var motd: String
    var version: String
}
