import SwiftUI

struct UserInfoView: View {
    @EnvironmentObject var connection: TTConnectionController
    @Environment(\.dismiss) private var dismiss
    let user: UserEntry

    @State private var showKickConfirm = false
    @State private var showBanConfirm = false

    var body: some View {
        NavigationStack {
            List {
                Section("Nutzer") {
                    LabeledContent("Spitzname", value: user.nickname)
                    LabeledContent("Benutzername", value: user.username.isEmpty ? "—" : user.username)
                    if !user.statusMessage.isEmpty {
                        LabeledContent("Status", value: user.statusMessage)
                    }
                    LabeledContent("Geschlecht", value: genderLabel)
                }
                Section("Aktionen") {
                    Button {
                        showKickConfirm = true
                    } label: {
                        Label("Kicken", systemImage: "person.fill.xmark")
                            .foregroundStyle(.orange)
                    }
                    .accessibilityLabel("Nutzer \(user.nickname) kicken")

                    Button(role: .destructive) {
                        showBanConfirm = true
                    } label: {
                        Label("Bannen", systemImage: "nosign")
                    }
                    .accessibilityLabel("Nutzer \(user.nickname) bannen")
                }
            }
            .navigationTitle(user.nickname)
            .toolbar {
                ToolbarItem(placement: .cancellationAction) {
                    Button("Schließen") { dismiss() }
                }
            }
            .confirmationDialog("Nutzer kicken?",
                                isPresented: $showKickConfirm,
                                titleVisibility: .visible) {
                Button("Kicken", role: .destructive) {
                    Task {
                        await connection.kickUser(userId: user.id)
                        dismiss()
                    }
                }
                Button("Abbrechen", role: .cancel) {}
            }
            .confirmationDialog("\(user.nickname) dauerhaft bannen?",
                                isPresented: $showBanConfirm,
                                titleVisibility: .visible) {
                Button("Bannen", role: .destructive) {
                    Task {
                        await connection.banUser(userId: user.id)
                        dismiss()
                    }
                }
                Button("Abbrechen", role: .cancel) {}
            }
        }
    }

    private var genderLabel: String {
        switch user.gender.uppercased() {
        case "M": return "Männlich"
        case "F": return "Weiblich"
        default:  return "Keine Angabe"
        }
    }
}
