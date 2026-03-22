import copy

from book_translator.logger import system_logger

def apply_diffs(
    chunks: list[dict[str, str | int]],
    diffs: list[dict[str, str | int]],
) -> tuple[list[dict[str, str | int]], int, int]:
    """Apply a list of diffs to a list of chunks.

    Each diff should have: chunk_index (int), find (str), replace (str).
    A diff is only applied if the 'find' string appears exactly once.

    Returns:
        (updated_chunks, applied_count, skipped_count)
    """
    updated_chunks = copy.deepcopy(chunks)
    applied = 0
    skipped = 0

    for diff in diffs:
        chunk_idx = diff.get("chunk_index")
        find_str = diff.get("find")
        replace_str = diff.get("replace")

        if chunk_idx is None or find_str is None or replace_str is None:
            system_logger.warning(f"Invalid diff format: {diff}")
            skipped += 1
            continue

        if not isinstance(chunk_idx, int):
            system_logger.warning(f"Chunk index invalid type: {chunk_idx!r}")
            skipped += 1
            continue

        # Look up by chunk_index field value, not array position (DB uses 1-based indexing)
        matching = [i for i, c in enumerate(updated_chunks) if c.get("chunk_index") == chunk_idx]
        if not matching:
            system_logger.warning(f"Diff skipped: chunk_index={chunk_idx} not found in chunk list")
            skipped += 1
            continue
        pos = matching[0]

        chunk = updated_chunks[pos]
        content = str(chunk.get("content_target", ""))
        find_str = str(find_str)
        replace_str = str(replace_str)

        occurrences = content.count(find_str)

        if occurrences == 1:
            updated_chunks[pos] = dict(chunk, content_target=content.replace(find_str, replace_str))
            system_logger.info(f"Applied diff to chunk {chunk_idx}: replaced '{find_str}' with '{replace_str}'")
            applied += 1
        elif occurrences == 0:
            system_logger.warning(f"Diff skipped: 'find' string not found in chunk {chunk_idx}. String: {find_str!r}")
            skipped += 1
        else:
            system_logger.warning(f"Diff skipped: 'find' string found {occurrences} times in chunk {chunk_idx}. String: {find_str!r}")
            skipped += 1

    return updated_chunks, applied, skipped
