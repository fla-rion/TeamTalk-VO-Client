import Foundation

@MainActor
class SavedServerStore: ObservableObject {
    @Published var servers: [SavedServerRecord] = []
    private let key = "saved_servers_v1"

    init() { load() }

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
    }

    private func load() {
        guard let data = UserDefaults.standard.data(forKey: key),
              let decoded = try? JSONDecoder().decode([SavedServerRecord].self, from: data)
        else { return }
        servers = decoded
    }
}
