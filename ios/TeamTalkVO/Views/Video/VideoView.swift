import SwiftUI

struct VideoView: View {
    @EnvironmentObject var connection: TTConnectionController
    @State private var myVideoEnabled = false

    var body: some View {
        NavigationStack {
            if connection.state != .loggedIn {
                ContentUnavailableView("Nicht verbunden", systemImage: "video.slash")
            } else {
                ScrollView {
                    LazyVGrid(columns: [GridItem(.adaptive(minimum: 160))], spacing: 12) {
                        VideoTileView(nickname: "Ich", isActive: myVideoEnabled, isOwn: true)
                            .accessibilityLabel("Eigenes Video, \(myVideoEnabled ? "aktiv" : "inaktiv")")

                        ForEach(connection.users.filter { $0.channelId == connection.currentChannelId }) { user in
                            VideoTileView(nickname: user.nickname, isActive: false, isOwn: false)
                                .accessibilityLabel("Video von \(user.nickname), inaktiv")
                        }
                    }
                    .padding()
                }
                .navigationTitle("Video")
                .toolbar {
                    ToolbarItem(placement: .primaryAction) {
                        Button(action: { myVideoEnabled.toggle() }) {
                            Image(systemName: myVideoEnabled ? "video.fill" : "video.slash")
                                .foregroundStyle(myVideoEnabled ? .green : .secondary)
                        }
                        .accessibilityLabel(myVideoEnabled ? "Eigenes Video deaktivieren" : "Eigenes Video aktivieren")
                    }
                }
            }
        }
    }
}

struct VideoTileView: View {
    let nickname: String
    let isActive: Bool
    let isOwn: Bool

    var body: some View {
        VStack(spacing: 8) {
            ZStack {
                RoundedRectangle(cornerRadius: 12)
                    .fill(Color(.systemGray5))
                    .aspectRatio(16/9, contentMode: .fit)
                if isActive {
                    Image(systemName: "video.fill")
                        .font(.largeTitle)
                        .foregroundStyle(.white)
                } else {
                    VStack(spacing: 4) {
                        Image(systemName: isOwn ? "person.fill" : "video.slash")
                            .font(.title)
                            .foregroundStyle(.secondary)
                        Text("Kein Video")
                            .font(.caption2)
                            .foregroundStyle(.tertiary)
                    }
                }
            }
            Text(nickname)
                .font(.caption)
                .fontWeight(isOwn ? .semibold : .regular)
                .lineLimit(1)
        }
    }
}
