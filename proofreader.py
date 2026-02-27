import logging
import copy
from typing import Any

logger = logging.getLogger('system')

def apply_diffs(chunks: list[dict[str, str | int]], diffs: list[dict[str, str | int]]) -> list[dict[str, str | int]]:
    """
    Applies a list of diffs to a list of chunks.
    
    Each diff should have:
    - chunk_index: int
    - find: str
    - replace: str
    
    A diff is only applied if the 'find' string appears exactly once in the
    'content_ru' of the specified chunk.
    """
    updated_chunks = copy.deepcopy(chunks)
    
    for diff in diffs:
        chunk_idx = diff.get("chunk_index")
        find_str = diff.get("find")
        replace_str = diff.get("replace")
        
        if chunk_idx is None or find_str is None or replace_str is None:
            logger.warning(f"Invalid diff format: {diff}")
            continue
            
        if not isinstance(chunk_idx, int) or chunk_idx < 0 or chunk_idx >= len(updated_chunks):
            logger.warning(f"Chunk index out of bounds or invalid: {chunk_idx}")
            continue
            
        chunk = updated_chunks[chunk_idx]
        content = chunk.get("content_ru", "")
        
        occurrences = content.count(find_str)
        
        if occurrences == 1:
            chunk["content_ru"] = content.replace(find_str, replace_str)
            logger.info(f"Applied diff to chunk {chunk_idx}: replaced '{find_str}' with '{replace_str}'")
        elif occurrences == 0:
            logger.warning(f"Diff skipped: 'find' string not found in chunk {chunk_idx}. String: {find_str!r}")
        else:
            logger.warning(f"Diff skipped: 'find' string found {occurrences} times in chunk {chunk_idx}. String: {find_str!r}")
            
    return updated_chunks
