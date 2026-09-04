import SwiftUI

struct ConnectionStatusBar: View {
    @EnvironmentObject var connection: TTConnectionController

    var body: some View {
        if connection.state != .loggedIn && connection.state != .disconnected {
            HStack(spacing: 8) {
                ProgressView()
                    .scaleEffect(0.7)
                    .accessibilityHidden(true)
                Text(statusText)
                    .font(.caption)
                    .fontWeight(.medium)
                Spacer()
                if connection.state == .connecting || connection.state == .connected {
                    Button("Abbrechen") { connection.disconnect() }
                        .font(.caption)
                        .accessibilityLabel("Verbindung abbrechen")
                }
            }
            .padding(.horizontal, 16)
            .padding(.vertical, 6)
            .background(Color.blue.opacity(0.9))
            .foregroundStyle(.white)
            .accessibilityElement(children: .combine)
            .accessibilityLabel(statusText)
        }
    }

    private var statusText: String {
        switch connection.state {
        case .connecting:       return "Verbinde…"
        case .connected:        return "Anmelden…"
        case .failed(let e):    return "Fehler: \(e)"
        default:                return ""
        }
    }
}
