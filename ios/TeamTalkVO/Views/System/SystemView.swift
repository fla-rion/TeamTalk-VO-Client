import SwiftUI

struct SystemView: View {
    @EnvironmentObject var connection: TTConnectionController
    @State private var now = Date()
    @State private var timer: Timer? = nil

    var uptime: String {
        guard let start = connection.sessionStartDate else { return "–" }
        let seconds = Int(now.timeIntervalSince(start))
        let h = seconds / 3600
        let m = (seconds % 3600) / 60
        let s = seconds % 60
        return String(format: "%02d:%02d:%02d", h, m, s)
    }

    var body: some View {
        NavigationStack {
            List {
                if connection.state == .loggedIn {
                    Section("Sitzungsstatistik") {
                        StatRow(label: "Verbindungszeit", value: uptime)
                        StatRow(label: "Nachrichten gesendet", value: "\(connection.messagesSent)")
                        StatRow(label: "Nachrichten empfangen", value: "\(connection.messagesReceived)")
                        StatRow(label: "Reconnects", value: "\(connection.reconnectCount)")
                        if let server = connection.serverProperties {
                            StatRow(label: "Server-Version", value: server.version)
                            StatRow(label: "MOTD", value: server.motd)
                        }
                    }
                } else {
                    Section {
                        Text("Nicht verbunden")
                            .foregroundStyle(.secondary)
                    }
                }

                Section("System-Log") {
                    if connection.systemLog.isEmpty {
                        Text("Keine Einträge")
                            .foregroundStyle(.secondary)
                            .accessibilityLabel("System-Log ist leer")
                    } else {
                        ForEach(connection.systemLog.reversed(), id: \.self) { entry in
                            Text(entry)
                                .font(.system(.caption, design: .monospaced))
                                .foregroundStyle(.primary)
                                .accessibilityLabel(entry)
                        }
                    }
                }
                .headerProminence(.increased)

                Section {
                    Button(role: .destructive, action: { connection.systemLog.removeAll() }) {
                        Label("Log leeren", systemImage: "trash")
                    }
                    .accessibilityLabel("System-Log leeren")

                    Button(action: copyLog) {
                        Label("Log kopieren", systemImage: "doc.on.clipboard")
                    }
                    .accessibilityLabel("System-Log in Zwischenablage kopieren")
                }
            }
            .navigationTitle("System")
            .onAppear {
                timer = Timer.scheduledTimer(withTimeInterval: 1, repeats: true) { _ in
                    now = Date()
                }
            }
            .onDisappear {
                timer?.invalidate()
                timer = nil
            }
        }
    }

    private func copyLog() {
        let text = connection.systemLog.joined(separator: "\n")
        UIPasteboard.general.string = text
        TTAccessibility.announce("Log kopiert")
    }
}

struct StatRow: View {
    let label: String
    let value: String

    var body: some View {
        HStack {
            Text(label)
                .foregroundStyle(.secondary)
            Spacer()
            Text(value)
                .font(.system(.body, design: .monospaced))
                .multilineTextAlignment(.trailing)
        }
        .accessibilityElement(children: .combine)
        .accessibilityLabel("\(label): \(value)")
    }
}
