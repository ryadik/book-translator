import json
from pathlib import Path

def clean_text(text):
    if not text:
        return ""
    # Remove tabs and newlines to not break TSV format
    return str(text).replace('\t', ' ').replace('\n', ' ').replace('\r', '').strip()

def main():
    old_glossary_path = Path("data/_glossary_old.json")
    output_tsv_path = Path("legacy_terms.tsv")
    
    if not old_glossary_path.exists():
        print(f"File not found: {old_glossary_path}")
        return

    with open(old_glossary_path, 'r', encoding='utf-8') as f:
        data = json.load(f)

    count = 0
    alias_count = 0

    with open(output_tsv_path, 'w', encoding='utf-8') as out:
        out.write("# source_term\ttarget_term\tcomment\n")
        
        for category, terms in data.items():
            if not isinstance(terms, dict):
                continue
                
            for term_id, term_data in terms.items():
                name_data = term_data.get("name", {})
                jp_name = clean_text(name_data.get("jp"))
                ru_name = clean_text(name_data.get("ru"))
                desc = clean_text(term_data.get("description", ""))
                
                # Add main term
                if jp_name and ru_name:
                    out.write(f"{jp_name}\t{ru_name}\t{desc}\n")
                    count += 1
                
                # Add aliases if they have both JP and RU
                aliases = term_data.get("aliases", [])
                if isinstance(aliases, list):
                    for alias in aliases:
                        if isinstance(alias, dict):
                            a_jp = clean_text(alias.get("jp"))
                            a_ru = clean_text(alias.get("ru"))
                            if a_jp and a_ru:
                                a_desc = f"Псевдоним/Альтернативное имя для: {ru_name}"
                                out.write(f"{a_jp}\t{a_ru}\t{a_desc}\n")
                                alias_count += 1

    print(f"Готово! Сгенерирован файл {output_tsv_path}")
    print(f"Экспортировано основных терминов: {count}")
    print(f"Экспортировано псевдонимов: {alias_count}")
    print(f"Всего строк для импорта: {count + alias_count}")
    print("\nТеперь вы можете импортировать его в вашу серию командой:")
    print("book-translator glossary import legacy_terms.tsv")

if __name__ == "__main__":
    main()
