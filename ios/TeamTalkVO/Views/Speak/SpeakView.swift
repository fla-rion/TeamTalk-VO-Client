import SwiftUI

private let elevenLabsModels: [(id: String, name: String)] = [
    ("eleven_multilingual_v2", "Multilingual v2"),
    ("eleven_turbo_v2_5", "Turbo v2.5 (schnell)"),
    ("eleven_turbo_v2", "Turbo v2"),
    ("eleven_monolingual_v1", "Englisch v1"),
]

struct SpeakView: View {
    @EnvironmentObject var connection: TTConnectionController
    @EnvironmentObject var elevenlabs: ElevenLabsService
    @EnvironmentObject var prefs: AppPreferencesStore
    @State private var text = ""
    @State private var isSynthesizing = false
    @State private var lastError: String? = nil
    @State private var ttsHistory: [(text: String, date: Date)] = []
    @State private var showHistory = false

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

                    Section("Stimme & Modell") {
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

                        Picker("Modell", selection: Binding(
                            get: { prefs.preferences.elevenLabsModel },
                            set: { prefs.preferences.elevenLabsModel = $0; prefs.save() }
                        )) {
                            ForEach(elevenLabsModels, id: \.id) { model in
                                Text(model.name).tag(model.id)
                            }
                        }
                        .accessibilityLabel("ElevenLabs-Modell auswählen")
                    }

                    Section("Sprachqualität") {
                        VStack(alignment: .leading, spacing: 4) {
                            Text("Stabilität: \(Int(prefs.preferences.elevenLabsStability * 100))%")
                            Slider(value: Binding(
                                get: { prefs.preferences.elevenLabsStability },
                                set: { prefs.preferences.elevenLabsStability = $0; prefs.save() }
                            ), in: 0...1, step: 0.05)
                            .accessibilityLabel("Stimm-Stabilität")
                            .accessibilityValue("\(Int(prefs.preferences.elevenLabsStability * 100)) Prozent")
                        }

                        VStack(alignment: .leading, spacing: 4) {
                            Text("Klarheit: \(Int(prefs.preferences.elevenLabsSimilarity * 100))%")
                            Slider(value: Binding(
                                get: { prefs.preferences.elevenLabsSimilarity },
                                set: { prefs.preferences.elevenLabsSimilarity = $0; prefs.save() }
                            ), in: 0...1, step: 0.05)
                            .accessibilityLabel("Stimm-Klarheit (Similarity)")
                            .accessibilityValue("\(Int(prefs.preferences.elevenLabsSimilarity * 100)) Prozent")
                        }
                    }

                    Section("Modus") {
                        Toggle("Echtzeit-Streaming", isOn: Binding(
                            get: { prefs.preferences.elevenLabsStreamingMode },
                            set: { prefs.preferences.elevenLabsStreamingMode = $0; prefs.save() }
                        ))
                        .accessibilityLabel("Echtzeit-Streaming-Modus")
                        .accessibilityHint("Im Streaming-Modus wird Audio direkt während der Synthese gesendet")
                    }

                    if !ttsHistory.isEmpty {
                        Section("Verlauf") {
                            ForEach(ttsHistory.prefix(10), id: \.date) { entry in
                                VStack(alignment: .leading, spacing: 2) {
                                    Text(entry.text)
                                        .lineLimit(2)
                                    Text(entry.date.formatted(date: .omitted, time: .shortened))
                                        .font(.caption2)
                                        .foregroundStyle(.tertiary)
                                }
                                .contentShape(Rectangle())
                                .accessibilityElement(children: .combine)
                                .accessibilityLabel(entry.text)
                                .accessibilityHint("Tippe zum Wiederholen")
                                .onTapGesture {
                                    text = entry.text
                                    TTAccessibility.announce("Text aus Verlauf übernommen")
                                }
                            }
                            if ttsHistory.count > 10 {
                                Button("Weiteren Verlauf anzeigen (\(ttsHistory.count - 10) mehr)") {
                                    showHistory = true
                                }
                                .accessibilityLabel("Kompletten TTS-Verlauf anzeigen")
                            }
                            Button(role: .destructive, action: { ttsHistory.removeAll() }) {
                                Label("Verlauf löschen", systemImage: "trash")
                            }
                            .accessibilityLabel("TTS-Verlauf löschen")
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
                .sheet(isPresented: $showHistory) {
                    TTSHistorySheet(history: ttsHistory) { selected in
                        text = selected
                        showHistory = false
                    }
                }
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
                ttsHistory.insert((text: trimmed, date: Date()), at: 0)
                if ttsHistory.count > 100 { ttsHistory.removeLast() }
                TTAccessibility.announce("Gesprochen")
            } catch {
                lastError = error.localizedDescription
            }
        }
    }
}

struct TTSHistorySheet: View {
    @Environment(\.dismiss) private var dismiss
    let history: [(text: String, date: Date)]
    let onSelect: (String) -> Void

    var body: some View {
        NavigationStack {
            List(history, id: \.date) { entry in
                VStack(alignment: .leading, spacing: 4) {
                    Text(entry.text)
                    Text(entry.date.formatted())
                        .font(.caption)
                        .foregroundStyle(.secondary)
                }
                .contentShape(Rectangle())
                .accessibilityElement(children: .combine)
                .accessibilityLabel(entry.text)
                .accessibilityHint("Tippe zum Auswählen")
                .onTapGesture { onSelect(entry.text) }
            }
            .navigationTitle("TTS-Verlauf")
            .toolbar {
                ToolbarItem(placement: .cancellationAction) {
                    Button("Schließen") { dismiss() }
                }
            }
        }
    }
}
