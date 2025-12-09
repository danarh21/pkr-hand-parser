from pathlib import Path

from src.pkr_parser.hand_parser import parse_file_to_json_string

# Укажи здесь имя файла с историей раздач PokerOK,
# который лежит в той же папке, что и main.py
INPUT_FILE = "pokerok_history.txt"

# Имя JSON-файла, куда запишем результат
OUTPUT_FILE = "hands.json"


def main() -> None:
    input_path = Path(INPUT_FILE)

    if not input_path.exists():
        print(f"Файл {input_path} не найден. Проверь имя файла в переменной INPUT_FILE.")
        return

    json_text = parse_file_to_json_string(str(input_path))

    output_path = Path(OUTPUT_FILE)
    output_path.write_text(json_text, encoding="utf-8")

    print(f"Готово! Разобранные раздачи записаны в файл: {output_path}")


if __name__ == "__main__":
    main()
