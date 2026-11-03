import SwiftUI

struct SessionHistoryEntry: Identifiable, Codable {
    var id = UUID()
    var serverName: String
    var host: String
    var connectedAt: Date
    var duration: TimeInterval
    var disconnectReason: String
}

@MainActor
class SessionHistoryStore: ObservableObject {
    @Published var entries: [SessionHistoryEntry] = []
    private let key = "session_history_v1"

    init() { load() }

    func add(serverName: String, host: String, duration: TimeInterval, reason: String = "Manuell getrennt") {
        let entry = SessionHistoryEntry(
            serverName: serverName.isEmpty ? host : serverName,
            host: host,
            connectedAt: Date().addingTimeInterval(-duration),
            duration: duration,
            disconnectReason: reason
        )
        entries.insert(entry, at: 0)
        if entries.count > 50 { entries = Array(entries.prefix(50)) }
        save()
    }

    func clear() { entries = []; save() }

    private func save() {
        if let data = try? JSONEncoder().encode(entries) {
            UserDefaults.standard.set(data, forKey: key)
        }
    }

    private func load() {
        guard let data = UserDefaults.standard.data(forKey: key),
              let decoded = try? JSONDecoder().decode([SessionHistoryEntry].self, from: data)
        else { return }
        entries = decoded
    }
}

struct SessionHistoryView: View {
    @StateObject private var store = SessionHistoryStore()
    @Environment(\.dismiss) var dismiss

    var body: some View {
        NavigationStack {
            Group {
                if store.entries.isEmpty {
                    ContentUnavailableView(
                        "Kein Verlauf",
                        systemImage: "clock.arrow.circlepath",
                        description: Text("Verbinde dich mit Servern, um den Verlauf zu sehen.")
                    )
                } else {
                    List {
                        ForEach(store.entries) { entry in
                            VStack(alignment: .leading, spacing: 4) {
                                Text(entry.serverName)
                                    .fontWeight(.semibold)
                                HStack {
                                    Text(entry.connectedAt, style: .date)
                                    Text("·")
                                    Text(formatDuration(entry.duration))
                                }
                                .font(.caption)
                                .foregroundStyle(.secondary)
                                if !entry.disconnectReason.isEmpty {
                                    Text(entry.disconnectReason)
                                        .font(.caption2)
                                        .foregroundStyle(.tertiary)
                                }
                            }
                            .accessibilityElement(children: .combine)
                            .accessibilityLabel("\(entry.serverName), verbunden am \(entry.connectedAt.formatted(date: .abbreviated, time: .shortened)), Dauer \(formatDuration(entry.duration))")
                        }
                    }
                }
            }
            .navigationTitle("Verbindungsverlauf")
            .toolbar {
                ToolbarItem(placement: .cancellationAction) {
                    Button("Schließen") { dismiss() }
                }
                if !store.entries.isEmpty {
                    ToolbarItem(placement: .destructiveAction) {
                        Button("Leeren", role: .destructive) { store.clear() }
                            .accessibilityLabel("Verlauf löschen")
                    }
                }
            }
        }
    }

    private func formatDuration(_ secs: TimeInterval) -> String {
        let m = Int(secs) / 60
        let s = Int(secs) % 60
        if m >= 60 { return "\(m/60)h \(m%60)m" }
        return "\(m)m \(s)s"
    }
}
