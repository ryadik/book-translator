import re
from book_translator.logger import system_logger


def split_chapter_intelligently(
    chapter_file_path,
    target_chars=3000,
    max_part_chars=5000,
    min_chunk_size=1,
):
    """Split a chapter file into chunks and return them as a list of dicts.

    Returns:
        list of {"id": int, "text": str}
    """
    system_logger.info(f"[Splitter] Обработка файла главы: {chapter_file_path}")

    with open(chapter_file_path, 'r', encoding='utf-8') as f:
        lines = f.readlines()

    current_chunk_lines = []
    current_chunk_chars = 0
    chunk_num = 1
    chunks_data = []

    def append_chunk(chunk_text):
        nonlocal chunk_num, chunks_data
        chunks_data.append({"id": chunk_num, "text": chunk_text})
        system_logger.info(f"[Splitter] Чанк №{chunk_num} ({len(chunk_text)} символов)")
        chunk_num += 1

    def write_part(force=False):
        nonlocal current_chunk_lines, current_chunk_chars, chunk_num, chunks_data
        if not current_chunk_lines:
            return
        chunk_text = "".join(current_chunk_lines)
        if (
            not force
            and len(chunk_text) < min_chunk_size
            and chunks_data
            and len(chunks_data[-1]["text"]) + len(chunk_text) <= max_part_chars
        ):
            chunks_data[-1]["text"] += chunk_text
            system_logger.info(
                f"[Splitter] Последний малый фрагмент ({len(chunk_text)} символов) "
                f"приклеен к чанку №{chunks_data[-1]['id']}"
            )
        else:
            append_chunk(chunk_text)
        current_chunk_lines = []
        current_chunk_chars = 0

    def is_scene_marker(line):
        return re.match(r'^(\s*\[\]\s*|\s*---\s*)$', line)

    def is_dialogue_start(line):
        stripped_line = line.strip()
        return stripped_line.startswith('「') or stripped_line.startswith('『')

    def is_blank_line(line):
        return not line.strip()

    def can_split_at(index: int) -> bool:
        left_lines = current_chunk_lines[:index + 1]
        right_lines = current_chunk_lines[index + 1:]
        left_chars = sum(len(line) for line in left_lines)
        right_chars = sum(len(line) for line in right_lines)

        if left_chars < min_chunk_size:
            return False
        if right_lines and right_chars < min_chunk_size:
            return False
        return True

    i = 0
    while i < len(lines):
        line = lines[i]
        current_chunk_lines.append(line)
        current_chunk_chars += len(line)

        if current_chunk_chars >= target_chars:
            best_break_index = -1

            for j in range(len(current_chunk_lines) - 1, -1, -1):
                current_line_in_buffer = current_chunk_lines[j]

                if is_scene_marker(current_line_in_buffer):
                    if can_split_at(j):
                        best_break_index = j
                        break

                if is_blank_line(current_line_in_buffer):
                    next_non_blank_line_is_dialogue = False
                    for k in range(j + 1, len(current_chunk_lines)):
                        if not is_blank_line(current_chunk_lines[k]):
                            if is_dialogue_start(current_chunk_lines[k]):
                                next_non_blank_line_is_dialogue = True
                            break

                    if not next_non_blank_line_is_dialogue and can_split_at(j):
                        best_break_index = j
                        break

            if best_break_index != -1:
                temp_lines = current_chunk_lines[best_break_index + 1:]
                current_chunk_lines = current_chunk_lines[:best_break_index + 1]
                write_part()
                current_chunk_lines = temp_lines
                current_chunk_chars = sum(len(l) for l in current_chunk_lines)
            elif current_chunk_chars >= max_part_chars:
                force_break_index = -1
                for j in range(len(current_chunk_lines) - 1, -1, -1):
                    if is_blank_line(current_chunk_lines[j]) and can_split_at(j):
                        force_break_index = j
                        break

                if force_break_index != -1:
                    temp_lines = current_chunk_lines[force_break_index + 1:]
                    current_chunk_lines = current_chunk_lines[:force_break_index + 1]
                    write_part()
                    current_chunk_lines = temp_lines
                    current_chunk_chars = sum(len(l) for l in current_chunk_lines)
                else:
                    write_part(force=True)

        i += 1

    write_part()
    return chunks_data
