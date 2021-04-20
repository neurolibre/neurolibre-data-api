import flask
import os
import json
import glob
import time
import subprocess
import requests
from flask_htpasswd import HtPasswdAuth

# https://stackoverflow.com/questions/41410199/how-to-configure-nginx-to-pass-user-info-to-wsgi-flask
# https://blog.miguelgrinberg.com/post/restful-authentication-with-flask

# GLOBAL VARIABLES
BOOK_PATHS = "/DATA/book-artifacts/*/*/*/*.tar.gz"
BOOK_URL = "http://neurolibre-data.conp.cloud/book-artifacts"

#https://programminghistorian.org/en/lessons/creating-apis-with-python-and-flask

app = flask.Flask(__name__)
app.config["DEBUG"] = True
app.config['FLASK_HTPASSWD_PATH'] = '/home/ubuntu/.htpasswd'
htpasswd = HtPasswdAuth(app)

def load_all(globpath=BOOK_PATHS):
    book_collection = []
    
    paths = glob.glob(globpath)
    for path in paths:
        path_list = path.replace(".tar.gz", "").split("/")
        commit_hash = path_list[-1]
        repo = path_list[-2]
        provider = path_list[-3]
        user = path_list[-4]
        book_dict = {"book_url": BOOK_URL + f"/{user}/{provider}/{repo}/{commit_hash}/html/"
                     , "download_link": BOOK_URL + path.replace("/DATA/book-artifacts", "")
                     , "repo_link": f"https://{provider}/{user}/{repo}"
                     , "user_name": user
                     , "repo_name": repo
                     , "provider_name": provider
                     , "commit_hash": commit_hash 
                     , "time_added": time.ctime(os.path.getctime(path))}
        book_collection += [book_dict]

    return book_collection

def doc():
    return """
<p> Build book from a specific repository (\"commit\" defaults to HEAD) </p>
<p> &nbsp; POST &nbsp; &nbsp; -H "Content-Type: application/json" -d '{"repo_url":"https://github.com/ltetrel/nha2020-nilearn", "commit_hash":"e29aa259f6807e62610bc84a86d406065028fe29"}' /api/v1/resources/books</p>
<p> List all books </p>
<p> &nbsp; GET &nbsp; &nbsp; /api/v1/resources/books/all </p>
<p> Retrieve book(s) by username </p>
<p> &nbsp; GET &nbsp; &nbsp; /api/v1/resources/books?user_name=jovyan </p>
<p> Retrieve specific book by commit hash </p>
<p> &nbsp; GET &nbsp; &nbsp; /api/v1/resources/books?commit_hash=737586b68c03b5fae1ee2a07b78ecb8b12ca2751 </p>
<p> Retrieve book(s) by repository name </p>
<p> &nbsp; GET &nbsp; &nbsp; /api/v1/resources/books?repo_name=hello-world </p>
"""

@app.route('/', methods=['GET'])
@htpasswd.required
def home(user):
    return """
<h1>Neurolibre book repository</h1>
<p>API for triggering, serving and downloading neurolibre book artifacts.</p>
{}
""".format(doc())

@app.route('/api/v1/resources/books/all', methods=['GET'])
@htpasswd.required
def api_all(user):
    books = load_all()
    
    return flask.jsonify(books)

@app.route('/api/v1/resources/books', methods=['POST'])
@htpasswd.required
def api_books_post(user):
    user_request = flask.request.get_json(force=True) 
    binderhub_api_url = "https://binder.conp.cloud/build/{provider}/{user_repo}/{repo}.git/{commit}"

    if "repo_url" in user_request:
        repo_url = user_request["repo_url"]
        repo = repo_url.split("/")[-1]
        user_repo = repo_url.split("/")[-2]
        provider = repo_url.split("/")[-3]
        if provider == "github.com":
            provider = "gh"
        elif provider == "gitlab.com":
            provider = "gl"
    else:
        flask.abort(400)

    if "commit_hash" in user_request:
        commit = user_request["commit_hash"]
    else:
        commit = "HEAD"
    
    lock_filepath = f"./{provider}_{user_repo}_{repo}.lock"
    if os.path.exists(lock_filepath):
        flask.abort(409)
    else:
        with open(lock_filepath, "w") as f:
            f.write("")

    # requests build
    binderhub_request = binderhub_api_url.format(provider=provider, user_repo=user_repo, repo=repo, commit=commit)
    req = requests.get(binderhub_request)
    commit_hash = None
    for item in req.content.decode("utf8").split("data: "):
        # create dict if string has repo_url
        print(item)
        if "repo_url" in item.strip():
            dict_log = json.loads(item.strip())
            # get commit hash just if log says that it was ready
            if dict_log["phase"] == "ready":
                commit_hash = dict_log["binder_ref_url"].split("/")[-1]
            else:
                os.remove(lock_filepath)
                flask.abort(500, "environment not ready!")
    if commit_hash == None:
        os.remove(lock_filepath)
        flask.abort(500, "commit hash not found from built environment!")
    results = book_get_by_params(commit_hash=commit_hash)
    os.remove(lock_filepath)
    if not results:
        flask.abort(424)

    return flask.jsonify(results)

    #def run():
    #    binderhub_request = binderhub_api_url.format(provider=provider, user_repo=user_repo, repo=repo, commit=commit)
    #    
    #    yield f"Hello {user}, you are requesting:\n{binderhub_request}\n"
    #    proc =  subprocess.Popen(["curl", binderhub_request], stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    #    for line in iter(process.stdout.read(), b''):
    #        #sys.stdout.write(line)
    #        yield line
    
    #return flask.Response(run(), mimetype='text/plain')

@app.route('/api/v1/resources/books', methods=['GET'])
@htpasswd.required
def api_books_get(user):
    # Check if a hash or repo url is provided
    commit_hash = None
    repo_name = None
    user_name = None
    if "user_name" in flask.request.args:
        user_name = str(flask.request.args['user_name'])
    elif "commit_hash" in flask.request.args:
        commit_hash = str(flask.request.args['commit_hash'])
    elif "repo_name" in flask.request.args:
        repo_name = str(flask.request.args['repo_name'])
    else:
        flask.abort(400)

    # Create an empty list for our results
    results = book_get_by_params(user_name, commit_hash, repo_name)
    if not results:
        flask.abort(404)
    
    # Use the jsonify function from Flask to convert our list of
    # Python dictionaries to the JSON format.
    return flask.jsonify(results)

def book_get_by_params(user_name=None, commit_hash=None, repo_name=None):
    books = load_all()
    
    # Create an empty list for our results
    results = []

    # If we have the hash, return the corresponding book
    if user_name is not None:
        for book in books:
            if book['user_name'] == user_name:
                results.append(book)
    elif commit_hash is not None:
        for book in books:
            if book['commit_hash'] == commit_hash:
                results.append(book)
    elif repo_name is not None:
        for book in books:
            if book['repo_name'] == repo_name:
                results.append(book)
    
    return results

@app.errorhandler(500)
def bad_request(e):
    return "<h1>500</h1><p>Internal server error</p>{}".format(str(e)), 500

@app.errorhandler(400)
def bad_request(e):
    return "<h1>400</h1><p>Bad request, valid requests are:</p>{}".format(doc()), 400

@app.errorhandler(404)
def page_not_found(e):
    return "<h1>404</h1><p>The resource could not be found.</p>", 404

@app.errorhandler(409)
def page_not_found(e):
    return """
<h1>409</h1>
<p>A similar request has been already sent!</p>
<p> Please be patient...</p>
<img src=\"https://media.giphy.com/media/3o7TKxBr7xhEgJhaFy/giphy.gif\">
""", 409

@app.errorhandler(424)
def page_not_found(e):
    return "<h1>424</h1><p>The request failed due to failure of the jupyter book build request.</p>", 424

if __name__ == '__main__':
    app.run(host="0.0.0.0", port=8081)

