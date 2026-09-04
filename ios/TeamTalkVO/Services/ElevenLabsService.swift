import Foundation
import AVFoundation

@MainActor
class ElevenLabsService: ObservableObject {
    @Published var voices: [ElevenLabsVoice] = []
    @Published var isLoading = false
    @Published var lastError: String? = nil

    private var audioPlayer: AVAudioPlayer?

    func fetchVoices(apiKey: String) async {
        guard !apiKey.isEmpty else { return }
        isLoading = true
        defer { isLoading = false }
        do {
            var request = URLRequest(url: URL(string: "https://api.elevenlabs.io/v1/voices")!)
            request.setValue(apiKey, forHTTPHeaderField: "xi-api-key")
            let (data, _) = try await URLSession.shared.data(for: request)
            let decoded = try JSONDecoder().decode(ElevenLabsVoicesResponse.self, from: data)
            voices = decoded.voices
        } catch {
            lastError = error.localizedDescription
        }
    }

    /// Synthetisiert Text und gibt PCM-Daten zurück für TeamTalk-Streaming.
    func synthesize(text: String, voiceId: String, apiKey: String) async throws -> Data {
        var request = URLRequest(url: URL(string: "https://api.elevenlabs.io/v1/text-to-speech/\(voiceId)")!)
        request.httpMethod = "POST"
        request.setValue(apiKey, forHTTPHeaderField: "xi-api-key")
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        let body = ["text": text, "model_id": "eleven_multilingual_v2",
                    "output_format": "pcm_16000"]
        request.httpBody = try JSONSerialization.data(withJSONObject: body)
        let (data, response) = try await URLSession.shared.data(for: request)
        guard let http = response as? HTTPURLResponse, http.statusCode == 200 else {
            throw NSError(domain: "ElevenLabs", code: -1,
                          userInfo: [NSLocalizedDescriptionKey: "Synthesis failed"])
        }
        return data
    }
}
