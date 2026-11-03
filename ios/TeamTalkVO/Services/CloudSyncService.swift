import Foundation
import Combine

/// Synchronisiert Serverliste und Einstellungen über iCloud Key-Value-Store.
///
/// Nutzt NSUbiquitousKeyValueStore (iCloud KVS) – kein CloudKit-Account nötig,
/// nur iCloud angemeldet. Änderungen werden automatisch auf alle Geräte übertragen.
@MainActor
final class CloudSyncService: ObservableObject {
    static let shared = CloudSyncService()

    @Published var syncEnabled: Bool {
        didSet {
            UserDefaults.standard.set(syncEnabled, forKey: "cloud_sync_enabled")
            if syncEnabled { uploadAll() }
        }
    }
    @Published var lastSyncDate: Date? = nil
    @Published var syncStatus: SyncStatus = .idle

    enum SyncStatus: Equatable {
        case idle
        case syncing
        case success(Date)
        case error(String)

        var label: String {
            switch self {
            case .idle:            return "Bereit"
            case .syncing:         return "Synchronisiere…"
            case .success(let d):  return "Zuletzt: \(d.formatted(date: .omitted, time: .shortened))"
            case .error(let msg):  return "Fehler: \(msg)"
            }
        }
    }

    private let kvs = NSUbiquitousKeyValueStore.default
    private var externalChangeTask: Task<Void, Never>? = nil

    // Keys im iCloud KVS
    static let serversKey = "icloud_saved_servers_v1"
    static let prefsKey   = "icloud_app_preferences_v1"

    private init() {
        syncEnabled = UserDefaults.standard.bool(forKey: "cloud_sync_enabled")
        startListening()
    }

    // MARK: - Upload (lokal → iCloud)

    func upload(servers: [SavedServerRecord]) {
        guard syncEnabled else { return }
        guard let data = try? JSONEncoder().encode(servers) else { return }
        kvs.set(data, forKey: CloudSyncService.serversKey)
        kvs.synchronize()
        lastSyncDate = Date()
        syncStatus = .success(Date())
    }

    func upload(preferences: AppPreferences) {
        guard syncEnabled else { return }
        // Kein API-Key in der Cloud (Sicherheit)
        var safePrefs = preferences
        safePrefs.elevenLabsApiKey = ""
        guard let data = try? JSONEncoder().encode(safePrefs) else { return }
        kvs.set(data, forKey: CloudSyncService.prefsKey)
        kvs.synchronize()
        lastSyncDate = Date()
    }

    func uploadAll() {
        syncStatus = .syncing
        kvs.synchronize()
        lastSyncDate = Date()
        syncStatus = .success(Date())
    }

    // MARK: - Download (iCloud → lokal)

    func downloadServers() -> [SavedServerRecord]? {
        guard let data = kvs.data(forKey: CloudSyncService.serversKey) else { return nil }
        return try? JSONDecoder().decode([SavedServerRecord].self, from: data)
    }

    func downloadPreferences() -> AppPreferences? {
        guard let data = kvs.data(forKey: CloudSyncService.prefsKey) else { return nil }
        return try? JSONDecoder().decode(AppPreferences.self, from: data)
    }

    // MARK: - Externe Änderungen empfangen

    private func startListening() {
        NotificationCenter.default.addObserver(
            self,
            selector: #selector(handleExternalChange),
            name: NSUbiquitousKeyValueStore.didChangeExternallyNotification,
            object: kvs
        )
        kvs.synchronize()
    }

    @objc private func handleExternalChange(_ note: Notification) {
        guard let reason = note.userInfo?[NSUbiquitousKeyValueStoreChangeReasonKey] as? Int else { return }
        let changedKeys = note.userInfo?[NSUbiquitousKeyValueStoreChangedKeysKey] as? [String] ?? []

        Task { @MainActor in
            self.syncStatus = .syncing
            // Benachrichtige Observer über geänderte Keys
            NotificationCenter.default.post(
                name: .cloudSyncDidReceiveExternalChanges,
                object: nil,
                userInfo: ["keys": changedKeys, "reason": reason]
            )
            self.lastSyncDate = Date()
            self.syncStatus = .success(Date())
        }
    }
}

extension Notification.Name {
    static let cloudSyncDidReceiveExternalChanges = Notification.Name("CloudSyncDidReceiveExternalChanges")
}
