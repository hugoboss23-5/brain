"""
RECURSIVE MEMORY SYSTEM (RLM-style)
===================================
Opus remembers EVERYTHING. Every conversation, every fact, every preference.

Inspired by DeepMind's RLM - eliminates the core limitation of AI memory.

Structure:
- conversations/     → Full conversation archives
- knowledge/         → Extracted facts, learnings, entities
- embeddings/        → Semantic search index (future)
- memory_index.json  → Master index of all memories
"""

import json
import os
import hashlib
from datetime import datetime
from typing import List, Dict, Optional
import re

MEMORY_ROOT = "system/memory"
CONVERSATIONS_DIR = f"{MEMORY_ROOT}/conversations"
KNOWLEDGE_DIR = f"{MEMORY_ROOT}/knowledge"
INDEX_FILE = f"{MEMORY_ROOT}/memory_index.json"

class RecursiveMemory:
    """
    Opus's long-term memory system.
    Remembers everything, extracts knowledge, retrieves relevant context.
    """

    def __init__(self):
        self._ensure_dirs()
        self.index = self._load_index()

    def _ensure_dirs(self):
        """Create memory directories if they don't exist"""
        for dir_path in [MEMORY_ROOT, CONVERSATIONS_DIR, KNOWLEDGE_DIR]:
            os.makedirs(dir_path, exist_ok=True)

    def _load_index(self) -> dict:
        """Load the master memory index"""
        if os.path.exists(INDEX_FILE):
            try:
                with open(INDEX_FILE, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except:
                pass
        return {
            "created": datetime.now().isoformat(),
            "total_conversations": 0,
            "total_facts": 0,
            "total_entities": 0,
            "conversations": [],
            "facts": [],
            "entities": {},
            "user_model": {
                "name": "Hugo",
                "preferences": [],
                "communication_style": [],
                "interests": [],
                "projects": []
            }
        }

    def _save_index(self):
        """Save the master memory index"""
        self.index["last_updated"] = datetime.now().isoformat()
        with open(INDEX_FILE, 'w', encoding='utf-8') as f:
            json.dump(self.index, f, indent=2)

    def archive_conversation(self, messages: List[Dict], session_id: int) -> str:
        """
        Archive a full conversation for permanent memory.
        Returns the archive ID.
        """
        timestamp = datetime.now()
        archive_id = f"conv_{timestamp.strftime('%Y%m%d_%H%M%S')}_{session_id}"

        # Create conversation archive
        archive = {
            "id": archive_id,
            "session_id": session_id,
            "timestamp": timestamp.isoformat(),
            "message_count": len(messages),
            "messages": messages,
            "summary": self._summarize_conversation(messages),
            "extracted_at": timestamp.isoformat()
        }

        # Save to file
        archive_path = f"{CONVERSATIONS_DIR}/{archive_id}.json"
        with open(archive_path, 'w', encoding='utf-8') as f:
            json.dump(archive, f, indent=2)

        # Update index
        self.index["conversations"].append({
            "id": archive_id,
            "timestamp": timestamp.isoformat(),
            "message_count": len(messages),
            "summary": archive["summary"][:200]
        })
        self.index["total_conversations"] += 1

        # Keep only last 100 conversation references in index (files are kept forever)
        if len(self.index["conversations"]) > 100:
            self.index["conversations"] = self.index["conversations"][-100:]

        self._save_index()
        return archive_id

    def _summarize_conversation(self, messages: List[Dict]) -> str:
        """Create a brief summary of the conversation"""
        topics = []
        for msg in messages:
            content = msg.get('content', '')
            if isinstance(content, str) and msg.get('role') == 'user':
                # Extract first sentence or first 100 chars
                first_line = content.split('\n')[0][:100]
                if first_line:
                    topics.append(first_line)

        if topics:
            return f"Topics: {'; '.join(topics[:5])}"
        return "General conversation"

    def extract_knowledge(self, user_message: str, assistant_response: str) -> Dict:
        """
        Extract facts, entities, and learnings from an exchange.
        This is the "learning" part of RLM.
        """
        extracted = {
            "timestamp": datetime.now().isoformat(),
            "facts": [],
            "entities": [],
            "user_preferences": [],
            "projects_mentioned": [],
            "technical_concepts": []
        }

        combined = f"{user_message} {assistant_response}".lower()

        # Extract user preferences (things Hugo likes/wants)
        pref_patterns = [
            r"i (?:like|love|prefer|want|need) (.+?)(?:\.|,|$)",
            r"(?:make it|i want it) (.+?)(?:\.|,|$)",
            r"my (?:favorite|preferred) (.+?) is (.+?)(?:\.|,|$)"
        ]
        for pattern in pref_patterns:
            matches = re.findall(pattern, user_message.lower())
            for match in matches:
                pref = match if isinstance(match, str) else ' '.join(match)
                if len(pref) > 3 and len(pref) < 100:
                    extracted["user_preferences"].append(pref.strip())

        # Extract project names (capitalized phrases, file paths, tech terms)
        project_patterns = [
            r'\b(brain|opus|eai|deepseek|tinyllama|swarm|pluribus)\b',
            r'(\w+\.py|\w+\.js|\w+\.html)',
            r'(?:working on|building|creating) (?:a |the )?([A-Za-z][A-Za-z0-9_\- ]{2,30})'
        ]
        for pattern in project_patterns:
            matches = re.findall(pattern, combined, re.IGNORECASE)
            for match in matches:
                if match and len(match) > 2:
                    extracted["projects_mentioned"].append(match)

        # Extract technical concepts
        tech_patterns = [
            r'\b(api|server|database|model|neural|ai|ml|llm|token|embedding|vector|memory|cache)\b',
            r'\b(python|javascript|html|css|json|react|flask|fastapi)\b',
            r'\b(ollama|anthropic|openai|claude|gpt|llama|deepseek)\b'
        ]
        for pattern in tech_patterns:
            matches = re.findall(pattern, combined, re.IGNORECASE)
            extracted["technical_concepts"].extend(matches)

        # Extract facts (statements about how things work)
        if "is a" in combined or "is the" in combined or "means" in combined:
            # Simple fact extraction - could be enhanced with NLP
            sentences = combined.split('.')
            for sentence in sentences:
                if any(marker in sentence for marker in ["is a", "is the", "means", "works by"]):
                    if len(sentence) > 10 and len(sentence) < 200:
                        extracted["facts"].append(sentence.strip())

        # Store extracted knowledge
        self._store_knowledge(extracted)

        return extracted

    def _store_knowledge(self, extracted: Dict):
        """Store extracted knowledge in the knowledge base"""
        timestamp = datetime.now().strftime('%Y%m%d')

        # Update user model
        if extracted["user_preferences"]:
            for pref in extracted["user_preferences"]:
                if pref not in self.index["user_model"]["preferences"]:
                    self.index["user_model"]["preferences"].append(pref)
            # Keep last 50 preferences
            self.index["user_model"]["preferences"] = self.index["user_model"]["preferences"][-50:]

        # Update projects
        if extracted["projects_mentioned"]:
            for proj in extracted["projects_mentioned"]:
                proj_lower = proj.lower()
                if proj_lower not in [p.lower() for p in self.index["user_model"]["projects"]]:
                    self.index["user_model"]["projects"].append(proj)
            self.index["user_model"]["projects"] = self.index["user_model"]["projects"][-30:]

        # Store facts
        if extracted["facts"]:
            for fact in extracted["facts"]:
                fact_entry = {
                    "content": fact,
                    "timestamp": extracted["timestamp"],
                    "hash": hashlib.md5(fact.encode()).hexdigest()[:8]
                }
                # Avoid duplicates
                if not any(f["hash"] == fact_entry["hash"] for f in self.index["facts"]):
                    self.index["facts"].append(fact_entry)
                    self.index["total_facts"] += 1

            # Keep last 200 facts
            self.index["facts"] = self.index["facts"][-200:]

        # Update entities (technical concepts seen)
        for concept in extracted["technical_concepts"]:
            concept_lower = concept.lower()
            if concept_lower not in self.index["entities"]:
                self.index["entities"][concept_lower] = {"count": 0, "first_seen": extracted["timestamp"]}
            self.index["entities"][concept_lower]["count"] += 1
            self.index["entities"][concept_lower]["last_seen"] = extracted["timestamp"]
            self.index["total_entities"] = len(self.index["entities"])

        self._save_index()

    def remember_fact(self, fact_type: str, content: str):
        """Explicitly remember a fact (called by Opus via remember tool)"""
        fact_entry = {
            "content": content,
            "type": fact_type,
            "timestamp": datetime.now().isoformat(),
            "hash": hashlib.md5(content.encode()).hexdigest()[:8],
            "explicit": True  # Marked as explicitly remembered
        }

        if not any(f["hash"] == fact_entry["hash"] for f in self.index["facts"]):
            self.index["facts"].append(fact_entry)
            self.index["total_facts"] += 1
            self._save_index()

    def get_relevant_memories(self, query: str, limit: int = 10) -> Dict:
        """
        Retrieve memories relevant to the current query.
        This is loaded into Opus's context before responding.
        """
        query_lower = query.lower()
        query_words = set(query_lower.split())

        relevant = {
            "user_model": self.index["user_model"],
            "recent_facts": [],
            "relevant_facts": [],
            "recent_conversations": [],
            "stats": {
                "total_conversations": self.index["total_conversations"],
                "total_facts": self.index["total_facts"],
                "total_entities": self.index["total_entities"]
            }
        }

        # Get recent facts (last 10)
        relevant["recent_facts"] = self.index["facts"][-10:]

        # Find facts relevant to query (simple keyword matching)
        for fact in self.index["facts"]:
            fact_words = set(fact["content"].lower().split())
            overlap = query_words & fact_words
            if len(overlap) >= 2:  # At least 2 words in common
                relevant["relevant_facts"].append(fact)
                if len(relevant["relevant_facts"]) >= limit:
                    break

        # Get recent conversation summaries
        relevant["recent_conversations"] = self.index["conversations"][-5:]

        return relevant

    def get_memory_context_string(self, query: str) -> str:
        """
        Generate a context string to inject into Opus's system prompt.
        This gives Opus access to long-term memories.
        """
        memories = self.get_relevant_memories(query)

        context_parts = []

        # User model
        user = memories["user_model"]
        if user["preferences"] or user["projects"]:
            context_parts.append("## WHAT I REMEMBER ABOUT HUGO:")
            if user["preferences"]:
                context_parts.append(f"Preferences: {', '.join(user['preferences'][-5:])}")
            if user["projects"]:
                context_parts.append(f"Projects: {', '.join(user['projects'][-5:])}")

        # Relevant facts
        if memories["relevant_facts"]:
            context_parts.append("\n## RELEVANT FACTS I'VE LEARNED:")
            for fact in memories["relevant_facts"][:5]:
                context_parts.append(f"- {fact['content'][:100]}")

        # Stats
        stats = memories["stats"]
        context_parts.append(f"\n## MY MEMORY STATS:")
        context_parts.append(f"Conversations archived: {stats['total_conversations']}")
        context_parts.append(f"Facts learned: {stats['total_facts']}")
        context_parts.append(f"Concepts encountered: {stats['total_entities']}")

        return '\n'.join(context_parts)

    def get_full_stats(self) -> Dict:
        """Get full memory statistics for dashboard"""
        return {
            "total_conversations": self.index["total_conversations"],
            "total_facts": self.index["total_facts"],
            "total_entities": self.index["total_entities"],
            "user_preferences_count": len(self.index["user_model"]["preferences"]),
            "projects_tracked": len(self.index["user_model"]["projects"]),
            "last_updated": self.index.get("last_updated", "never"),
            "created": self.index.get("created", "unknown")
        }


# Singleton instance
_memory_instance = None

def get_memory() -> RecursiveMemory:
    """Get the singleton memory instance"""
    global _memory_instance
    if _memory_instance is None:
        _memory_instance = RecursiveMemory()
    return _memory_instance
