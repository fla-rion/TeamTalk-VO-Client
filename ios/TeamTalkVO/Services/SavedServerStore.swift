import Foundation

@MainActor
class SavedServerStore: ObservableObject {
    @Published var servers: [SavedServerRecord] = []
    private let key = "saved_servers_v1"
    private let sync = CloudSyncService.shared

    init() {
        load()
        listenForCloudChanges()
    }

    func add(_ server: SavedServerRecord) {
        servers.append(server)
        save()
    }

    func update(_ server: SavedServerRecord) {
        if let idx = servers.firstIndex(where: { $0.id == server.id }) {
            servers[idx] = server
            save()
        }
    }

    func delete(at offsets: IndexSet) {
        servers.remove(atOffsets: offsets)
        save()
    }

    func delete(_ server: SavedServerRecord) {
        servers.removeAll { $0.id == server.id }
        save()
    }

    private func save() {
        if let data = try? JSONEncoder().encode(servers) {
            UserDefaults.standard.set(data, forKey: key)
        }
        sync.upload(servers: servers)
    }

    private func load() {
        // Prefer iCloud data if sync is enabled and iCloud has newer data
        if sync.syncEnabled, let cloudServers = sync.downloadServers(), !cloudServers.isEmpty {
            servers = cloudServers
            // Also persist locally
            if let data = try? JSONEncoder().encode(servers) {
                UserDefaults.standard.set(data, forKey: key)
            }
            return
        }
        guard let data = UserDefaults.standard.data(forKey: key),
              let decoded = try? JSONDecoder().decode([SavedServerRecord].self, from: data)
        else { return }
        servers = decoded
    }

    private func listenForCloudChanges() {
        NotificationCenter.default.addObserver(
            forName: .cloudSyncDidReceiveExternalChanges,
            object: nil,
            queue: .main
        ) { [weak self] note in
            guard let self else { return }
            let keys = note.userInfo?["keys"] as? [String] ?? []
            if keys.contains(CloudSyncService.serversKey) {
                Task { @MainActor in
                    if let cloudServers = self.sync.downloadServers() {
                        self.servers = cloudServers
                        if let data = try? JSONEncoder().encode(cloudServers) {
                            UserDefaults.standard.set(data, forKey: self.key)
                        }
                    }
                }
            }
        }
    }
}
