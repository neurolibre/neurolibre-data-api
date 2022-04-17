import flask
import os
import json
import glob
import time
import subprocess
import requests
import shutil
import git
from flask_htpasswd import HtPasswdAuth
from dotenv import load_dotenv

# THIS IS NEEDED UNLESS FLASK IS CONFIGURED TO AUTO-LOAD!
load_dotenv()

# https://stackoverflow.com/questions/41410199/how-to-configure-nginx-to-pass-user-info-to-wsgi-flask
# https://blog.miguelgrinberg.com/post/restful-authentication-with-flask

# GLOBAL VARIABLES
BOOK_PATHS = "/DATA/book-artifacts/*/*/*/*.tar.gz"
BOOK_URL = "http://neurolibre-data-prod.conp.cloud/book-artifacts"
DOCKER_REGISTRY = "https://binder-registry.conp.cloud"

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

def zenodo_create_bucket(title, archive_type, creators, user_url, fork_url, commit_user, commit_fork, issue_id):
    ZENODO_TOKEN = os.getenv('ZENODO_API')
    headers = {"Content-Type": "application/json",
                    "Authorization": "Bearer {}".format(ZENODO_TOKEN)}
    
    libre_text = f'<a href="{fork_url}/commit/{commit_fork}"> reference repository/commit by roboneuro</a>'
    user_text = f'<a href="{user_url}/commit/{commit_user}">latest change by the author</a>'
    review_text = f'<p>For details, please visit the corresponding <a href="https://github.com/neurolibre/neurolibre-reviews/issues/{issue_id}">NeuroLibre technical screening.</a></p>'
    sign_text = '\n<p><strong><a href="https://neurolibre.org" target="NeuroLibre">https://neurolibre.org</a></strong></p>'

    data = {}
    data["metadata"] = {}
    data["metadata"]["title"] = title
    data["metadata"]["creators"] = creators
    data["metadata"]["keywords"] = ["canadian-open-neuroscience-platform","neurolibre"]
    # (A) NeuroLibre artifact is a part of (isPartOf) the NeuroLibre preprint (B 10.55458/NeuroLibre.issue_id)
    data["metadata"]["related_identifiers"] = [{"relation": "isPartOf","identifier": f"10.55458/NeuroLibre.{'%05d'%issue_id}","resource_type": "publication-preprint"}]
    data["metadata"]["contributors"] = [{'name':'NeuroLibre, Admin', 'affiliation': 'NeuroLibre', 'type': 'ContactPerson' }]

    if (archive_type == 'book'):
        data["metadata"]["upload_type"] = 'publication'
        data["metadata"]["publication_type"] = 'preprint'
        data["metadata"]["description"] = 'NeuroLibre JupyterBook built at this ' + libre_text + ', based on the ' + user_text + '.' + review_text + sign_text
    elif (archive_type == 'data'):
        data["metadata"]["upload_type"] = 'dataset'
        data["metadata"]["description"] = 'Dataset provided for NeuroLibre preprint.\n' + f'Author repo: {user_url}\nNeuroLibre fork:{fork_url}' + review_text + sign_text
    elif (archive_type == 'repository'):
        data["metadata"]["upload_type"] = 'software'
        data["metadata"]["description"] = 'GitHub archive of the ' + libre_text + ', based on the ' + user_text + '.' + review_text + sign_text
    elif (archive_type == 'docker'):
        data["metadata"]["upload_type"] = 'software'
        data["metadata"]["description"] = 'Docker image built from the ' + libre_text + ', based on the ' + user_text + f", using repo2docker (through BinderHub). <br> To run locally: <ol> <li><pre><code class=\"language-bash\">docker load < DockerImage_10.55458_NeuroLibre_{'%05d'%issue_id}_{commit_fork[0:5]}.zip</code><pre></li><li><pre><code class=\"language-bash\">docker run -it --rm -p 8888:8888 DOCKER_IMAGE_ID jupyter lab --ip 0.0.0.0</code></pre> <strong>by replacing <code>DOCKER_IMAGE_ID</code> above with the respective ID of the Docker image loaded from the zip file.</strong></li></ol>" + review_text + sign_text

    # Make an empty deposit to create the bucket 
    r = requests.post('https://zenodo.org/api/deposit/depositions',
                headers=headers,
                data=json.dumps(data))
    if not r:
        return {"reason":"404: Cannot create " + archive_type + " bucket.", "commit_hash":commit_fork, "repo_url":fork_url}
    else:
        return r.json()

def docker_login():
    uname = os.getenv('DOCKER_USERNAME')
    pswd = os.getenv('DOCKER_PASSWORD')
    resp = os.system(f"echo {pswd} | docker login {DOCKER_REGISTRY} --username {uname} --password-stdin")
    return resp

def docker_logout():
    resp=os.system(f"docker logout {DOCKER_REGISTRY}")
    return resp

def docker_pull(image):
    resp = os.system(f"docker pull {image}")
    return resp

def docker_export(image,issue_id,commit_fork):
    save_name = os.path.join(get_archive_dir(issue_id),f"DockerImage_10.55458_NeuroLibre_{'%05d'%issue_id}_{commit_fork[0:6]}.tar.gz")
    resp=os.system(f"docker save {image} | gzip > {save_name}")
    return resp, save_name

def get_archive_dir(issue_id):
    path = f"/DATA/zenodo/{'%05d'%issue_id}"
    if not os.path.exists(path):
        os.makedirs(path)
    return path

def get_deposit_dir(issue_id):
    path = f"/DATA/zenodo_records/{'%05d'%issue_id}"
    if not os.path.exists(path):
        os.makedirs(path)
    return path

# docker rmi $(docker images 'busybox' -a -q)


def doc():
    return """
<p> Commad line: </p>
<p> &nbsp; curl -u user:pwd </p>
<p> Synchronize jupyter book build from test server (\"commit_hash\" defaults to HEAD): </p>
<p> &nbsp; POST &nbsp; &nbsp; -H "Content-Type: application/json" -d '{"repo_url":"https://github.com/ltetrel/nha2020-nilearn", "commit_hash":"e29aa259f6807e62610bc84a86d406065028fe29"}' /api/v1/resources/books/sync </p>
<p> Synchronize data from test server: </p>
<p> &nbsp; POST &nbsp; &nbsp; -H "Content-Type: application/json" -d '{"project_name": "nilearn_data"}' /api/v1/resources/data/sync </p>
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


# ---------------------------- CREATE ZENODO DEPOSITS
@app.route('/api/v1/resources/zenodo/buckets', methods=['POST'])
@htpasswd.required
def api_zenodo_post(user):
    user_request = flask.request.get_json(force=True)
    if "fork_url" in user_request:
        fork_url = user_request["fork_url"]
    else:
        flask.abort(400)
    if "user_url" in user_request:
        user_url = user_request["user_url"]
    else:
        flask.abort(400)
    if "commit_fork" in user_request:
        commit_fork = user_request["commit_fork"]
    else:
        flask.abort(400)
    if "commit_user" in user_request:
        commit_user = user_request["commit_user"]
    else:
        flask.abort(400)
    if "title" in user_request:
        title = user_request["title"]
    else:
        flask.abort(400)
    if "issue_id" in user_request:
        issue_id = user_request["issue_id"]
    else:
        flask.abort(400)
    if "creators" in user_request:
        creators = user_request["creators"]
    else:
        flask.abort(400)
    if "deposit_data" in user_request:
        deposit_data = user_request["deposit_data"]
    else:
        flask.abort(400)
    def run():
        ZENODO_TOKEN = os.getenv('ZENODO_API')
        headers = {"Content-Type": "application/json", "Authorization": "Bearer {}".format(ZENODO_TOKEN)}

        fname = f"zenodo_deposit_NeuroLibre_{'%05d'%issue_id}.json"
        local_file = os.path.join(get_deposit_dir(issue_id), fname)
        
        collect = {}

        if os.path.exists(local_file):
            # File already exists, do nothing.
            collect["message"] = f"Zenodo records already exist for this submission on NeuroLibre servers: {fname}"
        else:
            # File does not exist, move on.

            if deposit_data:
                # User does not have DOI'd data, we'll create.
                resources = ["book","repository","data","docker"]
            else:
                # Do not create a record for data, user already did.
                resources = ["book","repository","docker"]

            for archive_type in resources:
                r = zenodo_create_bucket(title, archive_type, creators, user_url, fork_url, commit_user, commit_fork, issue_id)
                collect[archive_type] = r
                time.sleep(0.5)

            if {k: v for k, v in collect.items() if 'reason' in v}:
                # This means at least one of the deposits has failed.
                print('Caught deposit issue. JSON will not be written.')
                # Delete deposition if succeeded for a certain resource
                remove_dict = {k: v for k, v in collect.items() if not 'reason' in v }
                for key in remove_dict:
                    print("Deleting " + remove_dict[key]["links"]["self"])
                    tmp = requests.delete(remove_dict[key]["links"]["self"], headers=headers)
                    time.sleep(0.5)
                    # Returns 204 if successful, cast str to display
                    collect[key + "_deleted"] = str(tmp)
            else:
                # This means that all requested deposits are successful
                print(f'Writing {local_file}...')
                with open(local_file, 'w') as outfile:
                    json.dump(collect, outfile)

        # The response will be returned to the caller regardless of the state.
        yield "\n" + json.dumps(collect)
        yield ""
    
    return flask.Response(run(), mimetype='text/plain')

# ---------------------------- UPLOAD ARTIFACTS TO ZENODO
@app.route('/api/v1/resources/zenodo/upload', methods=['POST'])
@htpasswd.required
def api_upload_post(user):
    user_request = flask.request.get_json(force=True)
    if "issue_id" in user_request:
        issue_id = user_request["issue_id"]
    else:
        flask.abort(400)
    if "repository_address" in user_request:
        user_repo_address = user_request["repository_address"]
    else:
        flask.abort(400)
    if "item" in user_request:
        item = user_request["item"]
    else:
        flask.abort(400)
    if "item_arg" in user_request:
        item_arg = user_request["item_arg"]
    else:
        flask.abort(400)
    if "fork_url" in user_request:
        fork_url = user_request["fork_url"]
        repofork = fork_url.split("/")[-1]
        fork_repo = fork_url.split("/")[-2]
        fork_provider = fork_url.split("/")[-3]
        if not ((fork_provider == "github.com") | (fork_provider == "gitlab.com")):
            flask.abort(400)
    else:
        flask.abort(400)
    if "commit_fork" in user_request:
        commit_fork = user_request["commit_fork"]
    else:
        flask.abort(400)
    def run():
        # Set env
        ZENODO_TOKEN = os.getenv('ZENODO_API')
        params = {'access_token': ZENODO_TOKEN}
        # Read json record of the deposit
        fname = f"zenodo_deposit_NeuroLibre_{'%05d'%issue_id}.json"
        local_file = os.path.join(get_deposit_dir(issue_id), fname)
        with open(local_file, 'r') as f:
            zenodo_record = json.load(f)
        # Fetch bucket url of the requested type of item
        bucket_url = zenodo_record[item]['links']['bucket']

        if item == "book":
           # We will archive the book created through the forked repository.
           local_path = os.path.join("/DATA", "book-artifacts", fork_repo, fork_provider, repofork, commit_fork, "_build", "html")
           # Descriptive file name
           zenodo_file = os.path.join(get_archive_dir(issue_id),f"JupyterBook_10.55458_NeuroLibre_{'%05d'%issue_id}_{commit_fork[0:6]}")
           # Zip it!
           shutil.make_archive(zenodo_file, 'zip', local_path)
           zpath = zenodo_file + ".zip"
        
           with open(zpath, "rb") as fp:
            r = requests.put(f"{bucket_url}/JupyterBook_10.55458_NeuroLibre_{'%05d'%issue_id}_{commit_fork[0:6]}.zip",
                                    params=params,
                                    data=fp)
           if not r:
            error = {"reason":f"404: Cannot upload {zpath} to {bucket_url}", "commit_hash":commit_fork, "repo_url":fork_repo,"issue_id":issue_id}
            yield "\n" + json.dumps(error)
            yield ""
           else:
            tmp = f"zenodo_uploaded_{item}_NeuroLibre_{'%05d'%issue_id}_{commit_fork[0:6]}.json"
            log_file = os.path.join(get_deposit_dir(issue_id), tmp)
            with open(log_file, 'w') as outfile:
                    json.dump(r.json(), outfile)
            
            yield "\n" + json.dumps(r.json())
            yield ""

        elif item == "docker":

            docker_login()
            # Docker image address should be here
            docker_pull(item_arg)

            in_r = docker_export(item_arg,issue_id,commit_fork)
            # in_r[0] os.system status, in_r[1] saved docker image absolute path

            docker_logout()
            if in_r[0] == 0:
                # Means that saved successfully, upload to zenodo.
                with open(in_r[1], "rb") as fp:
                    r = requests.put(f"{bucket_url}/DockerImage_10.55458_NeuroLibre_{'%05d'%issue_id}_{commit_fork[0:6]}.zip",
                                    params=params,
                                    data=fp)
                # TO_DO: Write a function to handle this, too many repetitions rn.
                if not r:
                    error = {"reason":f"404: Cannot upload {in_r[1]} to {bucket_url}", "commit_hash":commit_fork, "repo_url":fork_repo,"issue_id":issue_id}
                    yield "\n" + json.dumps(error)
                    yield ""
                else:
                    tmp = f"zenodo_uploaded_{item}_NeuroLibre_{'%05d'%issue_id}_{commit_fork[0:6]}.json"
                    log_file = os.path.join(get_deposit_dir(issue_id), tmp)
                    with open(log_file, 'w') as outfile:
                            json.dump(r.json(), outfile)

                    yield "\n" + json.dumps(r.json())
                    yield ""
            else:
            # Cannot save docker image succesfully
                error = {"reason":f"404: Cannot save requested docker image as tar.gz: {item_arg}", "commit_hash":commit_fork, "repo_url":fork_repo,"issue_id":issue_id}
                yield "\n" + json.dumps(error)
                yield ""

        elif item == "repository":
            
            download_url_main = f"{fork_url}/archive/refs/heads/main.zip"
            download_url_master = f"{fork_url}/archive/refs/heads/master.zip"

            zenodo_file = os.path.join(get_archive_dir(issue_id),f"GitHubRepo_10.55458_NeuroLibre_{'%05d'%issue_id}_{commit_fork[0:6]}.zip")
            
            # REFACTOR HERE AND MANAGE CONDITIONS CLEANER.
            # Try main first
            resp = os.system(f"wget -O {zenodo_file} {download_url_main}")
            if resp != 0:
                # Try master 
                resp2 = os.system(f"wget -O {zenodo_file} {download_url_master}")
                if resp2 != 0:
                    error = {"reason":f"404: Cannot download repository at {download_url_main} or from master branch.", "commit_hash":commit_fork, "repo_url":fork_repo,"issue_id":issue_id}
                    yield "\n" + json.dumps(error)
                    yield ""
                    # TRY FLASK.ABORT(code,custom) here for refactoring.
                else:
                    # Upload to Zenodo
                    with open(zenodo_file, "rb") as fp:
                        r = requests.put(f"{bucket_url}/GitHubRepo_10.55458_NeuroLibre_{'%05d'%issue_id}_{commit_fork[0:6]}.zip",
                                        params=params,
                                        data=fp)
                        if not r:
                            error = {"reason":f"404: Cannot upload {zenodo_file} to {bucket_url}", "commit_hash":commit_fork, "repo_url":fork_repo,"issue_id":issue_id}
                            yield "\n" + json.dumps(error)
                            yield ""
                        else:
                            tmp = f"zenodo_uploaded_{item}_NeuroLibre_{'%05d'%issue_id}_{commit_fork[0:6]}.json"
                            log_file = os.path.join(get_deposit_dir(issue_id), tmp)
                            with open(log_file, 'w') as outfile:
                                    json.dump(r.json(), outfile)
                        # Return answer to flask
                        yield "\n" + json.dumps(r.json())
                        yield ""
            else: 
                # main worked
                # Upload to Zenodo
                with open(zenodo_file, "rb") as fp:
                    r = requests.put(f"{bucket_url}/GitHubRepo_10.55458_NeuroLibre_{'%05d'%issue_id}_{commit_fork[0:6]}.zip",
                                    params=params,
                                    data=fp)
                    if not r:
                            error = {"reason":f"404: Cannot upload {zenodo_file} to {bucket_url}", "commit_hash":commit_fork, "repo_url":fork_repo,"issue_id":issue_id}
                            yield "\n" + json.dumps(error)
                            yield ""
                    else:
                        tmp = f"zenodo_uploaded_{item}_NeuroLibre_{'%05d'%issue_id}_{commit_fork[0:6]}.json"
                        log_file = os.path.join(get_deposit_dir(issue_id), tmp)
                        with open(log_file, 'w') as outfile:
                                json.dump(r.json(), outfile)
                        # Return answer to flask
                        yield "\n" + json.dumps(r.json())
                        yield ""

        elif item == "data":
           # We will archive the data synced from the test server. (item_arg is the project_name, indicating that the 
           # data is stored at the /DATA/project_name folder)
           local_path = os.path.join("/DATA", item_arg)
           # Descriptive file name
           zenodo_file = os.path.join(get_archive_dir(issue_id),f"Dataset_10.55458_NeuroLibre_{'%05d'%issue_id}_{commit_fork[0:6]}")
           # Zip it!
           shutil.make_archive(zenodo_file, 'zip', local_path)
           zpath = zenodo_file + ".zip"

           # UPLOAD data to zenodo        
           with open(zpath, "rb") as fp:
            r = requests.put(f"{bucket_url}/Dataset_10.55458_NeuroLibre_{'%05d'%issue_id}_{commit_fork[0:6]}.zip",
                                    params=params,
                                    data=fp)

            if not r:
                error = {"reason":f"404: Cannot upload {zenodo_file} to {bucket_url}", "commit_hash":commit_fork, "repo_url":fork_repo,"issue_id":issue_id}
                yield "\n" + json.dumps(error)
                yield ""
            else:
                tmp = f"zenodo_uploaded_{item}_NeuroLibre_{'%05d'%issue_id}_{commit_fork[0:6]}.json"
                log_file = os.path.join(get_deposit_dir(issue_id), tmp)
                with open(log_file, 'w') as outfile:
                        json.dump(r.json(), outfile)
                # Return answer to flask
                yield "\n" + json.dumps(r.json())
                yield ""

    return flask.Response(run(), mimetype='text/plain')

# ---------------------------- LIST ZENODO RESOURCES ON PROD
@app.route('/api/v1/resources/zenodo/list', methods=['POST'])
@htpasswd.required
def api_zenodo_list_post(user):
    user_request = flask.request.get_json(force=True)
    if "issue_id" in user_request:
        issue_id = user_request["issue_id"]
    else:
        flask.abort(400)
    def run():
        # Set env
        path = f"/DATA/zenodo_records/{'%05d'%issue_id}"
        if not os.path.exists(path):
            yield "<br> :neutral_face: I could not find any Zenodo-related records on NeuroLibre servers. Maybe start with `roboneuro zenodo deposit`?"
        else:
            files = os.listdir(path)
            yield "<br> These are the Zenodo records I have on NeuroLibre servers:"
            yield "<ul>"
            for file in files:
                yield f"<li>{file}</li>"
            yield "</ul>"

    return flask.Response(run(), mimetype='text/plain')

# ---------------------------- DELETE ZENODO DEPOSITS
@app.route('/api/v1/resources/zenodo/flush', methods=['POST'])
@htpasswd.required
def api_zenodo_flush_post(user):
    user_request = flask.request.get_json(force=True)
    if "issue_id" in user_request:
        issue_id = user_request["issue_id"]
    else:
        flask.abort(400)
    if "items" in user_request:
        items = user_request["items"]
    else:
        flask.abort(400)
    def run():
    # Set env
        ZENODO_TOKEN = os.getenv('ZENODO_API')
        headers = {"Content-Type": "application/json","Authorization": "Bearer {}".format(ZENODO_TOKEN)}
        # Read json record of the deposit
        fname = f"zenodo_deposit_NeuroLibre_{'%05d'%issue_id}.json"
        local_file = os.path.join(get_deposit_dir(issue_id), fname)
        dat2recmap = {"data":"Dataset","repository":"GitHubRepo","docker":"DockerImage","book":"JupyterBook"}
        
        with open(local_file, 'r') as f:
            zenodo_record = json.load(f)

        for item in items: 
            self_url = zenodo_record[item]['links']['self']
            # Delete the deposit
            r3 = requests.delete(self_url,headers=headers)
            if r3.status_code == 204:
                yield f"\n Deleted {item} deposit successfully at {self_url}."
                yield ""
                # We need to delete these from the Zenodo records file
                if item in zenodo_record: del zenodo_record[item]
                # Flush ALL the upload records (json) associated with the item
                tmp_record = glob.glob(os.path.join(get_deposit_dir(issue_id),f"zenodo_uploaded_{item}_NeuroLibre_{'%05d'%issue_id}_*.json"))
                if tmp_record:
                    for f in tmp_record:
                        os.remove(f)
                        yield f"\n Deleted {f} record from the server."
                # Flush ALL the uploaded files associated with the item
                tmp_file = glob.glob(os.path.join(get_archive_dir(issue_id),f"{dat2recmap[item]}_10.55458_NeuroLibre_{'%05d'%issue_id}_*.zip"))
                if tmp_file:
                    for f in tmp_file:
                        os.remove(f)
                        yield f"\n Deleted {f} record from the server."
            elif r3.status_code == 403: 
                yield f"\n The {item} archive has already been published, cannot be deleted."
                yield ""
            elif r3.status_code == 410:
                yield f"\n The {item} deposit does not exist."
                yield ""
        # Write zenodo record json file or rm existing one if empty at this point
        # Delete the old one
        os.remove(local_file)
        yield f"\n Deleted old {local_file} record from the server."
        # Write the new one
        if zenodo_record:
            with open(local_file, 'w') as outfile:
                json.dump(zenodo_record, outfile)
            yield f"\n Created new {local_file}."
        else:
            yield f"\n All the deposit records have been deleted."

    return flask.Response(run(), mimetype='text/plain')

# ---------------------------- LIST ZENODO RESOURCES ON PROD
@app.route('/api/v1/resources/zenodo/publish', methods=['POST'])
@htpasswd.required
def api_zenodo_publish(user):
    user_request = flask.request.get_json(force=True)
    if "issue_id" in user_request:
        issue_id = user_request["issue_id"]
    else:
        flask.abort(400)
    def run():
        ZENODO_TOKEN = os.getenv('ZENODO_API')
        params = {'access_token': ZENODO_TOKEN}
        # Read json record of the deposit
        fname = f"zenodo_deposit_NeuroLibre_{'%05d'%issue_id}.json"
        local_file = os.path.join(get_deposit_dir(issue_id), fname)
        dat2recmap = {"data":"Dataset","repository":"GitHub repository","docker":"Docker image","book":"Jupyter Book"}
        with open(local_file, 'r') as f:
            zenodo_record = json.load(f)
        if not os.path.exists(local_file):
            yield "<br> :neutral_face: I could not find any Zenodo-related records on NeuroLibre servers. Maybe start with <code>roboneuro zenodo deposit</code>?"
        else:
            # If there's a record, make sure that uploads are complete for all kind of items found in the deposit records.
            bool_array = []
            for item in zenodo_record.keys():
                tmp = glob.glob(os.path.join(get_deposit_dir(issue_id),f"zenodo_uploaded_{item}_NeuroLibre_{'%05d'%issue_id}_*.json"))
                if tmp:
                    bool_array.append(True)
                else:
                    bool_array.append(False)
            
            if all(bool_array):
                # We need self links from each record to publish.
                for item in zenodo_record.keys():
                    publish_link = zenodo_record[item]['links']['publish']
                    yield f"\n :ice_cube: {dat2recmap[item]} publish status:"
                    r = requests.post(publish_link,params=params)
                    response = r.json()
                    if r.status_code==202: 
                        yield f"\n :confetti_ball: <a href=\"{response['doi_url']}\"><img src=\"{response['links']['badge']}\"></a>"
                        tmp = f"zenodo_published_{item}_NeuroLibre_{'%05d'%issue_id}.json"
                        log_file = os.path.join(get_deposit_dir(issue_id), tmp)
                        with open(log_file, 'w') as outfile:
                            json.dump(r.json(), outfile)
                    else:
                        yield f"\n <details><summary> :wilted_flower: Could not publish {dat2recmap[item]} </summary><pre><code>{r.json()}</code></pre></details>"
            else:
                yield "\n :neutral_face: Not all archives are uploaded for the resources listed in the deposit record. Please ask <code>roboneuro zenodo status</code> and upload the missing (xxx) archives by <code>roboneuro zenodo archive-xxx</code>."

    return flask.Response(run(), mimetype='text/plain')

@app.route('/api/v1/resources/data/sync', methods=['POST'])
@htpasswd.required
def api_data_sync_post(user):
    user_request = flask.request.get_json(force=True)

    if "project_name" in user_request:
        project_name = user_request["project_name"]
    else:
        flask.abort(400)

    # transfer with rsync
    remote_path = os.path.join("neurolibre-test-api:", "DATA", project_name)
    try:
        f = open("/DATA/data_synclog.txt", "a")
        f.write(remote_path)
        f.close()
        subprocess.check_call(["rsync", "-avR", remote_path, "/"])
    except subprocess.CalledProcessError:
        flask.abort(404)

    # final check
    if len(os.listdir(os.path.join("/DATA", project_name))) == 0:
        return {"reason": "404: Data sync was not successfull.", "project_name": project_name}
    else:
        return {"reason": "200: Data sync succeeded."}


@app.route('/api/v1/resources/books/sync', methods=['POST'])
@htpasswd.required
def api_books_sync_post(user):
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
    remote_path = os.path.join("neurolibre-test-api:", "DATA", "book-artifacts", user_repo, provider, repo, commit_hash + "*")
    try:
        f = open("/DATA/synclog.txt", "a")
        f.write(remote_path)
        f.close()
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