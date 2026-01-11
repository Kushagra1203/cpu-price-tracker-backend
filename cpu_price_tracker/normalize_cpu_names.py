import json
import os
import re
import csv

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, 'data')

CSV_FILE = os.path.join(DATA_DIR, 'cpu_data.csv')

def load_json(json_file):
    with open(json_file, 'r', encoding='utf-8') as f:
        return json.load(f)

def save_json(data, json_file):
    with open(json_file, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2)

def clean_name(name):
    name = re.sub(r'\([^)]*\)', ' ', name)
    name = name.replace('-', ' ')
    name = re.sub(r'X3D', 'X3D_PLACEHOLDER', name, flags=re.IGNORECASE)
    name = re.sub(r'\s+', ' ', name).strip()
    name = name.replace('X3D_PLACEHOLDER', 'X3D')
    return name

def standardize_cpu_name(name):
    name = re.sub(r'\u2122', '', name)
    name = name.replace('™', '')
    name = re.sub(r'\s+', ' ', name).strip()

    if re.search(r'Intel i\d', name, re.IGNORECASE) and not re.search(r'Intel Core', name, re.IGNORECASE):
        name = re.sub(r'(Intel )i(\d+(-\d+)?)', r'\1Core i\2', name, flags=re.IGNORECASE)

    if re.match(r'AMD 4700S', name, re.IGNORECASE) and 'Ryzen 7' not in name:
        name = re.sub(r'AMD\s+4700S', 'AMD Ryzen 7 4700S', name, flags=re.IGNORECASE)

    name = re.sub(r'(?<=\w)\s+3D\b', '3D', name)

    return name

def clean_and_standardize_name(name):
    cleaned = clean_name(name)
    standardized = standardize_cpu_name(cleaned)
    return standardized

def match_name(name, dictionary_keys):
    name_words = set(name.lower().split())
    for dict_entry in dictionary_keys:
        dict_words = set(dict_entry.lower().split())
        if dict_words.issubset(name_words):
            return dict_entry
    return None

def load_augmented_dictionary(csv_file):
    metadata_dict = {}
    with open(csv_file, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            name = row['name'].strip()
            metadata_dict[name.lower()] = {
                "brand": row.get("brand", "Others"),
                "generation": row.get("generation", "Others"),
                "series": row.get("series", "Others"),
                "cores": row.get("cores", ""),
                "threads": row.get("threads", ""),
                "base_clock_ghz": row.get("base_clock_ghz", ""),
                "tdp_watt": row.get("tdp_watt", "")
            }
    return metadata_dict

def standardize_cpu_names(input_json, output_standardized_json, output_unmatched_json, augmented_dict):
    raw_data = load_json(input_json)
    matched_data = []
    unmatched_data = []

    for item in raw_data:
        raw_name = item.get('name', '')
        cleaned_name = clean_and_standardize_name(raw_name)
        standardized_name = match_name(cleaned_name, augmented_dict.keys())

        if standardized_name:
            item['standard_name'] = standardized_name

            meta = augmented_dict.get(standardized_name.lower(), {})
            item.update(meta)  # merge all metadata from CSV

            matched_data.append(item)
        else:
            unmatched_data.append(item)

    save_json(matched_data, output_standardized_json)
    save_json(unmatched_data, output_unmatched_json)

    print(f'Total entries processed: {len(raw_data)}')
    print(f'Matched entries: {len(matched_data)}')
    print(f'Unmatched entries: {len(unmatched_data)}')
    print(f'Standardized data saved to: {output_standardized_json}')
    print(f'Unmatched data saved to: {output_unmatched_json}')

if __name__ == '__main__':
    input_file = os.path.join(DATA_DIR, 'processors.json')
    output_matched = os.path.join(DATA_DIR, 'processors_standardized.json')
    output_unmatched = os.path.join(DATA_DIR, 'processors_unmatched.json')

    augmented_dict = load_augmented_dictionary(CSV_FILE)

    standardize_cpu_names(input_file, output_matched, output_unmatched, augmented_dict)
