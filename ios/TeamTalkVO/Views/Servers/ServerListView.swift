import SwiftUI

struct ServerListView: View {
    @EnvironmentObject var serverStore: SavedServerStore
    @EnvironmentObject var connection: TTConnectionController
    @State private var showEditor = false
    @State private var editingServer: SavedServerRecord? = nil
    @State private var connectingId: UUID? = nil

    var body: some View {
        NavigationStack {
            List {
                ForEach(serverStore.servers) { server in
                    ServerRowView(server: server, isConnecting: connectingId == server.id) {
                        connectingId = server.id
                        Task {
                            await connection.connect(to: server)
                            connectingId = nil
                        }
                    } onEdit: {
                        editingServer = server
                    }
                }
                .onDelete { offsets in serverStore.delete(at: offsets) }
            }
            .navigationTitle("TeamTalk VO")
            .toolbar {
                ToolbarItem(placement: .primaryAction) {
                    Button(action: { showEditor = true }) {
                        Label("Neuer Server", systemImage: "plus")
                    }
                    .accessibilityLabel("Neuen Server hinzufügen")
                }
            }
            .sheet(isPresented: $showEditor) {
                ServerEditorView(server: nil)
            }
            .sheet(item: $editingServer) { server in
                ServerEditorView(server: server)
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
        .accessibilityHint("Tippe doppelt zum Verbinden")
        .onTapGesture(count: 1) { onEdit() }
    }
}
