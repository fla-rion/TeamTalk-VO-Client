import SwiftUI

struct ChannelEditorView: View {
    @EnvironmentObject var connection: TTConnectionController
    @Environment(\.dismiss) private var dismiss

    @State private var name = ""
    @State private var topic = ""
    @State private var password = ""
    @State private var maxUsers = 32
    @State private var isCreating = false

    var body: some View {
        NavigationStack {
            Form {
                Section("Kanaldetails") {
                    TextField("Kanalname", text: $name)
                        .accessibilityLabel("Kanalname")
                    TextField("Thema (optional)", text: $topic)
                        .accessibilityLabel("Thema")
                    SecureField("Passwort (optional)", text: $password)
                        .accessibilityLabel("Kanalpasswort")
                }
                Section("Kapazität") {
                    Stepper("Max. Nutzer: \(maxUsers)", value: $maxUsers, in: 1...200)
                        .accessibilityLabel("Maximale Nutzerzahl: \(maxUsers)")
                }
                Section {
                    Button(action: create) {
                        HStack {
                            if isCreating { ProgressView() }
                            Text(isCreating ? "Wird erstellt…" : "Kanal erstellen")
                        }
                        .frame(maxWidth: .infinity)
                    }
                    .disabled(name.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty || isCreating)
                }
            }
            .navigationTitle("Neuer Kanal")
            .toolbar {
                ToolbarItem(placement: .cancellationAction) {
                    Button("Abbrechen") { dismiss() }
                }
            }
        }
    }

    private func create() {
        let trimmed = name.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !trimmed.isEmpty else { return }
        isCreating = true
        Task {
            defer { isCreating = false }
            await connection.createChannel(
                name: trimmed, topic: topic,
                password: password, maxUsers: maxUsers
            )
            dismiss()
        }
    }
}
