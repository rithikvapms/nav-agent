import json
from typing import Dict, List


class ScreenChunker:

    def chunk_screen(self, screen: Dict) -> List[Dict]:
        chunks = []

        section_mapping = {
            "basic": [
                "screen_id",
                "route",
                "title",
                "description",
                "module",
                "workflow",
                "business_capability",
                "intents",
                "permissions",
                "entry_points",
                "exit_points"
            ],
            "dependencies": ["dependencies"],
            "form": ["form"],
            "navigation": ["navigation"],
            "voice": ["voice"],
            "ai": ["ai"],
            "telemetry": ["telemetry"],
            "metadata": ["metadata"]
        }

        for chunk_type, fields in section_mapping.items():

            content = {}

            for field in fields:
                if field in screen:
                    content[field] = screen[field]

            chunks.append({
                "screen_id": screen["screen_id"],
                "chunk_id": f'{screen["screen_id"]}_{chunk_type}',
                "chunk_type": chunk_type,
                "title": screen["title"],
                "module": screen["module"],
                "content": json.dumps(content, ensure_ascii=False),
                "metadata": {
                    "route": screen["route"],
                    "version": screen["metadata"]["version"]
                }
            })

        return chunks