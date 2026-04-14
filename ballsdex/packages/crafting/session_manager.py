from __future__ import annotations

from typing import Dict, Optional, List
import datetime
import traceback
import threading

from ballsdex.core.models import Player, Ball

class CraftingSessionData:
    def __init__(self, player: Player, ingredient_instances: List[int], special=None):
        self.player = player
        self.ingredient_instances = ingredient_instances.copy()  # Create a copy to prevent external modifications
        self.special = special
        self.created_at = datetime.datetime.now()
        self.last_accessed = datetime.datetime.now()
        self.access_count = 0
        self.debug_log = []
        self._lock = threading.Lock()  # Thread safety
    
    def log_access(self, operation: str, details: str = "", file_name: str = ""):
        with self._lock:
            self.last_accessed = datetime.datetime.now()
            self.access_count += 1
            
            stack = traceback.extract_stack()
            caller_info = f"{stack[-3].filename}:{stack[-3].lineno}" if len(stack) >= 3 else "unknown"
            
            log_entry = {
                'timestamp': datetime.datetime.now().isoformat(),
                'operation': operation,
                'details': details,
                'caller': caller_info,
                'file': file_name,
                'ingredient_count': len(self.ingredient_instances),
                'access_count': self.access_count
            }
            self.debug_log.append(log_entry)
            
            print(f"[SESSION {self.player.id}] {operation}: {details} "
                  f"(ingredients: {len(self.ingredient_instances)}) "
                  f"from {caller_info}")
    
    def to_dict(self) -> Dict[str, Optional[object]]:
        """Convert to the format expected by existing code"""
        self.log_access("CONVERTED_TO_DICT", "Session data accessed")
        return {
            'player': self.player,
            'ingredient_instances': self.ingredient_instances.copy(),  # Always return a copy
            'special': self.special
        }
    
    def is_valid(self) -> tuple[bool, str]:
        """Check if session is still valid"""
        # Check age (expire after 30 minutes)
        if datetime.datetime.now() - self.created_at > datetime.timedelta(minutes=30):
            return False, "Session expired"
        
        # Check ingredients
        if not isinstance(self.ingredient_instances, list):
            return False, "Ingredient instances corrupted"
        
        if not self.ingredient_instances:
            return False, "No ingredients remaining"
        
        return True, "Valid"
    
    def remove_ingredients(self, instance_ids: List[int]) -> bool:
        """Safely remove ingredients from session"""
        with self._lock:
            try:
                removed_count = 0
                for instance_id in instance_ids:
                    if instance_id in self.ingredient_instances:
                        self.ingredient_instances.remove(instance_id)
                        removed_count += 1
                
                self.log_access("INGREDIENTS_REMOVED", f"Removed {removed_count} ingredients, {len(self.ingredient_instances)} remaining")
                return True
            except Exception as e:
                self.log_access("INGREDIENT_REMOVAL_FAILED", f"Error: {e}")
                return False
    
    def print_debug_log(self):
        """Print full debug log for troubleshooting"""
        print(f"[SESSION {self.player.id}] DEBUG LOG:")
        for entry in self.debug_log:
            print(f"  {entry['timestamp']}: {entry['operation']} - {entry['details']} "
                  f"(from {entry['caller']})")

_session_storage: Dict[int, CraftingSessionData] = {}

def create_session(user_id: int, player: Player, ingredient_instances: List[int], special=None) -> bool:
    """Create a new crafting session"""
    try:
        # End existing session if any
        if user_id in _session_storage:
            _session_storage[user_id].log_access("SESSION_REPLACED", "Creating new session")
            _session_storage[user_id].print_debug_log()
        
        session = CraftingSessionData(player, ingredient_instances, special)
        session.log_access("SESSION_CREATED", f"Initial ingredients: {len(ingredient_instances)}")
        _session_storage[user_id] = session
        
        print(f"[SESSION_MANAGER] Created session for user {user_id} with {len(ingredient_instances)} ingredients")
        return True
    except Exception as e:
        print(f"[SESSION_MANAGER] Failed to create session for user {user_id}: {e}")
        return False

def get_session(user_id: int) -> Optional[Dict[str, Optional[object]]]:
    """Get session data in the format expected by existing code"""
    if user_id not in _session_storage:
        print(f"[SESSION_MANAGER] No session found for user {user_id}")
        print(f"[SESSION_MANAGER] Available sessions: {list(_session_storage.keys())}")
        return None
    
    session = _session_storage[user_id]
    
    # Validate session
    is_valid, reason = session.is_valid()
    if not is_valid:
        session.log_access("SESSION_INVALID", f"Reason: {reason}")
        session.print_debug_log()
        del _session_storage[user_id]
        print(f"[SESSION_MANAGER] Removed invalid session for user {user_id}: {reason}")
        return None
    
    session.log_access("SESSION_ACCESSED", "Session data retrieved")
    return session.to_dict()

def update_session_ingredients(user_id: int, new_ingredients: List[int]) -> bool:
    """Update session ingredients safely"""
    if user_id not in _session_storage:
        print(f"[SESSION_MANAGER] Cannot update ingredients - no session for user {user_id}")
        return False
    
    session = _session_storage[user_id]
    session.ingredient_instances = new_ingredients.copy()
    session.log_access("INGREDIENTS_UPDATED", f"Set to {len(new_ingredients)} ingredients")
    return True

def remove_session_ingredients(user_id: int, instance_ids: List[int]) -> bool:
    """Remove specific ingredients from session"""
    if user_id not in _session_storage:
        print(f"[SESSION_MANAGER] Cannot remove ingredients - no session for user {user_id}")
        return False
    
    session = _session_storage[user_id]
    return session.remove_ingredients(instance_ids)

def end_session(user_id: int, reason: str = "Manual") -> bool:
    """End a crafting session"""
    if user_id not in _session_storage:
        print(f"[SESSION_MANAGER] Cannot end session - no session for user {user_id}")
        return False
    
    session = _session_storage[user_id]
    session.log_access("SESSION_ENDED", f"Reason: {reason}")
    session.print_debug_log()
    del _session_storage[user_id]
    
    print(f"[SESSION_MANAGER] Ended session for user {user_id}: {reason}")
    return True

def session_exists(user_id: int) -> bool:
    """Check if session exists and is valid"""
    if user_id not in _session_storage:
        return False
    
    session = _session_storage[user_id]
    is_valid, _ = session.is_valid()
    if not is_valid:
        del _session_storage[user_id]
        return False
    
    return True

def get_session_count() -> int:
    """Get total number of active sessions"""
    return len(_session_storage)

def cleanup_expired_sessions() -> int:
    """Clean up expired sessions"""
    expired_users = []
    for user_id, session in _session_storage.items():
        is_valid, reason = session.is_valid()
        if not is_valid:
            session.log_access("SESSION_EXPIRED", f"Reason: {reason}")
            expired_users.append(user_id)
    
    for user_id in expired_users:
        del _session_storage[user_id]
    
    if expired_users:
        print(f"[SESSION_MANAGER] Cleaned up {len(expired_users)} expired sessions")
    
    return len(expired_users)

crafting_sessions = _session_storage  # This will be empty, but maintains the import
