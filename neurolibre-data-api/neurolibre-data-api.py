import flask
import os
import json
import glob
import time
import subprocess
import requests
import git
from flask_htpasswd import HtPasswdAuth

# https://stackoverflow.com/questions/41410199/how-to-configure-nginx-to-pass-user-info-to-wsgi-flask
# https://blog.miguelgrinberg.com/post/restful-authentication-with-flask

# GLOBAL VARIABLES
BOOK_PATHS = "/DATA/book-artifacts/*/*/*/*.tar.gz"
BOOK_URL = "http://neurolibre-data-prod.conp.cloud/book-artifacts"

#https://programminghistorian.org/en/lessons/creating-apis-with-python-and-flask

app = flask.Flask(__name__)
app.config["DEBUG"] = True
app.config['FLASK_HTPASSWD_PATH'] = '/home/ubuntu/.htpasswd'
htpasswd = HtPasswdAuth(app)

def load_all(globpath=BOOK_PATHS):
    book_collection = []

    paths = glob.glob(globpath)
    for path in paths:
        curr_dir = path.replace(".tar.gz", "")
        path_list = curr_dir.split("/")
        commit_hash = path_list[-1]
        repo = path_list[-2]
        provider = path_list[-3]
        user = path_list[-4]
        nb_list = []
        for (dirpath, dirnames, filenames) in os.walk(curr_dir + "/_build/jupyter_execute"):
            for input_file in filenames:
                if input_file.split(".")[-1] == "ipynb":
                    nb_list += [os.path.join(dirpath, input_file).replace("/DATA/book-artifacts", BOOK_URL)]
        nb_list = sorted(nb_list)
        book_dict = {"book_url": BOOK_URL + f"/{user}/{provider}/{repo}/{commit_hash}/_build/html/"
                     , "book_build_logs": BOOK_URL + f"/{user}/{provider}/{repo}/{commit_hash}/book-build.log"
                     , "download_link": BOOK_URL + path.replace("/DATA/book-artifacts", "")
                     , "notebook_list": nb_list
                     , "repo_link": f"https://{provider}/{user}/{repo}"
                     , "user_name": user
                     , "repo_name": repo
                     , "provider_name": provider
                     , "commit_hash": commit_hash
                     , "time_added": time.ctime(os.path.getctime(path))}
        book_collection += [book_dict]

    return book_collection

def doc():
    aa = os.getenv("AGAH")
    return """
<p> Commad line: </p>
<p> &nbsp; curl -u user:pwd </p>
<p> Synchronize jupyter book build from test server (\"commit_hash\" defaults to HEAD): </p>
<p> &nbsp; POST &nbsp; &nbsp; -H "Content-Type: application/json" -d '{"repo_url":"https://github.com/ltetrel/nha2020-nilearn", "commit_hash":"e29aa259f6807e62610bc84a86d406065028fe29"}' /api/v1/resources/books/sync </p>
<p> Binder build a specific repository (\"commit_hash\" defaults to HEAD): </p>
<p> &nbsp; POST &nbsp; &nbsp; -H "Content-Type: application/json" -d '{"repo_url":"https://github.com/ltetrel/nha2020-nilearn", "commit_hash":"e29aa259f6807e62610bc84a86d406065028fe29"}' /api/v1/resources/binder/build</p>
<p> List all books </p>
<p> &nbsp; GET &nbsp; &nbsp; /api/v1/resources/books/all </p>
<p> Retrieve book(s) by username </p>
<p> &nbsp; GET &nbsp; &nbsp; /api/v1/resources/books?user_name=jovyan </p>
<p> Retrieve specific book by commit hash </p>
<p> &nbsp; GET &nbsp; &nbsp; /api/v1/resources/books?commit_hash=737586b68c03b5fae1ee2a07b78ecb8b12ca2751 </p>
<p> Retrieve book(s) by repository name </p>
<p> &nbsp; GET &nbsp; &nbsp; /api/v1/resources/books?repo_name=hello-world </p>
""" + aa

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

@app.route('/api/v1/resources/books/sync', methods=['POST'])
@htpasswd.required
def api_sync_post(user):
    user_request = flask.request.get_json(force=True)

    if "repo_url" in user_request:
        repo_url = user_request["repo_url"]
        repo = repo_url.split("/")[-1]
        user_repo = repo_url.split("/")[-2]
        provider = repo_url.split("/")[-3]
        if not ((provider == "github.com") | (provider == "gitlab.com")):
            flask.abort(400)
    else:
        flask.abort(400)
    if "commit_hash" in user_request:
        commit = user_request["commit_hash"]
    else:
        commit = "HEAD"
    # checking user commit hash
    commit_found  = False
    if commit == "HEAD":
        refs = git.cmd.Git().ls_remote(repo_url).split("\n")
        for ref in refs:
            if ref.split('\t')[1] == "HEAD":
                commit_hash = ref.split('\t')[0]
                commit_found = True
    else:
        commit_hash = commit

    # transfer with rsync
    remote_path = os.path.join("neurolibre-data-test:", "DATA", "book-artifacts", user_repo, provider, repo, commit_hash + "*")
    try:
        subprocess.check_call(["rsync", "-avR", remote_path, "/"])
    except subprocess.CalledProcessError:
        flask.abort(404)

    # final check
    def run():
        results = book_get_by_params(commit_hash=commit_hash)
        print(results)
        if not results:
            error = {"reason":"404: Could not found the jupyter book build!", "commit_hash":commit_hash, "repo_url":repo_url}
            yield "\n" + json.dumps(error)
            yield ""
        else:
            yield "\n" + json.dumps(results[0])
            yield ""

    return flask.Response(run(), mimetype='text/plain')


@app.route('/api/v1/resources/binder/build', methods=['POST'])
@htpasswd.required
def api_build_post(user):
    user_request = flask.request.get_json(force=True) 
    binderhub_api_url = "https://binder-mcgill.conp.cloud/build/{provider}/{user_repo}/{repo}.git/{commit}"

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
    
    # checking user commit hash
    commit_found  = False
    if commit == "HEAD":
        refs = git.cmd.Git().ls_remote(repo_url).split("\n")
        for ref in refs:
            if ref.split('\t')[1] == "HEAD":
                commit_hash = ref.split('\t')[0]
                commit_found = True
    else:
        commit_hash = commit

    # make binderhub and jupyter book builds
    binderhub_request = binderhub_api_url.format(provider=provider, user_repo=user_repo, repo=repo, commit=commit)
    lock_filepath = f"./{provider}_{user_repo}_{repo}.lock"
    if os.path.exists(lock_filepath):
        lock_age_in_secs = time.time() - os.path.getmtime(lock_filepath)
        # if lock file older than 30min, remove it
        if lock_age_in_secs > 1800:
            os.remove(lock_filepath)
    if os.path.exists(lock_filepath):
        binderhub_build_link = """
https://binder-mcgill.conp.cloud/v2/{provider}/{user_repo}/{repo}/{commit}
""".format(provider=provider, user_repo=user_repo, repo=repo, commit=commit)
        flask.abort(409, binderhub_build_link)
    else:
        with open(lock_filepath, "w") as f:
            f.write("")
    # requests builds
    req = requests.get(binderhub_request)
    def run():
        for line in req.iter_lines():
            if line:
                yield str(line.decode('utf-8')) + "\n"
        yield ""

    return flask.Response(run(), mimetype='text/plain')

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
def internal_error(e):
    return "<h1>500</h1><p>Internal server error</p>{}".format(str(e)), 500

@app.errorhandler(400)
def bad_request(e):
    return "<h1>400</h1><p>Bad request, valid requests are:</p>{}".format(doc()), 400

@app.errorhandler(404)
def page_not_found(e):
    return "<h1>404</h1><p>The resource could not be found.</p>", 404

@app.errorhandler(406)
def malformed_specs(e):
    return "<h1>406</h1><p>Given specifications does not conform any content.</p><p>{}</p>".format(str(e)), 406

@app.errorhandler(409)
def same_request(e):
    error = {"reason":"A similar request has been already sent!", "binderhub_url":str(e)}
    return json.dumps(error), 409

@app.errorhandler(424)
def previous_request_failed(e):
    return "<h1>424</h1><p>The request failed due to a previous request.</p><p>{}</p>".format(str(e)), 424

if __name__ == '__main__':
    app.run(host="0.0.0.0", port=29876)

