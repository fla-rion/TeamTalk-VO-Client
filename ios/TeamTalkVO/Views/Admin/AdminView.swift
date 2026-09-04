import SwiftUI

struct AdminView: View {
    @EnvironmentObject var connection: TTConnectionController
    @State private var selectedSection = 0

    var body: some View {
        NavigationStack {
            if connection.state != .loggedIn {
                ContentUnavailableView("Nicht verbunden", systemImage: "shield.slash")
            } else {
                Form {
                    Picker("Bereich", selection: $selectedSection) {
                        Text("Nutzerkonten").tag(0)
                        Text("Sperrliste").tag(1)
                        Text("Nutzerverwaltung").tag(2)
                    }
                    .pickerStyle(.segmented)
                    .accessibilityLabel("Administrations-Bereich auswählen")

                    switch selectedSection {
                    case 0: UserAccountsSection()
                    case 1: BanListSection()
                    default: UserManagementSection()
                    }
                }
                .navigationTitle("Administration")
                .onAppear {
                    Task {
                        await connection.loadUserAccounts()
                        await connection.loadBanList()
                    }
                }
            }
        }
    }
}

// MARK: - User Accounts

struct UserAccountsSection: View {
    @EnvironmentObject var connection: TTConnectionController
    @State private var showNewAccountSheet = false

    var body: some View {
        Section("Nutzerkonten") {
            ForEach(connection.userAccounts) { account in
                HStack {
                    VStack(alignment: .leading, spacing: 2) {
                        Text(account.username)
                            .font(.headline)
                        Text(account.userType.rawValue)
                            .font(.caption)
                            .foregroundStyle(.secondary)
                    }
                    Spacer()
                    Image(systemName: account.userType == .admin ? "star.fill" : "person.fill")
                        .foregroundStyle(account.userType == .admin ? .yellow : .secondary)
                        .accessibilityHidden(true)
                }
                .accessibilityElement(children: .combine)
                .accessibilityLabel("\(account.username), \(account.userType.rawValue)")
                .swipeActions(edge: .trailing) {
                    Button(role: .destructive) {
                        Task { await connection.deleteUserAccount(username: account.username) }
                    } label: {
                        Label("Löschen", systemImage: "trash")
                    }
                }
            }

            Button(action: { showNewAccountSheet = true }) {
                Label("Konto erstellen", systemImage: "person.badge.plus")
            }
            .accessibilityLabel("Neues Nutzerkonto erstellen")
        }
        .sheet(isPresented: $showNewAccountSheet) {
            NewUserAccountSheet()
        }
    }
}

struct NewUserAccountSheet: View {
    @EnvironmentObject var connection: TTConnectionController
    @Environment(\.dismiss) private var dismiss
    @State private var username = ""
    @State private var password = ""
    @State private var userType = UserAccount.UserType.default_

    var body: some View {
        NavigationStack {
            Form {
                Section("Zugangsdaten") {
                    TextField("Benutzername", text: $username)
                        .textInputAutocapitalization(.never)
                        .autocorrectionDisabled()
                        .accessibilityLabel("Benutzername")
                    SecureField("Passwort", text: $password)
                        .accessibilityLabel("Passwort")
                }
                Section("Typ") {
                    Picker("Kontotyp", selection: $userType) {
                        ForEach(UserAccount.UserType.allCases, id: \.self) { t in
                            Text(t.rawValue).tag(t)
                        }
                    }
                    .accessibilityLabel("Kontotyp auswählen")
                }
            }
            .navigationTitle("Neues Konto")
            .toolbar {
                ToolbarItem(placement: .cancellationAction) {
                    Button("Abbrechen") { dismiss() }
                }
                ToolbarItem(placement: .confirmationAction) {
                    Button("Erstellen") {
                        guard !username.isEmpty else { return }
                        Task {
                            await connection.createUserAccount(
                                UserAccount(username: username, userType: userType),
                                password: password)
                            dismiss()
                        }
                    }
                    .disabled(username.isEmpty)
                }
            }
        }
    }
}

// MARK: - Ban List

struct BanListSection: View {
    @EnvironmentObject var connection: TTConnectionController

    var body: some View {
        Section("Gesperrte Nutzer") {
            if connection.banList.isEmpty {
                Text("Keine gesperrten Nutzer")
                    .foregroundStyle(.secondary)
                    .accessibilityLabel("Sperrliste ist leer")
            } else {
                ForEach(connection.banList) { banned in
                    VStack(alignment: .leading, spacing: 2) {
                        Text(banned.nickname.isEmpty ? banned.ipAddress : banned.nickname)
                            .font(.headline)
                        Text(banned.ipAddress)
                            .font(.caption)
                            .foregroundStyle(.secondary)
                        Text(banned.bannedAt.formatted(date: .abbreviated, time: .shortened))
                            .font(.caption2)
                            .foregroundStyle(.tertiary)
                    }
                    .accessibilityElement(children: .combine)
                    .accessibilityLabel("Gesperrt: \(banned.nickname.isEmpty ? banned.ipAddress : banned.nickname)")
                    .swipeActions(edge: .trailing) {
                        Button(role: .destructive) {
                            Task { await connection.unbanUser(ipAddress: banned.ipAddress) }
                        } label: {
                            Label("Entsperren", systemImage: "person.fill.checkmark")
                        }
                    }
                }
            }

            Button(action: { Task { await connection.loadBanList() } }) {
                Label("Liste aktualisieren", systemImage: "arrow.clockwise")
            }
            .accessibilityLabel("Sperrliste aktualisieren")
        }
    }
}

// MARK: - User Management (kick/ban/move)

struct UserManagementSection: View {
    @EnvironmentObject var connection: TTConnectionController
    @State private var selectedUser: UserEntry? = nil
    @State private var showMoveSheet = false

    var body: some View {
        Section("Online-Nutzer") {
            ForEach(connection.users) { user in
                HStack {
                    Image(systemName: user.isTalking ? "waveform" : "person.fill")
                        .foregroundStyle(user.isTalking ? .green : .secondary)
                        .accessibilityHidden(true)
                    VStack(alignment: .leading, spacing: 2) {
                        Text(user.nickname)
                        Text("Kanal \(user.channelId)")
                            .font(.caption)
                            .foregroundStyle(.secondary)
                    }
                    Spacer()
                }
                .accessibilityElement(children: .combine)
                .accessibilityLabel("\(user.nickname), Kanal \(user.channelId)\(user.isTalking ? ", spricht" : "")")
                .contextMenu {
                    Button(role: .destructive) {
                        Task { await connection.kickUser(userId: user.id) }
                    } label: {
                        Label("Kicken", systemImage: "person.fill.xmark")
                    }
                    Button(role: .destructive) {
                        Task { await connection.banUser(userId: user.id) }
                    } label: {
                        Label("Bannen", systemImage: "nosign")
                    }
                    Button {
                        selectedUser = user
                        showMoveSheet = true
                    } label: {
                        Label("Verschieben…", systemImage: "arrow.right")
                    }
                }
                .swipeActions(edge: .trailing) {
                    Button(role: .destructive) {
                        Task { await connection.kickUser(userId: user.id) }
                    } label: {
                        Label("Kicken", systemImage: "person.fill.xmark")
                    }
                }
            }
        }
        .sheet(item: $selectedUser) { user in
            MoveUserSheet(user: user)
        }
    }
}

struct MoveUserSheet: View {
    @EnvironmentObject var connection: TTConnectionController
    @Environment(\.dismiss) private var dismiss
    let user: UserEntry

    var body: some View {
        NavigationStack {
            List {
                ForEach(connection.channels) { channel in
                    Button(channel.name) {
                        Task {
                            await connection.moveUser(userId: user.id, toChannel: channel.id)
                            dismiss()
                        }
                    }
                    .accessibilityLabel("In Kanal '\(channel.name)' verschieben")
                }
            }
            .navigationTitle("Nutzer verschieben")
            .toolbar {
                ToolbarItem(placement: .cancellationAction) {
                    Button("Abbrechen") { dismiss() }
                }
            }
        }
    }
}
