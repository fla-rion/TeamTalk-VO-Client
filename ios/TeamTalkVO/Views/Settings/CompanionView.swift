import SwiftUI

/// Verbindung mit dem macOS-Hauptclient über den lokalen CompanionServer.
struct CompanionView: View {
    @StateObject private var companion = CompanionClientService.shared
    @State private var host = ""
    @State private var port = "19880"
    @State private var token = ""
    @State private var isConnecting = false
    @State private var showMessage = false
    @State private var messageText = ""
    @State private var selectedChannelId = 0

    var body: some View {
        NavigationStack {
            Form {
                // Verbindungsstatus
                Section {
                    HStack(spacing: 12) {
                        Circle()
                            .fill(companion.isConnected ? Color.green : Color.red)
                            .frame(width: 10, height: 10)
                            .accessibilityHidden(true)
                        VStack(alignment: .leading, spacing: 2) {
                            Text(companion.isConnected ? "Verbunden mit Mac-Client" : "Nicht verbunden")
                                .fontWeight(.semibold)
                            if companion.isConnected, let s = companion.status {
                                Text(s.server ?? "Kein Server")
                                    .font(.caption)
                                    .foregroundStyle(.secondary)
                            }
                            if let err = companion.connectionError {
                                Text(err).font(.caption).foregroundStyle(.red)
                            }
                        }
                        Spacer()
                        if companion.isConnected {
                            Button("Trennen", role: .destructive) { companion.disconnect() }
                                .font(.caption)
                        }
                    }
                    .accessibilityElement(children: .combine)
                    .accessibilityLabel(companion.isConnected ? "Verbunden mit Mac-Client" : "Nicht verbunden")
                }

                // Bonjour-Erkennung
                if !companion.discoveredHosts.isEmpty {
                    Section("Im Netzwerk gefunden") {
                        ForEach(companion.discoveredHosts) { h in
                            Button(action: {
                                host = h.host; port = "\(h.port)"
                                Task { await companion.connect(host: h.host, port: h.port, token: token) }
                            }) {
                                HStack {
                                    Image(systemName: "desktopcomputer")
                                        .foregroundStyle(.blue)
                                        .accessibilityHidden(true)
                                    VStack(alignment: .leading) {
                                        Text(h.name).fontWeight(.medium)
                                        Text("\(h.host):\(h.port)").font(.caption).foregroundStyle(.secondary)
                                    }
                                    Spacer()
                                    Image(systemName: "arrow.right.circle")
                                        .foregroundStyle(.blue)
                                        .accessibilityHidden(true)
                                }
                            }
                            .foregroundStyle(.primary)
                            .accessibilityLabel("Mit \(h.name) verbinden: \(h.host):\(h.port)")
                        }
                    }
                }

                // Manuelle Verbindung
                Section("Mac-Client-Adresse") {
                    LabeledContent("Host/IP") {
                        TextField("192.168.1.100", text: $host)
                            .keyboardType(.URL)
                            .textInputAutocapitalization(.never)
                            .autocorrectionDisabled()
                            .accessibilityLabel("IP-Adresse oder Hostname des Mac")
                    }
                    LabeledContent("Port") {
                        TextField("19880", text: $port)
                            .keyboardType(.numberPad)
                            .accessibilityLabel("CompanionServer-Port")
                    }
                    LabeledContent("Token") {
                        SecureField("Optional", text: $token)
                            .accessibilityLabel("Authentifizierungs-Token")
                    }
                    HStack {
                        Button("Suchen") {
                            companion.startDiscovery()
                        }
                        .accessibilityLabel("Mac-Clients im Netzwerk suchen")
                        Spacer()
                        Button(isConnecting ? "Verbinde…" : "Verbinden") {
                            isConnecting = true
                            Task {
                                await companion.connect(
                                    host: host.isEmpty ? companion.serverHost : host,
                                    port: Int(port) ?? 19880,
                                    token: token
                                )
                                isConnecting = false
                            }
                        }
                        .buttonStyle(.borderedProminent)
                        .disabled(isConnecting)
                        .accessibilityLabel("Mit Mac-Client verbinden")
                    }
                }

                // Live-Status vom Mac
                if companion.isConnected {
                    Section("Kanäle (Mac)") {
                        if companion.channels.isEmpty {
                            Text("Keine Kanäle").foregroundStyle(.secondary)
                        } else {
                            ForEach(companion.channels) { ch in
                                HStack {
                                    Image(systemName: "folder")
                                        .foregroundStyle(.secondary)
                                        .accessibilityHidden(true)
                                    Text(ch.name)
                                    Spacer()
                                    Text("\(ch.userCount)")
                                        .foregroundStyle(.secondary)
                                        .font(.caption)
                                }
                                .accessibilityLabel("Kanal \(ch.name), \(ch.userCount) Nutzer")
                                .onTapGesture { selectedChannelId = ch.id }
                            }
                        }
                    }

                    Section("Nutzer (Mac)") {
                        ForEach(companion.users) { u in
                            HStack {
                                Circle()
                                    .fill(u.isTalking ? Color.green : Color.secondary)
                                    .frame(width: 8, height: 8)
                                    .accessibilityHidden(true)
                                Text(u.nickname)
                                Spacer()
                                if u.isTalking {
                                    Image(systemName: "waveform")
                                        .foregroundStyle(.green)
                                        .accessibilityHidden(true)
                                }
                            }
                            .accessibilityLabel("\(u.nickname)\(u.isTalking ? ", spricht gerade" : "")")
                        }
                    }

                    Section {
                        Button(action: { showMessage = true }) {
                            Label("Nachricht über Mac senden", systemImage: "paperplane")
                        }
                        .accessibilityLabel("Nachricht über den Mac-Client in den aktiven Kanal senden")
                    }
                }

                Section("Info") {
                    Text("Starte den Haupt-Client auf deinem Mac und aktiviere dort den CompanionServer (Einstellungen → Companion-API). iOS und Mac müssen im selben WLAN sein.")
                        .font(.caption)
                        .foregroundStyle(.secondary)
                        .accessibilityLabel("Anleitung: CompanionServer im Mac-Client aktivieren und gleiches WLAN nutzen")
                }
            }
            .navigationTitle("Mac-Client-Sync")
            .onAppear { companion.startDiscovery() }
            .onDisappear { companion.stopDiscovery() }
            .sheet(isPresented: $showMessage) {
                CompanionMessageSheet(companion: companion, channelId: selectedChannelId)
            }
        }
    }
}

struct CompanionMessageSheet: View {
    @Environment(\.dismiss) var dismiss
    @ObservedObject var companion: CompanionClientService
    let channelId: Int
    @State private var text = ""
    @State private var isSending = false

    var body: some View {
        NavigationStack {
            Form {
                Section("Nachricht") {
                    TextEditor(text: $text)
                        .frame(minHeight: 80)
                        .accessibilityLabel("Nachrichtentext")
                }
                if !companion.channels.isEmpty {
                    Section("Kanal") {
                        Picker("Kanal", selection: Binding(
                            get: { channelId },
                            set: { _ in }
                        )) {
                            ForEach(companion.channels) { ch in
                                Text(ch.name).tag(ch.id)
                            }
                        }
                        .accessibilityLabel("Zielkanal auswählen")
                    }
                }
            }
            .navigationTitle("Nachricht senden")
            .toolbar {
                ToolbarItem(placement: .cancellationAction) {
                    Button("Abbrechen") { dismiss() }
                }
                ToolbarItem(placement: .confirmationAction) {
                    Button(isSending ? "Sende…" : "Senden") {
                        isSending = true
                        Task {
                            _ = await companion.sendMessage(text: text, channelId: channelId)
                            isSending = false
                            dismiss()
                        }
                    }
                    .disabled(text.trimmingCharacters(in: .whitespaces).isEmpty || isSending)
                    .accessibilityLabel("Nachricht absenden")
                }
            }
        }
    }
}
