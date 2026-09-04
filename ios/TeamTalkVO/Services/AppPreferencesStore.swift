import Foundation

@MainActor
class AppPreferencesStore: ObservableObject {
    @Published var preferences: AppPreferences = AppPreferences()
    private let key = "app_preferences_v1"

    init() { load() }

    func save() {
        if let data = try? JSONEncoder().encode(preferences) {
            UserDefaults.standard.set(data, forKey: key)
        }
    }

    private func load() {
        guard let data = UserDefaults.standard.data(forKey: key),
              let decoded = try? JSONDecoder().decode(AppPreferences.self, from: data)
        else { return }
        preferences = decoded
    }
}
