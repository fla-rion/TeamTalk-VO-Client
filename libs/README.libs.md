# Bibliotheken (libs/)

Dieses Verzeichnis enthält native Bibliotheken, die nicht ins Git-Repository
eingecheckt werden (Lizenzgründe oder fehlende Android-Binaries).

## TeamTalk5.aar (Android SDK)

### Woher bekomme ich das AAR?

**Option A – Fertiges AAR aus dem BearWare-Download:**

1. Gehe auf die offizielle BearWare SDK-Downloadseite:
   https://bearware.dk/teamtalksdk

2. Wähle das **TeamTalk 5 SDK** fuer **Android**.

3. Entpacke das heruntergeladene Archiv.

4. Das AAR liegt typischerweise unter:
   `TeamTalk5SDK/Library/TeamTalk_DLL/TeamTalk5.aar`

5. Kopiere `TeamTalk5.aar` in dieses Verzeichnis (`libs/TeamTalk5.aar`).

**Option B – AAR aus vorhandenen Repo-Dateien selbst bauen:**

Das Repo enthaelt bereits das Java-Archiv unter:
`third_party/teamtalk/tt5sdk_v5.19a_macos_universal/Library/TeamTalkJNI/libs/TeamTalk5.jar`

Fuer Android werden zusaetzlich die JNI-Shared-Libraries (`.so`) benoetigt,
die fuer jede Android-Architektur separat heruntergeladen werden muessen
(armeabi-v7a, arm64-v8a, x86, x86_64). Diese `.so`-Dateien werden zusammen
mit dem JAR zu einem AAR verpackt.

Kurzanleitung:
```bash
mkdir -p aar_build/jni/armeabi-v7a aar_build/jni/arm64-v8a
# .so-Dateien aus dem Android-SDK-Download hier ablegen
cp /pfad/zum/sdk/libs/armeabi-v7a/libTeamTalk5-jni.so aar_build/jni/armeabi-v7a/
cp /pfad/zum/sdk/libs/arm64-v8a/libTeamTalk5-jni.so  aar_build/jni/arm64-v8a/
cp third_party/teamtalk/tt5sdk_v5.19a_macos_universal/Library/TeamTalkJNI/libs/TeamTalk5.jar aar_build/classes.jar
cd aar_build && zip -r ../libs/TeamTalk5.aar . && cd ..
```

### Warum ist das AAR nicht im Repo?

Das BearWare TeamTalk SDK steht unter einer proprietaeren Lizenz und darf
nicht ohne Zustimmung von BearWare weitergegeben werden. Die Android-JNI-
Shared-Libraries sind zudem nicht im Repo enthalten (nur macOS-Dylib).
Jeder Entwickler muss das SDK selbst herunterladen und der Lizenz zustimmen.

### Verwendung durch Briefcase

Die Datei wird ueber `support_libs` in `pyproject.toml` eingebunden:

```toml
[tool.briefcase.app.teamtalk-vo.android]
support_libs = ["libs/TeamTalk5.aar"]
```

Briefcase kopiert das AAR beim Build in das Android-Projektverzeichnis und
bindet es als lokale Maven-Abhaengigkeit ein.
