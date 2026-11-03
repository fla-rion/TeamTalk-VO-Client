import Foundation

@MainActor
class AppPreferencesStore: ObservableObject {
    @Published var preferences: AppPreferences = AppPreferences()
    private let key = "app_preferences_v1"
    private let sync = CloudSyncService.shared

    init() {
        load()
        listenForCloudChanges()
    }

    func save() {
        if let data = try? JSONEncoder().encode(preferences) {
            UserDefaults.standard.set(data, forKey: key)
        }
        sync.upload(preferences: preferences)
    }

    private func load() {
        // Prefer iCloud preferences if sync enabled
        if sync.syncEnabled, let cloudPrefs = sync.downloadPreferences() {
            var merged = cloudPrefs
            // Restore local API key (never synced)
            if let data = UserDefaults.standard.data(forKey: key),
               let local = try? JSONDecoder().decode(AppPreferences.self, from: data) {
                merged.elevenLabsApiKey = local.elevenLabsApiKey
            }
            preferences = merged
            return
        }
        guard let data = UserDefaults.standard.data(forKey: key),
              let decoded = try? JSONDecoder().decode(AppPreferences.self, from: data)
        else { return }
        preferences = decoded
    }

    private func listenForCloudChanges() {
        NotificationCenter.default.addObserver(
            forName: .cloudSyncDidReceiveExternalChanges,
            object: nil,
            queue: .main
        ) { [weak self] note in
            guard let self else { return }
            let keys = note.userInfo?["keys"] as? [String] ?? []
            if keys.contains(CloudSyncService.prefsKey) {
                Task { @MainActor in
                    if let cloudPrefs = self.sync.downloadPreferences() {
                        var merged = cloudPrefs
                        merged.elevenLabsApiKey = self.preferences.elevenLabsApiKey
                        self.preferences = merged
                    }
                }
            }
        }
    }
}
