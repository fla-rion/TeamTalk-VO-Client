import Foundation
import Combine

// MARK: - Connection State
enum TTConnectionState: Equatable {
    case disconnected
    case connecting
    case connected
    case loggedIn
    case failed(String)
}

// MARK: - Events
enum TTEvent {
    case userJoined(UserEntry)
    case userLeft(UserEntry)
    case userTalkingChanged(UserEntry)
    case channelMessage(ChannelChatMessage)
    case privateMessage(PrivateChatMessage)
    case channelListUpdated([ChannelEntry])
    case userListUpdated([UserEntry])
    case connectionLost
    case kicked
    case serverProperties(ServerProperties)
    case fileListUpdated
    case streamingStarted
    case streamingStopped
}

// MARK: - Controller
@MainActor
class TTConnectionController: ObservableObject {
    @Published var state: TTConnectionState = .disconnected
    @Published var channels: [ChannelEntry] = []
    @Published var users: [UserEntry] = []
    @Published var currentChannelId: Int = 0
    @Published var isTalking: Bool = false
    @Published var serverProperties: ServerProperties? = nil

    let eventPublisher = PassthroughSubject<TTEvent, Never>()

    private var eventLoopTask: Task<Void, Never>? = nil
    private var currentServer: SavedServerRecord? = nil

    // MARK: - Connection
    func connect(to server: SavedServerRecord) async {
        state = .connecting
        currentServer = server
        // SDK-Call: TT_Connect / TT_DoLogin
        // Hier wird das echte TeamTalk xcframework aufgerufen sobald eingebunden.
        // Für Entwicklung ohne SDK: Simulation
        await simulateConnection(server: server)
    }

    func disconnect() {
        eventLoopTask?.cancel()
        state = .disconnected
        channels = []
        users = []
        currentChannelId = 0
        serverProperties = nil
    }

    // MARK: - Channel Operations
    func joinChannel(_ channel: ChannelEntry, password: String = "") async {
        // TT_DoJoinChannel
        currentChannelId = channel.id
    }

    func leaveChannel() async {
        // TT_DoLeaveChannel
        currentChannelId = 0
    }

    // MARK: - Audio
    func startTransmitting() {
        // TT_EnableTransmission
        isTalking = true
    }

    func stopTransmitting() {
        // TT_EnableTransmission(false)
        isTalking = false
    }

    func setUserVolume(userId: Int, volume: Int) {
        // TT_SetUserVolume
    }

    func setMasterVolume(_ volume: Int) {
        // TT_SetSoundOutputVolume
    }

    func setMicrophoneGain(_ gain: Int) {
        // TT_SetSoundInputGain
    }

    func enableVoiceActivation(_ enabled: Bool, level: Int = 2000) {
        // TT_EnableVoiceActivation
    }

    // MARK: - Messaging
    func sendChannelMessage(_ text: String) async {
        // TT_DoSendMessage
        let msg = ChannelChatMessage(author: currentServer?.nickname ?? "Me",
                                      content: text, timestamp: Date(), isOwn: true)
        eventPublisher.send(.channelMessage(msg))
    }

    func sendPrivateMessage(_ text: String, to userId: Int, nickname: String) async {
        // TT_DoSendMessage (private)
        let msg = PrivateChatMessage(from: currentServer?.nickname ?? "Me",
                                      to: nickname, content: text, timestamp: Date(), isOwn: true)
        eventPublisher.send(.privateMessage(msg))
    }

    // MARK: - Media Streaming
    func startMediaStream(url: String) async -> Bool {
        // TT_StartStreamingMediaFileToChannel
        eventPublisher.send(.streamingStarted)
        return true
    }

    func stopMediaStream() {
        // TT_StopStreamingMediaFileToChannel
        eventPublisher.send(.streamingStopped)
    }

    // MARK: - ElevenLabs TTS → Channel
    func streamPCMToChannel(_ pcmData: Data) async {
        // TT_SendAudioBlock – streamt PCM direkt in den Kanal
        // Wird aufgerufen nachdem ElevenLabsService.synthesize() PCM liefert
    }

    // MARK: - Admin
    func kickUser(userId: Int, fromChannel: Bool = true) async {
        // TT_DoKickUser
    }

    func banUser(userId: Int) async {
        // TT_DoBanUser
    }

    func moveUser(userId: Int, toChannel channelId: Int) async {
        // TT_DoMoveUser
    }

    // MARK: - Simulation (Entwicklung ohne SDK)
    private func simulateConnection(server: SavedServerRecord) async {
        try? await Task.sleep(nanoseconds: 800_000_000)
        state = .loggedIn
        serverProperties = ServerProperties(name: server.name, motd: "Willkommen", version: "5.12")
        channels = [
            ChannelEntry(id: 1, name: "Root", parentId: 0, topic: "", userCount: 3, hasPassword: false, isJoined: true),
            ChannelEntry(id: 2, name: "Lobby", parentId: 1, topic: "Allgemein", userCount: 1, hasPassword: false, isJoined: false),
            ChannelEntry(id: 3, name: "Privat", parentId: 1, topic: "", userCount: 0, hasPassword: true, isJoined: false),
        ]
        users = [
            UserEntry(id: 1, nickname: server.nickname, username: server.username, channelId: 1, isTalking: false, isMuted: false, gender: "N", statusMessage: ""),
            UserEntry(id: 2, nickname: "Testnutzer", username: "test", channelId: 1, isTalking: false, isMuted: false, gender: "M", statusMessage: "Hallo"),
        ]
        currentChannelId = 1
        eventPublisher.send(.channelListUpdated(channels))
        eventPublisher.send(.userListUpdated(users))
    }
}
