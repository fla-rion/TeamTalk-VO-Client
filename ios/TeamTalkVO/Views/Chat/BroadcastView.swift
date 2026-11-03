import SwiftUI

struct BroadcastView: View {
    @EnvironmentObject var connection: TTConnectionController
    @Environment(\.dismiss) private var dismiss

    @State private var messageText = ""
    @State private var isSending = false

    var body: some View {
        NavigationStack {
            VStack(spacing: 0) {
                VStack(alignment: .leading, spacing: 8) {
                    Label("Servernachricht an alle", systemImage: "megaphone.fill")
                        .font(.headline)
                        .foregroundStyle(.orange)
                        .accessibilityAddTraits(.isHeader)
                    Text("Die Nachricht wird an alle verbundenen Nutzer gesendet.")
                        .font(.caption)
                        .foregroundStyle(.secondary)
                }
                .padding()

                TextEditor(text: $messageText)
                    .frame(minHeight: 120)
                    .padding(8)
                    .background(Color(.systemGray6))
                    .clipShape(RoundedRectangle(cornerRadius: 8))
                    .padding(.horizontal)
                    .accessibilityLabel("Broadcast-Nachricht")

                Spacer()

                Button(action: send) {
                    HStack {
                        if isSending { ProgressView() }
                        Label(isSending ? "Wird gesendet…" : "An alle senden",
                              systemImage: "megaphone")
                    }
                    .frame(maxWidth: .infinity)
                    .padding()
                    .background(messageText.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
                                ? Color.gray : Color.orange)
                    .foregroundStyle(.white)
                    .clipShape(RoundedRectangle(cornerRadius: 12))
                    .padding()
                }
                .disabled(messageText.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty || isSending)
                .accessibilityLabel("Servernachricht an alle senden")
            }
            .navigationTitle("Broadcast")
            .toolbar {
                ToolbarItem(placement: .cancellationAction) {
                    Button("Abbrechen") { dismiss() }
                }
            }
        }
    }

    private func send() {
        let text = messageText.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !text.isEmpty else { return }
        isSending = true
        Task {
            defer { isSending = false }
            await connection.sendBroadcastMessage(text)
            dismiss()
        }
    }
}
