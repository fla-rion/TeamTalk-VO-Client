import Foundation

struct SavedServerRecord: Identifiable, Codable, Hashable {
    var id: UUID = UUID()
    var name: String
    var host: String
    var tcpPort: Int = 10333
    var udpPort: Int = 10333
    var username: String = ""
    var password: String = ""
    var nickname: String = ""
    var channel: String = ""
    var channelPassword: String = ""
    var encrypted: Bool = false
    var autoConnect: Bool = false
    var lastConnected: Date? = nil
}
