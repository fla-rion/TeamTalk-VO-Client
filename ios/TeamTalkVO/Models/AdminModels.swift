import Foundation

struct RemoteFile: Identifiable {
    let id: Int
    let name: String
    let size: Int64
    let owner: String
    let channelId: Int

    var sizeFormatted: String {
        ByteCountFormatter.string(fromByteCount: size, countStyle: .file)
    }
}

struct UserAccount: Identifiable {
    var id: String { username }
    var username: String
    var userType: UserType

    enum UserType: String, CaseIterable {
        case default_ = "Standard"
        case admin = "Administrator"
    }
}

struct BannedUser: Identifiable {
    var id: String { ipAddress }
    var ipAddress: String
    var nickname: String
    var bannedAt: Date
}
