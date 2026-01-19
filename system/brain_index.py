import os
import json
from datetime import datetime

INDEX_FILE = "system/brain_index.json"

class BrainIndex:
    def __init__(self, brain_path: str):
        self.brain_path = brain_path
        self.index = self._load()
    
    def _load(self):
        try:
            if os.path.exists(INDEX_FILE):
                with open(INDEX_FILE, 'r') as f:
                    return json.load(f)
        except:
            pass
        return {"files": {}, "last_indexed": None}
    
    def save(self):
        os.makedirs(os.path.dirname(INDEX_FILE), exist_ok=True)
        with open(INDEX_FILE, 'w') as f:
            json.dump(self.index, f, indent=2)
    
    def reindex(self):
        """Full reindex of brain directory"""
        self.index["files"] = {}
        skip_dirs = {'.venv', '__pycache__', '.git', 'node_modules'}
        
        for root, dirs, files in os.walk(self.brain_path):
            dirs[:] = [d for d in dirs if d not in skip_dirs]
            
            for file in files:
                if file.startswith('.'):
                    continue
                
                full_path = os.path.join(root, file)
                rel_path = os.path.relpath(full_path, self.brain_path)
                
                try:
                    stat = os.stat(full_path)
                    ext = os.path.splitext(file)[1].lower()
                    
                    file_info = {
                        "name": file,
                        "ext": ext,
                        "size": stat.st_size,
                        "modified": datetime.fromtimestamp(stat.st_mtime).isoformat(),
                        "type": self._get_file_type(ext),
                        "preview": None
                    }
                    
                    # Get preview for text files
                    if ext in ['.py', '.js', '.md', '.txt', '.json', '.html', '.css']:
                        try:
                            with open(full_path, 'r', encoding='utf-8', errors='ignore') as f:
                                content = f.read(500)
                                file_info["preview"] = content[:200]
                        except:
                            pass
                    
                    self.index["files"][rel_path] = file_info
                except:
                    pass
        
        self.index["last_indexed"] = datetime.now().isoformat()
        self.index["total_files"] = len(self.index["files"])
        self.save()
        return self.index["total_files"]
    
    def _get_file_type(self, ext: str) -> str:
        types = {
            '.py': 'python',
            '.js': 'javascript',
            '.html': 'html',
            '.css': 'css',
            '.json': 'config',
            '.md': 'markdown',
            '.txt': 'text',
            '.yml': 'config',
            '.yaml': 'config'
        }
        return types.get(ext, 'other')
    
    def search(self, query: str) -> list:
        """Search files by name, path, or content preview"""
        results = []
        query_lower = query.lower()
        
        for path, info in self.index.get("files", {}).items():
            score = 0
            
            if query_lower in path.lower():
                score += 10
            if query_lower in info.get("name", "").lower():
                score += 20
            if info.get("preview") and query_lower in info["preview"].lower():
                score += 5
            
            if score > 0:
                results.append({"path": path, "score": score, **info})
        
        return sorted(results, key=lambda x: x["score"], reverse=True)[:20]
    
    def get_by_type(self, file_type: str) -> list:
        """Get all files of a specific type"""
        return [
            {"path": path, **info}
            for path, info in self.index.get("files", {}).items()
            if info.get("type") == file_type
        ]
    
    def get_structure(self) -> dict:
        """Get directory structure summary"""
        structure = {}
        for path in self.index.get("files", {}).keys():
            parts = path.split(os.sep)
            if len(parts) > 1:
                folder = parts[0]
                if folder not in structure:
                    structure[folder] = []
                structure[folder].append(path)
        return {k: len(v) for k, v in structure.items()}
