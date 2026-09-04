import SwiftUI

struct SettingsView: View {
    @EnvironmentObject var prefs: AppPreferencesStore
    @EnvironmentObject var connection: TTConnectionController

    var body: some View {
        NavigationStack {
            Form {
                Section("Profil") {
                    LabeledContent("Nickname") {
                        TextField("Mein Name", text: $prefs.preferences.nickname)
                            .onChange(of: prefs.preferences.nickname) { _, _ in prefs.save() }
                            .accessibilityLabel("Standard-Nickname")
                    }
                    LabeledContent("Status") {
                        TextField("", text: $prefs.preferences.statusMessage)
                            .onChange(of: prefs.preferences.statusMessage) { _, _ in prefs.save() }
                            .accessibilityLabel("Status-Nachricht")
                    }
                }

                Section("Audio-Voreinstellungen") {
                    Toggle("Push-to-Talk", isOn: $prefs.preferences.pushToTalkEnabled)
                        .onChange(of: prefs.preferences.pushToTalkEnabled) { _, _ in prefs.save() }
                    Toggle("Sprachaktivierung", isOn: $prefs.preferences.voiceActivationEnabled)
                        .onChange(of: prefs.preferences.voiceActivationEnabled) { _, _ in prefs.save() }
                }

                Section("Barrierefreiheit") {
                    Toggle("Ansagen aktiviert", isOn: $prefs.preferences.announcementsEnabled)
                        .onChange(of: prefs.preferences.announcementsEnabled) { _, _ in prefs.save() }
                        .accessibilityLabel("VoiceOver-Ansagen ein- oder ausschalten")
                    Picker("Ansage-Modus", selection: $prefs.preferences.announcementMode) {
                        Text("Vollständig").tag(AnnouncementMode.full)
                        Text("Ruhig").tag(AnnouncementMode.quiet)
                    }
                    .onChange(of: prefs.preferences.announcementMode) { _, _ in prefs.save() }
                    .accessibilityLabel("VoiceOver-Ansage-Modus")
                    Picker("Sound-Theme", selection: $prefs.preferences.soundTheme) {
                        Text("Standard").tag(SoundTheme.default_)
                        Text("Majorly-G").tag(SoundTheme.majorlyG)
                        Text("Kein Sound").tag(SoundTheme.none)
                    }
                    .onChange(of: prefs.preferences.soundTheme) { _, _ in prefs.save() }
                    .accessibilityLabel("Sound-Theme auswählen")
                }

                Section("Verbindung") {
                    Toggle("Auto-Reconnect", isOn: $prefs.preferences.autoReconnect)
                        .onChange(of: prefs.preferences.autoReconnect) { _, _ in prefs.save() }
                    Toggle("Letzten Kanal beitreten", isOn: $prefs.preferences.rejoinLastChannel)
                        .onChange(of: prefs.preferences.rejoinLastChannel) { _, _ in prefs.save() }
                }

                Section("ElevenLabs TTS") {
                    LabeledContent("API-Key") {
                        SecureField("sk-…", text: $prefs.preferences.elevenLabsApiKey)
                            .onChange(of: prefs.preferences.elevenLabsApiKey) { _, _ in prefs.save() }
                            .accessibilityLabel("ElevenLabs API-Schlüssel")
                    }
                }

                Section("Info") {
                    LabeledContent("Version",
                        value: Bundle.main.infoDictionary?["CFBundleShortVersionString"] as? String ?? "–")
                    LabeledContent("SDK", value: "TeamTalk5 xcframework")
                    Link("Quellcode auf GitHub",
                         destination: URL(string: "https://github.com/fla-rion/TeamTalk-VO-Client")!)
                        .accessibilityLabel("Quellcode auf GitHub öffnen")
                }
            }
            .navigationTitle("Einstellungen")
        }
    }
}
