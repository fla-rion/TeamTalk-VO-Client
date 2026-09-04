import SwiftUI

/// Übersicht aller Sync-Kanäle mit Status und Direktaktionen.
struct SyncOverviewView: View {
    @ObservedObject private var iCloud = CloudSyncService.shared
    @ObservedObject private var google = GoogleDriveSyncService.shared
    @ObservedObject private var companion = CompanionClientService.shared

    var body: some View {
        Form {
            // iCloud
            Section {
                HStack {
                    Image(systemName: "icloud.fill")
                        .font(.title2)
                        .foregroundStyle(iCloud.syncEnabled ? .blue : .secondary)
                        .frame(width: 36)
                        .accessibilityHidden(true)
                    VStack(alignment: .leading, spacing: 2) {
                        Text("iCloud").fontWeight(.semibold)
                        Text("iOS ↔ macOS (Apple-Geräte)").font(.caption).foregroundStyle(.secondary)
                        Text(iCloud.syncStatus.label).font(.caption2).foregroundStyle(iCloud.syncEnabled ? .green : .secondary)
                    }
                    Spacer()
                    Toggle("", isOn: $iCloud.syncEnabled)
                        .labelsHidden()
                        .accessibilityLabel("iCloud-Sync")
                }
                .accessibilityElement(children: .combine)
                .accessibilityLabel("iCloud-Sync: \(iCloud.syncEnabled ? "aktiv" : "inaktiv"), \(iCloud.syncStatus.label)")
                if iCloud.syncEnabled {
                    Button("Jetzt synchronisieren") { iCloud.uploadAll() }
                        .accessibilityLabel("Daten jetzt mit iCloud synchronisieren")
                }
            } header: { Text("Apple iCloud") }

            // Google Drive
            Section {
                HStack {
                    Image(systemName: "g.circle.fill")
                        .font(.title2)
                        .foregroundStyle(google.isSignedIn ? .red : .secondary)
                        .frame(width: 36)
                        .accessibilityHidden(true)
                    VStack(alignment: .leading, spacing: 2) {
                        Text("Google Drive").fontWeight(.semibold)
                        Text("iOS ↔ Android ↔ Windows ↔ macOS").font(.caption).foregroundStyle(.secondary)
                        if google.isSignedIn {
                            Text(google.syncStatus.label).font(.caption2).foregroundStyle(.green)
                        } else {
                            Text("Nicht angemeldet").font(.caption2).foregroundStyle(.secondary)
                        }
                    }
                    Spacer()
                    if google.isSignedIn {
                        Toggle("", isOn: $google.syncEnabled)
                            .labelsHidden()
                            .accessibilityLabel("Google Drive Sync")
                    }
                }
                .accessibilityElement(children: .combine)
                .accessibilityLabel("Google Drive: \(google.isSignedIn ? "angemeldet als \(google.userEmail)" : "nicht angemeldet")")

                if !google.isSignedIn {
                    Button(action: { Task { await google.signIn() } }) {
                        Label("Mit Google anmelden", systemImage: "arrow.right.circle")
                    }
                    .accessibilityLabel("Google-Konto für plattformübergreifenden Sync verbinden")
                } else {
                    Button("Jetzt hochladen") {
                        Task { await google.upload(servers: [], preferences: AppPreferences()) }
                    }
                    .accessibilityLabel("Daten jetzt zu Google Drive hochladen")
                    Button("Abmelden", role: .destructive) { google.signOut() }
                        .accessibilityLabel("Von Google-Konto abmelden")
                }
            } header: { Text("Google (Plattformübergreifend)") }
            footer: {
                Text("Für Google Drive Sync muss eine OAuth Client-ID im Google Cloud Console erstellt und in Info.plist als GOOGLE_CLIENT_ID hinterlegt werden.")
                    .accessibilityLabel("Hinweis: Google Cloud Client-ID erforderlich")
            }

            // Mac-Client (lokal)
            Section {
                HStack {
                    Image(systemName: companion.isConnected ? "desktopcomputer" : "desktopcomputer.slash")
                        .font(.title2)
                        .foregroundStyle(companion.isConnected ? .green : .secondary)
                        .frame(width: 36)
                        .accessibilityHidden(true)
                    VStack(alignment: .leading, spacing: 2) {
                        Text("Mac-Client (lokal)").fontWeight(.semibold)
                        Text("Gleiches WLAN · Port 19880").font(.caption).foregroundStyle(.secondary)
                        Text(companion.isConnected ? "Verbunden mit \(companion.serverHost)" : "Nicht verbunden")
                            .font(.caption2)
                            .foregroundStyle(companion.isConnected ? .green : .secondary)
                    }
                    Spacer()
                    if companion.isConnected {
                        Image(systemName: "checkmark.circle.fill").foregroundStyle(.green).accessibilityHidden(true)
                    }
                }
                .accessibilityElement(children: .combine)
                .accessibilityLabel("Mac-Client-Sync: \(companion.isConnected ? "verbunden" : "nicht verbunden")")

                NavigationLink("Verbindung einrichten", destination: CompanionView())
                    .accessibilityLabel("Mac-Client-Verbindung einrichten")
            } header: { Text("Lokales Netzwerk") }
            footer: {
                Text("Verbindet die iOS-App direkt mit dem laufenden Mac-Client. Serverliste und Einstellungen werden in Echtzeit übertragen – kein Internet nötig.")
                    .accessibilityLabel("Kein Internet nötig. Direktverbindung zum Mac-Client über WLAN.")
            }

            // Was wird synchronisiert
            Section("Synchronisierte Daten") {
                syncItem(icon: "server.rack", label: "Serverliste", synced: iCloud.syncEnabled || google.syncEnabled || companion.isConnected)
                syncItem(icon: "gear", label: "Einstellungen", synced: iCloud.syncEnabled || google.syncEnabled || companion.isConnected)
                syncItem(icon: "key.slash", label: "ElevenLabs API-Schlüssel", synced: false, note: "Aus Sicherheitsgründen nie synchronisiert")
            }
        }
        .navigationTitle("Synchronisierung")
    }

    @ViewBuilder
    private func syncItem(icon: String, label: String, synced: Bool, note: String? = nil) -> some View {
        HStack(spacing: 10) {
            Image(systemName: icon).foregroundStyle(.secondary).frame(width: 24).accessibilityHidden(true)
            VStack(alignment: .leading, spacing: 2) {
                Text(label)
                if let note { Text(note).font(.caption2).foregroundStyle(.secondary) }
            }
            Spacer()
            Image(systemName: synced ? "checkmark.circle.fill" : "minus.circle")
                .foregroundStyle(synced ? .green : .secondary)
                .accessibilityHidden(true)
        }
        .accessibilityElement(children: .combine)
        .accessibilityLabel("\(label): \(synced ? "wird synchronisiert" : "nicht synchronisiert")\(note.map { ", \($0)" } ?? "")")
    }
}
