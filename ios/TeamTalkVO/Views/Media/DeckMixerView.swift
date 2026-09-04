import SwiftUI
import AVFoundation

@MainActor
class DeckMixerController: ObservableObject {
    @Published var deckAName: String = "—"
    @Published var deckBName: String = "—"
    @Published var deckAPlaying: Bool = false
    @Published var deckBPlaying: Bool = false
    @Published var deckAVolume: Float = 1.0
    @Published var deckBVolume: Float = 1.0
    @Published var crossfadeProgress: Double = 0.0
    @Published var activeDeck: Int = 0

    private var playerA: AVAudioPlayer?
    private var playerB: AVAudioPlayer?
    private var crossfadeTimer: Timer?
    private let crossfadeDuration: Double = 2.0
    private let crossfadeSteps: Int = 20

    func loadDeck(_ deck: Int, url: URL) {
        do {
            if deck == 1 {
                playerA = try AVAudioPlayer(contentsOf: url)
                playerA?.prepareToPlay()
                deckAName = url.lastPathComponent
            } else {
                playerB = try AVAudioPlayer(contentsOf: url)
                playerB?.prepareToPlay()
                deckBName = url.lastPathComponent
            }
        } catch { print("Deck \(deck) Ladefehler: \(error)") }
    }

    func play(deck: Int) {
        let fromPlayer = deck == 1 ? playerB : playerA
        let toPlayer   = deck == 1 ? playerA : playerB
        crossfadeTimer?.invalidate()
        toPlayer?.volume = 0
        toPlayer?.play()
        if deck == 1 { deckAPlaying = true } else { deckBPlaying = true }
        activeDeck = deck
        var step = 0
        crossfadeTimer = Timer.scheduledTimer(
            withTimeInterval: crossfadeDuration / Double(crossfadeSteps),
            repeats: true
        ) { [weak self] t in
            guard let self else { t.invalidate(); return }
            step += 1
            let ratio = Float(step) / Float(self.crossfadeSteps)
            Task { @MainActor in
                toPlayer?.volume = ratio * (deck == 1 ? self.deckAVolume : self.deckBVolume)
                fromPlayer?.volume = (1 - ratio) * (deck == 1 ? self.deckBVolume : self.deckAVolume)
                self.crossfadeProgress = Double(ratio)
                if step >= self.crossfadeSteps {
                    t.invalidate()
                    fromPlayer?.stop()
                    if deck == 1 { self.deckBPlaying = false } else { self.deckAPlaying = false }
                    self.crossfadeProgress = 0
                }
            }
        }
    }

    func stop(deck: Int) {
        if deck == 1 { playerA?.stop(); deckAPlaying = false }
        else          { playerB?.stop(); deckBPlaying = false }
        if activeDeck == deck { activeDeck = 0 }
    }

    func setVolume(deck: Int, volume: Float) {
        if deck == 1 { deckAVolume = volume; if deckAPlaying { playerA?.volume = volume } }
        else          { deckBVolume = volume; if deckBPlaying { playerB?.volume = volume } }
    }
}

struct DeckMixerView: View {
    @StateObject private var mixer = DeckMixerController()
    @State private var pickingDeck: Int? = nil
    @EnvironmentObject var connection: TTConnectionController

    var body: some View {
        NavigationStack {
            Form {
                if mixer.crossfadeProgress > 0 {
                    Section {
                        VStack(alignment: .leading, spacing: 4) {
                            Text("Crossfade läuft…")
                                .font(.caption)
                                .foregroundStyle(.secondary)
                            ProgressView(value: mixer.crossfadeProgress)
                                .accessibilityLabel("Crossfade-Fortschritt \(Int(mixer.crossfadeProgress * 100)) Prozent")
                        }
                    }
                }
                deckSection(deck: 1, name: mixer.deckAName, playing: mixer.deckAPlaying, volume: $mixer.deckAVolume)
                deckSection(deck: 2, name: mixer.deckBName, playing: mixer.deckBPlaying, volume: $mixer.deckBVolume)
            }
            .navigationTitle("Deck-Mischer")
            .fileImporter(
                isPresented: Binding(get: { pickingDeck != nil }, set: { if !$0 { pickingDeck = nil } }),
                allowedContentTypes: [.audio]
            ) { result in
                guard let deck = pickingDeck, case .success(let url) = result else { return }
                _ = url.startAccessingSecurityScopedResource()
                mixer.loadDeck(deck, url: url)
                pickingDeck = nil
            }
        }
    }

    @ViewBuilder
    private func deckSection(deck: Int, name: String, playing: Bool, volume: Binding<Float>) -> some View {
        let label = deck == 1 ? "A" : "B"
        Section("Deck \(label)") {
            HStack {
                Image(systemName: playing ? "play.circle.fill" : "stop.circle")
                    .foregroundStyle(playing ? .green : .secondary)
                    .font(.title2)
                    .accessibilityHidden(true)
                VStack(alignment: .leading) {
                    Text(name).lineLimit(1)
                    Text(playing ? "Spielt" : "Gestoppt")
                        .font(.caption).foregroundStyle(.secondary)
                }
                Spacer()
                Button("Laden") { pickingDeck = deck }
                    .accessibilityLabel("Audiodatei für Deck \(label) laden")
            }
            .accessibilityElement(children: .combine)
            .accessibilityLabel("Deck \(label): \(name), \(playing ? "spielt" : "gestoppt")")

            HStack(spacing: 16) {
                Button(action: { mixer.play(deck: deck) }) {
                    Label("Abspielen", systemImage: "play.fill").frame(maxWidth: .infinity)
                }
                .buttonStyle(.borderedProminent)
                .disabled(name == "—")
                .accessibilityLabel("Deck \(label) abspielen mit Crossfade")

                Button(action: { mixer.stop(deck: deck) }) {
                    Label("Stopp", systemImage: "stop.fill").frame(maxWidth: .infinity)
                }
                .buttonStyle(.bordered)
                .disabled(!playing)
                .accessibilityLabel("Deck \(label) stoppen")
            }

            VStack(alignment: .leading, spacing: 2) {
                Text("Lautstärke: \(Int(volume.wrappedValue * 100))%").font(.caption)
                Slider(value: volume, in: 0...1, step: 0.05) { _ in
                    mixer.setVolume(deck: deck, volume: volume.wrappedValue)
                }
                .accessibilityLabel("Lautstärke Deck \(label)")
                .accessibilityValue("\(Int(volume.wrappedValue * 100)) Prozent")
            }
        }
    }
}
