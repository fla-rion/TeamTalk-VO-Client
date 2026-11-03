import SwiftUI

struct ChatView: View {
    @EnvironmentObject var connection: TTConnectionController
    @EnvironmentObject var chatHistory: ChatHistoryStore
    @State private var messageText = ""
    @State private var showPrivate = false
    @State private var showBroadcast = false

    var body: some View {
        NavigationStack {
            if connection.state != .loggedIn {
                ContentUnavailableView("Nicht verbunden", systemImage: "message.slash")
            } else {
                VStack(spacing: 0) {
                    ScrollViewReader { proxy in
                        ScrollView {
                            LazyVStack(alignment: .leading, spacing: 8) {
                                ForEach(chatHistory.channelMessages) { msg in
                                    ChatBubble(message: msg)
                                        .id(msg.id)
                                }
                            }
                            .padding()
                        }
                        .onChange(of: chatHistory.channelMessages.count) { _, _ in
                            if let last = chatHistory.channelMessages.last {
                                withAnimation { proxy.scrollTo(last.id, anchor: .bottom) }
                            }
                        }
                    }
                    Divider()
                    HStack {
                        TextField("Nachricht…", text: $messageText, axis: .vertical)
                            .textFieldStyle(.roundedBorder)
                            .lineLimit(1...4)
                            .accessibilityLabel("Nachricht eingeben")
                        Button(action: sendMessage) {
                            Image(systemName: "arrow.up.circle.fill")
                                .font(.title2)
                                .foregroundStyle(messageText.isEmpty ? .gray : .blue)
                        }
                        .disabled(messageText.isEmpty)
                        .accessibilityLabel("Senden")
                    }
                    .padding()
                }
                .navigationTitle("Chat")
                .toolbar {
                    ToolbarItem {
                        Button(action: { showPrivate = true }) {
                            Label("Privat", systemImage: "bubble.left.and.bubble.right")
                        }
                        .accessibilityLabel("Private Nachrichten")
                    }
                    ToolbarItem(placement: .secondaryAction) {
                        Button(action: { showBroadcast = true }) {
                            Label("Broadcast", systemImage: "megaphone")
                        }
                        .accessibilityLabel("Servernachricht an alle senden")
                    }
                }
                .sheet(isPresented: $showPrivate) {
                    PrivateMessagesView()
                }
                .sheet(isPresented: $showBroadcast) {
                    BroadcastView()
                }
            }
        }
    }

    private func sendMessage() {
        let text = messageText.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !text.isEmpty else { return }
        messageText = ""
        Task { await connection.sendChannelMessage(text) }
    }
}

struct ChatBubble: View {
    let message: ChannelChatMessage

    var body: some View {
        HStack(alignment: .bottom) {
            if message.isOwn { Spacer(minLength: 60) }
            VStack(alignment: message.isOwn ? .trailing : .leading, spacing: 2) {
                if !message.isOwn {
                    Text(message.author)
                        .font(.caption2)
                        .foregroundStyle(.secondary)
                        .accessibilityHidden(true)
                }
                Text(message.content)
                    .padding(.horizontal, 12)
                    .padding(.vertical, 8)
                    .background(message.isOwn ? Color.blue : Color(.systemGray5))
                    .foregroundStyle(message.isOwn ? .white : .primary)
                    .clipShape(RoundedRectangle(cornerRadius: 16))
                Text(message.timestamp, style: .time)
                    .font(.caption2)
                    .foregroundStyle(.tertiary)
                    .accessibilityHidden(true)
            }
            if !message.isOwn { Spacer(minLength: 60) }
        }
        .accessibilityElement(children: .combine)
        .accessibilityLabel("\(message.isOwn ? "Du" : message.author): \(message.content)")
    }
}

struct PrivateMessagesView: View {
    @EnvironmentObject var chatHistory: ChatHistoryStore
    @EnvironmentObject var connection: TTConnectionController
    @Environment(\.dismiss) var dismiss

    var body: some View {
        NavigationStack {
            List(connection.users.filter { !$0.isOwn }) { user in
                NavigationLink(user.nickname) {
                    PrivateConversationView(partnerNickname: user.nickname, partnerId: user.id)
                }
                .accessibilityLabel("Privatnachricht an \(user.nickname)")
            }
            .navigationTitle("Private Nachrichten")
            .toolbar {
                ToolbarItem(placement: .cancellationAction) {
                    Button("Schließen") { dismiss() }
                }
            }
        }
    }
}

struct PrivateConversationView: View {
    @EnvironmentObject var chatHistory: ChatHistoryStore
    @EnvironmentObject var connection: TTConnectionController
    let partnerNickname: String
    let partnerId: Int
    @State private var messageText = ""

    var messages: [PrivateChatMessage] {
        chatHistory.privateConversations[partnerNickname] ?? []
    }

    var body: some View {
        VStack(spacing: 0) {
            ScrollViewReader { proxy in
                ScrollView {
                    LazyVStack(alignment: .leading, spacing: 8) {
                        ForEach(messages) { msg in
                            HStack {
                                if msg.isOwn { Spacer() }
                                Text(msg.content)
                                    .padding(10)
                                    .background(msg.isOwn ? Color.blue : Color(.systemGray5))
                                    .foregroundStyle(msg.isOwn ? .white : .primary)
                                    .clipShape(RoundedRectangle(cornerRadius: 12))
                                    .accessibilityLabel("\(msg.isOwn ? "Du" : msg.from): \(msg.content)")
                                if !msg.isOwn { Spacer() }
                            }
                            .id(msg.id)
                        }
                    }
                    .padding()
                }
            }
            Divider()
            HStack {
                TextField("Nachricht…", text: $messageText)
                    .textFieldStyle(.roundedBorder)
                    .accessibilityLabel("Private Nachricht")
                Button(action: {
                    let text = messageText.trimmingCharacters(in: .whitespacesAndNewlines)
                    guard !text.isEmpty else { return }
                    messageText = ""
                    Task { await connection.sendPrivateMessage(text, to: partnerId, nickname: partnerNickname) }
                }) {
                    Image(systemName: "arrow.up.circle.fill")
                        .font(.title2)
                }
                .disabled(messageText.isEmpty)
                .accessibilityLabel("Senden")
            }
            .padding()
        }
        .navigationTitle(partnerNickname)
    }
}

private extension UserEntry {
    var isOwn: Bool { false }
}

