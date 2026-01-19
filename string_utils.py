def reverse_string(s):
    return s[::-1]

def capitalize_words(s):
    return ' '.join(word.capitalize() for word in s.split())