import SwiftUI

struct MediaView: View {
    @EnvironmentObject var connection: TTConnectionController
    @EnvironmentObject var prefs: AppPreferencesStore
    @State private var customURL = ""
    @State private var isStreaming = false

    let presets: [(name: String, url: String)] = [
        ("DLF", "https://st01.sslstream.dlf.de/dlf/01/128/mp3/stream.mp3"),
        ("DLF Kultur", "https://st02.sslstream.dlf.de/dlf/02/128/mp3/stream.mp3"),
        ("WDR 5", "https://wdr-wdr5-live.icecast.wdr.de/wdr/wdr5/live/mp3/128/stream.mp3"),
        ("Bayern 2", "https://streams.br.de/bayern2_2.m3u"),
        ("NDR Info", "https://ndr-ndrinfo-live.cast.addradio.de/ndr/ndrinfo/live/mp3/128/stream.mp3"),
    ]

    var body: some View {
        NavigationStack {
            if connection.state != .loggedIn {
                ContentUnavailableView("Nicht verbunden", systemImage: "radio.slash")
            } else {
                Form {
                    Section("Status") {
                        HStack {
                            Image(systemName: isStreaming ? "dot.radiowaves.left.and.right" : "radio")
                                .foregroundStyle(isStreaming ? .green : .secondary)
                                .accessibilityHidden(true)
                            Text(isStreaming ? "Streaming läuft" : "Nicht aktiv")
                                .accessibilityLabel(isStreaming ? "Streaming läuft" : "Kein Streaming")
                            Spacer()
                            if isStreaming {
                                Button("Stoppen", role: .destructive) { stopStream() }
                                    .accessibilityLabel("Streaming stoppen")
                            }
                        }
                    }
                    Section("Webradio-Voreinstellungen") {
                        ForEach(presets, id: \.url) { preset in
                            Button(action: { startStream(url: preset.url) }) {
                                HStack {
                                    Text(preset.name)
                                    Spacer()
                                    Image(systemName: "play.circle")
                                        .foregroundStyle(.blue)
                                        .accessibilityHidden(true)
                                }
                            }
                            .foregroundStyle(.primary)
                            .accessibilityLabel("\(preset.name) starten")
                            .accessibilityHint("Sendet \(preset.name) in den aktuellen Kanal")
                        }
                    }
                    Section("Eigene URL") {
                        TextField("https://…", text: $customURL)
                            .keyboardType(.URL)
                            .textInputAutocapitalization(.never)
                            .accessibilityLabel("Eigene Stream-URL")
                        Button("Stream starten") { startStream(url: customURL) }
                            .disabled(customURL.isEmpty)
                            .accessibilityLabel("Eigene URL streamen")
                    }
                }
                .navigationTitle("Medien")
            }
        }
    }

    private func startStream(url: String) {
        Task {
            isStreaming = await connection.startMediaStream(url: url)
        }
    }

    private func stopStream() {
        connection.stopMediaStream()
        isStreaming = false
    }
}
