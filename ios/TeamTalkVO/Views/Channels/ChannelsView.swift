import SwiftUI

struct ChannelsView: View {
    @EnvironmentObject var connection: TTConnectionController
    @EnvironmentObject var prefs: AppPreferencesStore
    @State private var searchText = ""
    @State private var showOnlyFavorites = false
    @State private var selectedUser: UserEntry? = nil

    var filteredChannels: [ChannelEntry] {
        var list = connection.channels
        if showOnlyFavorites {
            let favIds = Set(prefs.preferences.favoriteChannelIds)
            list = list.filter { favIds.contains($0.id) }
        }
        if searchText.isEmpty { return list }
        return list.filter { $0.name.localizedCaseInsensitiveContains(searchText) ||
                             $0.topic.localizedCaseInsensitiveContains(searchText) }
    }

    var body: some View {
        NavigationStack {
            if connection.state != .loggedIn {
                ContentUnavailableView("Nicht verbunden",
                    systemImage: "network.slash",
                    description: Text("Verbinde dich mit einem Server im Tab 'Server'."))
            } else {
                List {
                    if !filteredChannels.isEmpty {
                        Section("Kanäle") {
                            ForEach(filteredChannels) { channel in
                                ChannelRowView(channel: channel)
                                    .contextMenu {
                                        Button {
                                            toggleFavorite(channel: channel)
                                        } label: {
                                            let isFav = prefs.preferences.favoriteChannelIds.contains(channel.id)
                                            Label(isFav ? "Favorit entfernen" : "Als Favorit markieren",
                                                  systemImage: isFav ? "star.slash" : "star")
                                        }
                                        if !channel.isJoined {
                                            Button {
                                                Task { await connection.joinChannel(channel) }
                                            } label: {
                                                Label("Beitreten", systemImage: "arrow.right")
                                            }
                                        }
                                    }
                            }
                        }
                    } else if !searchText.isEmpty {
                        ContentUnavailableView.search(text: searchText)
                    }

                    let currentUsers = connection.users.filter { $0.channelId == connection.currentChannelId }
                    if !currentUsers.isEmpty {
                        Section("Nutzer im Kanal") {
                            ForEach(currentUsers) { user in
                                UserRowView(user: user)
                                    .contextMenu {
                                        Button {
                                            selectedUser = user
                                        } label: {
                                            Label("Privatnachricht", systemImage: "envelope")
                                        }
                                        Button(role: .destructive) {
                                            Task { await connection.kickUser(userId: user.id) }
                                        } label: {
                                            Label("Kicken", systemImage: "person.fill.xmark")
                                        }
                                        Button(role: .destructive) {
                                            Task { await connection.banUser(userId: user.id) }
                                        } label: {
                                            Label("Bannen", systemImage: "nosign")
                                        }
                                    }
                            }
                        }
                    }
                }
                .searchable(text: $searchText, prompt: "Kanal suchen")
                .navigationTitle(connection.serverProperties?.name ?? "Kanäle")
                .toolbar {
                    ToolbarItem(placement: .secondaryAction) {
                        Button(action: { showOnlyFavorites.toggle() }) {
                            Label(showOnlyFavorites ? "Alle zeigen" : "Nur Favoriten",
                                  systemImage: showOnlyFavorites ? "star.fill" : "star")
                                .foregroundStyle(showOnlyFavorites ? .yellow : .primary)
                        }
                        .accessibilityLabel(showOnlyFavorites ? "Alle Kanäle anzeigen" : "Nur Favoriten anzeigen")
                    }
                }
                .sheet(item: $selectedUser) { user in
                    PrivateMessageSheet(user: user)
                }
            }
        }
    }

    private func toggleFavorite(channel: ChannelEntry) {
        var favs = prefs.preferences.favoriteChannelIds
        if let idx = favs.firstIndex(of: channel.id) {
            favs.remove(at: idx)
            TTAccessibility.announce("'\(channel.name)' aus Favoriten entfernt")
        } else {
            favs.append(channel.id)
            TTAccessibility.announce("'\(channel.name)' zu Favoriten hinzugefügt")
        }
        prefs.preferences.favoriteChannelIds = favs
        prefs.save()
    }
}

struct PrivateMessageSheet: View {
    @EnvironmentObject var connection: TTConnectionController
    @Environment(\.dismiss) private var dismiss
    let user: UserEntry
    @State private var messageText = ""
    @State private var isSending = false

    var body: some View {
        NavigationStack {
            VStack(spacing: 0) {
                Text("Privatnachricht an \(user.nickname)")
                    .font(.headline)
                    .padding()
                    .accessibilityAddTraits(.isHeader)

                TextEditor(text: $messageText)
                    .padding()
                    .accessibilityLabel("Nachrichtentext an \(user.nickname)")

                Button(action: send) {
                    HStack {
                        if isSending { ProgressView() }
                        Text(isSending ? "Wird gesendet…" : "Senden")
                    }
                    .frame(maxWidth: .infinity)
                    .padding()
                    .background(Color.blue)
                    .foregroundStyle(.white)
                    .clipShape(RoundedRectangle(cornerRadius: 12))
                    .padding()
                }
                .disabled(messageText.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty || isSending)
                .accessibilityLabel("Privatnachricht an \(user.nickname) senden")
            }
            .navigationTitle("Privatnachricht")
            .toolbar {
                ToolbarItem(placement: .cancellationAction) {
                    Button("Abbrechen") { dismiss() }
                }
            }
        }
    }

    private func send() {
        let text = messageText.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !text.isEmpty else { return }
        isSending = true
        Task {
            defer { isSending = false }
            await connection.sendPrivateMessage(text, to: user.id, nickname: user.nickname)
            dismiss()
        }
    }
}

struct ChannelRowView: View {
    @EnvironmentObject var connection: TTConnectionController
    @EnvironmentObject var prefs: AppPreferencesStore
    let channel: ChannelEntry

    var isFavorite: Bool { prefs.preferences.favoriteChannelIds.contains(channel.id) }

    var body: some View {
        HStack {
            Image(systemName: channel.isJoined ? "folder.fill" : "folder")
                .foregroundStyle(channel.isJoined ? .blue : .secondary)
                .accessibilityHidden(true)
            VStack(alignment: .leading, spacing: 2) {
                HStack(spacing: 4) {
                    Text(channel.name)
                        .fontWeight(channel.isJoined ? .semibold : .regular)
                    if isFavorite {
                        Image(systemName: "star.fill")
                            .font(.caption2)
                            .foregroundStyle(.yellow)
                            .accessibilityHidden(true)
                    }
                }
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
        .accessibilityLabel("\(channel.name)\(isFavorite ? ", Favorit" : "")\(channel.topic.isEmpty ? "" : ", \(channel.topic)")\(channel.hasPassword ? ", geschützt" : ""), \(channel.userCount) Nutzer\(channel.isJoined ? ", aktueller Kanal" : "")")
        .accessibilityHint(channel.isJoined ? "Kontextmenü für Optionen" : "Tippe doppelt zum Beitreten, Kontextmenü für Optionen")
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
        .accessibilityHint("Kontextmenü für Privatnachricht, Kick oder Ban")
    }
}
