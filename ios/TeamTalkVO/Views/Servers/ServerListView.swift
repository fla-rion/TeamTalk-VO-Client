import SwiftUI

struct ServerListView: View {
    @EnvironmentObject var serverStore: SavedServerStore
    @EnvironmentObject var connection: TTConnectionController
    @EnvironmentObject var prefs: AppPreferencesStore
    @State private var showEditor = false
    @State private var editingServer: SavedServerRecord? = nil
    @State private var connectingId: UUID? = nil
    @State private var searchText = ""
    @State private var showTTImport = false
    @State private var ttImportURL = ""
    @State private var importError: String? = nil
    @State private var showGroupManager = false
    @State private var selectedGroup: String? = nil

    var groups: [String] {
        Array(prefs.preferences.serverGroups.keys).sorted()
    }

    var filteredServers: [SavedServerRecord] {
        let base = serverStore.servers
        let grouped: [SavedServerRecord]
        if let g = selectedGroup, let ids = prefs.preferences.serverGroups[g] {
            let idSet = Set(ids)
            grouped = base.filter { idSet.contains($0.id.uuidString) }
        } else {
            grouped = base
        }
        if searchText.isEmpty { return grouped }
        return grouped.filter {
            $0.name.localizedCaseInsensitiveContains(searchText) ||
            $0.host.localizedCaseInsensitiveContains(searchText)
        }
    }

    var body: some View {
        NavigationStack {
            List {
                if !groups.isEmpty {
                    Section("Gruppen") {
                        ScrollView(.horizontal, showsIndicators: false) {
                            HStack {
                                GroupChip(label: "Alle", isSelected: selectedGroup == nil) {
                                    selectedGroup = nil
                                }
                                ForEach(groups, id: \.self) { group in
                                    GroupChip(label: group, isSelected: selectedGroup == group) {
                                        selectedGroup = selectedGroup == group ? nil : group
                                    }
                                }
                            }
                            .padding(.vertical, 4)
                        }
                        .listRowInsets(EdgeInsets())
                        .listRowBackground(Color.clear)
                    }
                }

                Section("Server") {
                    ForEach(filteredServers) { server in
                        ServerRowView(server: server, isConnecting: connectingId == server.id) {
                            connectingId = server.id
                            Task {
                                await connection.connect(to: server)
                                connectingId = nil
                            }
                        } onEdit: {
                            editingServer = server
                        }
                        .contextMenu {
                            Button {
                                editingServer = server
                            } label: {
                                Label("Bearbeiten", systemImage: "pencil")
                            }
                            Button {
                                addToGroup(server: server)
                            } label: {
                                Label("Zu Gruppe hinzufügen", systemImage: "folder.badge.plus")
                            }
                            Divider()
                            Button(role: .destructive) {
                                if let idx = serverStore.servers.firstIndex(where: { $0.id == server.id }) {
                                    serverStore.delete(at: IndexSet([idx]))
                                }
                            } label: {
                                Label("Löschen", systemImage: "trash")
                            }
                        }
                    }
                    .onDelete { offsets in
                        let ids = offsets.map { filteredServers[$0].id }
                        for id in ids {
                            if let idx = serverStore.servers.firstIndex(where: { $0.id == id }) {
                                serverStore.delete(at: IndexSet([idx]))
                            }
                        }
                    }
                }
            }
            .searchable(text: $searchText, prompt: "Server suchen")
            .navigationTitle("TeamTalk VO")
            .toolbar {
                ToolbarItem(placement: .primaryAction) {
                    Button(action: { showEditor = true }) {
                        Label("Neuer Server", systemImage: "plus")
                    }
                    .accessibilityLabel("Neuen Server hinzufügen")
                }
                ToolbarItem(placement: .secondaryAction) {
                    Button(action: { showTTImport = true }) {
                        Label("tt://-Link importieren", systemImage: "link.badge.plus")
                    }
                    .accessibilityLabel("Server aus tt://-Link importieren")
                }
                ToolbarItem(placement: .secondaryAction) {
                    Button(action: { showGroupManager = true }) {
                        Label("Gruppen verwalten", systemImage: "folder")
                    }
                    .accessibilityLabel("Server-Gruppen verwalten")
                }
            }
            .sheet(isPresented: $showEditor) {
                ServerEditorView(server: nil)
            }
            .sheet(item: $editingServer) { server in
                ServerEditorView(server: server)
            }
            .alert("tt://-Link importieren", isPresented: $showTTImport) {
                TextField("tt://host:port/?...", text: $ttImportURL)
                    .textInputAutocapitalization(.never)
                    .autocorrectionDisabled()
                Button("Importieren") { importTTLink() }
                Button("Abbrechen", role: .cancel) { ttImportURL = "" }
            } message: {
                if let err = importError {
                    Text(err)
                } else {
                    Text("Füge einen tt://-Link ein um einen Server zu importieren.")
                }
            }
            .sheet(isPresented: $showGroupManager) {
                GroupManagerSheet()
            }
        }
    }

    private func importTTLink() {
        let urlStr = ttImportURL.trimmingCharacters(in: .whitespacesAndNewlines)
        guard let url = URL(string: urlStr), url.scheme == "tt" else {
            importError = "Ungültiger tt://-Link."
            return
        }
        let host = url.host ?? ""
        let port = url.port ?? 10333
        var name = ""
        var username = ""
        var password = ""
        var channel = ""
        var channelPassword = ""

        if let comps = URLComponents(url: url, resolvingAgainstBaseURL: false) {
            for item in comps.queryItems ?? [] {
                switch item.name {
                case "srvname": name = item.value ?? ""
                case "username": username = item.value ?? ""
                case "password": password = item.value ?? ""
                case "channel": channel = item.value ?? ""
                case "chanpasswd": channelPassword = item.value ?? ""
                default: break
                }
            }
        }

        let record = SavedServerRecord(
            name: name.isEmpty ? host : name,
            host: host,
            tcpPort: port,
            udpPort: port,
            username: username,
            password: password,
            nickname: prefs.preferences.nickname,
            channel: channel,
            channelPassword: channelPassword
        )
        serverStore.add(record)
        ttImportURL = ""
        importError = nil
        TTAccessibility.announce("Server '\(record.name)' importiert")
    }

    private func addToGroup(server: SavedServerRecord) {
        // Quick-add to "Favoriten" group as default
        var groups = prefs.preferences.serverGroups
        let groupName = "Favoriten"
        var members = groups[groupName] ?? []
        if !members.contains(server.id.uuidString) {
            members.append(server.id.uuidString)
        }
        groups[groupName] = members
        prefs.preferences.serverGroups = groups
        prefs.save()
    }
}

struct GroupChip: View {
    let label: String
    let isSelected: Bool
    let onTap: () -> Void

    var body: some View {
        Button(action: onTap) {
            Text(label)
                .font(.subheadline)
                .padding(.horizontal, 12)
                .padding(.vertical, 6)
                .background(isSelected ? Color.blue : Color(.systemGray5))
                .foregroundStyle(isSelected ? .white : .primary)
                .clipShape(Capsule())
        }
        .buttonStyle(.borderless)
        .accessibilityLabel(label)
        .accessibilityAddTraits(isSelected ? [.isSelected] : [])
    }
}

struct GroupManagerSheet: View {
    @EnvironmentObject var prefs: AppPreferencesStore
    @Environment(\.dismiss) private var dismiss
    @State private var newGroupName = ""

    var groups: [String] { Array(prefs.preferences.serverGroups.keys).sorted() }

    var body: some View {
        NavigationStack {
            List {
                Section("Neue Gruppe") {
                    HStack {
                        TextField("Gruppenname", text: $newGroupName)
                            .accessibilityLabel("Name der neuen Gruppe")
                        Button("Erstellen") {
                            let name = newGroupName.trimmingCharacters(in: .whitespaces)
                            guard !name.isEmpty else { return }
                            prefs.preferences.serverGroups[name] = []
                            prefs.save()
                            newGroupName = ""
                        }
                        .disabled(newGroupName.trimmingCharacters(in: .whitespaces).isEmpty)
                    }
                }
                Section("Gruppen") {
                    ForEach(groups, id: \.self) { group in
                        HStack {
                            Text(group)
                            Spacer()
                            Text("\(prefs.preferences.serverGroups[group]?.count ?? 0) Server")
                                .font(.caption)
                                .foregroundStyle(.secondary)
                        }
                        .swipeActions(edge: .trailing) {
                            Button(role: .destructive) {
                                prefs.preferences.serverGroups.removeValue(forKey: group)
                                prefs.save()
                            } label: {
                                Label("Löschen", systemImage: "trash")
                            }
                        }
                    }
                }
            }
            .navigationTitle("Gruppen verwalten")
            .toolbar {
                ToolbarItem(placement: .confirmationAction) {
                    Button("Fertig") { dismiss() }
                }
            }
        }
    }
}

struct ServerRowView: View {
    let server: SavedServerRecord
    let isConnecting: Bool
    let onConnect: () -> Void
    let onEdit: () -> Void

    var body: some View {
        HStack {
            VStack(alignment: .leading, spacing: 4) {
                Text(server.name.isEmpty ? server.host : server.name)
                    .font(.headline)
                Text("\(server.host):\(server.tcpPort)")
                    .font(.caption)
                    .foregroundStyle(.secondary)
                if !server.nickname.isEmpty {
                    Text(server.nickname)
                        .font(.caption2)
                        .foregroundStyle(.tertiary)
                }
            }
            Spacer()
            if isConnecting {
                ProgressView()
            } else {
                Button(action: onConnect) {
                    Image(systemName: "arrow.right.circle.fill")
                        .font(.title2)
                        .foregroundStyle(.blue)
                }
                .buttonStyle(.borderless)
                .accessibilityLabel("Mit \(server.name.isEmpty ? server.host : server.name) verbinden")
            }
        }
        .contentShape(Rectangle())
        .accessibilityElement(children: .combine)
        .accessibilityLabel("\(server.name.isEmpty ? server.host : server.name), \(server.host) Port \(server.tcpPort)")
        .accessibilityHint("Tippe doppelt zum Verbinden, Kontextmenü für weitere Optionen")
        .onTapGesture(count: 1) { onEdit() }
    }
}
