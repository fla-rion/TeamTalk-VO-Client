import AVFoundation
import simd

@MainActor
class SpatialAudioService: ObservableObject {
    static let shared = SpatialAudioService()

    @Published var isEnabled: Bool = false
    @Published var userCount: Int = 0

    private var engine = AVAudioEngine()
    private var environment: AVAudioEnvironmentNode
    private var playerNodes: [Int: (AVAudioPlayerNode, AVAudioMixerNode)] = [:]
    private var isRunning = false

    private init() {
        environment = AVAudioEnvironmentNode()
        environment.listenerPosition = AVAudio3DPoint(x: 0, y: 0, z: 0)
        environment.listenerVectorOrientation = AVAudio3DVectorOrientation(
            forward: AVAudio3DVector(x: 0, y: 0, z: -1),
            up:      AVAudio3DVector(x: 0, y: 1, z: 0)
        )
        environment.reverbParameters.enable = false
        engine.attach(environment)
        engine.connect(environment, to: engine.outputNode, format: nil)
    }

    func enable(userIds: [Int]) {
        guard !isRunning else { return }
        isEnabled = true
        do {
            try engine.start()
            isRunning = true
        } catch {
            print("[SpatialAudio] Engine-Start fehlgeschlagen: \(error)")
            return
        }
        repositionUsers(userIds: userIds)
    }

    func disable() {
        isEnabled = false
        engine.stop()
        isRunning = false
        for (_, (player, _)) in playerNodes {
            player.stop()
            engine.detach(player)
        }
        playerNodes.removeAll()
    }

    func repositionUsers(userIds: [Int]) {
        userCount = userIds.count
        guard userIds.count > 0 else { return }
        let total = userIds.count
        for (i, uid) in userIds.enumerated() {
            let angle = (2 * Float.pi / Float(total)) * Float(i)
            let radius: Float = 2.0
            let x = radius * sin(angle)
            let z = -radius * cos(angle)
            if let (player, _) = playerNodes[uid] {
                player.position = AVAudio3DPoint(x: x, y: 0, z: z)
            } else {
                let player = AVAudioPlayerNode()
                let mixer  = AVAudioMixerNode()
                engine.attach(player)
                engine.attach(mixer)
                let fmt = AVAudioFormat(standardFormatWithSampleRate: 48000, channels: 1)!
                engine.connect(player, to: mixer, format: fmt)
                engine.connect(mixer, to: environment, format: fmt)
                player.position = AVAudio3DPoint(x: x, y: 0, z: z)
                player.renderingAlgorithm = .HRTF
                playerNodes[uid] = (player, mixer)
            }
        }
        let stale = Set(playerNodes.keys).subtracting(userIds)
        for uid in stale {
            if let (player, mixer) = playerNodes.removeValue(forKey: uid) {
                player.stop()
                engine.detach(player)
                engine.detach(mixer)
            }
        }
    }

    func feedPCM(userId: Int, buffer: AVAudioPCMBuffer) {
        guard isEnabled, let (player, _) = playerNodes[userId] else { return }
        if !player.isPlaying { player.play() }
        player.scheduleBuffer(buffer, completionHandler: nil)
    }
}
