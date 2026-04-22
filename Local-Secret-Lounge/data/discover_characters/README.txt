Discover character packs live in data/discover_characters/.

Create one folder per character.
Each folder should contain:
- one .py or .json card file
- one image file referenced by avatar/image, or an image with the same basename as the card file

Example:
  data/discover_characters/elara_smith/elara_smith.py
  data/discover_characters/elara_smith/elara_smith.png

Recommended .py format:
CHARACTER = {
    "id": "discover_elara_smith",
    "slug": "elara_smith",
    "name": "Elara Smith",
    "role": "Sorceress",
    "story_role": "Supportive and nurturing sorceress",
    "avatar": "elara_smith.png",
    "identity": {
        "public_summary": "Short description shown in Discover Characters."
    },
    "voice": {
        "tone": "Warm and calm"
    },
    "tags": ["fantasy", "magic"]
}
