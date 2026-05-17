from src.clean_data import clean_full_game
from src.split_data import split_clean_data_into_chunks


def main() -> None:
    clean_full_game()
    split_clean_data_into_chunks()


if __name__ == "__main__":
    main()