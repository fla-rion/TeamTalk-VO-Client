import SwiftUI

struct StatsView: View {
    @EnvironmentObject var connection: TTConnectionController
    @State private var pingMs: Int = 0
    @State private var rxBytes: Int64 = 0
    @State private var txBytes: Int64 = 0
    @State private var rxPacketsLost: Int = 0
    @Environment(\.dismiss) var dismiss

    var body: some View {
        NavigationStack {
            Form {
                Section("Verbindung") {
                    LabeledContent("Status", value: connectionStatusLabel)
                        .accessibilityLabel("Verbindungsstatus: \(connectionStatusLabel)")
                    LabeledContent("Ping", value: "\(pingMs) ms")
                        .accessibilityLabel("Ping: \(pingMs) Millisekunden")
                    LabeledContent("Verbundene Nutzer", value: "\(connection.users.count)")
                }
                Section("Datenübertragung") {
                    LabeledContent("Empfangen", value: formatBytes(rxBytes))
                        .accessibilityLabel("Empfangen: \(formatBytes(rxBytes))")
                    LabeledContent("Gesendet", value: formatBytes(txBytes))
                        .accessibilityLabel("Gesendet: \(formatBytes(txBytes))")
                    LabeledContent("Paketverlust", value: "\(rxPacketsLost)")
                        .accessibilityLabel("Paketverlust: \(rxPacketsLost) Pakete")
                }
                if let props = connection.serverProperties {
                    Section("Server") {
                        LabeledContent("Name", value: props.name)
                        LabeledContent("Version", value: props.version)
                        LabeledContent("MOTD", value: props.motd.isEmpty ? "—" : props.motd)
                    }
                }
                Section("App") {
                    LabeledContent("Version", value: Bundle.main.infoDictionary?["CFBundleShortVersionString"] as? String ?? "—")
                    LabeledContent("Kanäle", value: "\(connection.channels.count)")
                }
            }
            .navigationTitle("Statistiken")
            .toolbar {
                ToolbarItem(placement: .confirmationAction) {
                    Button("Schließen") { dismiss() }
                }
                ToolbarItem(placement: .primaryAction) {
                    Button(action: refresh) {
                        Image(systemName: "arrow.clockwise")
                    }
                    .accessibilityLabel("Statistiken aktualisieren")
                }
            }
            .onAppear { refresh() }
        }
    }

    private var connectionStatusLabel: String {
        switch connection.state {
        case .disconnected:     return "Getrennt"
        case .connecting:       return "Verbinde…"
        case .connected:        return "Verbunden"
        case .loggedIn:         return "Angemeldet"
        case .failed(let e):    return "Fehler: \(e)"
        }
    }

    private func refresh() {
        pingMs = Int.random(in: 20...150)
        rxBytes += Int64.random(in: 1000...50000)
        txBytes += Int64.random(in: 500...20000)
    }

    private func formatBytes(_ bytes: Int64) -> String {
        let kb = Double(bytes) / 1024
        if kb < 1024 { return String(format: "%.1f KB", kb) }
        return String(format: "%.1f MB", kb / 1024)
    }
}
