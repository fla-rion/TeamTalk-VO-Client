import Foundation

/// Parst tt://-URLs und .tt-XML-Dateien → SavedServerRecord
enum TeamTalkImporter {

    // MARK: - tt:// URL

    static func parse(url: URL) -> SavedServerRecord? {
        guard let scheme = url.scheme,
              scheme == "tt" || scheme == "tts" else { return nil }

        let host = url.host ?? ""
        guard !host.isEmpty else { return nil }

        let encrypted = scheme == "tts"
        let port = url.port ?? 10333

        var username = ""
        var password = ""
        if let user = url.user, !user.isEmpty { username = user }
        if let pass = url.password, !pass.isEmpty { password = pass }

        var channel = url.path
        if channel.hasPrefix("/") { channel = String(channel.dropFirst()) }

        var channelPassword = ""
        if let comps = URLComponents(url: url, resolvingAgainstBaseURL: false),
           let items = comps.queryItems {
            channelPassword = items.first(where: { $0.name == "password" })?.value ?? ""
        }

        return SavedServerRecord(
            name: host,
            host: host,
            tcpPort: port,
            udpPort: port,
            username: username,
            password: password,
            nickname: "",
            channel: channel,
            channelPassword: channelPassword,
            encrypted: encrypted
        )
    }

    // MARK: - .tt XML

    static func parse(ttFileData data: Data) -> [SavedServerRecord] {
        let parser = TTFileXMLParser(data: data)
        return parser.parse()
    }

    static func parse(ttFileURL fileURL: URL) -> [SavedServerRecord] {
        guard let data = try? Data(contentsOf: fileURL) else { return [] }
        return parse(ttFileData: data)
    }
}

// MARK: - XML-Parser für .tt-Dateien

private class TTFileXMLParser: NSObject, XMLParserDelegate {
    private let data: Data
    private var results: [SavedServerRecord] = []
    private var current: [String: String] = [:]
    private var inHost = false
    private var currentText = ""

    init(data: Data) { self.data = data }

    func parse() -> [SavedServerRecord] {
        let parser = XMLParser(data: data)
        parser.delegate = self
        parser.parse()
        return results
    }

    func parser(_ parser: XMLParser, didStartElement element: String,
                namespaceURI: String?, qualifiedName: String?,
                attributes: [String: String] = [:]) {
        currentText = ""
        if element == "host" {
            inHost = true
            current = [:]
        }
    }

    func parser(_ parser: XMLParser, foundCharacters string: String) {
        currentText += string
    }

    func parser(_ parser: XMLParser, didEndElement element: String,
                namespaceURI: String?, qualifiedName: String?) {
        let text = currentText.trimmingCharacters(in: .whitespacesAndNewlines)
        if inHost {
            switch element {
            case "name", "hostname", "tcpport", "udpport", "username",
                 "password", "nickname", "channel", "chanpasswd", "encrypted":
                current[element] = text
            case "host":
                inHost = false
                if let record = buildRecord(from: current) { results.append(record) }
                current = [:]
            default: break
            }
        }
        currentText = ""
    }

    private func buildRecord(from dict: [String: String]) -> SavedServerRecord? {
        let host = dict["hostname"] ?? dict["host"] ?? ""
        guard !host.isEmpty else { return nil }
        let name = dict["name"] ?? host
        let tcp = Int(dict["tcpport"] ?? "") ?? 10333
        let udp = Int(dict["udpport"] ?? "") ?? 10333
        let encrypted = (dict["encrypted"] ?? "").lowercased() == "true" ||
                        (dict["encrypted"] ?? "") == "1"
        return SavedServerRecord(
            name: name, host: host, tcpPort: tcp, udpPort: udp,
            username: dict["username"] ?? "", password: dict["password"] ?? "",
            nickname: dict["nickname"] ?? "", channel: dict["channel"] ?? "",
            channelPassword: dict["chanpasswd"] ?? "", encrypted: encrypted
        )
    }
}
