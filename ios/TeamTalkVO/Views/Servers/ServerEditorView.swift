import SwiftUI

struct ServerEditorView: View {
    @Environment(\.dismiss) var dismiss
    @EnvironmentObject var serverStore: SavedServerStore
    @EnvironmentObject var prefs: AppPreferencesStore

    let server: SavedServerRecord?
    @State private var draft: SavedServerRecord

    init(server: SavedServerRecord?) {
        self.server = server
        _draft = State(initialValue: server ?? SavedServerRecord(
            name: "", host: "", tcpPort: 10333, udpPort: 10333,
            username: "guest", password: "", nickname: "", channel: "",
            channelPassword: "", encrypted: false, autoConnect: false))
    }

    var body: some View {
        NavigationStack {
            Form {
                Section("Verbindung") {
                    LabeledContent("Name") {
                        TextField("Mein Server", text: $draft.name)
                            .textInputAutocapitalization(.never)
                            .accessibilityLabel("Server-Name")
                    }
                    LabeledContent("Host") {
                        TextField("teamtalk.example.com", text: $draft.host)
                            .textInputAutocapitalization(.never)
                            .keyboardType(.URL)
                            .accessibilityLabel("Host-Adresse")
                    }
                    LabeledContent("TCP-Port") {
                        TextField("10333", value: $draft.tcpPort, format: .number)
                            .keyboardType(.numberPad)
                            .accessibilityLabel("TCP-Port")
                    }
                    LabeledContent("UDP-Port") {
                        TextField("10333", value: $draft.udpPort, format: .number)
                            .keyboardType(.numberPad)
                            .accessibilityLabel("UDP-Port")
                    }
                    Toggle("Verschlüsselt (TLS)", isOn: $draft.encrypted)
                        .accessibilityLabel("TLS-Verschlüsselung")
                }
                Section("Anmeldung") {
                    LabeledContent("Benutzername") {
                        TextField("guest", text: $draft.username)
                            .textInputAutocapitalization(.never)
                            .accessibilityLabel("Benutzername")
                    }
                    LabeledContent("Passwort") {
                        SecureField("", text: $draft.password)
                            .accessibilityLabel("Server-Passwort")
                    }
                    LabeledContent("Nickname") {
                        TextField(prefs.preferences.nickname, text: $draft.nickname)
                            .accessibilityLabel("Nickname")
                    }
                }
                Section("Kanal") {
                    LabeledContent("Kanal") {
                        TextField("/Root/Lobby", text: $draft.channel)
                            .textInputAutocapitalization(.never)
                            .accessibilityLabel("Start-Kanal")
                    }
                    LabeledContent("Kanal-Passwort") {
                        SecureField("", text: $draft.channelPassword)
                            .accessibilityLabel("Kanal-Passwort")
                    }
                }
                Section("Optionen") {
                    Toggle("Automatisch verbinden", isOn: $draft.autoConnect)
                }
            }
            .navigationTitle(server == nil ? "Neuer Server" : "Server bearbeiten")
            .toolbar {
                ToolbarItem(placement: .cancellationAction) {
                    Button("Abbrechen") { dismiss() }
                }
                ToolbarItem(placement: .confirmationAction) {
                    Button("Sichern") {
                        if server == nil { serverStore.add(draft) }
                        else { serverStore.update(draft) }
                        dismiss()
                    }
                    .disabled(draft.host.isEmpty)
                    .accessibilityLabel("Server speichern")
                }
            }
        }
    }
}
