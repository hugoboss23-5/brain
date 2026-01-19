from flask import Flask, render_template, request
app = Flask(__name__)
@app.route('/', methods=['GET', 'POST'])
def index():
    if request.method == 'POST':
        message = request.form['message']
        # TO DO: Pass message to Claude through system
        print(message)
    return render_template('chat.html')
if __name__ == '__main__':
    app.run(debug=True)