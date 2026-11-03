import UIKit
import SwiftUI

extension View {
    func teamTalkKeyCommands(connection: TTConnectionController) -> some View {
        self.background(KeyCommandView(connection: connection))
    }
}

private struct KeyCommandView: UIViewControllerRepresentable {
    let connection: TTConnectionController

    func makeUIViewController(context: Context) -> KeyCommandViewController {
        KeyCommandViewController(connection: connection)
    }
    func updateUIViewController(_ vc: KeyCommandViewController, context: Context) {}
}

class KeyCommandViewController: UIViewController {
    let connection: TTConnectionController

    init(connection: TTConnectionController) {
        self.connection = connection
        super.init(nibName: nil, bundle: nil)
    }
    required init?(coder: NSCoder) { fatalError() }

    override var keyCommands: [UIKeyCommand]? {
        [
            UIKeyCommand(
                title: "Sprechen (Push-to-Talk)",
                action: #selector(startPTT),
                input: " ",
                modifierFlags: [],
                discoverabilityTitle: "PTT starten"
            ),
            UIKeyCommand(
                title: "Sprechen beenden",
                action: #selector(stopPTT),
                input: " ",
                modifierFlags: .shift,
                discoverabilityTitle: "PTT stoppen"
            ),
            UIKeyCommand(
                title: "Mikrofon stummschalten",
                action: #selector(toggleMute),
                input: "m",
                modifierFlags: .command,
                discoverabilityTitle: "Mikrofon stummschalten"
            ),
        ]
    }

    @objc func startPTT() {
        Task { @MainActor in connection.startTransmitting() }
    }

    @objc func stopPTT() {
        Task { @MainActor in connection.stopTransmitting() }
    }

    @objc func toggleMute() {
        Task { @MainActor in
            if connection.isTalking { connection.stopTransmitting() }
        }
    }
}
