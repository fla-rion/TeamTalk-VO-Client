import SwiftUI

struct ChannelsView: View {
    @EnvironmentObject var connection: TTConnectionController

    var body: some View {
        NavigationStack {
            if connection.state != .loggedIn {
                ContentUnavailableView("Nicht verbunden",
                    systemImage: "network.slash",
                    description: Text("Verbinde dich mit einem Server im Tab 'Server'."))
            } else {
                List {
                    if !connection.channels.isEmpty {
                        Section("Kanäle") {
                            ForEach(connection.channels) { channel in
                                ChannelRowView(channel: channel)
                            }
                        }
                    }
                    let currentUsers = connection.users.filter { $0.channelId == connection.currentChannelId }
                    if !currentUsers.isEmpty {
                        Section("Nutzer im Kanal") {
                            ForEach(currentUsers) { user in
                                UserRowView(user: user)
                            }
                        }
                    }
                }
                .navigationTitle(connection.serverProperties?.name ?? "Kanäle")
            }
        }
    }
}

struct ChannelRowView: View {
    @EnvironmentObject var connection: TTConnectionController
    let channel: ChannelEntry

    var body: some View {
        HStack {
            Image(systemName: channel.isJoined ? "folder.fill" : "folder")
                .foregroundStyle(channel.isJoined ? .blue : .secondary)
                .accessibilityHidden(true)
            VStack(alignment: .leading, spacing: 2) {
                Text(channel.name)
                    .fontWeight(channel.isJoined ? .semibold : .regular)
                if !channel.topic.isEmpty {
                    Text(channel.topic)
                        .font(.caption)
                        .foregroundStyle(.secondary)
                }
            }
            Spacer()
            HStack(spacing: 4) {
                if channel.hasPassword {
                    Image(systemName: "lock.fill")
                        .font(.caption)
                        .foregroundStyle(.secondary)
                }
                Text("\(channel.userCount)")
                    .font(.caption)
                    .foregroundStyle(.secondary)
            }
        }
        .contentShape(Rectangle())
        .accessibilityElement(children: .combine)
        .accessibilityLabel("\(channel.name)\(channel.topic.isEmpty ? "" : ", \(channel.topic)")\(channel.hasPassword ? ", geschützt" : ""), \(channel.userCount) Nutzer\(channel.isJoined ? ", aktueller Kanal" : "")")
        .accessibilityHint(channel.isJoined ? "" : "Tippe doppelt zum Beitreten")
        .onTapGesture {
            guard !channel.isJoined else { return }
            Task { await connection.joinChannel(channel) }
        }
    }
}

struct UserRowView: View {
    let user: UserEntry

    var body: some View {
        HStack {
            Image(systemName: user.isTalking ? "waveform" : "person.fill")
                .foregroundStyle(user.isTalking ? .green : .secondary)
                .symbolEffect(.variableColor.iterative, isActive: user.isTalking)
                .accessibilityHidden(true)
            VStack(alignment: .leading, spacing: 2) {
                Text(user.nickname)
                if !user.statusMessage.isEmpty {
                    Text(user.statusMessage)
                        .font(.caption)
                        .foregroundStyle(.secondary)
                }
            }
            Spacer()
            if user.isMuted {
                Image(systemName: "speaker.slash.fill")
                    .foregroundStyle(.secondary)
                    .font(.caption)
                    .accessibilityHidden(true)
            }
        }
        .accessibilityElement(children: .combine)
        .accessibilityLabel("\(user.nickname)\(user.statusMessage.isEmpty ? "" : ", \(user.statusMessage)")\(user.isTalking ? ", spricht" : "")\(user.isMuted ? ", stummgeschaltet" : "")")
    }
}
