import Foundation

@MainActor
class ChatHistoryStore: ObservableObject {
    @Published var channelMessages: [ChannelChatMessage] = []
    @Published var privateConversations: [String: [PrivateChatMessage]] = [:]

    func appendChannel(_ msg: ChannelChatMessage) {
        channelMessages.append(msg)
        if channelMessages.count > 500 { channelMessages.removeFirst() }
    }

    func appendPrivate(_ msg: PrivateChatMessage) {
        let key = msg.isOwn ? msg.to : msg.from
        privateConversations[key, default: []].append(msg)
    }

    func clearChannel() { channelMessages = [] }
    func clearAll() { channelMessages = []; privateConversations = [:] }
}
