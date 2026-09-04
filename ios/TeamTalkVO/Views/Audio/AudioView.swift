import SwiftUI
import AVFoundation

struct AudioView: View {
    @EnvironmentObject var connection: TTConnectionController
    @EnvironmentObject var prefs: AppPreferencesStore
    @ObservedObject private var audioSession = AudioSessionManager.shared

    var body: some View {
        NavigationStack {
            if connection.state != .loggedIn {
                ContentUnavailableView("Nicht verbunden", systemImage: "mic.slash")
            } else {
                Form {
                    Section {
                        PTTButton()
                    }
                    Section("Audioausgang") {
                        // Lautsprecher-Umschaltung — AEC bleibt in beiden Modi aktiv
                        Button(action: { audioSession.toggleSpeaker() }) {
                            HStack {
                                Image(systemName: audioSession.currentRoute.systemImageName)
                                    .foregroundStyle(audioSession.currentRoute == .speaker ? .green : .primary)
                                    .accessibilityHidden(true)
                                VStack(alignment: .leading, spacing: 2) {
                                    Text("Ausgang: \(audioSession.currentRoute.displayName)")
                                    Text("Echo-Unterdrückung aktiv")
                                        .font(.caption)
                                        .foregroundStyle(.secondary)
                                }
                                Spacer()
                                Image(systemName: "chevron.right")
                                    .font(.caption)
                                    .foregroundStyle(.secondary)
                                    .accessibilityHidden(true)
                            }
                        }
                        .foregroundStyle(.primary)
                        .accessibilityLabel("Audio-Ausgang: \(audioSession.currentRoute.displayName)")
                        .accessibilityHint("Tippe zum Umschalten zwischen Hörer und Lautsprecher. Echo-Unterdrückung bleibt aktiv.")
                    }
                    Section("Lautstärke") {
                        VStack(alignment: .leading) {
                            Text("Ausgabelautstärke: \(prefs.preferences.masterVolume)%")
                            Slider(value: Binding(
                                get: { Double(prefs.preferences.masterVolume) },
                                set: {
                                    prefs.preferences.masterVolume = Int($0)
                                    connection.setMasterVolume(Int($0))
                                    prefs.save()
                                }
                            ), in: 0...200, step: 5)
                            .accessibilityLabel("Ausgabelautstärke")
                            .accessibilityValue("\(prefs.preferences.masterVolume) Prozent")
                        }
                        VStack(alignment: .leading) {
                            Text("Mikrofonlautstärke: \(prefs.preferences.microphoneGain)%")
                            Slider(value: Binding(
                                get: { Double(prefs.preferences.microphoneGain) },
                                set: {
                                    prefs.preferences.microphoneGain = Int($0)
                                    connection.setMicrophoneGain(Int($0))
                                    prefs.save()
                                }
                            ), in: 0...200, step: 5)
                            .accessibilityLabel("Mikrofonlautstärke")
                            .accessibilityValue("\(prefs.preferences.microphoneGain) Prozent")
                        }
                    }
                    Section("Sprachaktivierung") {
                        Toggle("Sprachaktivierung", isOn: Binding(
                            get: { prefs.preferences.voiceActivationEnabled },
                            set: {
                                prefs.preferences.voiceActivationEnabled = $0
                                connection.enableVoiceActivation($0, level: prefs.preferences.voiceActivationLevel)
                                prefs.save()
                            }
                        ))
                        .accessibilityLabel("Sprachaktivierung ein- oder ausschalten")
                        if prefs.preferences.voiceActivationEnabled {
                            VStack(alignment: .leading) {
                                Text("Schwellwert: \(prefs.preferences.voiceActivationLevel)")
                                Slider(value: Binding(
                                    get: { Double(prefs.preferences.voiceActivationLevel) },
                                    set: {
                                        prefs.preferences.voiceActivationLevel = Int($0)
                                        connection.enableVoiceActivation(true, level: Int($0))
                                        prefs.save()
                                    }
                                ), in: 100...10000, step: 100)
                                .accessibilityLabel("Sprachaktivierungs-Schwellwert")
                                .accessibilityValue("\(prefs.preferences.voiceActivationLevel)")
                            }
                        }
                    }
                    Section("Nutzer-Lautstärken") {
                        ForEach(connection.users.filter { $0.channelId == connection.currentChannelId }) { user in
                            UserVolumeRow(user: user)
                        }
                    }
                }
                .navigationTitle("Audio")
            }
        }
    }
}

struct PTTButton: View {
    @EnvironmentObject var connection: TTConnectionController

    var body: some View {
        Button(action: {}) {
            Label(
                connection.isTalking ? "Spreche…" : "Drücken zum Sprechen",
                systemImage: connection.isTalking ? "waveform.circle.fill" : "mic.circle.fill"
            )
            .font(.title2)
            .frame(maxWidth: .infinity)
            .padding(.vertical, 20)
            .background(connection.isTalking ? Color.green : Color.blue)
            .foregroundStyle(.white)
            .clipShape(RoundedRectangle(cornerRadius: 16))
        }
        .simultaneousGesture(
            DragGesture(minimumDistance: 0)
                .onChanged { _ in
                    if !connection.isTalking { connection.startTransmitting() }
                }
                .onEnded { _ in
                    connection.stopTransmitting()
                }
        )
        .accessibilityLabel("Drücken zum Sprechen")
        .accessibilityHint("Gedrückt halten zum Senden, loslassen zum Stoppen")
        .accessibilityAddTraits(.isButton)
    }
}

struct UserVolumeRow: View {
    @EnvironmentObject var connection: TTConnectionController
    let user: UserEntry
    @State private var volume: Double = 100

    var body: some View {
        VStack(alignment: .leading, spacing: 4) {
            Text(user.nickname)
            Slider(value: $volume, in: 0...200, step: 5) { _ in
                connection.setUserVolume(userId: user.id, volume: Int(volume))
            }
            .accessibilityLabel("Lautstärke von \(user.nickname)")
            .accessibilityValue("\(Int(volume)) Prozent")
        }
    }
}
