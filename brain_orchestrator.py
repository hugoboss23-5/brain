import ollama
import json
import os
import time

MODEL = "tinyllama:latest"
MAX_TOKENS = 150

def detect_intent(text):
    """Code-based intent detection - no model needed"""
    t = text.lower()
    if any(w in t for w in ['create', 'make', 'write', 'save']):
        return 'file_op'
    if '?' in text:
        return 'question'
    if any(w in t for w in ['search', 'find', 'look for', 'where']):
        return 'search'
    return 'conversation'

def get_intent_prompt(intent, user_input):
    """Get focused prompt based on intent"""
    if intent == 'file_op':
        return f"User wants to create/write something. Extract: filename and content. Input: {user_input}"
    if intent == 'question':
        return f"Answer this directly in 1-2 sentences: {user_input}"
    if intent == 'search':
        return f"User is searching for something. What are they looking for? Input: {user_input}"
    return f"Respond briefly: {user_input}"

def stream_response(messages, max_tokens=MAX_TOKENS):
    """Stream response from tinyllama"""
    response_text = ""
    try:
        stream = ollama.chat(
            model=MODEL,
            messages=messages,
            stream=True,
            options={'num_predict': max_tokens, 'temperature': 0.3}
        )
        print("Marcos: ", end="", flush=True)
        for chunk in stream:
            token = chunk.get('message', {}).get('content', '')
            if token:
                print(token, end="", flush=True)
                response_text += token
        print()
    except Exception as e:
        print(f"Error: {e}")
        return None
    return response_text

def check_response(original_question, response):
    """Ask model if response actually answers the question"""
    if not response or len(response.strip()) < 5:
        return False
    try:
        check = ollama.chat(
            model=MODEL,
            messages=[{
                "role": "user",
                "content": f'Does this response answer "{original_question}"?\nResponse: "{response}"\nReply YES or NO only.'
            }],
            options={'num_predict': 10, 'temperature': 0.1}
        )
        answer = check.get('message', {}).get('content', '').strip().upper()
        return 'YES' in answer
    except:
        return True  # Assume OK on error

def attempt_response(user_input, intent, retry=False):
    """Generate response, with optional retry adjustment"""
    prompt = get_intent_prompt(intent, user_input)
    if retry:
        prompt = f"Be more direct. Actually answer: {user_input}"

    messages = [
        {"role": "system", "content": "You are Marcos, a fast AI assistant. Short answers only. No explanations unless asked."},
        {"role": "user", "content": prompt}
    ]
    return stream_response(messages)

def handle_file_op(user_input):
    """Handle file creation requests"""
    # Extract filename and content from input
    messages = [
        {"role": "system", "content": "Extract filename and content. Reply as JSON: {\"filename\": \"...\", \"content\": \"...\"}"},
        {"role": "user", "content": user_input}
    ]
    try:
        resp = ollama.chat(model=MODEL, messages=messages, options={'num_predict': 200})
        text = resp.get('message', {}).get('content', '')
        # Try to parse JSON
        start = text.find('{')
        end = text.rfind('}') + 1
        if start >= 0 and end > start:
            data = json.loads(text[start:end])
            filename = data.get('filename', 'output.txt')
            content = data.get('content', '')
            with open(filename, 'w') as f:
                f.write(content)
            print(f"Marcos: Done. Created {filename}")
            return True
    except Exception as e:
        print(f"Marcos: Failed: {e}")
    return False

def thinking_loop():
    """Main thinking loop: input → intent → response → check → retry if needed"""
    while True:
        try:
            user_input = input("Hugo: ").strip()
        except (KeyboardInterrupt, EOFError):
            print("\nMarcos: Goodbye.")
            break

        if not user_input:
            continue
        if user_input.lower() in ['exit', 'quit', 'bye']:
            print("Marcos: Goodbye.")
            break

        # Step 1: Detect intent
        intent = detect_intent(user_input)

        # Step 2: Handle based on intent
        if intent == 'file_op':
            handle_file_op(user_input)
            continue

        # Step 3: Attempt response
        response = attempt_response(user_input, intent)
        if not response:
            continue

        # Step 4: Check if response actually answers
        if intent == 'question':
            answered = check_response(user_input, response)
            if not answered:
                # Step 5: Retry once with adjustment
                print("[retrying...]")
                attempt_response(user_input, intent, retry=True)

def main():
    print("Marcos online.")
    # Warm up model
    try:
        ollama.chat(model=MODEL, messages=[{"role": "user", "content": "hi"}], options={'num_predict': 1})
    except:
        print("Warning: Ollama not responding. Run: ollama serve")
    thinking_loop()

if __name__ == '__main__':
    main()
