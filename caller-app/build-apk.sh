#!/usr/bin/env bash
# Build a debug APK for the Aapda Awaaz caller app.
# Requires Java 21 and Android SDK (set ANDROID_HOME).
set -e

DIR="$(cd "$(dirname "$0")" && pwd)"

# --- Java 21 ---
if [ -z "$JAVA_HOME" ] || ! "$JAVA_HOME/bin/java" -version 2>&1 | grep -q '"21'; then
  for candidate in /usr/lib/jvm/java-21-openjdk /usr/local/lib/jvm/java-21 "$HOME/.local/share/jvm/java-21"; do
    if [ -x "$candidate/bin/java" ]; then
      export JAVA_HOME="$candidate"
      break
    fi
  done
fi
export PATH="$JAVA_HOME/bin:$PATH"
java -version 2>&1 | head -1

# --- Android SDK ---
if [ -z "$ANDROID_HOME" ]; then
  echo "Set ANDROID_HOME to your Android SDK path." >&2
  exit 1
fi

# --- Build web assets ---
echo "Building web assets..."
cd "$DIR"
npm run build

# --- Sync to Android ---
npx cap sync android

# --- Gradle assembleDebug ---
echo "Building APK..."
cd "$DIR/android"
./gradlew assembleDebug

APK="$DIR/android/app/build/outputs/apk/debug/app-debug.apk"
DEST="$DIR/../AapdaAwaaz-caller.apk"
cp "$APK" "$DEST"
echo ""
echo "✓  APK ready: $DEST  ($(du -h "$DEST" | cut -f1))"
