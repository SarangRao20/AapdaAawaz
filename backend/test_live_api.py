#!/usr/bin/env python3
"""Quick test of live Gnani API integration: Prisma → Evon → Timbre."""
import sys
from pathlib import Path

# Add app to path
sys.path.insert(0, str(Path(__file__).parent))

from app.config import settings
from app.providers.prisma import PrismaSTT
from app.providers.evon import EvonExtractor
from app.providers.timbre import TimbreTTS

def test_prisma():
    """Test Prisma STT with one of our synthetic audio files."""
    print("🎤 Testing Prisma STT...")
    audio_path = Path(__file__).parent / "data" / "audio" / "syn-001.wav"
    
    if not audio_path.exists():
        print(f"   ❌ Audio file not found: {audio_path}")
        return False
    
    try:
        stt = PrismaSTT()
        result = stt.transcribe(audio_path, "audio/wav", "hi")
        print(f"   ✅ Prisma STT successful")
        print(f"      Provider: {result.provider} (mode: {result.mode})")
        print(f"      Language: {result.language_code}")
        print(f"      Transcript: {result.transcript[:100]}...")
        return True
    except Exception as e:
        print(f"   ❌ Prisma failed: {e}")
        return False

def test_evon():
    """Test Evon extraction with a sample transcript."""
    print("\n🧠 Testing Evon extraction...")
    sample_transcript = (
        "Haan, mera naam Ramesh hai, main Khadakwasla se bol raha hoon. "
        "Yahan bahut zyada paani aa gaya hai, kaafi log phaansey hue hain."
    )
    
    try:
        extractor = EvonExtractor()
        print(f"      Endpoint: {extractor.base_url}/chat/completions")
        print(f"      Model: {extractor.model}")
        result = extractor.extract(sample_transcript, language_hint="hi")
        print(f"   ✅ Evon extraction successful")
        print(f"      Provider: {result.provider} (mode: {result.mode})")
        print(f"      Location: {result.location.place if result.location else 'None'}")
        print(f"      Summary: {result.summary[:100] if result.summary else 'None'}...")
        return True
    except Exception as e:
        print(f"   ❌ Evon failed: {type(e).__name__}: {e}")
        import traceback
        print(f"      Details: {traceback.format_exc().split('Traceback')[-1][:200]}")
        return False

def test_timbre():
    """Test Timbre TTS with a sample acknowledgement."""
    print("\n🔊 Testing Timbre TTS...")
    sample_text = "आपकी रिपोर्ट मिल गई है। मदद जल्द आएगी।"
    
    try:
        tts = TimbreTTS()
        print(f"      Endpoint: {tts.base_url}/api/v1/tts/inference")
        print(f"      Model: {settings.timbre_model}")
        result = tts.synthesize(sample_text, "hi")
        print(f"   ✅ Timbre TTS successful")
        print(f"      Provider: {result.provider} (mode: {result.mode})")
        print(f"      Voice: {result.voice}")
        print(f"      Audio size: {len(result.audio)} bytes")
        return True
    except Exception as e:
        print(f"   ❌ Timbre failed: {type(e).__name__}: {e}")
        import traceback
        print(f"      Details: {traceback.format_exc().split('Traceback')[-1][:200]}")
        return False

def main():
    """Run all three tests."""
    print("=" * 70)
    print("Testing Live Gnani API Integration")
    print("=" * 70)
    print(f"API Key configured: {'Yes' if settings.gnani_api_key else 'No'}")
    print(f"STT Provider: {settings.stt_provider}")
    print(f"Extraction Provider: {settings.extraction_provider}")
    print(f"TTS Provider: {settings.tts_provider}")
    print("=" * 70)
    
    results = {
        "Prisma STT": test_prisma(),
        "Evon Extraction": test_evon(),
        "Timbre TTS": test_timbre(),
    }
    
    print("\n" + "=" * 70)
    print("RESULTS")
    print("=" * 70)
    for name, passed in results.items():
        status = "✅ PASS" if passed else "❌ FAIL"
        print(f"{name:20s} {status}")
    
    all_passed = all(results.values())
    print("=" * 70)
    if all_passed:
        print("🎉 All three Gnani models working with live API!")
    else:
        print("⚠️  Some tests failed. Check configuration and API key.")
    print("=" * 70)
    
    return 0 if all_passed else 1

if __name__ == "__main__":
    sys.exit(main())
