#!/usr/bin/env python3
"""Test audio preprocessing: spectral gate + RMS normalization."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from app.services.audio_prep import preprocess_audio
from app.config import settings

def test_preprocessing():
    """Test preprocessing on one of our synthetic audio files."""
    print("=" * 70)
    print("Testing Audio Preprocessing (Noise Canceller Award)")
    print("=" * 70)
    print(f"AUDIO_PREPROCESSING enabled: {settings.audio_preprocessing_enabled}")
    print("=" * 70)
    
    # Test with one of our synthetic files
    audio_path = Path(__file__).parent / "data" / "audio" / "syn-001.wav"
    
    if not audio_path.exists():
        print(f"❌ Audio file not found: {audio_path}")
        return False
    
    print(f"\n📂 Input: {audio_path.name}")
    print(f"   Size: {audio_path.stat().st_size:,} bytes")
    
    try:
        # Preprocess
        print("\n🔄 Applying preprocessing...")
        print("   - Converting stereo → mono (if needed)")
        print("   - Spectral noise gate (noisereduce)")
        print("   - RMS loudness normalization to -20 dBFS")
        
        output_path = preprocess_audio(audio_path)
        
        if output_path == audio_path:
            print("\n⚠️  Preprocessing returned original file (may have failed or skipped)")
            return False
        
        print(f"\n✅ Preprocessing successful!")
        print(f"📂 Output: {output_path.name}")
        print(f"   Size: {output_path.stat().st_size:,} bytes")
        
        # Show file locations
        print(f"\n📁 Files in {audio_path.parent}:")
        for f in sorted(audio_path.parent.glob("syn-001*")):
            print(f"   {f.name} ({f.stat().st_size:,} bytes)")
        
        print("\n" + "=" * 70)
        print("✅ Audio preprocessing test PASSED")
        print("=" * 70)
        print("\nNext steps:")
        print("1. Upload audio via UI to test with Prisma STT")
        print("2. Compare transcription accuracy with/without preprocessing")
        print("3. Document results in README.md")
        print("\nFor Noise Canceller Award:")
        print("- Test with background noise added to audio")
        print("- Show WER improvement (before/after preprocessing)")
        return True
        
    except Exception as e:
        print(f"\n❌ Preprocessing failed: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    success = test_preprocessing()
    sys.exit(0 if success else 1)
