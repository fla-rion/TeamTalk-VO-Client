import Foundation
import Network
import Combine

/// Verbindet die iOS-App mit dem lokalen CompanionServer des macOS-Hauptclients (Port 19880).
///
/// Der Mac-Client läuft den CompanionServer automatisch im Hintergrund.
/// Die iOS-App findet ihn per Bonjour (_teamtalk-companion._tcp) oder manuelle IP-Eingabe.
/// API: GET /status, /channels, /users, POST /say, GET /events (SSE).
@MainActor
final class CompanionClientService: ObservableObject {
    static let shared = CompanionClientService()

    @Published var isConnected: Bool = false
    @Published var serverHost: String = ""
    @Published var serverPort: Int = 19880
    @Published var authToken: String = ""
    @Published var status: CompanionStatus? = nil
    @Published var channels: [CompanionChannel] = []
    @Published var users: [CompanionUser] = []
    @Published var connectionError: String? = nil
    @Published var discoveredHosts: [DiscoveredHost] = []

    struct CompanionStatus: Codable {
        var connected: Bool
        var server: String?
        var channel: String?
        var userCount: Int?
        enum CodingKeys: String, CodingKey {
            case connected, server, channel
            case userCount = "user_count"
        }
    }

    struct CompanionChannel: Codable, Identifiable {
        var id: Int
        var name: String
        var parentId: Int?
        var userCount: Int
        enum CodingKeys: String, CodingKey {
            case id, name
            case parentId = "parent_id"
            case userCount = "user_count"
        }
    }

    struct CompanionUser: Codable, Identifiable {
        var id: Int
        var nickname: String
        var channelId: Int
        var isTalking: Bool
        enum CodingKeys: String, CodingKey {
            case id, nickname
            case channelId = "channel_id"
            case isTalking = "is_talking"
        }
    }

    struct DiscoveredHost: Identifiable {
        var id = UUID()
        var name: String
        var host: String
        var port: Int
    }

    private var sseTask: URLSessionDataTask? = nil
    private var pollTimer: Timer? = nil
    private var browser: NWBrowser? = nil

    private init() {
        serverHost = UserDefaults.standard.string(forKey: "companion_host") ?? ""
        serverPort = UserDefaults.standard.integer(forKey: "companion_port") == 0
            ? 19880 : UserDefaults.standard.integer(forKey: "companion_port")
        authToken  = UserDefaults.standard.string(forKey: "companion_token") ?? ""
    }

    // MARK: - Bonjour-Erkennung

    func startDiscovery() {
        browser?.cancel()
        discoveredHosts = []
        let params = NWParameters()
        params.includePeerToPeer = true
        browser = NWBrowser(for: .bonjourWithTXTRecord(type: "_teamtalk-companion._tcp", domain: nil), using: params)
        browser?.browseResultsChangedHandler = { [weak self] results, _ in
            Task { @MainActor [weak self] in
                guard let self else { return }
                self.discoveredHosts = results.compactMap { result -> DiscoveredHost? in
                    if case .service(let name, _, let domain, _) = result.endpoint {
                        return DiscoveredHost(name: name, host: "\(name).\(domain)", port: 19880)
                    }
                    return nil
                }
            }
        }
        browser?.start(queue: .main)
    }

    func stopDiscovery() { browser?.cancel(); browser = nil }

    // MARK: - Verbindung

    func connect(host: String? = nil, port: Int? = nil, token: String? = nil) async {
        let h = host ?? serverHost
        let p = port ?? serverPort
        let t = token ?? authToken
        guard !h.isEmpty else { connectionError = "Kein Host angegeben"; return }

        serverHost = h; serverPort = p; authToken = t
        UserDefaults.standard.set(h, forKey: "companion_host")
        UserDefaults.standard.set(p, forKey: "companion_port")
        UserDefaults.standard.set(t, forKey: "companion_token")

        connectionError = nil
        await fetchStatus()
        await fetchChannels()
        await fetchUsers()
        if isConnected { startPolling() }
    }

    func disconnect() {
        stopPolling()
        stopDiscovery()
        isConnected = false
        status = nil
        channels = []
        users = []
    }

    // MARK: - API-Abfragen

    func fetchStatus() async {
        guard let data = await get("/status") else { return }
        if let s = try? JSONDecoder().decode(CompanionStatus.self, from: data) {
            status = s
            isConnected = true
        }
    }

    func fetchChannels() async {
        guard let data = await get("/channels") else { return }
        if let ch = try? JSONDecoder().decode([CompanionChannel].self, from: data) {
            channels = ch
        }
    }

    func fetchUsers() async {
        guard let data = await get("/users") else { return }
        if let u = try? JSONDecoder().decode([CompanionUser].self, from: data) {
            users = u
        }
    }

    func sendMessage(text: String, channelId: Int) async -> Bool {
        let body = ["text": text, "channel_id": channelId] as [String: Any]
        guard let data = try? JSONSerialization.data(withJSONObject: body) else { return false }
        return await post("/say", body: data)
    }

    func registerPushToken(_ token: String) async {
        let body = ["token": token, "platform": "ios"]
        guard let data = try? JSONSerialization.data(withJSONObject: body) else { return }
        _ = await post("/push_token", body: data)
    }

    // MARK: - Polling (alle 3 Sekunden)

    private func startPolling() {
        pollTimer?.invalidate()
        pollTimer = Timer.scheduledTimer(withTimeInterval: 3.0, repeats: true) { [weak self] _ in
            Task { @MainActor [weak self] in
                await self?.fetchStatus()
                await self?.fetchUsers()
            }
        }
    }

    private func stopPolling() {
        pollTimer?.invalidate()
        pollTimer = nil
    }

    // MARK: - HTTP Helpers

    private func makeRequest(path: String, method: String = "GET", body: Data? = nil) -> URLRequest? {
        guard !serverHost.isEmpty else { return nil }
        let scheme = "http"
        guard let url = URL(string: "\(scheme)://\(serverHost):\(serverPort)\(path)") else { return nil }
        var req = URLRequest(url: url, timeoutInterval: 5)
        req.httpMethod = method
        if !authToken.isEmpty { req.setValue(authToken, forHTTPHeaderField: "X-Companion-Token") }
        if let body { req.httpBody = body; req.setValue("application/json", forHTTPHeaderField: "Content-Type") }
        return req
    }

    private func get(_ path: String) async -> Data? {
        guard let req = makeRequest(path: path) else { return nil }
        do {
            let (data, response) = try await URLSession.shared.data(for: req)
            if (response as? HTTPURLResponse)?.statusCode == 200 { return data }
            connectionError = "HTTP \((response as? HTTPURLResponse)?.statusCode ?? 0)"
            isConnected = false
        } catch {
            connectionError = error.localizedDescription
            isConnected = false
        }
        return nil
    }

    @discardableResult
    private func post(_ path: String, body: Data) async -> Bool {
        guard let req = makeRequest(path: path, method: "POST", body: body) else { return false }
        guard let (_, response) = try? await URLSession.shared.data(for: req) else { return false }
        return (response as? HTTPURLResponse)?.statusCode == 200
    }
}
