import AVFoundation
import Combine

/// Verwaltet AVAudioSession für TeamTalk-VoIP mit automatischer Echo-Unterdrückung.
///
/// Nutzt den iOS `.voiceChat`-Modus, der intern `kAudioUnitSubType_VoiceProcessingIO`
/// aktiviert – dieselbe AEC-Engine wie FaceTime, WhatsApp und Discord.
/// Das AEC arbeitet auch bei aktivem Lautsprecher und filtert VoiceOver-Sprachausgabe
/// zuverlässig aus dem Mikrofonsignal heraus.
@MainActor
class AudioSessionManager: ObservableObject {

    static let shared = AudioSessionManager()

    @Published var currentRoute: AudioRoute = .earpiece
    @Published var isSessionActive = false
    @Published var micPermissionGranted = false

    private var routeChangeTask: Task<Void, Never>? = nil

    enum AudioRoute {
        case earpiece
        case speaker
        case headphones
        case bluetooth
        case unknown

        var displayName: String {
            switch self {
            case .earpiece:   return "Hörer"
            case .speaker:    return "Lautsprecher"
            case .headphones: return "Kopfhörer"
            case .bluetooth:  return "Bluetooth"
            case .unknown:    return "Unbekannt"
            }
        }

        var systemImageName: String {
            switch self {
            case .earpiece:   return "phone.fill"
            case .speaker:    return "speaker.wave.3.fill"
            case .headphones: return "headphones"
            case .bluetooth:  return "headphones"
            case .unknown:    return "speaker.slash"
            }
        }
    }

    private init() {}

    // MARK: - Session Setup

    /// Aktiviert die Audio-Session für VoIP.
    /// Muss vor dem ersten SDK-Connect aufgerufen werden.
    func activate() async {
        await requestMicPermission()
        await configureSession()
        startRouteMonitoring()
    }

    func deactivate() {
        routeChangeTask?.cancel()
        try? AVAudioSession.sharedInstance().setActive(false, options: .notifyOthersOnDeactivation)
        isSessionActive = false
    }

    // MARK: - Konfiguration

    private func configureSession() async {
        let session = AVAudioSession.sharedInstance()
        do {
            // .voiceChat aktiviert automatisch:
            // • Acoustic Echo Cancellation (AEC) — auch bei Lautsprecher
            // • Noise Reduction / Suppression
            // • Automatic Gain Control (AGC)
            // • Ducking von Hintergrundmusik
            // Das AEC kennt den eigenen Lautsprecher-Output und filtert ihn
            // aus dem Mikrofon-Input heraus, bevor er ans SDK geht.
            // Dasselbe gilt für VoiceOver-Sprache: sie wird subtrahiert.
            try session.setCategory(
                .playAndRecord,
                mode: .voiceChat,
                options: [
                    .allowBluetooth,          // AirPods, BT-Headsets
                    .allowBluetoothA2DP,      // HQ-Bluetooth-Headphones
                    .mixWithOthers,            // Hintergrundmusik ducken statt stoppen
                ]
            )
            try session.setPreferredSampleRate(48000)
            try session.setPreferredIOBufferDuration(0.02) // 20ms – VoIP-Standard
            try session.setActive(true)
            isSessionActive = true
            updateCurrentRoute()
        } catch {
            print("[AudioSession] Konfiguration fehlgeschlagen: \(error)")
        }
    }

    // MARK: - Lautsprecher-Umschaltung

    /// Schaltet zwischen Hörer (Ear) und Lautsprecher um.
    /// Das AEC bleibt in beiden Modi aktiv.
    func toggleSpeaker() {
        let session = AVAudioSession.sharedInstance()
        let goToSpeaker = currentRoute != .speaker
        do {
            try session.overrideOutputAudioPort(goToSpeaker ? .speaker : .none)
            // Route-Update kommt via Notification; updateCurrentRoute() wird reaktiv aufgerufen.
        } catch {
            print("[AudioSession] Lautsprecher-Umschaltung fehlgeschlagen: \(error)")
        }
    }

    /// Erzwingt Lautsprecher (für App-Start oder Nutzer-Präferenz).
    func enableSpeaker(_ enabled: Bool) {
        let session = AVAudioSession.sharedInstance()
        try? session.overrideOutputAudioPort(enabled ? .speaker : .none)
    }

    // MARK: - Route-Monitoring

    private func startRouteMonitoring() {
        NotificationCenter.default.addObserver(
            self,
            selector: #selector(handleRouteChange),
            name: AVAudioSession.routeChangeNotification,
            object: nil
        )
        NotificationCenter.default.addObserver(
            self,
            selector: #selector(handleInterruption),
            name: AVAudioSession.interruptionNotification,
            object: nil
        )
    }

    @objc private func handleRouteChange(_ notification: Notification) {
        Task { @MainActor in
            updateCurrentRoute()
        }
    }

    @objc private func handleInterruption(_ notification: Notification) {
        guard let info = notification.userInfo,
              let typeValue = info[AVAudioSessionInterruptionTypeKey] as? UInt,
              let type = AVAudioSession.InterruptionType(rawValue: typeValue)
        else { return }

        Task { @MainActor in
            switch type {
            case .began:
                // Anruf oder Siri hat Audio übernommen
                isSessionActive = false
            case .ended:
                // Session reaktivieren nach Unterbrechung (z.B. Anruf beendet)
                if let optionsValue = info[AVAudioSessionInterruptionOptionKey] as? UInt {
                    let options = AVAudioSession.InterruptionOptions(rawValue: optionsValue)
                    if options.contains(.shouldResume) {
                        await configureSession()
                    }
                }
            @unknown default:
                break
            }
        }
    }

    private func updateCurrentRoute() {
        let session = AVAudioSession.sharedInstance()
        let outputs = session.currentRoute.outputs

        if outputs.contains(where: { $0.portType == .builtInSpeaker }) {
            currentRoute = .speaker
        } else if outputs.contains(where: { $0.portType == .headphones || $0.portType == .headsetMic }) {
            currentRoute = .headphones
        } else if outputs.contains(where: {
            $0.portType == .bluetoothA2DP || $0.portType == .bluetoothHFP || $0.portType == .bluetoothLE
        }) {
            currentRoute = .bluetooth
        } else if outputs.contains(where: { $0.portType == .builtInReceiver }) {
            currentRoute = .earpiece
        } else {
            currentRoute = .unknown
        }
    }

    // MARK: - Mikrofon-Berechtigung

    func requestMicPermission() async {
        if #available(iOS 17.0, *) {
            let granted = await AVAudioApplication.requestRecordPermission()
            micPermissionGranted = granted
        } else {
            await withCheckedContinuation { continuation in
                AVAudioSession.sharedInstance().requestRecordPermission { granted in
                    Task { @MainActor in
                        self.micPermissionGranted = granted
                        continuation.resume()
                    }
                }
            }
        }
    }
}
