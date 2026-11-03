import SwiftUI

struct ServerPropertiesView: View {
    @EnvironmentObject var connection: TTConnectionController
    @Environment(\.dismiss) private var dismiss

    var props: ServerProperties? { connection.serverProperties }

    var body: some View {
        NavigationStack {
            if let props = props {
                List {
                    Section("Server-Info") {
                        LabeledContent("Name", value: props.name)
                        LabeledContent("Version", value: props.version)
                    }
                    if !props.motd.isEmpty {
                        Section("Nachricht des Tages") {
                            Text(props.motd)
                                .font(.body)
                                .accessibilityLabel("Nachricht des Tages: \(props.motd)")
                        }
                    }
                    Section("Statistik") {
                        LabeledContent("Nutzer online",
                                       value: "\(connection.users.count)")
                        LabeledContent("Kanäle", value: "\(connection.channels.count)")
                    }
                }
                .navigationTitle("Server-Eigenschaften")
            } else {
                ContentUnavailableView("Keine Verbindung", systemImage: "server.rack")
                    .navigationTitle("Server-Eigenschaften")
            }
            // toolbar always visible
        }
        .toolbar {
            ToolbarItem(placement: .cancellationAction) {
                Button("Schließen") { dismiss() }
            }
        }
    }
}
