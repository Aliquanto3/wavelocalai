import re
import unicodedata

none_dict = {
    "fr": ["aucun"],
}


def clean_text(text):
    return text.strip().lower().replace('\u200c', '').replace(' ', '')

def is_correct_order(correct_answer, model_answer):
    model_answer = model_answer.strip().lower()
    correct_answer = [correct.strip().lower() for correct in correct_answer]
    return all(word in model_answer for word in correct_answer)

def compare_numbers(lang, correct_answer, model_answer):    
    if '-' in lang:
        inst_lang = lang.split("-")[1]
    else:
        inst_lang = lang
    if not model_answer:
        return False
    processed_model_answer = unicodedata.normalize("NFKC", model_answer)
   
    none_words = none_dict[inst_lang]
    # Step 1.5: Check if any word in none_words is present in the processed answer; if yes, auto-fail.
    for word in none_words:
        if word in processed_model_answer or clean_text(word) in processed_model_answer:
            return False
    
    # Step 2: Extract all numeric substrings from the processed answer.
    numeric_strings = re.findall(r'\d+', processed_model_answer)

    # Step 3: Remove numbers that consist of a single digit.
    numeric_strings = [num for num in numeric_strings if len(num) > 1]

    # Step 4: Remove duplicates while preserving the original order.
    numeric_strings = list(dict.fromkeys(numeric_strings))

    # If no numerics are found after processing, return "0".
    if not numeric_strings:
        return False

    # Step 5: Convert the extracted number strings to integers.
    try:
        extracted_numbers = [int(num) for num in numeric_strings]
    except Exception:
        return False

    # Convert correct_answers elements to integers to ensure numeric comparison.
    try:
        correct_converted = [int(item) for item in correct_answer]
    except Exception:
        return False

    # Step 6: Check that the number of extracted numbers matches the length of correct_answers.
    if len(extracted_numbers) != len(correct_converted):
        return False

    # Step 7: Compare the extracted numbers with the correct answers element-wise.
    if set(extracted_numbers) == set(correct_converted):
        return True
    else:
        return False

def compare_none(lang, correct_answer, model_answer):   
    # Lower-case all inputs for consistent, case-insensitive processing.
    if '-' in lang:
        inst_lang = lang.split("-")[1]
    else:
        inst_lang = lang

    processed_model_answer = clean_text(unicodedata.normalize("NFKC", model_answer))
    correct_answer = [clean_text(answer) for answer in correct_answer]
    none_words = [clean_text(word) for word in none_dict[inst_lang]]

    # Step 2: Remove single digit numbers from the processed answer.
    processed_model_answer = re.sub(r'\b\d\b', '', processed_model_answer)

    # Step 3: Extract all numeric sequences from the processed answer.
    numbers = re.findall(r'\d+', processed_model_answer)

    # If any multi-digit number is found, return "0".
    # if numbers:
    #     return False
    # Step 4: Check if any of the words in none_words are present.
    for word in none_words:
        if word in processed_model_answer:
            return True

    # If none of the none_words are found, return "0".
    return False
