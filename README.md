# Kindle Butch Gen (Ukrainization & Audiobook Generation)

A tool suite to automate EPUB/Markdown translation and generate Ukrainian audiobooks using high-quality neural TTS models.

## TTS Engine, Voice Quality & License Details

This project uses the Piper text-to-speech synthesis engine to generate Ukrainian audio. The following voice models are supported:

1. **uk_UA-lada-x_low**
   - **Quality**: `x_low`
   - **Dataset**: Lada dataset (Apache 2.0 License).
   - **License**: Apache 2.0.
   
2. **uk_UA-ukrainian_tts-medium**
   - **Quality**: `medium`
   - **Dataset**: OHF voice datasets (CC0 Public Domain).
   - **License**: CC0.

- **Piper Engine**: Licensed under the **MIT License**.

### How to Configure Voice in `config.json`

You can specify the desired voice and quality in your book's `config.json` file. For example, to use the high-quality CC0 medium voice, configure it as follows:

```json
{
  "tts_voice": "ukrainian_tts",
  "tts_voice_quality": "medium"
}
```

For the low-complexity Lada voice, use:

```json
{
  "tts_voice": "lada",
  "tts_voice_quality": "x_low"
}
```

