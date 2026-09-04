import SwiftUI

struct SpeakView: View {
    @EnvironmentObject var connection: TTConnectionController
    @EnvironmentObject var elevenlabs: ElevenLabsService
    @EnvironmentObject var prefs: AppPreferencesStore
    @State private var text = ""
    @State private var isSynthesizing = false
    @State private var lastError: String? = nil

    var selectedVoiceId: String { prefs.preferences.elevenLabsVoiceId }
    var apiKey: String { prefs.preferences.elevenLabsApiKey }

    var body: some View {
        NavigationStack {
            if connection.state != .loggedIn {
                ContentUnavailableView("Nicht verbunden", systemImage: "waveform.slash")
            } else {
                Form {
                    Section("Text sprechen") {
                        TextEditor(text: $text)
                            .frame(minHeight: 100)
                            .accessibilityLabel("Text zum Vorlesen")

                        Button(action: speak) {
                            HStack {
                                if isSynthesizing {
                                    ProgressView()
                                } else {
                                    Image(systemName: "waveform")
                                }
                                Text(isSynthesizing ? "Wird synthetisiert…" : "In Kanal sprechen")
                            }
                            .frame(maxWidth: .infinity)
                        }
                        .disabled(
                            text.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
                            || apiKey.isEmpty
                            || selectedVoiceId.isEmpty
                            || isSynthesizing
                        )
                        .accessibilityLabel(isSynthesizing ? "Synthese läuft" : "Text via ElevenLabs in Kanal sprechen")
                    }

                    if let error = lastError {
                        Section {
                            Text(error)
                                .foregroundStyle(.red)
                                .accessibilityLabel("Fehler: \(error)")
                        }
                    }

                    Section("Stimme") {
                        if elevenlabs.voices.isEmpty {
                            Button("Stimmen laden") {
                                Task { await elevenlabs.fetchVoices(apiKey: apiKey) }
                            }
                            .disabled(apiKey.isEmpty)
                            .accessibilityLabel("ElevenLabs-Stimmen laden")
                        } else {
                            Picker("Stimme", selection: Binding(
                                get: { selectedVoiceId },
                                set: { prefs.preferences.elevenLabsVoiceId = $0; prefs.save() }
                            )) {
                                ForEach(elevenlabs.voices) { voice in
                                    Text(voice.name).tag(voice.voiceId)
                                }
                            }
                            .accessibilityLabel("ElevenLabs-Stimme auswählen")
                        }
                    }

                    Section {
                        NavigationLink("API-Key in Einstellungen") {
                            SettingsView()
                        }
                        .accessibilityLabel("ElevenLabs API-Key in den Einstellungen konfigurieren")
                    }
                }
                .navigationTitle("Sprechen")
            }
        }
    }

    private func speak() {
        let trimmed = text.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !trimmed.isEmpty, !apiKey.isEmpty, !selectedVoiceId.isEmpty else { return }
        isSynthesizing = true
        lastError = nil
        Task {
            defer { isSynthesizing = false }
            do {
                let pcm = try await elevenlabs.synthesize(
                    text: trimmed, voiceId: selectedVoiceId, apiKey: apiKey)
                await connection.streamPCMToChannel(pcm)
            } catch {
                lastError = error.localizedDescription
            }
        }
    }
}
