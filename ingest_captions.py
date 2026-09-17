import json
from search import add_chunk

with open(r"D:\FactoryKA\all_captions.json", "r", encoding="utf-8") as f:
    captions = json.load(f)

count = 0
for item in captions:
    if item['caption'] == "CAPTION_FAILED":
        continue

    chunk_id = f"img_{item['source_file']}_{item['image_path'].split(chr(92))[-1]}"
    try:
        add_chunk(
            chunk_id=chunk_id,
            text=item['caption'],
            metadata={
                "source_file": item['source_file'],
                "page_number": item.get('page_number', 0),
                "chunk_type": "picture_caption",
                "image_path": item['image_path']
            }
        )
        count += 1
    except Exception:
        pass

print(f"Added {count} picture captions to the search database")