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
        user_lower = user_message.lower()

        # Extract user preferences (things Hugo likes/wants) - MORE PATTERNS
        pref_patterns = [
            r"i (?:like|love|prefer|want|need|hate|dont like) (.+?)(?:\.|,|!|$)",
            r"(?:make it|i want it|lets|let's) (.+?)(?:\.|,|!|$)",
            r"my (?:favorite|preferred) (.+?) is (.+?)(?:\.|,|$)",
            r"can you (.+?)(?:\?|$)",  # Requests reveal preferences
            r"i think (.+?)(?:\.|,|$)",
        ]
        for pattern in pref_patterns:
            matches = re.findall(pattern, user_lower)
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

        # Extract technical concepts - EXPANDED
        tech_patterns = [
            r'\b(api|server|database|model|neural|ai|ml|llm|token|embedding|vector|memory|cache)\b',
            r'\b(python|javascript|html|css|json|react|flask|fastapi|uvicorn)\b',
            r'\b(ollama|anthropic|openai|claude|gpt|llama|deepseek|codellama)\b',
            r'\b(file|folder|directory|path|create|edit|search|index|tool)\b',
            r'\b(safety|security|internet|research|improvement|learning)\b',
        ]
        for pattern in tech_patterns:
            matches = re.findall(pattern, combined, re.IGNORECASE)
            extracted["technical_concepts"].extend([m.lower() for m in matches])

        # Extract facts - MORE AGGRESSIVE
        fact_markers = ["is a", "is the", "means", "works by", "can be", "should be",
                       "allows", "enables", "helps", "created", "built", "designed"]
        sentences = combined.replace('!', '.').replace('?', '.').split('.')
        for sentence in sentences:
            sentence = sentence.strip()
            if any(marker in sentence for marker in fact_markers):
                if len(sentence) > 15 and len(sentence) < 250:
                    extracted["facts"].append(sentence)

        # Also extract any sentence that mentions Brain components as facts
        brain_facts = []
        for sentence in sentences:
            if any(term in sentence.lower() for term in ['opus', 'eai', 'brain', 'thinker', 'swarm']):
                if len(sentence) > 10 and len(sentence) < 250:
                    brain_facts.append(sentence.strip())
        extracted["facts"].extend(brain_facts[:3])  # Limit to avoid spam

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

    def remember_fact(self, fact_type: str, content: str, tags: List[str] = None):
        """
        Explicitly remember a fact (called by Opus via remember tool).

        Supported types:
        - key_fact: Important factual information
        - project: Project info (marked as active)
        - preference: User preference
        - decision: Important decision made
        - conversation_summary: Summary of a conversation
        - project_state: Current state of a project
        - learned_skill: New skill or technique learned
        """
        fact_entry = {
            "content": content,
            "type": fact_type,
            "timestamp": datetime.now().isoformat(),
            "hash": hashlib.md5(content.encode()).hexdigest()[:8],
            "explicit": True,  # Marked as explicitly remembered
            "tags": tags or []
        }

        # Mark project types as active
        if fact_type in ["project", "project_state"]:
            fact_entry["active"] = True

        if not any(f["hash"] == fact_entry["hash"] for f in self.index["facts"]):
            self.index["facts"].append(fact_entry)
            self.index["total_facts"] += 1

            # Also update user model for preferences
            if fact_type == "preference" and content not in self.index["user_model"]["preferences"]:
                self.index["user_model"]["preferences"].append(content)
                self.index["user_model"]["preferences"] = self.index["user_model"]["preferences"][-50:]

            # Track projects
            if fact_type in ["project", "project_state"]:
                # Extract project name (first word or phrase before colon/dash)
                proj_name = content.split(':')[0].split('-')[0].strip()[:30]
                if proj_name and proj_name not in [p.lower() for p in self.index["user_model"]["projects"]]:
                    self.index["user_model"]["projects"].append(proj_name)
                    self.index["user_model"]["projects"] = self.index["user_model"]["projects"][-30:]

            self._save_index()

        return fact_entry

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

    def search_memories(self, query: str, limit: int = 20) -> Dict:
        """
        Search all memories by keyword. Returns matching facts, entities, convos.
        This is the tool Opus can use to explicitly query memories.
        """
        query_lower = query.lower()
        query_words = set(query_lower.split())

        results = {
            "query": query,
            "matching_facts": [],
            "matching_entities": [],
            "matching_conversations": [],
            "matching_preferences": [],
            "matching_projects": []
        }

        # Search facts
        for fact in self.index.get("facts", []):
            content = fact.get("content", "").lower()
            fact_words = set(content.split())

            # Check for word overlap or substring match
            overlap = query_words & fact_words
            if overlap or query_lower in content:
                score = len(overlap) + (2 if query_lower in content else 0)
                results["matching_facts"].append({
                    "content": fact["content"],
                    "timestamp": fact.get("timestamp", "unknown"),
                    "type": fact.get("type", "extracted"),
                    "relevance": score
                })

        # Sort by relevance and limit
        results["matching_facts"] = sorted(
            results["matching_facts"],
            key=lambda x: x["relevance"],
            reverse=True
        )[:limit]

        # Search entities
        for entity, info in self.index.get("entities", {}).items():
            if query_lower in entity or any(w in entity for w in query_words):
                results["matching_entities"].append({
                    "name": entity,
                    "count": info.get("count", 0),
                    "first_seen": info.get("first_seen", "unknown"),
                    "last_seen": info.get("last_seen", "unknown")
                })

        results["matching_entities"] = results["matching_entities"][:limit]

        # Search conversation summaries
        for conv in self.index.get("conversations", []):
            summary = conv.get("summary", "").lower()
            if query_lower in summary or any(w in summary for w in query_words):
                results["matching_conversations"].append({
                    "id": conv.get("id"),
                    "timestamp": conv.get("timestamp"),
                    "summary": conv.get("summary", "")[:200],
                    "message_count": conv.get("message_count", 0)
                })

        results["matching_conversations"] = results["matching_conversations"][:5]

        # Search user preferences
        for pref in self.index.get("user_model", {}).get("preferences", []):
            if query_lower in pref.lower() or any(w in pref.lower() for w in query_words):
                results["matching_preferences"].append(pref)

        # Search projects
        for proj in self.index.get("user_model", {}).get("projects", []):
            if query_lower in proj.lower() or any(w in proj.lower() for w in query_words):
                results["matching_projects"].append(proj)

        results["total_matches"] = (
            len(results["matching_facts"]) +
            len(results["matching_entities"]) +
            len(results["matching_conversations"]) +
            len(results["matching_preferences"]) +
            len(results["matching_projects"])
        )

        return results

    def get_session_context(self) -> Dict:
        """
        Get context to load on session startup.
        Returns last 3 conversation summaries and active project memories.
        """
        context = {
            "recent_conversations": [],
            "active_projects": [],
            "recent_facts": [],
            "user_snapshot": {}
        }

        # Last 3 conversation summaries
        convos = self.index.get("conversations", [])
        for conv in convos[-3:]:
            context["recent_conversations"].append({
                "timestamp": conv.get("timestamp"),
                "summary": conv.get("summary", ""),
                "id": conv.get("id")
            })

        # Projects from user model
        context["active_projects"] = self.index.get("user_model", {}).get("projects", [])[-5:]

        # Recent facts (last 10)
        context["recent_facts"] = self.index.get("facts", [])[-10:]

        # User snapshot
        user_model = self.index.get("user_model", {})
        context["user_snapshot"] = {
            "name": user_model.get("name", "User"),
            "preferences": user_model.get("preferences", [])[-5:],
            "interests": user_model.get("interests", [])[-5:],
            "communication_style": user_model.get("communication_style", [])
        }

        return context

    def format_memory_for_context(self, memory_item: Dict, mem_type: str) -> str:
        """Format a memory item for injection into Opus's context"""
        timestamp = memory_item.get("timestamp", "unknown")
        if isinstance(timestamp, str) and "T" in timestamp:
            timestamp = timestamp.split("T")[0]  # Just the date

        content = memory_item.get("content", str(memory_item))[:100]
        category = memory_item.get("type", mem_type)

        return f"[MEMORY] {category}:{content} ({timestamp})"


# Singleton instance
_memory_instance = None

def get_memory() -> RecursiveMemory:
    """Get the singleton memory instance"""
    global _memory_instance
    if _memory_instance is None:
        _memory_instance = RecursiveMemory()
    return _memory_instance
