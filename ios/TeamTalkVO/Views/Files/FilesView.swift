import SwiftUI
import UniformTypeIdentifiers

struct FilesView: View {
    @EnvironmentObject var connection: TTConnectionController
    @State private var downloadProgress: [Int: Double] = [:]
    @State private var downloadedFiles: [Int: URL] = [:]
    @State private var showFilePicker = false
    @State private var transferLog: [(String, Date)] = []
    @State private var isUploading = false

    var body: some View {
        NavigationStack {
            if connection.state != .loggedIn {
                ContentUnavailableView("Nicht verbunden", systemImage: "folder.badge.minus")
            } else {
                List {
                    if !transferLog.isEmpty {
                        Section("Letzte Transfers") {
                            ForEach(transferLog, id: \.1) { entry in
                                Label(entry.0, systemImage: "checkmark.circle.fill")
                                    .font(.caption)
                                    .foregroundStyle(.secondary)
                                    .accessibilityLabel(entry.0)
                            }
                        }
                    }

                    Section("Dateien im Kanal") {
                        if connection.remoteFiles.isEmpty {
                            Text("Keine Dateien vorhanden")
                                .foregroundStyle(.secondary)
                                .accessibilityLabel("Keine Dateien im aktuellen Kanal")
                        } else {
                            ForEach(connection.remoteFiles) { file in
                                FileRowView(
                                    file: file,
                                    progress: downloadProgress[file.id],
                                    isDownloaded: downloadedFiles[file.id] != nil
                                ) {
                                    startDownload(file: file)
                                }
                                .swipeActions(edge: .trailing) {
                                    Button(role: .destructive) {
                                        Task { await connection.deleteFile(fileId: file.id) }
                                    } label: {
                                        Label("Löschen", systemImage: "trash")
                                    }
                                }
                            }
                        }
                    }
                }
                .navigationTitle("Dateien")
                .toolbar {
                    ToolbarItem(placement: .primaryAction) {
                        Button(action: { showFilePicker = true }) {
                            Label("Hochladen", systemImage: isUploading ? "arrow.up.circle" : "arrow.up.circle.fill")
                        }
                        .disabled(isUploading)
                        .accessibilityLabel("Datei hochladen")
                    }
                    ToolbarItem(placement: .secondaryAction) {
                        Button(action: { Task { await connection.refreshFileList() } }) {
                            Label("Aktualisieren", systemImage: "arrow.clockwise")
                        }
                        .accessibilityLabel("Dateiliste aktualisieren")
                    }
                }
                .fileImporter(
                    isPresented: $showFilePicker,
                    allowedContentTypes: [.data, .audio, .text, .pdf, .image],
                    allowsMultipleSelection: false
                ) { result in
                    handleFileImport(result: result)
                }
                .onAppear {
                    Task { await connection.refreshFileList() }
                }
            }
        }
    }

    private func startDownload(file: RemoteFile) {
        guard downloadProgress[file.id] == nil else { return }
        downloadProgress[file.id] = 0.0

        let dest = FileManager.default.temporaryDirectory.appendingPathComponent(file.name)

        Task {
            do {
                try await connection.downloadFile(file, to: dest) { p in
                    Task { @MainActor in downloadProgress[file.id] = p }
                }
                downloadedFiles[file.id] = dest
                downloadProgress.removeValue(forKey: file.id)
                let msg = "'\(file.name)' heruntergeladen"
                transferLog.insert((msg, Date()), at: 0)
                if transferLog.count > 20 { transferLog.removeLast() }
                TTAccessibility.announce(msg)
            } catch {
                downloadProgress.removeValue(forKey: file.id)
            }
        }
    }

    private func handleFileImport(result: Result<[URL], Error>) {
        guard case .success(let urls) = result, let url = urls.first else { return }
        isUploading = true
        Task {
            defer { isUploading = false }
            // TT_DoSendFile stub
            try? await Task.sleep(nanoseconds: 500_000_000)
            let msg = "'\(url.lastPathComponent)' hochgeladen"
            transferLog.insert((msg, Date()), at: 0)
            TTAccessibility.announce(msg)
            await connection.refreshFileList()
        }
    }
}

struct FileRowView: View {
    let file: RemoteFile
    let progress: Double?
    let isDownloaded: Bool
    let onDownload: () -> Void

    var body: some View {
        HStack(spacing: 12) {
            Image(systemName: iconName(for: file.name))
                .font(.title3)
                .foregroundStyle(.blue)
                .frame(width: 32)
                .accessibilityHidden(true)

            VStack(alignment: .leading, spacing: 2) {
                Text(file.name)
                    .font(.headline)
                    .lineLimit(1)
                HStack {
                    Text(file.sizeFormatted)
                    Text("·")
                    Text(file.owner)
                }
                .font(.caption)
                .foregroundStyle(.secondary)

                if let p = progress {
                    ProgressView(value: p)
                        .progressViewStyle(.linear)
                        .accessibilityLabel("Download: \(Int(p * 100)) Prozent")
                }
            }

            Spacer()

            if progress != nil {
                ProgressView()
                    .accessibilityLabel("Wird heruntergeladen")
            } else if isDownloaded {
                Image(systemName: "checkmark.circle.fill")
                    .foregroundStyle(.green)
                    .accessibilityLabel("Heruntergeladen")
            } else {
                Button(action: onDownload) {
                    Image(systemName: "arrow.down.circle")
                        .font(.title3)
                }
                .buttonStyle(.borderless)
                .accessibilityLabel("'\(file.name)' herunterladen")
            }
        }
        .contentShape(Rectangle())
        .accessibilityElement(children: .combine)
        .accessibilityLabel("\(file.name), \(file.sizeFormatted), von \(file.owner)\(isDownloaded ? ", heruntergeladen" : "")")
        .accessibilityHint(isDownloaded ? "" : "Tippe Download-Taste zum Herunterladen")
    }

    private func iconName(for filename: String) -> String {
        let ext = (filename as NSString).pathExtension.lowercased()
        switch ext {
        case "mp3", "wav", "ogg", "flac", "aac", "m4a": return "music.note"
        case "mp4", "mkv", "avi", "mov": return "film"
        case "pdf": return "doc.fill"
        case "jpg", "jpeg", "png", "gif", "webp": return "photo"
        case "zip", "tar", "gz", "7z": return "archivebox"
        case "txt", "md": return "doc.text"
        default: return "doc"
        }
    }
}
