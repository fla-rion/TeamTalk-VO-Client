import Foundation
import AuthenticationServices

/// Synchronisiert Serverliste und Einstellungen via Google Drive (appDataFolder).
///
/// Ablauf: ASWebAuthenticationSession → OAuth2 → Drive REST API.
/// Datei liegt im versteckten App-Ordner (für Nutzer nicht sichtbar).
/// Plattformübergreifend: iOS ↔ Android ↔ Windows ↔ macOS (über Google-Konto).
@MainActor
final class GoogleDriveSyncService: NSObject, ObservableObject, ASWebAuthenticationPresentationContextProviding {
    static let shared = GoogleDriveSyncService()

    @Published var isSignedIn: Bool = false
    @Published var userEmail: String = ""
    @Published var syncStatus: GoogleSyncStatus = .idle
    @Published var syncEnabled: Bool {
        didSet { UserDefaults.standard.set(syncEnabled, forKey: "google_sync_enabled") }
    }

    enum GoogleSyncStatus: Equatable {
        case idle
        case authenticating
        case syncing
        case success(Date)
        case error(String)

        var label: String {
            switch self {
            case .idle:            return "Nicht verbunden"
            case .authenticating:  return "Anmeldung…"
            case .syncing:         return "Synchronisiere…"
            case .success(let d):  return "Zuletzt: \(d.formatted(date: .omitted, time: .shortened))"
            case .error(let msg):  return "Fehler: \(msg)"
            }
        }
    }

    // Google OAuth2 – trage eigene Client-ID ein (Google Cloud Console)
    // Bundle ID als Redirect-URI: cc.leons.teamtalk-vo:/oauth2redirect
    private let clientId = "YOUR_GOOGLE_CLIENT_ID"  // ← In Info.plist setzen
    private let redirectURI = "cc.leons.teamtalk-vo:/oauth2redirect"
    private let scope = "https://www.googleapis.com/auth/drive.appdata"

    private let driveFileName = "teamtalk_vo_sync.json"
    private var accessToken: String? {
        get { KeychainHelper.load(key: "google_access_token") }
        set { if let v = newValue { KeychainHelper.save(key: "google_access_token", value: v) }
              else { KeychainHelper.delete(key: "google_access_token") } }
    }
    private var refreshToken: String? {
        get { KeychainHelper.load(key: "google_refresh_token") }
        set { if let v = newValue { KeychainHelper.save(key: "google_refresh_token", value: v) }
              else { KeychainHelper.delete(key: "google_refresh_token") } }
    }

    private override init() {
        syncEnabled = UserDefaults.standard.bool(forKey: "google_sync_enabled")
        super.init()
        if refreshToken != nil {
            isSignedIn = true
            userEmail = UserDefaults.standard.string(forKey: "google_user_email") ?? ""
        }
    }

    // MARK: - Anmeldung

    func signIn() async {
        syncStatus = .authenticating
        let authURL = buildAuthURL()
        guard let url = authURL else {
            syncStatus = .error("Auth-URL fehlerhaft")
            return
        }

        await withCheckedContinuation { (cont: CheckedContinuation<Void, Never>) in
            let session = ASWebAuthenticationSession(
                url: url,
                callbackURLScheme: "cc.leons.teamtalk-vo"
            ) { [weak self] callbackURL, error in
                guard let self else { cont.resume(); return }
                Task { @MainActor in
                    if let url = callbackURL, let code = self.extractCode(from: url) {
                        await self.exchangeCode(code)
                    } else {
                        self.syncStatus = .error(error?.localizedDescription ?? "Abgebrochen")
                    }
                    cont.resume()
                }
            }
            session.presentationContextProvider = self
            session.prefersEphemeralWebBrowserSession = false
            session.start()
        }
    }

    func signOut() {
        accessToken = nil
        refreshToken = nil
        isSignedIn = false
        userEmail = ""
        UserDefaults.standard.removeObject(forKey: "google_user_email")
        syncEnabled = false
        syncStatus = .idle
    }

    // MARK: - Sync (Upload)

    func upload(servers: [SavedServerRecord], preferences: AppPreferences) async {
        guard syncEnabled, isSignedIn else { return }
        syncStatus = .syncing
        var safePrefs = preferences
        safePrefs.elevenLabsApiKey = ""
        let payload = SyncPayload(servers: servers, preferences: safePrefs, syncedAt: Date())
        guard let data = try? JSONEncoder().encode(payload) else {
            syncStatus = .error("Kodierungsfehler"); return
        }
        do {
            try await uploadToDrive(data: data)
            syncStatus = .success(Date())
        } catch {
            if case DriveError.unauthorized = error {
                await refreshAccessToken()
                do {
                    try await uploadToDrive(data: data)
                    syncStatus = .success(Date())
                } catch {
                    syncStatus = .error(error.localizedDescription)
                }
            } else {
                syncStatus = .error(error.localizedDescription)
            }
        }
    }

    // MARK: - Sync (Download)

    func download() async -> SyncPayload? {
        guard syncEnabled, isSignedIn else { return nil }
        syncStatus = .syncing
        do {
            let data = try await downloadFromDrive()
            let payload = try JSONDecoder().decode(SyncPayload.self, from: data)
            syncStatus = .success(Date())
            return payload
        } catch {
            if case DriveError.unauthorized = error {
                await refreshAccessToken()
                do {
                    let data = try await downloadFromDrive()
                    let payload = try JSONDecoder().decode(SyncPayload.self, from: data)
                    syncStatus = .success(Date())
                    return payload
                } catch { syncStatus = .error(error.localizedDescription); return nil }
            }
            syncStatus = .error(error.localizedDescription)
            return nil
        }
    }

    // MARK: - Drive REST API

    private func uploadToDrive(data: Data) async throws {
        guard let token = accessToken else { throw DriveError.unauthorized }

        // Suche vorhandene Datei
        let fileId = try await findDriveFile()

        let url: URL
        let method: String
        if let id = fileId {
            url = URL(string: "https://www.googleapis.com/upload/drive/v3/files/\(id)?uploadType=media")!
            method = "PATCH"
        } else {
            // Erstelle Datei in appDataFolder
            let metaURL = URL(string: "https://www.googleapis.com/drive/v3/files")!
            var metaReq = URLRequest(url: metaURL)
            metaReq.httpMethod = "POST"
            metaReq.setValue("Bearer \(token)", forHTTPHeaderField: "Authorization")
            metaReq.setValue("application/json", forHTTPHeaderField: "Content-Type")
            let meta = ["name": driveFileName, "parents": ["appDataFolder"]]
            metaReq.httpBody = try? JSONSerialization.data(withJSONObject: meta)
            let (metaData, _) = try await URLSession.shared.data(for: metaReq)
            guard let json = try? JSONSerialization.jsonObject(with: metaData) as? [String: Any],
                  let newId = json["id"] as? String else { throw DriveError.uploadFailed }
            url = URL(string: "https://www.googleapis.com/upload/drive/v3/files/\(newId)?uploadType=media")!
            method = "PATCH"
        }

        var req = URLRequest(url: url)
        req.httpMethod = method
        req.setValue("Bearer \(token)", forHTTPHeaderField: "Authorization")
        req.setValue("application/json", forHTTPHeaderField: "Content-Type")
        req.httpBody = data
        let (_, response) = try await URLSession.shared.data(for: req)
        guard (response as? HTTPURLResponse)?.statusCode == 200 else { throw DriveError.uploadFailed }
    }

    private func downloadFromDrive() async throws -> Data {
        guard let token = accessToken else { throw DriveError.unauthorized }
        guard let fileId = try await findDriveFile() else { throw DriveError.fileNotFound }
        var req = URLRequest(url: URL(string: "https://www.googleapis.com/drive/v3/files/\(fileId)?alt=media")!)
        req.setValue("Bearer \(token)", forHTTPHeaderField: "Authorization")
        let (data, response) = try await URLSession.shared.data(for: req)
        let status = (response as? HTTPURLResponse)?.statusCode ?? 0
        if status == 401 { throw DriveError.unauthorized }
        if status != 200 { throw DriveError.downloadFailed }
        return data
    }

    private func findDriveFile() async throws -> String? {
        guard let token = accessToken else { throw DriveError.unauthorized }
        let q = "name='\(driveFileName)' and 'appDataFolder' in parents and trashed=false"
        var comps = URLComponents(string: "https://www.googleapis.com/drive/v3/files")!
        comps.queryItems = [URLQueryItem(name: "spaces", value: "appDataFolder"),
                            URLQueryItem(name: "q", value: q),
                            URLQueryItem(name: "fields", value: "files(id,name)")]
        var req = URLRequest(url: comps.url!)
        req.setValue("Bearer \(token)", forHTTPHeaderField: "Authorization")
        let (data, response) = try await URLSession.shared.data(for: req)
        if (response as? HTTPURLResponse)?.statusCode == 401 { throw DriveError.unauthorized }
        guard let json = try? JSONSerialization.jsonObject(with: data) as? [String: Any],
              let files = json["files"] as? [[String: Any]] else { return nil }
        return files.first?["id"] as? String
    }

    // MARK: - OAuth Helpers

    private func buildAuthURL() -> URL? {
        guard clientId != "YOUR_GOOGLE_CLIENT_ID" else { return nil }
        var comps = URLComponents(string: "https://accounts.google.com/o/oauth2/v2/auth")!
        comps.queryItems = [
            URLQueryItem(name: "client_id", value: clientId),
            URLQueryItem(name: "redirect_uri", value: redirectURI),
            URLQueryItem(name: "response_type", value: "code"),
            URLQueryItem(name: "scope", value: scope),
            URLQueryItem(name: "access_type", value: "offline"),
            URLQueryItem(name: "prompt", value: "consent"),
        ]
        return comps.url
    }

    private func extractCode(from url: URL) -> String? {
        URLComponents(url: url, resolvingAgainstBaseURL: false)?
            .queryItems?.first(where: { $0.name == "code" })?.value
    }

    private func exchangeCode(_ code: String) async {
        guard clientId != "YOUR_GOOGLE_CLIENT_ID" else { return }
        let body = [
            "code": code, "client_id": clientId,
            "redirect_uri": redirectURI, "grant_type": "authorization_code"
        ]
        var req = URLRequest(url: URL(string: "https://oauth2.googleapis.com/token")!)
        req.httpMethod = "POST"
        req.setValue("application/x-www-form-urlencoded", forHTTPHeaderField: "Content-Type")
        req.httpBody = body.map { "\($0.key)=\($0.value.addingPercentEncoding(withAllowedCharacters: .urlQueryAllowed) ?? "")" }
                           .joined(separator: "&").data(using: .utf8)
        guard let (data, _) = try? await URLSession.shared.data(for: req),
              let json = try? JSONSerialization.jsonObject(with: data) as? [String: Any] else {
            syncStatus = .error("Token-Austausch fehlgeschlagen"); return
        }
        accessToken  = json["access_token"] as? String
        refreshToken = json["refresh_token"] as? String
        await fetchUserEmail()
        isSignedIn = true
        syncStatus = .idle
    }

    private func refreshAccessToken() async {
        guard let refresh = refreshToken, clientId != "YOUR_GOOGLE_CLIENT_ID" else { return }
        let body = ["refresh_token": refresh, "client_id": clientId, "grant_type": "refresh_token"]
        var req = URLRequest(url: URL(string: "https://oauth2.googleapis.com/token")!)
        req.httpMethod = "POST"
        req.setValue("application/x-www-form-urlencoded", forHTTPHeaderField: "Content-Type")
        req.httpBody = body.map { "\($0.key)=\($0.value)" }.joined(separator: "&").data(using: .utf8)
        guard let (data, _) = try? await URLSession.shared.data(for: req),
              let json = try? JSONSerialization.jsonObject(with: data) as? [String: Any],
              let newToken = json["access_token"] as? String else { return }
        accessToken = newToken
    }

    private func fetchUserEmail() async {
        guard let token = accessToken else { return }
        var req = URLRequest(url: URL(string: "https://www.googleapis.com/oauth2/v2/userinfo")!)
        req.setValue("Bearer \(token)", forHTTPHeaderField: "Authorization")
        guard let (data, _) = try? await URLSession.shared.data(for: req),
              let json = try? JSONSerialization.jsonObject(with: data) as? [String: Any],
              let email = json["email"] as? String else { return }
        userEmail = email
        UserDefaults.standard.set(email, forKey: "google_user_email")
    }

    // MARK: - ASWebAuthenticationPresentationContextProviding

    nonisolated func presentationAnchor(for session: ASWebAuthenticationSession) -> ASPresentationAnchor {
        UIApplication.shared.connectedScenes
            .compactMap { $0 as? UIWindowScene }
            .first?.windows.first ?? ASPresentationAnchor()
    }
}

// MARK: - Shared Payload (plattformübergreifendes Format)

struct SyncPayload: Codable {
    var servers: [SavedServerRecord]
    var preferences: AppPreferences
    var syncedAt: Date
    var platform: String = "ios"
    var appVersion: String = Bundle.main.infoDictionary?["CFBundleShortVersionString"] as? String ?? "?"
}

// MARK: - Drive Errors

enum DriveError: Error {
    case unauthorized
    case fileNotFound
    case uploadFailed
    case downloadFailed
}

// MARK: - Keychain Helper

struct KeychainHelper {
    static func save(key: String, value: String) {
        guard let data = value.data(using: .utf8) else { return }
        let q: [CFString: Any] = [kSecClass: kSecClassGenericPassword, kSecAttrAccount: key]
        SecItemDelete(q as CFDictionary)
        let attrs: [CFString: Any] = [kSecClass: kSecClassGenericPassword,
                                       kSecAttrAccount: key, kSecValueData: data]
        SecItemAdd(attrs as CFDictionary, nil)
    }

    static func load(key: String) -> String? {
        let q: [CFString: Any] = [kSecClass: kSecClassGenericPassword, kSecAttrAccount: key,
                                   kSecReturnData: true, kSecMatchLimit: kSecMatchLimitOne]
        var result: AnyObject?
        guard SecItemCopyMatching(q as CFDictionary, &result) == errSecSuccess,
              let data = result as? Data else { return nil }
        return String(data: data, encoding: .utf8)
    }

    static func delete(key: String) {
        let q: [CFString: Any] = [kSecClass: kSecClassGenericPassword, kSecAttrAccount: key]
        SecItemDelete(q as CFDictionary)
    }
}
